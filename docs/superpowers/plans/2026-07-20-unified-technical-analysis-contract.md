# Unified Technical Analysis Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `check`, `analyze`, `brief`가 같은 3년 기술 결과를 사용하게 하고, 다중 ticker 확인·Analyze Macro 종합 해설·SMA 100/200 기울기 표시를 제공하면서 중복 `report ticker`를 제거한다.

**Architecture:** `TechnicalAnalysisTool`이 3년 canonical period의 단일 진입점이 되고 모든 제품 파이프라인은 period override 없이 이를 호출한다. 기술 결과는 결정론적으로 유지하고, `analyze`는 모든 규칙 계산이 끝난 뒤 뉴스·재무·공시·수급·Macro·Playbook·가격 레벨을 하나의 고정-action LLM 해설에 전달한다. 표시용 장기 이동평균 slope는 `IndicatorSnapshot`의 숫자 값과 공통 formatter로 제공한다.

**Tech Stack:** Python 3.13, Typer, Pydantic v2, pandas/pandas-ta, LangChain structured output, pytest/pytest-asyncio, Ruff, uv

## Global Constraints

- Package manager와 실행은 항상 `uv`를 사용한다.
- Canonical technical period는 정확히 `3y`다.
- 동일 ticker와 동일 OHLCV snapshot이면 component/raw/adjusted/verdict/history가 소비 파이프라인과 무관하게 같아야 한다.
- Macro와 LLM은 technical score와 rule action을 변경하지 않는다.
- Macro는 `analyze`와 `brief`에만 표시한다.
- SMA slope는 21거래일 변화율을 사용하며 `+0.5% 초과=↗ 상승`, `-0.5% 미만=↘ 하락`, 그 사이는 `→ 보합`이다.
- 신규 상장처럼 값이 부족해도 SMA 100·200 행은 `N/A · — 데이터 부족`으로 표시한다.
- 현재 `main`의 사용자 변경은 건드리지 않고 `feature/unified-technical-analysis` worktree에서만 작업한다.

---

## File Map

- `src/tools/technical/tool.py`: canonical 3년 조회 계약
- `src/tools/technical/indicators.py`: SMA 100과 21일 slope 계산
- `src/tools/technical/models.py`: 장기 이동평균 snapshot 필드
- `src/tools/technical/presentation.py`: SMA 100·200 공통 표시 포맷
- `src/pipelines/quick_check.py`: 공통 기술 결과의 check payload와 표시
- `src/pipelines/deep_dive.py`: Macro 수집, rule decision 이후 최종 LLM 해설 조립
- `src/pipelines/brief.py`: canonical Tool 호출 사용
- `src/llm/models.py`: 최종 종합 해설 입력 계약
- `src/llm/analyzer.py`: 모든 분석 소스를 받는 고정-action 종합 해설
- `src/cli/main.py`: 다중 ticker check, Analyze Macro/SMA 표시, report ticker 제거
- `src/pipelines/ticker_report.py`: 삭제
- `tests/`: 각 책임의 단위·통합·CLI 계약
- `docs/FEATURES.md`, `docs/CLI_USAGE.md`, `docs/ARCHITECTURE.md`, `docs/changes/`: 현재 기능과 변경 기록
- `.agents/skills/jarvis-check/SKILL.md`, `.claude/skills/jarvis-check/SKILL.md`: mirrored check skill 설명 동기화
- `.agents/skills/jarvis-analyze/SKILL.md`, `.claude/skills/jarvis-analyze/SKILL.md`: mirrored analyze skill 설명 동기화

---

### Task 1: Canonical 3-Year Technical Contract

**Files:**
- Modify: `src/tools/technical/tool.py:9-27`
- Modify: `src/pipelines/deep_dive.py:139`
- Modify: `src/pipelines/brief.py:89`
- Test: `tests/tools/technical/test_tool.py`
- Test: `tests/pipelines/test_quick_check.py`
- Test: `tests/pipelines/test_deep_dive.py`
- Test: `tests/pipelines/test_brief.py`

**Interfaces:**
- Produces: `CANONICAL_TECHNICAL_PERIOD: Final[str] = "3y"`
- Produces: `TechnicalAnalysisTool.execute(ticker: str, period: str = CANONICAL_TECHNICAL_PERIOD, **kwargs) -> ToolResult`
- Consumes: existing `BaseProvider.get_price_history(ticker, period)` and `TechnicalScorer.score(df, ticker)`

