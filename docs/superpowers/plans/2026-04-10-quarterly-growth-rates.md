# 분기별 성장률 기능 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매출과 이익의 YoY/QoQ 성장률을 계산하고 분기별 추이를 표와 리스트로 표시

**Architecture:** FundamentalTool이 8개 분기 데이터를 수집하고 YoY/QoQ 계산 → QuarterlyData 모델로 구조화 → CLI에서 Rich Table과 리스트로 표시

**Tech Stack:** yfinance, pydantic, rich (table), pytest

---

## File Structure

```
src/tools/
└── fundamental.py         # QuarterlyData 모델 추가, FundamentalSnapshot 수정, 계산 로직 구현

src/cli/
└── main.py               # 분기별 표 렌더링, 분기별 리스트 섹션 추가

tests/tools/
└── test_fundamental.py   # 신규 테스트 6개 추가

tests/integration/
└── test_e2e_plan4.py     # 통합 테스트 1개 추가

tests/llm/
└── test_analyzer.py      # 기존 테스트 업데이트 (quarterly_revenue 제거)
```

---

## Task 1: QuarterlyData 모델 추가

**Files:**
- Modify: `src/tools/fundamental.py:10-60`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_fundamental.py - append to end of file
from src.tools.fundamental import QuarterlyData


def test_quarterly_data_model():
    """QuarterlyData 모델 검증"""
    data = QuarterlyData(
        period="2026-Q1",
        revenue=143756000000,
        earnings=36500000000,
        revenue_yoy=0.1565,
        revenue_qoq=0.4030,
        earnings_yoy=0.1830,
        earnings_qoq=0.3520,
    )
    assert data.period == "2026-Q1"
    assert data.revenue == 143756000000
    assert data.revenue_yoy == 0.1565
    assert data.revenue_qoq == 0.4030
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_fundamental.py::test_quarterly_data_model -v`
Expected: FAIL with "cannot import name 'QuarterlyData'"

- [ ] **Step 3: Add QuarterlyData model**

```python
# src/tools/fundamental.py - add after line 9 (after imports)
class QuarterlyData(BaseModel):
    """분기별 재무 데이터 및 성장률"""
    period: str
    revenue: float | None = None
    earnings: float | None = None
    revenue_yoy: float | None = None
    revenue_qoq: float | None = None
    earnings_yoy: float | None = None
    earnings_qoq: float | None = None


```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_fundamental.py::test_quarterly_data_model -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/fundamental.py tests/tools/test_fundamental.py
git commit -m "feat(fundamental): add QuarterlyData model"
```

---

## Task 2: FundamentalSnapshot 모델 수정

**Files:**
- Modify: `src/tools/fundamental.py:11-60`
- Test: `tests/tools/test_fundamental.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_fundamental.py - append to end of file
def test_fundamental_snapshot_with_quarterly_data():
    """FundamentalSnapshot이 quarterly_data 필드를 지원하는지 검증"""
    quarterly = [
        QuarterlyData(period="2026-Q1", revenue=143756000000, earnings=36500000000),
        QuarterlyData(period="2025-Q4", revenue=102466000000, earnings=28300000000),
    ]
    snapshot = FundamentalSnapshot(
        market_cap=3828660000000,
        pe_ratio=33.0,
        quarterly_data=quarterly,
    )
    assert snapshot.quarterly_data is not None
    assert len(snapshot.quarterly_data) == 2
    assert snapshot.quarterly_data[0].period == "2026-Q1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_fundamental.py::test_fundamental_snapshot_with_quarterly_data -v`
Expected: FAIL with "FundamentalSnapshot has no field quarterly_data"

- [ ] **Step 3: Modify FundamentalSnapshot model**

```python
# src/tools/fundamental.py - replace lines 38-40 with:
    # Quarterly data with growth rates
    quarterly_data: list[QuarterlyData] | None = None
```

Note: Remove these two lines:
```python
    quarterly_revenue: list[dict] | None = None
    quarterly_earnings: list[dict] | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_fundamental.py::test_fundamental_snapshot_with_quarterly_data -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/fundamental.py tests/tools/test_fundamental.py
git commit -m "feat(fundamental): replace quarterly_revenue/earnings with quarterly_data"
```

---

## Task 3: _fetch_fundamentals() - 8분기 수집 및 YoY/QoQ 계산

