# Change Record: Stock Report V2 합성 엔진 (map-reduce + 이벤트 안전망 + Google grounding)

**Status**: In Progress
**Created**: 2026-06-04
**PRs**: #33 (feature/stock-report-google-grounding), feature/report-quality-polish (pending)

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

단일 호출 합성이 입력 chunk의 약 65%를 본문에서 누락했고, 특히 M&A·대형 자본조달 같은
고임팩트 이벤트가 nondeterministic하게 빠졌다(2026-05-28·2026-06-02 실데이터 감사로 확인).
프롬프트 강화로는 LLM nondeterminism을 못 이긴다는 게 데이터로 드러나, 합성 구조 자체와
고임팩트 이벤트 보장 방식을 바꿔야 했다.

## What

1. **카테고리별 map-reduce 합성**으로 전환 (단일 호출 경로 삭제). map = 카테고리/티커
   consolidation, reduce = 카드 기반 Pulse + Core Themes 생성. 카테고리별 토큰 예산과
   결정적 raw fallback 포함. (→ ADR-0007)
2. **결정적 high-impact 이벤트 안전망** 추가. `event_type ∈ {M&A, 자본조달}`인데 LLM이
   인용하지 않은 chunk를 카테고리 카드에 강제 보강. (→ ADR-0008)
3. **골든셋 회귀(2트랙)**: content 기반 정적 픽스처(2026-05-28·2026-06-02 must-have 11건) +
   헤르메틱 pytest 회귀 + live `--golden` drift 체크(`scripts/stock_report_eval.py`).
4. **Google Search Grounding 실험 경로(T09-B)**: DB chunk 기반 grounding-only 파이프라인
   (`daily-v2-google`), Markdown 출력, citation 렌더링.
5. `CANONICAL_EVENT_TYPES`를 단일 출처 상수로 승격하고 `HIGH_IMPACT ⊆ CANONICAL` drift
   가드 테스트 추가. grounding 모델은 `gemini-3.5-flash`.

## Constraints

- 합성 LLM은 당일 bundle에 없는 수치/회사명/연결을 만들지 않는다(기존 evidence 계약 유지).
- 안전망은 LLM 성공 카드에만 적용한다(raw fallback은 이미 전 chunk 포함).
- 골든 픽스처는 chunk id가 매 적재마다 바뀌므로 **content 기반**으로 동결한다.

## Checklist

- [x] 핵심 구현 (map-reduce, 안전망, 골든셋, grounding)
- [x] 테스트 통과 (761 passed)
- [x] `docs/FEATURES.md` 업데이트
- [x] ADR-0007 / ADR-0008 작성
- [x] PR #33 머지
- [x] 리포트 가독성 개선 (feature/report-quality-polish, 아래 참조)
- [ ] feature/report-quality-polish PR 생성 및 머지

---

## 후속: 리포트 가독성 개선 (2026-06-08)

**Branch**: `feature/report-quality-polish`

### Why

PR #33 이후 `daily_v2_2026-06-04` 리포트 리뷰에서 4종 가독성 문제 발견:
- minor 카테고리 10개가 저품질 raw 카드로 개별 노출돼 SNR 저하
- 출처 줄에 동일 채널 chunk가 최대 26개까지 나열
- LLM 출력에 '카테리'(→'카테고리') 오타 간헐 등장
- Focus Tickers에 동일 종목 이름/티커 버킷 중복 가능성

### What

1. **기타 단신 통합**: chunk<3 minor 카테고리를 개별 카드 대신 단일 `기타 단신` 항목으로
   병합. 고임팩트 이벤트 우선 배치, flat bullet 렌더. (→ ADR-0009)
2. **출처 채널 dedup + cap**: chunk-level → 채널 단위 dedup, 상위 6개 + `외 N건`.
   DB `report_evidence` 영속은 chunk 단위 그대로. (→ ADR-0009)
3. **오타 가드**: `_normalize_report_typos` 결정적 후처리 + 시스템 프롬프트 맞춤법 주의.
4. **raw 티커 카드 보강**: `_typed_evidence_texts`로 fallback 카드의 risk/metric 축을
   typed evidence에서 추출.
5. **티커 버킷 dedup**: chunk 집합 완전 동일 버킷을 보수적으로 병합. (→ ADR-0009)
6. **Gemini 프롬프트 정합**: 맞춤법 주의·티커 중복 금지 지침 추가.

### Constraints

- DB attribution(report_evidence) 영속 경로 불변. 렌더 표시만 요약.
- 부분집합 기반 ticker alias 병합 기각 — 실데이터(Ford⊆GM, 삼성디스플레이⊆BOE)로 오병합
  위험 확인(ADR-0009 참조).
- 날조 없음: risk evidence 없는 thin ticker 카드(SpaceX)는 리스크 축 공란 수용.

## Related

- 상세 설계: `docs/superpowers/specs/2026-05-08-stock-report-engine-v2-design.md`,
  `docs/superpowers/plans/2026-05-08-stock-report-engine-v2.md`
- ADR: ADR-0007(map-reduce 합성), ADR-0008(이벤트 안전망), ADR-0009(가독성 개선 결정)
