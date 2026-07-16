# Change Record: Technical Scoring Redesign

**Status**: Draft
**Date**: 2026-07-16
**PRs**: -
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

기존 `total_score`는 8개 technical component의 단순 합계라 추세 강도, 신규 진입 가능성, 보유 관리 신호가 한 숫자에 섞였다. 삼성전자, BE, PANW 구간을 날짜별로 비교했을 때 같은 높은 점수라도 "신규 매수"와 "과열 보유"의 의미가 달랐다.

raw OHLCV 별도 score를 추가하면 같은 가격 데이터에서 나온 점수 체계가 두 개가 되어 해석이 더 어려워진다. 그래서 component raw 합계는 유지하고, OHLCV derived state는 `MarketContext`로만 사용해 조정 점수와 technical-only verdict를 만든다.

## What

1. **점수 계약 분리**: `TechnicalResult`에 `component_raw_total`, `adjusted_score`, `technical_verdict`, `score_history`, `aggregation_trace`를 추가했다. `total_score`는 compatibility 기간 동안 component raw 합계로 유지한다.
2. **MarketContext + ScoreAggregator**: OHLCV에서 추세, 과열, breakdown, support 같은 상태를 계산하되 별도 raw score로 노출하지 않고, `ScoreAggregator`가 context와 component metadata를 이용해 `adjusted_score`와 verdict를 만든다.
3. **문자열 파싱 제거**: Aggregator는 component의 `signal_metadata`를 소비한다. 사람이 읽는 `signals` 문자열은 판단 로직 입력으로 쓰지 않는다.
4. **최근 5거래일 점수 추이**: `score_history`는 각 날짜의 raw OHLCV를 먼저 cutoff한 뒤 indicator를 재계산해 만든다. future leakage를 방지하기 위해 regression test도 같은 순서를 따른다.
5. **출력 통합**: `quick_check`, `deep_dive`, `brief`, `analyze_decision`이 `technical_verdict`와 `score_history`를 전달하고 표시한다.
6. **LLM 역할 제한**: LLM prompt는 score/action을 재판단하지 않고 fixed rule facts를 한국어로 설명하도록 제한한다.
7. **실데이터 회귀 fixture**: PANW, BE, 005930.KS 구간의 OHLCV CSV fixture를 저장하고 local fixture 기반 regression test를 추가했다.

## Impact

- `jarvis check` 출력에 raw component 합계, 조정 점수, verdict 이유, 주의점, 무효화 가격, 최근 점수 추이가 함께 표시된다.
- `jarvis analyze`의 technical summary와 decision bundle은 verdict가 있으면 이를 우선 참고하고, 없을 때만 기존 raw score 기반 판단으로 fallback한다.
- `jarvis brief`는 종목별 technical verdict와 최근 점수 흐름을 facts/narrative/render 단계에 반영한다.
- 기존 `total_score` 사용자는 즉시 깨지지 않으며, 새 판단에는 `adjusted_score`와 `technical_verdict`를 사용할 수 있다.

## Constraints

- raw OHLCV 별도 score는 만들지 않는다.
- `total_score`는 1차 구현에서 component raw 합계 계약을 유지한다.
- `technical_verdict`는 technical-only hint이며, 최종 매매 판단과 sizing은 playbook 계층의 책임이다.
- LLM은 rule output으로 확정된 score와 verdict를 설명만 한다.

## Tests

- `uv run pytest tests/tools/technical/test_scoring_models.py tests/tools/technical/test_market_context.py tests/tools/technical/test_score_aggregator.py tests/tools/technical/test_scorer.py tests/tools/technical/test_tool_scorer_integration.py tests/tools/technical/test_scoring_regression.py tests/pipelines/test_quick_check.py tests/pipelines/test_analyze_decision.py tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py tests/tools/brief/test_render.py tests/llm/test_analyzer.py tests/llm/test_brief_narratives.py -v`
- `uv run ruff check src tests`
- `uv run pytest`

## Related

- ADR: [ADR-0010: TechnicalScorer 점수를 raw total과 adjusted verdict로 분리](../adr/0010-technical-scoring-adjusted-verdict.md)
- 설계: [docs/superpowers/specs/2026-07-16-technical-scoring-redesign-design.md](../superpowers/specs/2026-07-16-technical-scoring-redesign-design.md)
- 구현 계획: [docs/superpowers/plans/2026-07-16-technical-scoring-redesign.md](../superpowers/plans/2026-07-16-technical-scoring-redesign.md)
- worklog: [docs/worklog/technical-scoring-redesign.md](../worklog/technical-scoring-redesign.md)