**Files:**
- Modify: `src/tools/fundamental.py:86-137`
- Test: `tests/tools/test_fundamental.py`

- [ ] **Step 1: Write the failing test for YoY calculation**

```python
# tests/tools/test_fundamental.py - append to end of file
import pandas as pd
from datetime import datetime


def test_quarterly_yoy_calculation():
    """YoY 성장률 계산 검증"""
    mock_info = {"marketCap": 3e12}
    
    # 8개 분기 mock 데이터
    quarters = [
        pd.Period("2026Q1"),
        pd.Period("2025Q4"),
        pd.Period("2025Q3"),
        pd.Period("2025Q2"),
        pd.Period("2025Q1"),  # 4분기 전 (YoY 비교 대상)
        pd.Period("2024Q4"),
        pd.Period("2024Q3"),
        pd.Period("2024Q2"),
    ]
    
    revenues = [143756e6, 102466e6, 94036e6, 88230e6, 124300e6, 95000e6, 90000e6, 85000e6]
    earnings = [36500e6, 28300e6, 24200e6, 22100e6, 30800e6, 25000e6, 21000e6, 19000e6]
    
    qf = pd.DataFrame(
        {
            "Total Revenue": revenues,
            "Net Income": earnings,
        },
        index=["Total Revenue", "Net Income"],
        columns=quarters,
    )
    
    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = qf
    
    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = asyncio.run(tool.execute("AAPL"))
    
    assert result.success is True
    quarterly_data = result.data.quarterly_data
    assert quarterly_data is not None
    assert len(quarterly_data) == 4  # 최근 4분기만
    
    # Q1 2026 YoY 계산 확인: (143756 - 124300) / 124300 = 0.1565
    assert quarterly_data[0].period == "2026-Q1"
    assert quarterly_data[0].revenue_yoy is not None
    assert abs(quarterly_data[0].revenue_yoy - 0.1565) < 0.001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_fundamental.py::test_quarterly_yoy_calculation -v`
Expected: FAIL (quarterly_data is None or calculations wrong)

- [ ] **Step 3: Write the failing test for QoQ calculation**

```python
# tests/tools/test_fundamental.py - append to end of file
def test_quarterly_qoq_calculation():
    """QoQ 성장률 계산 검증"""
    mock_info = {"marketCap": 3e12}
    
    quarters = [
        pd.Period("2026Q1"),
        pd.Period("2025Q4"),
        pd.Period("2025Q3"),
        pd.Period("2025Q2"),
        pd.Period("2025Q1"),
    ]
    
    revenues = [143756e6, 102466e6, 94036e6, 88230e6, 124300e6]
    earnings = [36500e6, 28300e6, 24200e6, 22100e6, 30800e6]
    
    qf = pd.DataFrame(
        {"Total Revenue": revenues, "Net Income": earnings},
        index=["Total Revenue", "Net Income"],
        columns=quarters,
    )
    
    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = qf
    
    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = asyncio.run(tool.execute("AAPL"))
    
    quarterly_data = result.data.quarterly_data
    
    # Q1 2026 QoQ 계산 확인: (143756 - 102466) / 102466 = 0.4030
    assert quarterly_data[0].revenue_qoq is not None
    assert abs(quarterly_data[0].revenue_qoq - 0.4030) < 0.001
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_fundamental.py::test_quarterly_qoq_calculation -v`
Expected: FAIL

- [ ] **Step 5: Implement quarterly data collection and calculation**

Replace the quarterly data parsing section in `_fetch_fundamentals()` (lines 86-104) with:

```python
        # Quarterly data with YoY/QoQ growth rates
        quarterly_data_list = None
        try:
            qf = t.quarterly_financials
            if qf is not None and not qf.empty:
                # Parse up to 8 quarters
                num_quarters = min(len(qf.columns), 8)
                quarters_raw = []
                
                for col in qf.columns[:num_quarters]:
                    period = f"{col.year}-Q{col.quarter}" if hasattr(col, "quarter") else str(col)
                    rev = qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else None
                    earn = qf.loc["Net Income", col] if "Net Income" in qf.index else None
                    
                    quarters_raw.append({
                        "period": period,
                        "revenue": float(rev) if rev is not None else None,
                        "earnings": float(earn) if earn is not None else None,
                    })
                
                # Calculate growth rates for most recent 4 quarters
                quarterly_data_list = []
                for i in range(min(4, len(quarters_raw))):
                    q = quarters_raw[i]
                    
                    # YoY calculation (compare with 4 quarters ago)
                    revenue_yoy = None
                    earnings_yoy = None
                    if len(quarters_raw) >= i + 5:  # Need i+5 quarters for YoY
                        q_yoy = quarters_raw[i + 4]
                        if q["revenue"] is not None and q_yoy["revenue"] is not None and q_yoy["revenue"] > 0:
                            revenue_yoy = (q["revenue"] - q_yoy["revenue"]) / q_yoy["revenue"]
                        if q["earnings"] is not None and q_yoy["earnings"] is not None and q_yoy["earnings"] > 0:
                            earnings_yoy = (q["earnings"] - q_yoy["earnings"]) / q_yoy["earnings"]
                    
                    # QoQ calculation (compare with 1 quarter ago)
                    revenue_qoq = None
                    earnings_qoq = None
                    if len(quarters_raw) >= i + 2:  # Need i+2 quarters for QoQ
                        q_qoq = quarters_raw[i + 1]
                        if q["revenue"] is not None and q_qoq["revenue"] is not None and q_qoq["revenue"] > 0:
                            revenue_qoq = (q["revenue"] - q_qoq["revenue"]) / q_qoq["revenue"]
                        if q["earnings"] is not None and q_qoq["earnings"] is not None and q_qoq["earnings"] > 0:
                            earnings_qoq = (q["earnings"] - q_qoq["earnings"]) / q_qoq["earnings"]
                    
                    quarterly_data_list.append(QuarterlyData(
                        period=q["period"],
                        revenue=q["revenue"],
                        earnings=q["earnings"],
                        revenue_yoy=revenue_yoy,
                        revenue_qoq=revenue_qoq,
                        earnings_yoy=earnings_yoy,
                        earnings_qoq=earnings_qoq,
                    ))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to parse quarterly financials: %s", e)
```

And update the return statement (around line 106-137) to use `quarterly_data=quarterly_data_list` instead of `quarterly_revenue=quarterly_revenue, quarterly_earnings=quarterly_earnings`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/tools/test_fundamental.py::test_quarterly_yoy_calculation tests/tools/test_fundamental.py::test_quarterly_qoq_calculation -v`
Expected: PASS (both tests)

- [ ] **Step 7: Commit**

```bash
git add src/tools/fundamental.py tests/tools/test_fundamental.py
git commit -m "feat(fundamental): add YoY/QoQ growth rate calculations"
```

---

## Task 4: 단위 테스트 - 엣지 케이스

**Files:**
- Test: `tests/tools/test_fundamental.py`

- [ ] **Step 1: Write test for insufficient data (fewer than 5 quarters)**

```python
# tests/tools/test_fundamental.py - append to end of file
def test_quarterly_insufficient_data_for_yoy():
    """5개 미만 분기일 때 YoY는 None, QoQ만 계산"""
    mock_info = {"marketCap": 3e12}
    
    quarters = [
        pd.Period("2026Q1"),
        pd.Period("2025Q4"),
        pd.Period("2025Q3"),
    ]
    
    revenues = [143756e6, 102466e6, 94036e6]
    
    qf = pd.DataFrame(
        {"Total Revenue": revenues},
        index=["Total Revenue"],
        columns=quarters,
    )
    
    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = qf
    
    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = asyncio.run(tool.execute("AAPL"))
    
    quarterly_data = result.data.quarterly_data
    assert quarterly_data is not None
    assert len(quarterly_data) == 3
    
    # YoY는 None (4분기 전 데이터 없음)
    assert quarterly_data[0].revenue_yoy is None
    # QoQ는 계산됨
    assert quarterly_data[0].revenue_qoq is not None
```

- [ ] **Step 2: Write test for zero denominator**

```python
# tests/tools/test_fundamental.py - append to end of file
def test_quarterly_zero_denominator():
    """분모가 0일 때 None 반환"""
    mock_info = {"marketCap": 3e12}
    
    quarters = [
        pd.Period("2026Q1"),
        pd.Period("2025Q4"),
        pd.Period("2025Q3"),
        pd.Period("2025Q2"),
        pd.Period("2025Q1"),
    ]
    
    revenues = [143756e6, 0, 94036e6, 88230e6, 0]  # Q4 2025와 Q1 2025가 0
    
    qf = pd.DataFrame(
        {"Total Revenue": revenues},
        index=["Total Revenue"],
        columns=quarters,
    )
    
    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = qf
    
    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = asyncio.run(tool.execute("AAPL"))
    
    quarterly_data = result.data.quarterly_data
    
    # Q1 2026: QoQ 분모가 0이므로 None
    assert quarterly_data[0].revenue_qoq is None
    # Q1 2026: YoY 분모가 0이므로 None
    assert quarterly_data[0].revenue_yoy is None