- [ ] **Step 1: Write the failing canonical-period tests**

Add a provider assertion to `tests/tools/technical/test_tool.py`:

```python
@pytest.mark.asyncio
async def test_technical_tool_uses_canonical_three_year_period_by_default(mock_provider, scorer):
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)

    await tool.execute("AAPL")

    mock_provider.get_price_history.assert_awaited_once_with("AAPL", "3y")
```

Update pipeline expectations so `DeepDivePipeline` and `BriefPipeline` call `execute(ticker)` without a local `period`, while `QuickCheckPipeline` keeps the same call.

- [ ] **Step 2: Run the contract tests and verify failure**

Run:

```bash
uv run pytest \
  tests/tools/technical/test_tool.py::test_technical_tool_uses_canonical_three_year_period_by_default \
  tests/pipelines/test_quick_check.py::test_quick_check_run \
  tests/pipelines/test_deep_dive.py \
  tests/pipelines/test_brief.py -q
```

Expected: the new Tool test reports the current `1y`; DeepDive/Brief mock expectations fail while production still passes explicit `3y`.

- [ ] **Step 3: Implement the single period source**

In `src/tools/technical/tool.py`:

```python
from typing import Final

CANONICAL_TECHNICAL_PERIOD: Final[str] = "3y"


class TechnicalAnalysisTool(BaseTool):
    async def execute(
        self,
        ticker: str,
        period: str = CANONICAL_TECHNICAL_PERIOD,
        **kwargs,
    ) -> ToolResult:
        try:
            logger.debug("Fetching price history: %s (period=%s)", ticker, period)
            df = await self.provider.get_price_history(ticker, period)
            if df.empty:
                return ToolResult(success=False, data=None, error=f"No data found for {ticker}")
            df = self.calculator.calculate(df)
            technical_result = self.scorer.score(df, ticker=ticker)
            return ToolResult(success=True, data=technical_result)
        except Exception as error:
            logger.debug("Technical analysis error for %s: %s", ticker, error)
            return ToolResult(success=False, data=None, error=str(error))
```

Preserve the existing execute body. In `DeepDivePipeline.run()` and `BriefPipeline._analyze_target()`, replace explicit `period="3y"` calls with `execute(ticker)`.

- [ ] **Step 4: Run focused tests**

```bash
uv run pytest \
  tests/tools/technical/test_tool.py::test_technical_tool_uses_canonical_three_year_period_by_default \
  tests/pipelines/test_quick_check.py::test_quick_check_run \
  tests/pipelines/test_deep_dive.py \
  tests/pipelines/test_brief.py -q
```

Expected: PASS; every product consumer uses the Tool default and the provider receives `3y`.

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/tool.py src/pipelines/deep_dive.py src/pipelines/brief.py \
  tests/tools/technical/test_tool.py tests/pipelines/test_quick_check.py \
  tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py
git commit -m "refactor: unify technical analysis period"
```

---

### Task 2: SMA 100/200 Values, Slopes, and Shared Presentation

**Files:**
- Create: `src/tools/technical/presentation.py`
- Modify: `src/tools/technical/indicators.py:23-29,163-239`
- Modify: `src/tools/technical/models.py:125-132`
- Modify: `src/pipelines/quick_check.py:50-75,160-190`
- Modify: `src/cli/main.py:601-613`
- Test: `tests/tools/technical/test_indicators.py`
- Create: `tests/tools/technical/test_presentation.py`
- Test: `tests/pipelines/test_quick_check.py`
- Test: `tests/cli/test_analyze_output.py`

**Interfaces:**
- Produces: `IndicatorSnapshot.sma_100: float | None`
- Produces: `IndicatorSnapshot.sma_100_slope_pct: float | None`
- Produces: `IndicatorSnapshot.sma_200_slope_pct: float | None`
- Produces: `format_long_sma(value: float | None, slope_pct: float | None) -> str`

- [ ] **Step 1: Write failing slope and formatter tests**

Add a 260-row deterministic fixture and assertions:

```python
def _trend_df(step: float, rows: int = 260) -> pd.DataFrame:
    close = 100.0 + np.arange(rows) * step
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(rows, 1_000_000),
        }
    )


