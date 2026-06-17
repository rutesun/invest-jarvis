# 연결: deep_dive · veto · CLI Implementation Plan (Plan 9/9, 마지막)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. 체크박스(`- [ ]`)로 추적.

**Goal:** `PlaybookEngine`을 `analyze` 파이프라인에 연결하고, veto를 사용자가 보는 `decision_summary`에 반영하며, CLI에 "📋 플레이북 평가" 섹션을 렌더한다. 더불어 Plan 2에서 생긴 `main.py` annual_data 접근 버그를 고친다.

**Architecture:** `deep_dive`가 이미 만든 `technical_result`/`fundamental`/`flow`/`zone_set`을 `PlaybookEngine.evaluate`에 넘겨 `playbook_verdict`를 얻는다(fundamental 전달 → 업종 매핑·sector 작동). veto는 `analyze_decision.apply_playbook_veto`(순수 함수)로 `decision_summary`를 후처리한다(빌더 본체는 순수 유지). CLI는 verdict를 별도 섹션으로 출력.

**Tech Stack:** Python 3.12, pytest. `uv run`.

**선행:** Plan 8(`PlaybookEngine`, `evaluate_gate`, `plan_position`, `evaluate_exit`, `load_holdings`).

---

## File Structure
- **Modify:** `src/cli/main.py` — annual_data 버그 가드(Task 1) + "📋 플레이북 평가" 렌더(Task 4)
- **Modify:** `src/pipelines/deep_dive.py` — `PlaybookEngine` 주입·호출, 출력 dict에 `playbook_verdict`(Task 2)
- **Modify:** `src/pipelines/analyze_decision.py` — `apply_playbook_veto(summary, verdict)`(Task 3)
- **Modify:** `src/llm/models.py` — `AnalyzeDecisionSummary`에 `action_original: str|None`, `veto_applied: bool`(Task 3)
- **Test:** `tests/.../test_apply_playbook_veto.py`, 기존 cli/deep_dive 테스트 갱신

---

## Task 1: main.py annual_data 버그 수정 (우려 2)
`cli/main.py:721` 부근에서 `fundamental.annual_data`를 직접 접근해, 그 필드가 없거나 None인 mock에서 기존 테스트(`test_format_deep_dive_output_shows_na_for_missing_fundamental_metrics`)가 실패한다.
- [ ] **Step 1:** 실패 테스트 재현 — `uv run pytest tests/.../test_*format_deep_dive* -v` (현재 1 fail).
- [ ] **Step 2~3:** `annual_data`/`eps` 접근을 `getattr(fundamental, "annual_data", None)` + None 가드로 감싼다. 연간 EPS 추이 렌더는 데이터 있을 때만.
- [ ] **Step 4~5:** 통과 + 커밋 `fix(cli): guard annual_data access in deep_dive output`

## Task 2: deep_dive → PlaybookEngine 연결
- [ ] **Step 1:** 실패 테스트 — `DeepDivePipeline.run(ticker)` 결과 dict에 `"playbook_verdict"` 키가 있고 `PlaybookVerdict`인지(mock provider/engine).
- [ ] **Step 2~3:** `DeepDivePipeline.__init__`에 `playbook_engine: PlaybookEngine | None = None`(또는 index/fmp/kis provider로 내부 생성). `run()`에서 `zone_set`(이미 `deep_dive.py:184` 생성), `holding = load_holdings().find(ticker)`를 얻어 `verdict = await self.playbook_engine.evaluate(ticker, technical_data, fundamental_data, flow_data, zone_set, holding)`. 출력 dict에 `"playbook_verdict": verdict`. engine 없으면 None(기존 동작 보존).
- [ ] **Step 4~5:** 통과 + 커밋 `feat(deep_dive): wire PlaybookEngine -> playbook_verdict`

## Task 3: apply_playbook_veto (decision_summary 후처리)
- [ ] **Step 1:** 실패 테스트 — 미보유+gate FAIL → `summary.action=="관망"`, `summary.veto_applied is True`, `action_original` 보존. 미보유+PASS → 유지. 보유 → exit_verdict 반영.
- [ ] **Step 2~3:** `models.py` `AnalyzeDecisionSummary`에 `action_original: str | None = None`, `veto_applied: bool = False`. `analyze_decision.py`에 순수 함수:

```python
def apply_playbook_veto(summary: AnalyzeDecisionSummary, verdict) -> AnalyzeDecisionSummary:
    if verdict is None:
        return summary
    if not verdict.holding and verdict.gate is not None and not verdict.gate.passed:
        return summary.model_copy(update={
            "action_original": summary.action,
            "veto_applied": True,
            "action": "관망",
            "action_sentence": f"신규진입 부적격: {verdict.gate.veto_reason}",
        })
    if verdict.holding and verdict.exit_verdict is not None and verdict.exit_verdict.action in ("청산", "비중축소"):
        return summary.model_copy(update={
            "action_original": summary.action,
            "veto_applied": True,
            "action_sentence": f"보유 판정: {verdict.exit_verdict.action} ({verdict.exit_verdict.detail})",
        })
    return summary
```
`build_analyze_decision_bundle`은 순수 유지; `deep_dive.run`에서 `bundle.summary = apply_playbook_veto(bundle.summary, verdict)` 합성.
- [ ] **Step 4~5:** 통과 + 커밋 `feat(analyze): apply_playbook_veto to decision_summary`

## Task 4: CLI "📋 플레이북 평가" 섹션
- [ ] **Step 1:** 실패 테스트 — `format_deep_dive_output`에 `playbook_verdict`가 있으면 "플레이북 평가" 헤더 + 판정/체크리스트/CANSLIM/포지션(or 매도)이 문자열에 포함.
- [ ] **Step 2~3:** `main.py`에 렌더 함수: 판정(적격/부적격+veto_reason), gate.checklist(A/B/C/E ✅/❌/—), canslim.summary, 미보유면 position_plan(수량/손절/R), 보유면 exit_verdict. 스펙 §15 형식.
- [ ] **Step 4:** 통과
- [ ] **Step 5: 실데이터** — `uv run jarvis analyze AAPL`로 플레이북 섹션이 출력되는지(gate 판정, canslim, position/veto). 한국 종목도 1건(`jarvis analyze 005930.KS`, KIS 순차) 확인.
- [ ] **Step 6:** 커밋 `feat(cli): render playbook evaluation section`

---

## Self-Review
**1. 스펙 커버리지:** §12(veto→decision_summary, action_original)→T3; §15(CLI 섹션)→T4; §5(deep_dive 연결, fundamental 전달로 sector 작동)→T2; 우려2(annual_data)→T1.
**2. Placeholder:** 없음.
**3. 타입 일관성:** `apply_playbook_veto(summary, verdict)`, `AnalyzeDecisionSummary.action_original/veto_applied`, dict 키 `"playbook_verdict"`.

> **회귀:** `uv run pytest`(전체)가 통과해야 함. deep_dive/analyze_decision/cli 기존 테스트가 깨지면 갱신. engine 미주입 시 기존 동작 보존(verdict=None → veto 미적용).

---

## 완료 후
전체 9개 Plan 완료. `superpowers:finishing-a-development-branch`로 마무리(전체 테스트 + PR/머지 옵션). FEATURES.md Playbook 섹션을 "Plan 1~9 완료"로 갱신 권장(`/document-release`).
