# Sector-Specific Fundamental Metrics Design

**Date:** 2026-04-11
**Status:** Draft
**Author:** Claude Code

## Overview

Add sector-specific prioritization and highlighting of fundamental metrics in CLI output and LLM analysis. Different sectors emphasize different metrics (e.g., Technology focuses on PEG/PSR, Financials on ROE/P/B), so users should see the most relevant metrics first with visual emphasis.

## Goals

1. Display sector-appropriate metrics at the top of fundamental analysis output
2. Highlight priority metrics with ⭐ emoji and bold formatting
3. Inform LLM which metrics are most important for each sector
4. Support 7-10 major sectors with customized metric priorities
5. Maintain all existing metrics in output (reorder only, no removal)

## Non-Goals

- Sector average/benchmark comparisons (data collection complexity)
- Threshold-based automatic valuations (LLM handles this)
- Runtime configurable metrics via YAML (hard-coded is sufficient)
- Custom user-defined sectors

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│  yfinance API → FundamentalSnapshot (all metrics)       │
└────────────────────┬────────────────────────────────────┘
                     ↓
         ┌───────────────────────────┐
         │   SectorMetrics Class     │
         │  (sector identification   │
         │   + priority metrics)     │
         └───────────┬───────────────┘
                     ↓
        ┌────────────┴────────────┐
        ↓                         ↓
┌───────────────┐        ┌────────────────┐
│  CLI Output   │        │  LLM Prompt    │
│ (⭐ emphasis) │        │ ([핵심] tags)  │
└───────────────┘        └────────────────┘
```

### New Module: `src/utils/sector_metrics.py`

Defines sector-to-metrics mappings and provides utility functions for:
- Identifying sector from yfinance sector string
- Retrieving priority metrics for a given sector
- Sorting metrics (priority first, then alphabetical)

### Modified Module: `src/cli/main.py`

Changes to `format_deep_dive_output()`:
- Query `SectorMetrics` for priority metrics
- Render priority metrics first with ⭐ emoji
- Render remaining metrics after priority section

### Modified Module: `src/llm/analyzer.py`

Changes to `generate_fundamental_summary()`:
- Mark priority metrics with [핵심] prefix in prompt
- Include all metrics (no filtering)
- LLM uses [핵심] tags to focus analysis

## Data Model

### Sector-to-Metrics Mapping

**Supported Sectors (10):**

1. **Technology**
   - Priority: PEG Ratio, PSR, Revenue Growth, Earnings Growth, Operating Margin, FCF Yield, Debt/Equity

2. **Financials**
   - Priority: ROE, ROA, P/B Ratio, Debt/Equity, Earnings Growth

3. **Consumer Cyclical**
   - Priority: P/E Ratio, Revenue Growth, Gross Margin, Debt/Equity, Free Cash Flow

4. **Consumer Defensive**
   - Priority: Dividend Yield, P/E Ratio, Gross Margin, ROE, Payout Ratio

5. **Healthcare**
   - Priority: PEG Ratio, Revenue Growth, Operating Margin, ROE, FCF Yield

6. **Industrials**
   - Priority: P/E Ratio, ROE, Debt/Equity, Free Cash Flow, Operating Margin

7. **Energy**
   - Priority: P/B Ratio, Debt/Equity, FCF Yield, Operating Margin, Dividend Yield

8. **Real Estate**
   - Priority: P/B Ratio, Dividend Yield, Debt/Equity, Free Cash Flow

9. **Utilities**
   - Priority: Dividend Yield, P/E Ratio, Debt/Equity, Payout Ratio

10. **Communication Services**
    - Priority: P/E Ratio, EV/EBITDA, Revenue Growth, FCF Yield, Operating Margin

**Default (fallback):**
- Priority: P/E Ratio, ROE, Revenue Growth, Debt/Equity, Free Cash Flow

### Field Name Mapping

Metric internal names to display names:
```python
{
    "pe_ratio": "P/E Ratio",
    "forward_pe": "Forward P/E",
    "peg_ratio": "PEG Ratio",
    "pb_ratio": "P/B Ratio",
    "ps_ratio": "PSR",
    "ev_ebitda": "EV/EBITDA",
    "roe": "ROE",
    "roa": "ROA",
    "revenue_growth": "매출 성장률",
    "earnings_growth": "이익 성장률",
    "gross_margin": "매출총이익률",
    "operating_margin": "영업이익률",
    "profit_margin": "순이익률",
    "debt_to_equity": "Debt/Equity",
    "free_cash_flow": "Free Cash Flow",
    "operating_cash_flow": "Operating Cash Flow",
    "fcf_yield": "FCF Yield",
    "dividend_yield": "배당 수익률",
    "payout_ratio": "배당 성향",
    "current_ratio": "유동비율",
    "quick_ratio": "당좌비율",
}
```

## Implementation Details

### 1. SectorMetrics Class

**File:** `src/utils/sector_metrics.py`

```python
class SectorMetrics:
    """Sector-specific priority metrics definitions."""
    
    TECHNOLOGY = [
        "peg_ratio", "ps_ratio", "revenue_growth", "earnings_growth",
        "operating_margin", "fcf_yield", "debt_to_equity"
    ]
    
    FINANCIALS = [
        "roe", "roa", "pb_ratio", "debt_to_equity", "earnings_growth"
    ]
    
    # ... (other sectors)
    
    DEFAULT = [
        "pe_ratio", "roe", "revenue_growth", "debt_to_equity", "free_cash_flow"
    ]
    
    @classmethod
    def get_priority_metrics(cls, sector: str | None) -> list[str]:
        """Get priority metrics for a given sector.
        
        Uses fuzzy matching to handle yfinance sector name variations.
        Returns DEFAULT if sector is None or not recognized.
        """
        if not sector:
            return cls.DEFAULT
        
        sector_lower = sector.lower()
        
        if "technolog" in sector_lower:
            return cls.TECHNOLOGY
        elif "financial" in sector_lower:
            return cls.FINANCIALS
        elif "consumer cyclical" in sector_lower or "consumer discretionary" in sector_lower:
            return cls.CONSUMER_CYCLICAL
        elif "consumer defensive" in sector_lower or "consumer staples" in sector_lower:
            return cls.CONSUMER_DEFENSIVE
        elif "healthcare" in sector_lower or "health care" in sector_lower:
            return cls.HEALTHCARE
        elif "industrial" in sector_lower:
            return cls.INDUSTRIALS
        elif "energy" in sector_lower:
            return cls.ENERGY
        elif "real estate" in sector_lower:
            return cls.REAL_ESTATE
        elif "utilit" in sector_lower:
            return cls.UTILITIES
        elif "communication" in sector_lower:
            return cls.COMMUNICATION_SERVICES
        
        return cls.DEFAULT