def test_snapshot_includes_sma_100_and_long_sma_slopes():
    calculated = IndicatorCalculator().calculate(_trend_df(0.5))
    snapshot = IndicatorCalculator().create_snapshot(calculated)

    assert snapshot.sma_100 is not None
    assert snapshot.sma_200 is not None
    assert snapshot.sma_100_slope_pct > 0.5
    assert snapshot.sma_200_slope_pct > 0.5
```

Create `tests/tools/technical/test_presentation.py`:

```python
from src.tools.technical.presentation import format_long_sma


def test_format_long_sma_directions_and_missing_data():
    assert format_long_sma(123.45, 0.82) == "$123.45 · ↗ 상승 (+0.82%/21일)"
    assert format_long_sma(110.20, 0.12) == "$110.20 · → 보합 (+0.12%/21일)"
    assert format_long_sma(98.0, -0.75) == "$98.00 · ↘ 하락 (-0.75%/21일)"
    assert format_long_sma(None, None) == "N/A · — 데이터 부족"
```

Add CLI assertions that both check and analyze always contain `SMA 100:` and `SMA 200:` even when values are missing.

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest \
  tests/tools/technical/test_indicators.py \
  tests/tools/technical/test_presentation.py \
  tests/pipelines/test_quick_check.py \
  tests/cli/test_analyze_output.py -q
```

Expected: FAIL because SMA 100, slope fields, formatter, and always-visible rows do not exist.

- [ ] **Step 3: Add indicator and snapshot fields**

In `IndicatorCalculator.calculate()` add:

```python
df["SMA_100"] = ta.sma(df["Close"], length=100)
```

In `IndicatorCalculator` add:

```python
@staticmethod
def _slope_pct(df: pd.DataFrame, column: str, lookback: int = 21) -> float | None:
    values = df[column].dropna() if column in df.columns else pd.Series(dtype=float)
    if len(values) <= lookback:
        return None
    current = float(values.iloc[-1])
    previous = float(values.iloc[-lookback - 1])
    if previous == 0:
        return None
    return round((current / previous - 1.0) * 100.0, 2)
```

Populate the three new `IndicatorSnapshot` fields from `create_snapshot()`.

- [ ] **Step 4: Add shared formatter and wire both outputs**

Create `src/tools/technical/presentation.py`:

```python
LONG_SMA_FLAT_THRESHOLD_PCT = 0.5


def format_long_sma(value: float | None, slope_pct: float | None) -> str:
    if value is None or slope_pct is None:
        return "N/A · — 데이터 부족"
    if slope_pct > LONG_SMA_FLAT_THRESHOLD_PCT:
        icon, label = "↗", "상승"
    elif slope_pct < -LONG_SMA_FLAT_THRESHOLD_PCT:
        icon, label = "↘", "하락"
    else:
        icon, label = "→", "보합"
    return f"${value:.2f} · {icon} {label} ({slope_pct:+.2f}%/21일)"
```

Add `sma_100`, `sma_200`, and both slopes to the QuickCheck result payload. Render these exact lines in check and analyze:

```python
f"- **SMA 100**: {format_long_sma(snapshot.sma_100, snapshot.sma_100_slope_pct)}"
f"- **SMA 200**: {format_long_sma(snapshot.sma_200, snapshot.sma_200_slope_pct)}"
```

- [ ] **Step 5: Run focused tests**

```bash
uv run pytest \
  tests/tools/technical/test_indicators.py \
  tests/tools/technical/test_presentation.py \
  tests/pipelines/test_quick_check.py \
  tests/cli/test_analyze_output.py -q
```

Expected: PASS for rising, flat, falling, missing-data, check output, and analyze output cases.

- [ ] **Step 6: Commit**

```bash
git add src/tools/technical/indicators.py src/tools/technical/models.py \
  src/tools/technical/presentation.py src/pipelines/quick_check.py src/cli/main.py \
  tests/tools/technical/test_indicators.py tests/tools/technical/test_presentation.py \
  tests/pipelines/test_quick_check.py tests/cli/test_analyze_output.py
git commit -m "feat: show long moving average trends"
```

---

### Task 3: Multi-Ticker Check and report ticker Removal

**Files:**
- Modify: `src/cli/main.py:17-21,219-247,1103-1215`
- Delete: `src/pipelines/ticker_report.py`
- Modify: `tests/cli/test_cli.py`
- Delete: `tests/pipelines/test_ticker_report.py`

**Interfaces:**
- Produces: `run_quick_checks(queries: list[str]) -> list[dict]`
- Preserves: `uv run jarvis check AAPL`
- Adds: `uv run jarvis check AAPL MSFT NVDA`
- Removes: `uv run jarvis report ticker`