```

- [ ] **Step 3: Write test for missing earnings**

```python
# tests/tools/test_fundamental.py - append to end of file
def test_quarterly_missing_earnings():
    """매출만 있고 이익 없을 때 부분 결과"""
    mock_info = {"marketCap": 3e12}
    
    quarters = [
        pd.Period("2026Q1"),
        pd.Period("2025Q4"),
        pd.Period("2025Q3"),
        pd.Period("2025Q2"),
        pd.Period("2025Q1"),
    ]
    
    revenues = [143756e6, 102466e6, 94036e6, 88230e6, 124300e6]
    
    qf = pd.DataFrame(
        {"Total Revenue": revenues},
        index=["Total Revenue"],  # Net Income 없음
        columns=quarters,
    )
    
    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = qf
    
    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = asyncio.run(tool.execute("AAPL"))
    
    quarterly_data = result.data.quarterly_data
    
    # 매출 데이터와 성장률은 있음
    assert quarterly_data[0].revenue is not None
    assert quarterly_data[0].revenue_yoy is not None
    assert quarterly_data[0].revenue_qoq is not None
    
    # 이익 데이터와 성장률은 None
    assert quarterly_data[0].earnings is None
    assert quarterly_data[0].earnings_yoy is None
    assert quarterly_data[0].earnings_qoq is None