```

### 2. CLI Rendering Changes

**File:** `src/cli/main.py`

**Helper Function:**
```python
def _format_metric_value(metric_name: str, value: float) -> str:
    """Format metric value based on type."""
    if metric_name in ["revenue_growth", "earnings_growth", "gross_margin", 
                       "operating_margin", "profit_margin", "fcf_yield", 
                       "dividend_yield", "roe", "roa"]:
        return f"{value*100:.1f}%"
    elif metric_name in ["free_cash_flow", "operating_cash_flow"]:
        return f"${value/1e9:.1f}B"
    elif metric_name == "payout_ratio":
        return f"{value*100:.1f}%"
    else:
        return f"{value:.1f}" if abs(value) > 10 else f"{value:.2f}"
```

**Modified format_deep_dive_output():**
```python
from src.utils.sector_metrics import SectorMetrics

# In fundamental section (after Sector/Industry line):
priority_metrics = SectorMetrics.get_priority_metrics(fundamental.sector)

# Render priority metrics first with ⭐
for metric_name in priority_metrics:
    value = getattr(fundamental, metric_name, None)
    if value is not None:
        display_name = METRIC_DISPLAY_NAMES.get(metric_name, metric_name)
        formatted = _format_metric_value(metric_name, value)
        output += f"⭐ **{display_name}**: {formatted}\n"

output += "\n"  # Separator

# Render remaining metrics
all_metric_names = [
    "market_cap", "pe_ratio", "forward_pe", "peg_ratio", "pb_ratio", 
    "ps_ratio", "ev_ebitda", "roe", "roa", "gross_margin", 
    "operating_margin", "profit_margin", "revenue_growth", 
    "earnings_growth", "debt_to_equity", "current_ratio", 
    "quick_ratio", "free_cash_flow", "operating_cash_flow", 
    "fcf_yield", "dividend_yield", "payout_ratio"
]

remaining_metrics = [m for m in all_metric_names if m not in priority_metrics]