- [ ] **Step 1: Write failing CLI tests**

Add to `tests/cli/test_cli.py`:

```python
def test_check_accepts_multiple_tickers():
    results = [
        {"success": True, "ticker": "AAPL", "price": 100.0, "change_pct": 1.0},
        {"success": True, "ticker": "MSFT", "price": 200.0, "change_pct": -1.0},
    ]
    with (
        patch("src.cli.main.run_quick_checks", new=AsyncMock(return_value=results)),
        patch("src.pipelines.quick_check.QuickCheckPipeline.format_output", side_effect=["AAPL result", "MSFT result"]),
    ):
        result = runner.invoke(app, ["check", "AAPL", "MSFT"])

    assert result.exit_code == 0
    assert "AAPL result" in result.stdout
    assert "MSFT result" in result.stdout


def test_check_reports_all_results_then_exits_nonzero_on_partial_failure():
    results = [
        {"success": True, "ticker": "AAPL", "price": 100.0, "change_pct": 1.0},
        {"success": False, "ticker": "INVALID", "error": "No data"},
    ]
    with patch("src.cli.main.run_quick_checks", new=AsyncMock(return_value=results)):
        result = runner.invoke(app, ["check", "AAPL", "INVALID"])

    assert result.exit_code == 1
    assert "No data" in result.stdout
```

Replace the existing `report ticker` CLI test with:

```python
def test_report_ticker_command_is_removed():
    result = runner.invoke(app, ["report", "ticker"])
    assert result.exit_code != 0
    assert "No such command" in result.stdout
```

- [ ] **Step 2: Run CLI tests and verify failure**

```bash
uv run pytest tests/cli/test_cli.py -q
```

Expected: multi-ticker parsing fails and `report ticker` still exists.

- [ ] **Step 3: Implement batch check orchestration**

Add:

```python
async def run_quick_checks(queries: list[str]) -> list[dict]:
    results: list[dict] = []
    for query in queries:
        try:
            results.append(await run_quick_check(query))
        except Exception as exc:
            results.append(
                {
                    "ticker": query,
                    "error": str(exc),
                    "success": False,
                }
            )
    return results
```

Change `check` from a scalar argument to a required `list[str]` Typer argument, execute the batch once, render all successes, render all failures, then raise `typer.Exit(1)` after rendering if any failed. Keep `--detail-history` behavior for each success.

- [ ] **Step 4: Remove ticker report production code and tests**

Delete `TickerReportPipeline` import, `run_daily_report`, `format_daily_report_output`, and `report_ticker` from `src/cli/main.py`. Delete `src/pipelines/ticker_report.py` and `tests/pipelines/test_ticker_report.py`. Keep `report_app` because daily, upload, ingest-pdf and other report commands still use it.

- [ ] **Step 5: Run focused tests and CLI help**

```bash
uv run pytest tests/cli/test_cli.py tests/pipelines/test_quick_check.py -q
uv run jarvis check --help
uv run jarvis report --help
```

Expected: tests pass; check help shows multiple ticker arguments; report help does not list `ticker`.

- [ ] **Step 6: Commit**

```bash
git add src/cli/main.py src/pipelines/ticker_report.py \
  tests/cli/test_cli.py tests/pipelines/test_ticker_report.py
git commit -m "feat: support multi-ticker quick checks"
```

---

### Task 4: Analyze Macro Collection and Display

**Files:**
- Modify: `src/pipelines/deep_dive.py:85-120,173-207,285-320`
- Modify: `src/cli/main.py:250-375,947-983`
- Test: `tests/pipelines/test_deep_dive.py`
- Test: `tests/cli/test_analyze_output.py`

**Interfaces:**
- Consumes: `MacroTool.execute() -> ToolResult[TickerMacroSnapshot]`
- Produces: `DeepDivePipeline.__init__` parameter `macro_tool: MacroTool | None = None`
- Produces: deep-dive result key `macro: TickerMacroSnapshot | None`
- Produces: `_format_macro_section(macro: TickerMacroSnapshot | None) -> str`

- [ ] **Step 1: Write failing Macro pipeline tests**

Add a `mock_macro_tool` that returns a complete `TickerMacroSnapshot`. Verify `result["macro"]` contains it. Add the failure case to the existing DeepDive success-test fixture arrangement:

```python
@pytest.mark.asyncio
async def test_deep_dive_continues_when_macro_fails(
    mock_technical_tool,
    mock_news_tool,
    mock_llm,
):
    macro_tool = AsyncMock()
    macro_tool.execute.return_value = ToolResult(success=False, data=None, error="macro down")
    with (
        patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock),
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock),
        patch("src.llm.analyzer.generate_integrated_analysis", new_callable=AsyncMock),
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock),
    ):
        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
            macro_tool=macro_tool,
        )
        result = await pipeline.run("AAPL")

    assert result["macro"] is None
    assert result["technical"] is not None
```

Add an output test asserting the Macro section contains VIX, Fear & Greed, WTI, 10Y, 2Y, spread, and DXY.

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest \
  tests/pipelines/test_deep_dive.py \
  tests/cli/test_analyze_output.py -q
```

Expected: FAIL because DeepDive has no Macro dependency or output section.

- [ ] **Step 3: Collect Macro as optional data**

Add `macro_tool` to `DeepDivePipeline.__init__`. In the optional tool collection, append `self.macro_tool.execute()` under key `macro`. Read `macro_data = optional_data.get("macro")` and include it in the returned result. Preserve warning-and-continue behavior.

In `run_deep_dive()`, construct `MacroTool()` and inject it into the pipeline.

- [ ] **Step 4: Render Macro near the top of Analyze output**

Add a pure formatter that returns an empty string for `None` and otherwise renders all snapshot fields. Call it immediately after the price line in `format_deep_dive_output()`.

- [ ] **Step 5: Run focused tests**

```bash
uv run pytest \
  tests/pipelines/test_deep_dive.py \
  tests/cli/test_analyze_output.py -q
```

Expected: PASS; Macro success displays all fields and Macro failure does not block Analyze.

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/deep_dive.py src/cli/main.py \
  tests/pipelines/test_deep_dive.py tests/cli/test_analyze_output.py
git commit -m "feat: add macro context to analyze"
```

---

### Task 5: One Final All-Source LLM Explanation

**Files:**
- Modify: `src/llm/models.py:108-160`
- Modify: `src/llm/analyzer.py:407-570`
- Modify: `src/pipelines/deep_dive.py:198-320,495-526`
- Modify: `src/cli/main.py:15,851-875,986-1078`
- Modify: `tests/llm/test_models.py`
- Modify: `tests/llm/test_analyzer.py`
- Modify: `tests/pipelines/test_deep_dive.py`
- Modify: `tests/pipelines/test_deep_dive_structure_contract.py`
- Modify: `tests/cli/test_cli.py`
- Modify: `tests/cli/test_analyze_output.py`

**Interfaces:**
- Produces: expanded `IntegratedAnalysisInput` containing fixed decision and every analysis source
- Preserves: `IntegratedAnalysisOutput(recommendation, rationale, risks, action_summary)`
- Removes: `ActionableSignalOutput`, `generate_actionable_signal()`, `display_actionable_signal()` and `result["actionable_signal"]`
- Guarantees: returned `IntegratedAnalysisOutput.recommendation == fixed_action`

- [ ] **Step 1: Write failing all-source input and fixed-action tests**

Expand the integrated analyzer test to construct:

```python
input_data = IntegratedAnalysisInput(
    ticker="AAPL",
    fixed_action="관망",
    fixed_timing="조정_대기",
    fixed_action_sentence="조정 확인 후 접근이 유리",
    technical_context={"adjusted_score": 35, "action": "watch"},
    news_analysis={"sentiment": "긍정", "summary": "신제품 기대"},
    fundamental_summary={"valuation_assessment": "고평가", "summary": "밸류 부담"},
    disclosure_items=[{"form_type": "8-K", "date": "2026-07-20", "description": "계약", "url": "u"}],
    flow_summary="외국인 5일 매수",
    macro_context={"vix": 28.0, "fear_greed": 20, "us_10y": 4.5, "dxy": 105.0},
    playbook_summary="시장 gate 미통과",
    scenarios=[{"name": "기본", "expected_path": "눌림 후 재확인"}],
    structure_summary="핵심 지지 180~185",
    execution_summary="SMA200 175",
)
```

Mock the LLM returning `recommendation="매수"`; assert the function returns `recommendation="관망"`. Capture the prompt arguments and assert every source appears.

- [ ] **Step 2: Run LLM and DeepDive tests to verify failure**