```

- [ ] **Step 4: Run all new tests**

Run: `uv run pytest tests/tools/test_fundamental.py::test_quarterly_insufficient_data_for_yoy tests/tools/test_fundamental.py::test_quarterly_zero_denominator tests/tools/test_fundamental.py::test_quarterly_missing_earnings -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/tools/test_fundamental.py
git commit -m "test(fundamental): add edge case tests for quarterly calculations"
```

---

## Task 5: 기존 테스트 업데이트

**Files:**
- Modify: `tests/tools/test_fundamental.py`
- Modify: `tests/llm/test_analyzer.py`

- [ ] **Step 1: Run existing fundamental tests to find failures**

Run: `uv run pytest tests/tools/test_fundamental.py -v`
Expected: Some tests fail due to quarterly_revenue/quarterly_earnings removal

- [ ] **Step 2: Fix test_fundamental_tool_execute**

Find the test that checks `quarterly_revenue` and update it to check `quarterly_data`:

```python
# tests/tools/test_fundamental.py - find and update test_fundamental_tool_execute
# Change the assertions from:
#   assert snapshot.quarterly_revenue is something
# To check quarterly_data instead - or remove if not essential
```

If the test mock has `quarterly_financials.empty = True`, the test should now check:
```python
assert result.data.quarterly_data is None  # Because empty=True
```

- [ ] **Step 3: Run analyzer tests to find failures**

Run: `uv run pytest tests/llm/test_analyzer.py -v`
Expected: May have failures if tests reference quarterly fields

- [ ] **Step 4: Fix analyzer tests if needed**

If `test_generate_fundamental_summary` or other tests mock `FundamentalSnapshot` with `quarterly_revenue`/`quarterly_earnings`, remove those fields from the mock.

- [ ] **Step 5: Run all tests to verify fixes**

Run: `uv run pytest tests/tools/test_fundamental.py tests/llm/test_analyzer.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add tests/tools/test_fundamental.py tests/llm/test_analyzer.py
git commit -m "test: update tests for quarterly_data model change"
```

---

## Task 6: CLI - 분기별 표 렌더링

**Files:**
- Modify: `src/cli/main.py:205-268`

- [ ] **Step 1: Add import for rich Table**

```python
# src/cli/main.py - check if already imported, add if not (around line 10)
from rich.table import Table
```

- [ ] **Step 2: Add helper function for table rendering**

```python
# src/cli/main.py - add before format_deep_dive_output() function (around line 100)
def _render_quarterly_table(quarterly_data: list) -> str:
    """분기별 데이터를 Rich Table로 렌더링"""
    if not quarterly_data or len(quarterly_data) == 0:
        return ""
    
    table = Table(title="분기별 추이 (최근 4분기)", show_header=True, header_style="bold cyan")
    
    # Add columns
    table.add_column("Metric", style="white", no_wrap=True)
    for q in quarterly_data:
        table.add_column(q.period, justify="right")
    
    # Revenue row
    revenue_values = []
    for q in quarterly_data:
        if q.revenue is not None:
            revenue_values.append(f"${q.revenue/1e9:.2f}B")
        else:
            revenue_values.append("N/A")
    table.add_row("Revenue", *revenue_values)
    
    # Revenue YoY row
    yoy_values = []
    for q in quarterly_data:
        if q.revenue_yoy is not None:
            color = "green" if q.revenue_yoy >= 0 else "red"
            yoy_values.append(f"[{color}]{q.revenue_yoy*100:+.2f}%[/{color}]")
        else:
            yoy_values.append("N/A")
    table.add_row("YoY Growth %", *yoy_values)
    
    # Revenue QoQ row
    qoq_values = []
    for q in quarterly_data:
        if q.revenue_qoq is not None:
            color = "green" if q.revenue_qoq >= 0 else "red"
            qoq_values.append(f"[{color}]{q.revenue_qoq*100:+.2f}%[/{color}]")
        else:
            qoq_values.append("N/A")
    table.add_row("QoQ Growth %", *qoq_values)
    
    # Earnings row
    earnings_values = []
    for q in quarterly_data:
        if q.earnings is not None:
            earnings_values.append(f"${q.earnings/1e9:.2f}B")
        else:
            earnings_values.append("N/A")
    table.add_row("Earnings", *earnings_values)
    
    # Earnings YoY row
    yoy_e_values = []
    for q in quarterly_data:
        if q.earnings_yoy is not None:
            color = "green" if q.earnings_yoy >= 0 else "red"
            yoy_e_values.append(f"[{color}]{q.earnings_yoy*100:+.2f}%[/{color}]")
        else:
            yoy_e_values.append("N/A")
    table.add_row("YoY Growth %", *yoy_e_values)
    
    # Earnings QoQ row
    qoq_e_values = []
    for q in quarterly_data:
        if q.earnings_qoq is not None:
            color = "green" if q.earnings_qoq >= 0 else "red"
            qoq_e_values.append(f"[{color}]{q.earnings_qoq*100:+.2f}%[/{color}]")
        else:
            qoq_e_values.append("N/A")
    table.add_row("QoQ Growth %", *qoq_e_values)
    
    from io import StringIO
    from rich.console import Console
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True)
    console.print(table)
    return buffer.getvalue()
```

- [ ] **Step 3: Insert table in format_deep_dive_output**

Find the section after valuation metrics (around line 220, after EV/EBITDA) and before profitability metrics (ROE), insert:

```python
        # Quarterly trends table
        if fundamental.quarterly_data is not None:
            output += "\n"
            output += _render_quarterly_table(fundamental.quarterly_data)
            output += "\n"
```

- [ ] **Step 4: Test the CLI output manually**

Run: `uv run jarvis analyze AAPL --provider openai`
Expected: Should see a table with quarterly data after valuation metrics

- [ ] **Step 5: Commit**

```bash
git add src/cli/main.py
git commit -m "feat(cli): add quarterly trends table rendering"
```

---

## Task 7: CLI - 분기별 실적 리스트 섹션

**Files:**
- Modify: `src/cli/main.py:205-268`

- [ ] **Step 1: Add helper function for growth rate formatting**

```python
# src/cli/main.py - add before format_deep_dive_output() function
def _format_growth_rate(value: float | None) -> str:
    """성장률을 포맷팅 (양수면 +, 음수면 - 표시)"""
    if value is None:
        return "N/A"
    return f"{value*100:+.2f}%"