for metric_name in remaining_metrics:
    value = getattr(fundamental, metric_name, None)
    if value is not None:
        display_name = METRIC_DISPLAY_NAMES.get(metric_name, metric_name)
        formatted = _format_metric_value(metric_name, value)
        output += f"- **{display_name}**: {formatted}\n"
```

### 3. LLM Prompt Changes

**File:** `src/llm/analyzer.py`

**Modified generate_fundamental_summary():**
```python
from src.utils.sector_metrics import SectorMetrics

async def generate_fundamental_summary(
    input_data: FundamentalSummaryInput,
    llm: BaseChatModel,
) -> FundamentalSummaryOutput:
    priority_metrics = SectorMetrics.get_priority_metrics(input_data.sector)
    
    # Build metrics text with [핵심] prefix for priority metrics
    metrics_text = []
    
    all_metrics = [
        ("pe_ratio", "P/E"),
        ("forward_pe", "Forward P/E"),
        ("peg_ratio", "PEG"),
        ("pb_ratio", "P/B"),
        ("ps_ratio", "PSR"),
        ("ev_ebitda", "EV/EBITDA"),
        ("roe", "ROE"),
        ("roa", "ROA"),
        ("revenue_growth", "매출 성장률"),
        ("earnings_growth", "이익 성장률"),
        ("gross_margin", "매출총이익률"),
        ("operating_margin", "영업이익률"),
        ("profit_margin", "순이익률"),
        ("debt_to_equity", "D/E"),
        ("free_cash_flow", "FCF"),
        ("fcf_yield", "FCF Yield"),
        ("dividend_yield", "배당 수익률"),
        ("payout_ratio", "배당 성향"),
    ]
    
    for metric_name, display_name in all_metrics:
        value = getattr(input_data, metric_name, None)
        if value is not None:
            prefix = "[핵심] " if metric_name in priority_metrics else ""
            formatted = _format_metric_value(metric_name, value)
            metrics_text.append(f"{prefix}{display_name}: {formatted}")
    
    if not metrics_text:
        metrics_text.append("No financial metrics available")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a fundamental analysis expert."),
        ("user", """Analyze the following fundamental data for {ticker}:

**Sector**: {sector} / {industry}

**Key Metrics** (핵심 지표는 [핵심]으로 표시):
{metrics_text}

Provide summary with:
- summary: overall fundamental assessment in Korean
- strengths: list of 2-3 key strengths (핵심 지표를 중심으로)
- weaknesses: list of 2-3 key weaknesses
- valuation_assessment: "저평가", "적정", or "고평가"
- confidence: 0.0-1.0""")
    ])
    
    chain = prompt | llm.with_structured_output(FundamentalSummaryOutput)
    
    result = await chain.ainvoke({
        "ticker": input_data.ticker,
        "sector": input_data.sector or "N/A",
        "industry": input_data.industry or "N/A",
        "metrics_text": "\n".join(f"- {m}" for m in metrics_text),
    })
    
    return result
```

## Example Output

### CLI Output (NVDA - Technology)

**Before:**
```
Sector/Industry: Technology / Semiconductors

- 시가총액: $4572.99B
- P/E Ratio: 38.5
- Forward P/E: 16.9
- EV/EBITDA: 33.2
- ROE: 101.5%
...
```

**After:**
```
Sector/Industry: Technology / Semiconductors

⭐ **PEG Ratio**: 2.1
⭐ **PSR**: 8.5
⭐ **매출 성장률**: 73.2%
⭐ **이익 성장률**: 95.6%
⭐ **영업이익률**: 65.0%
⭐ **FCF Yield**: 1.3%
⭐ **Debt/Equity**: 7.3

- **시가총액**: $4572.99B
- **P/E Ratio**: 38.5
- **Forward P/E**: 16.9
- **EV/EBITDA**: 33.2
- **ROE**: 101.5%
- **ROA**: 51.2%
...
```

### LLM Prompt (NVDA - Technology)

```
**Sector**: Technology / Semiconductors

