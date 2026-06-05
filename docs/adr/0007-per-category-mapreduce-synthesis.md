# ADR-0007: 카테고리별 map-reduce 합성으로 전환

**상태:** 수락
**날짜:** 2026-06-04

## 컨텍스트

Phase 1 초기 설계(`2026-05-08-stock-report-engine-v2-design.md`의 Synthesis Contract)는
LLM이 `same-day bundle` 전체를 한 번에 읽어 `Pulse / Category Summaries / Core Themes /
Focus Tickers`를 생성하는 **단일 호출 합성**이었다.

실데이터 운영에서 문제가 드러났다.

- 단일 호출이 입력 chunk의 약 65%를 본문에서 누락했다. 컨텍스트가 길어질수록 LLM이
  consolidation을 "생략"으로 처리했다.
- 문제를 "chunk 커버리지"로 보면 안 된다는 점이 분명해졌다. 같은 사건이 여러 채널에
  중복으로 들어오므로, 목표는 **chunk 개수 보존이 아니라 distinct-content 보존**이다.
  중복은 병합하고, 서로 다른 사건은 모두 남겨야 한다.
- 즉 합성 단계의 진짜 역할은 "요약"이 아니라 **카테고리 단위 consolidation(중복 병합 +
  사건 보존)**이다.

제약:

- LLM은 당일 bundle에 없는 수치/회사명/연결을 만들지 않는다(기존 계약 유지).
- 토큰 비용과 일일 운영 시간이 감당 가능해야 한다.
- `report_runs / report_evidence` evidence trace가 깨지면 안 된다.
- Phase 2에서 카테고리 분석에 RAG가 들어올 자리를 막지 않아야 한다.

## 고려한 옵션

### 옵션 A: 단일 호출 합성 유지
- 장점:
  - 호출이 1회라 비용/지연이 가장 작다.
  - 구현 변경이 없다.
- 단점:
  - 입력의 다수 사건을 본문에서 통째로 누락한다(약 65%).
  - 컨텍스트가 커질수록 누락이 악화되고 튜닝으로 막기 어렵다.
  - 카테고리별 RAG 보강(Phase 2)을 끼울 자연스러운 경계가 없다.

### 옵션 B: 카테고리별 map-reduce 합성
- 장점:
  - map = 카테고리 단위 consolidation 엔진. 입력 컨텍스트가 작아져 누락이 급감한다.
  - 카테고리 경계가 Phase 2 RAG 주입 지점이 된다.
  - reduce가 카테고리 카드만 읽고 `Pulse / Core Themes`를 만들어 책임이 분리된다.
  - 카테고리별로 graceful fallback(LLM 실패 시 결정적 raw 카드)을 둘 수 있다.
- 단점:
  - 호출 수가 카테고리 수만큼 늘어 비용/지연이 증가한다(동시성 캡으로 완화).
  - 카테고리별 토큰 예산 관리가 필요하다.

### 옵션 C: LLM 없는 결정적 dump
- 장점:
  - 누락 0, 비용 0, 완전 재현 가능.
- 단점:
  - 중복 병합/서술 구조화가 없어 사람이 읽는 리포트로서 가치가 낮다.
  - "consolidation"이라는 목표 자체를 포기한다.

## 결정

옵션 B를 채택한다.

1. 합성은 **map(카테고리·티커별 LLM consolidation) → reduce(카드만 읽어 Pulse + Core
   Themes 생성)** 2단계로 나눈다.
2. map의 LLM 역할을 "요약"이 아니라 **중복 병합 + distinct 사건 보존**으로 명시한다.
3. 카테고리당 토큰 예산(`CATEGORY_CONTEXT_BUDGET_CHARS`)을 두고, 초과 시 evidence →
   supporting_facts → 저우선 chunk 순으로 trim한다.
4. chunk 수가 임계 미만이거나 LLM 호출이 실패하면 **결정적 raw 카드**로 graceful
   fallback한다(누락보다 원문 노출을 택한다).
5. reduce가 grounding에 실패하면 비-grounding → 결정적 pulse 순으로 강등한다.

## 결과

- 단일 호출 대비 본문 content 보존이 크게 개선된다(중복은 병합, 사건은 유지).
- 카테고리 경계가 Phase 2 카테고리별 RAG 보강의 주입 지점이 된다.
- 호출 수 증가는 동시성 캡(`_TIER_MAP_CONCURRENCY`)과 top-N ticker 제한으로 통제한다.
- 카테고리별 fallback 덕분에 일부 카테고리의 LLM 실패가 전체 리포트를 막지 않는다.
- map의 consolidation이 여전히 nondeterministic하게 대형 이벤트를 누락할 수 있다는
  점은 별도 결정으로 보강한다(→ ADR-0008).
- 기존 단일 호출 경로 코드는 삭제한다(중복 유지 비용 회피).