```bash
uv run pytest \
  tests/llm/test_models.py \
  tests/llm/test_analyzer.py \
  tests/pipelines/test_deep_dive.py \
  tests/pipelines/test_deep_dive_structure_contract.py \
  tests/cli/test_analyze_output.py -q
```

Expected: FAIL because the input fields and fixed-action enforcement do not exist.

- [ ] **Step 3: Expand the structured input contract**

Replace mutable list defaults with `Field(default_factory=list)` and define:

```python
class IntegratedAnalysisInput(BaseModel):
    ticker: str
    fixed_action: str
    fixed_timing: str
    fixed_action_sentence: str
    technical_context: dict[str, Any]
    news_analysis: dict[str, Any] | None = None
    fundamental_summary: dict[str, Any] | None = None
    disclosure_items: list[dict[str, Any]] = Field(default_factory=list)
    flow_summary: str | None = None
    macro_context: dict[str, Any] | None = None
    playbook_summary: str | None = None
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    structure_summary: str | None = None
    execution_summary: str | None = None
```

- [ ] **Step 4: Make integrated analysis the single final LLM explanation**

Serialize `IntegratedAnalysisInput` with `model_dump_json(indent=2)`, instruct the LLM that action/timing are fixed facts, and request rationale/risks/action summary. Enforce the rule result after invocation:

```python
result = await chain.ainvoke({"facts_json": input_data.model_dump_json(indent=2)})
return result.model_copy(update={"recommendation": input_data.fixed_action})
```

Do not ask the LLM to derive a new action.

- [ ] **Step 5: Reorder DeepDive finalization and pass every source**

Build chart patterns, levels, Playbook verdict, decision bundle, and Playbook veto before integrated analysis. Then construct `IntegratedAnalysisInput` from:

```python
technical_context={
    "component_raw_total": technical_data.component_raw_total,
    "adjusted_score": technical_data.adjusted_score,
    "technical_verdict": technical_data.technical_verdict.model_dump(),
    "score_history": [point.model_dump() for point in technical_data.score_history],
},
news_analysis=news_analysis.model_dump() if news_analysis else None,
fundamental_summary=fundamental_summary.model_dump() if fundamental_summary else None,
macro_context=macro_data.model_dump(mode="json") if macro_data else None,
playbook_summary=playbook_verdict.headline if playbook_verdict else None,
scenarios=[scenario.model_dump() for scenario in decision_bundle.scenarios],
structure_summary=presented_structure.structure_summary,
execution_summary=presented_structure.execution_summary,
```

Always request integrated analysis after rule finalization, even when disclosure and flow are absent.

- [ ] **Step 6: Remove the conflicting legacy actionable-signal path**

Remove `ActionableSignalOutput`, `generate_actionable_signal`, CLI panel rendering, DeepDive invocation/result key, and their dedicated tests. Convert the structure contract test to assert that `IntegratedAnalysisInput.structure_summary` and `execution_summary` receive the presented structure values.

- [ ] **Step 7: Run focused tests**

```bash
uv run pytest \
  tests/llm/test_models.py \
  tests/llm/test_analyzer.py \
  tests/pipelines/test_deep_dive.py \
  tests/pipelines/test_deep_dive_structure_contract.py \
  tests/cli/test_analyze_output.py \
  tests/cli/test_cli.py -q
```

Expected: PASS; one final LLM explanation receives every source and cannot override the fixed action.

- [ ] **Step 8: Commit**

```bash
git add src/llm/models.py src/llm/analyzer.py src/pipelines/deep_dive.py src/cli/main.py \
  tests/llm/test_models.py tests/llm/test_analyzer.py tests/pipelines/test_deep_dive.py \
  tests/pipelines/test_deep_dive_structure_contract.py tests/cli/test_cli.py \
  tests/cli/test_analyze_output.py
git commit -m "feat: unify analyze final explanation"
```

---

### Task 6: Documentation, Skills, and Full Verification

**Files:**
- Modify: `docs/FEATURES.md`
- Modify: `docs/CLI_USAGE.md`
- Modify: `docs/ARCHITECTURE.md`
- Create: `docs/changes/unified-technical-analysis-contract.md`
- Modify: `docs/changes/INDEX.md`
- Modify: `.agents/skills/jarvis-check/SKILL.md`
- Modify: `.claude/skills/jarvis-check/SKILL.md`
- Modify: `.agents/skills/jarvis-analyze/SKILL.md`
- Modify: `.claude/skills/jarvis-analyze/SKILL.md`
- Modify: `docs/worklog/technical-scoring-redesign.md`