**Key Metrics** (핵심 지표는 [핵심]으로 표시):
- [핵심] PEG: 2.1
- [핵심] PSR: 8.5
- [핵심] 매출 성장률: 73.2%
- [핵심] 이익 성장률: 95.6%
- [핵심] 영업이익률: 65.0%
- [핵심] FCF Yield: 1.3%
- [핵심] D/E: 7.3
- P/E: 38.5
- Forward P/E: 16.9
- ROE: 101.5%
- ROA: 51.2%
- 매출총이익률: 71.1%
- 순이익률: 55.6%
...
```

## Testing Strategy

### Unit Tests

**File:** `tests/utils/test_sector_metrics.py`

Tests for `SectorMetrics` class:
1. `test_get_priority_metrics_technology()` - Verify Technology sector mapping
2. `test_get_priority_metrics_financials()` - Verify Financials sector mapping
3. `test_get_priority_metrics_fuzzy_match()` - Test "Technology" vs "Information Technology"
4. `test_get_priority_metrics_none()` - Verify DEFAULT returned for None
5. `test_get_priority_metrics_unknown()` - Verify DEFAULT for unrecognized sector
6. `test_all_sectors_covered()` - Verify all 10 sectors have mappings

**File:** `tests/cli/test_main.py`

Tests for CLI rendering:
1. `test_format_metric_value_percent()` - Test percentage formatting
2. `test_format_metric_value_dollar()` - Test dollar amount formatting
3. `test_cli_priority_metrics_order()` - Verify priority metrics appear first
4. `test_cli_priority_metrics_emoji()` - Verify ⭐ emoji present

### Integration Tests

**File:** `tests/integration/test_e2e_plan4.py`

Integration test:
```python
@pytest.mark.integration
def test_analyze_shows_sector_priority_metrics():
    """Verify CLI shows sector-specific priority metrics with emphasis"""
    result = runner.invoke(app, ["analyze", "NVDA", "--provider", "openai"])
    
    # Technology sector should show PEG and PSR with ⭐
    assert "⭐ **PEG Ratio**" in result.stdout
    assert "⭐ **PSR**" in result.stdout
    
    # Non-priority metrics should not have ⭐
    assert "⭐ **P/E Ratio**" not in result.stdout
```

### Manual Testing

**Test Cases:**
1. Technology stock: `uv run jarvis analyze NVDA --provider openai`
   - Verify PEG, PSR appear first with ⭐
2. Financial stock: `uv run jarvis analyze JPM --provider openai`
   - Verify ROE, P/B appear first with ⭐
3. Unknown sector: Mock ticker with sector="Unknown"
   - Verify DEFAULT metrics used
4. LLM response: Check that strengths mention [핵심] metrics

## Error Handling

**Scenarios:**

1. **Sector is None**: Use DEFAULT metrics
2. **Unrecognized sector string**: Use DEFAULT metrics
3. **Metric value is None**: Skip in rendering (existing behavior)
4. **All priority metrics are None**: Show remaining metrics only

## Dependencies

- No new external dependencies
- Uses existing `yfinance` for sector data
- Uses existing `pydantic` for type safety

## Risks and Mitigation

**Risk 1: yfinance sector names vary**
- Mitigation: Fuzzy matching with substring checks
- Impact: Low - DEFAULT fallback ensures functionality

**Risk 2: Sector classifications change over time**
- Mitigation: Easy to update mappings in single file
- Impact: Low - changes are infrequent

**Risk 3: Breaking existing CLI output**
- Mitigation: Only reordering, no removal of metrics
- Impact: Low - users still see all information

**Risk 4: LLM misinterprets [핵심] tags**
- Mitigation: Clear prompt instructions + LLM is capable
- Impact: Low - worst case LLM ignores tags (no worse than current)

## Future Enhancements (Out of Scope)

- Sector average/benchmark comparisons
- User-customizable metric priorities via config
- Per-industry (not just sector) granularity
- Automatic valuation thresholds per sector
- Historical sector rotation analysis

## Implementation Checklist

- [ ] Create `src/utils/sector_metrics.py` with SectorMetrics class
- [ ] Add all 10 sector metric mappings + DEFAULT
- [ ] Implement `get_priority_metrics()` with fuzzy matching
- [ ] Create METRIC_DISPLAY_NAMES mapping in CLI
- [ ] Add `_format_metric_value()` helper function
- [ ] Modify `format_deep_dive_output()` to render priority metrics first
- [ ] Add ⭐ emoji to priority metrics
- [ ] Modify `generate_fundamental_summary()` to add [핵심] tags
- [ ] Update LLM prompt to mention [핵심] tags
- [ ] Write 6 unit tests for SectorMetrics
- [ ] Write 4 unit tests for CLI formatting
- [ ] Write 1 integration test for E2E verification
- [ ] Manually test with NVDA (Technology) and JPM (Financials)
- [ ] Update documentation if needed