```

- [ ] **Step 2: Add quarterly performance section**

Find the location between "Key Metrics" and "LLM Analysis" sections (around line 250), insert:

```python
        # Quarterly Performance section
        if fundamental.quarterly_data is not None and len(fundamental.quarterly_data) > 0:
            output += "### 분기별 실적\n\n"
            
            # Revenue trends
            output += "**매출 추이:**\n"
            for q in fundamental.quarterly_data:
                if q.revenue is not None:
                    revenue_str = f"${q.revenue/1e9:.2f}B"
                    yoy_str = _format_growth_rate(q.revenue_yoy)
                    qoq_str = _format_growth_rate(q.revenue_qoq)
                    output += f"• {q.period}: {revenue_str} (YoY {yoy_str}, QoQ {qoq_str})\n"
            
            output += "\n"
            
            # Earnings trends
            output += "**이익 추이:**\n"
            for q in fundamental.quarterly_data:
                if q.earnings is not None:
                    earnings_str = f"${q.earnings/1e9:.2f}B"
                    yoy_str = _format_growth_rate(q.earnings_yoy)
                    qoq_str = _format_growth_rate(q.earnings_qoq)
                    output += f"• {q.period}: {earnings_str} (YoY {yoy_str}, QoQ {qoq_str})\n"
            
            output += "\n"
```

- [ ] **Step 3: Test the CLI output manually**

Run: `uv run jarvis analyze AAPL --provider openai`
Expected: Should see "분기별 실적" section with bullet lists

- [ ] **Step 4: Commit**

```bash
git add src/cli/main.py
git commit -m "feat(cli): add quarterly performance list section"
```

---

## Task 8: 통합 테스트

**Files:**
- Modify: `tests/integration/test_e2e_plan4.py`

- [ ] **Step 1: Add integration test**

```python
# tests/integration/test_e2e_plan4.py - append to end of file
@pytest.mark.integration
def test_analyze_shows_quarterly_trends():
    """CLI에서 분기별 표와 리스트가 표시되는지 검증"""
    result = runner.invoke(app, ["analyze", "AAPL", "--provider", "openai"])
    
    # 표 확인
    assert "분기별 추이" in result.stdout
    assert "YoY Growth %" in result.stdout
    
    # 리스트 확인
    assert "분기별 실적" in result.stdout
    assert "매출 추이:" in result.stdout
    assert "이익 추이:" in result.stdout
    
    # 성장률 포맷 확인 (+ 또는 - 기호)
    import re
    assert re.search(r"YoY [+-]\d+\.\d+%", result.stdout) is not None
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_e2e_plan4.py::test_analyze_shows_quarterly_trends -v`
Expected: PASS (requires API keys)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_e2e_plan4.py
git commit -m "test(integration): add quarterly trends CLI verification"
```

---

## Task 9: 전체 테스트 및 수동 검증

**Files:**
- No file changes

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ --ignore=tests/integration -v`
Expected: All tests PASS

- [ ] **Step 2: Manual test - US stock with full data**

Run: `uv run jarvis analyze AAPL --provider openai`
Verify:
- Table shows 4 quarters
- YoY and QoQ percentages are present
- Colors (green/red) are correct
- List section shows revenue and earnings separately

- [ ] **Step 3: Manual test - Newly listed stock**

Run: `uv run jarvis analyze COIN --provider openai`
Verify:
- Handles fewer than 8 quarters gracefully
- YoY may show N/A for some quarters
- No crashes

- [ ] **Step 4: Manual test - Korean stock**

Run: `uv run jarvis analyze 005930.KS --provider openai`
Verify:
- Works with Korean ticker
- Data displays correctly

- [ ] **Step 5: Final commit and tag**

```bash
git add -A
git commit -m "feat(fundamental): add YoY/QoQ quarterly growth rates and trends

- Add QuarterlyData model with growth rate fields
- Modify FundamentalSnapshot to use quarterly_data
- Collect 8 quarters and calculate YoY/QoQ growth rates
- Add Rich table for quarterly trends in CLI
- Add bullet list section for quarterly performance
- Update existing tests for model changes
- Add 6 unit tests for calculations and edge cases
- Add integration test for CLI output
"
```

---

## Spec Coverage Check

**Spec Section → Implementation Task:**
- ✅ QuarterlyData model → Task 1
- ✅ FundamentalSnapshot modification → Task 2
- ✅ 8 quarters collection → Task 3
- ✅ YoY calculation → Task 3
- ✅ QoQ calculation → Task 3
- ✅ CLI table rendering → Task 6
- ✅ CLI list section → Task 7
- ✅ Unit tests (6개) → Task 3, 4
- ✅ Integration test → Task 8
- ✅ Existing test updates → Task 5
- ✅ Error handling → Task 4 (edge cases)
- ✅ Manual testing → Task 9

All spec requirements covered.