**Interfaces:**
- Documents: current command roles and canonical technical contract
- Documents: `report ticker` removal and migration to multi-ticker `check`
- Keeps: `.agents` and `.claude` skill copies byte-for-byte equivalent

- [ ] **Step 1: Update current-state documentation**

Document the exact command examples:

```bash
uv run jarvis check AAPL MSFT NVDA
uv run jarvis analyze AAPL
uv run jarvis brief
```

Remove `report ticker` examples. Describe Macro as Analyze/Brief-only context and state that Analyze passes it to the final LLM explanation without changing the rule action.

- [ ] **Step 2: Add the change record and INDEX entry**

Create a change record with `Why`, `What`, `Before / After`, `Impact`, `Constraints`, `Tests`, and `Related`. Record the PR as `-` until a PR exists and set status to `Draft`.

- [ ] **Step 3: Synchronize jarvis-check skills**

Both skill files must describe 8 components, canonical 3-year analysis, multiple ticker usage, no LLM, and no Macro:

```markdown
# Quick Check

여러 ticker의 공통 3년 기술 분석을 LLM 없이 빠르게 확인한다.

```bash
uv run jarvis check AAPL MSFT 005930.KS
```
```

Copy the same final contents to both mirrored paths and verify:

```bash
diff -u .agents/skills/jarvis-check/SKILL.md .claude/skills/jarvis-check/SKILL.md
```

Expected: no output.

Update both `jarvis-analyze` copies with the same content describing 3년 기술 분석, 뉴스·재무·공시·수급·Macro, fixed rule action, and final all-source LLM explanation. Verify:

```bash
diff -u .agents/skills/jarvis-analyze/SKILL.md .claude/skills/jarvis-analyze/SKILL.md
```

Expected: no output.

- [ ] **Step 4: Run targeted verification**

```bash
uv run pytest \
  tests/tools/technical/test_tool.py \
  tests/tools/technical/test_indicators.py \
  tests/tools/technical/test_presentation.py \
  tests/tools/technical/test_scoring_regression.py \
  tests/pipelines/test_quick_check.py \
  tests/pipelines/test_deep_dive.py \
  tests/pipelines/test_deep_dive_structure_contract.py \
  tests/pipelines/test_brief.py \
  tests/llm/test_models.py \
  tests/llm/test_analyzer.py \
  tests/cli/test_cli.py \
  tests/cli/test_analyze_output.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run lint and full regression**

```bash
uv run ruff check src tests
uv run pytest
```

Expected: Ruff exits 0; pytest reports no failures. The baseline reference before implementation is `1215 passed, 15 deselected, 3 warnings`.

- [ ] **Step 6: Record verified implementation in worklog**

Append a `[Bug]` entry only after Step 5 succeeds. Record the prior period drift, missing final LLM inputs, implemented fixes, and exact verification counts.

- [ ] **Step 7: Commit**

```bash
git add docs/FEATURES.md docs/CLI_USAGE.md docs/ARCHITECTURE.md \
  docs/changes/unified-technical-analysis-contract.md docs/changes/INDEX.md \
  docs/worklog/technical-scoring-redesign.md \
  .agents/skills/jarvis-check/SKILL.md .claude/skills/jarvis-check/SKILL.md \
  .agents/skills/jarvis-analyze/SKILL.md .claude/skills/jarvis-analyze/SKILL.md
git commit -m "docs: document unified technical analysis"
```

---

## Final Review Checklist

- [ ] `rg -n 'period="3y"|period="1y"' src/pipelines src/cli/main.py` finds no product-pipeline period override.
- [ ] `rg -n 'TickerReportPipeline|report_ticker|run_daily_report|ActionableSignalOutput|generate_actionable_signal' src tests` finds no remaining production or test references.
- [ ] `uv run jarvis check --help` represents multi-ticker syntax accurately.
- [ ] Analyze output contains Macro, SMA 100, SMA 200, fixed rule action, and final integrated explanation.
- [ ] Check output contains SMA 100 and SMA 200 but no Macro.
- [ ] Brief still displays Macro and uses Playbook for final action.
- [ ] Same fixture produces identical technical core values across all consumers.
- [ ] Original `main` working tree retains only the user's pre-existing changes.
