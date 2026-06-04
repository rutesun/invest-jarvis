# Change Record: Stock Report V2 합성 엔진 (map-reduce + 이벤트 안전망 + Google grounding)

**Status**: In Progress
**Created**: 2026-06-04
**PRs**: (pending — branch `feature/stock-report-google-grounding`)

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
- [ ] PR 생성 및 머지

## Related

- 상세 설계: `docs/superpowers/specs/2026-05-08-stock-report-engine-v2-design.md`,
  `docs/superpowers/plans/2026-05-08-stock-report-engine-v2.md`
- ADR: ADR-0007(map-reduce 합성), ADR-0008(이벤트 안전망)
