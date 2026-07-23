# Change Record: Unified Technical Analysis Contract

**Status**: Merged
**Date**: 2026-07-22
**PRs**: #51
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`check`·`analyze`·`brief`가 각기 다른 조회 기간과 파이프라인으로 기술 분석을 수행해, 같은 종목·같은 시점인데도 소비처마다 점수·verdict가 달라질 수 있었다. 또한 `analyze`의 최종 LLM은 규칙이 확정한 액션(`decision_summary`)과 별개로 자체 액션(`ActionableSignal`)을 만들어, 화면에 서로 다른 두 개의 액션이 공존했다. 중복된 `report ticker`는 다중 종목 기술 확인이라는 점에서 `check`와 역할이 겹치면서 실제로는 생성한 LLM 결과를 쓰지 않았다.

## What

1. **공통 기술 계약**: 세 소비처가 동일한 canonical 3년 기술 스냅샷을 사용하도록 통일 (`CANONICAL_TECHNICAL_PERIOD = "3y"`).
2. **다중 티커 check**: `jarvis check <TICKER ...>`가 여러 티커를 한 번에 처리하고, 일부 실패해도 나머지 결과를 계속 출력한다.
3. **설명 전용 최종 LLM**: `analyze`의 최종 LLM을 `IntegratedExplanationOutput`(decision_explanation / rationale / risks / monitoring_points)으로 전환했다. LLM은 규칙이 확정한 액션·타이밍을 바꾸지 않고 설명만 한다.
4. **전 소스 통합 입력**: DeepDive가 레벨·Playbook을 decision보다 먼저 확정하고 veto를 적용한 뒤, veto가 반영된 요약으로 시나리오를 재구성한다. 기술·뉴스·재무·공시·수급·Macro·Playbook·레벨과 고정 decision을 단일 `generate_integrated_explanation` 호출로 전달한다.
5. **프롬프트 주입 방어**: 뉴스 분석과 최종 해설 LLM 모두 입력을 하나의 `<untrusted_facts>` JSON 경계로 직렬화하고 꺾쇠(`<`/`>`)를 이스케이프해 중첩 텍스트가 delimiter를 조기에 닫지 못하게 한다.
6. **Macro 표시**: `analyze`/`brief`는 Macro를 표시·전달하되, Macro는 규칙 액션을 바꾸지 않고 최종 해설의 근거로만 쓰인다. `check`는 Macro를 포함하지 않는다.
7. **장기 이동평균 방향**: 주요 지표에 SMA 100·200과 21거래일 기울기(보합 band 포함)를 항상 표시한다.

## Before / After

- **Before**: `analyze`가 `decision_summary`(규칙)와 `ActionableSignal`(LLM) 두 개의 액션을 각각 렌더. `report ticker`가 다중 종목 기술 배치를 담당. 최종 LLM에 news·Macro가 함께 전달되지 않는 공백 존재.
- **After**: 규칙이 확정한 `decision_summary` 하나만 권위 있는 액션. 최종 LLM은 모든 소스를 받아 그 결정을 설명만 함(`종합 해설` 섹션 1개). 다중 종목 기술 확인은 `jarvis check <TICKER ...>`가 담당.

## Breaking / Removed

- `jarvis report ticker`가 alias 없이 제거되었다.
- 기술 전용 배치는 `jarvis check <TICKER> [TICKER ...]`로 마이그레이션한다.
- Analyze의 `ActionableSignal` 출력 계약이 제거되었다. 소비처는 규칙이 확정한 decision 요약과 설명 전용 통합 출력을 사용한다.
- 제거된 심볼: `IntegratedAnalysisInput/Output`, `ActionableSignalOutput`, `generate_actionable_signal()`, `generate_integrated_analysis()`, `display_actionable_signal()`, `TickerReportPipeline`, 결과 키 `integrated_analysis`·`actionable_signal`.

## Impact

- `jarvis analyze` 출력은 Macro 스냅샷 + 규칙 확정 액션 + `종합 해설`(근거/리스크/모니터링 포인트) 순으로 구성된다. 경쟁하던 액션 패널 두 개가 하나의 설명 섹션으로 통합됐다.
- `jarvis check`는 여러 티커를 한 번에 받으며 Macro는 표시하지 않는다.
- 같은 fixture에서 component/raw/adjusted/verdict/history/trace 값이 세 소비처에서 동일하게 나온다.

## Constraints

- 최종 LLM은 규칙이 확정한 action/timing을 새로 만들거나 바꾸지 않는다 (설명 전용).
- Macro는 `analyze`/`brief` 전용 컨텍스트이며 `check`에는 포함하지 않는다.
- veto 이후 재구성된 시나리오만 노출·직렬화된다.
- 외부 텍스트(뉴스·공시)는 `<untrusted_facts>` 경계 안에서만 다루고 명령·역할 변경 지시를 무시한다.

## Tests

- `uv run pytest tests/pipelines/test_deep_dive.py tests/pipelines/test_deep_dive_structure_contract.py tests/pipelines/test_technical_contract_parity.py tests/llm/test_models.py tests/llm/test_analyzer.py tests/cli/test_cli.py tests/cli/test_analyze_output.py -q`
- `uv run ruff check src tests`
- `uv run pytest`

## Related

- 설계: [docs/superpowers/specs/2026-07-20-unified-technical-analysis-contract-design.md](../superpowers/specs/2026-07-20-unified-technical-analysis-contract-design.md)
- 구현 계획: [docs/superpowers/plans/2026-07-20-unified-technical-analysis-contract.md](../superpowers/plans/2026-07-20-unified-technical-analysis-contract.md)
- worklog: [docs/worklog/technical-scoring-redesign.md](../worklog/technical-scoring-redesign.md)
- 선행: [technical-scoring-redesign.md](technical-scoring-redesign.md)
