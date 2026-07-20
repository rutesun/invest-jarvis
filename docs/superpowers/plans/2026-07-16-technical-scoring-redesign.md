# Technical Scoring Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 technical component 단순합을 보존하면서 `MarketContext`, `ScoreAggregator`, `technical_verdict`, 최근 5거래일 `score_history`를 추가한다.

**Architecture:** `src/tools/technical`에 context builder와 aggregator를 추가하고, `TechnicalScorer`가 기존 component 결과를 `component_raw_total`로 보존한 뒤 adjusted score와 verdict를 계산한다. `quick_check`, `deep_dive`, `brief`, `analyze_decision`은 새 필드를 소비하되 기존 `total_score` fallback을 유지한다.

**Tech Stack:** Python 3.12, Pydantic v2, pandas, pandas-ta, pytest, pytest-asyncio, Typer/Rich CLI.

## Global Constraints

- Package manager는 항상 `uv`를 사용한다.
- raw OHLCV 별도 score는 만들지 않는다.
- raw OHLCV는 `MarketContext` 상태로만 쓴다.
- `total_score`는 1차 구현에서 기존 component 단순합 계약을 유지한다.
- `component_raw_total`은 component score 합계와 같아야 한다.
- `adjusted_score`는 `ScoreAggregator` rule output이며 LLM이 재판단하지 않는다.
- Aggregator는 `signals` 문자열을 파싱하지 않고 `signal_metadata`를 사용한다.
- `technical_verdict`는 technical-only hint이며 playbook final verdict가 아니다.
- `score_history`는 최근 5거래일 기본값을 사용하고 각 날짜까지의 OHLCV만 참조한다.
- 외부 API raw 응답을 fixture로 저장하는 경우 테스트는 fixture만 사용하고 네트워크를 호출하지 않는다.

---

## File Structure

- Modify: `src/tools/technical/models.py`
  - `ComponentSignal`, `MarketContext`, `AggregationTraceEntry`, `TechnicalVerdict`, `ScoreHistoryPoint` 모델 추가
  - `ComponentResult.signal_metadata` 추가
  - `TechnicalResult`에 `component_raw_total`, `adjusted_score`, `technical_verdict`, `score_history`, `score_history_warning`, `aggregation_trace` 추가
- Create: `src/tools/technical/context.py`
  - OHLCV/indicator dataframe에서 `MarketContext`를 계산
- Create: `src/tools/technical/aggregator.py`
  - component score와 metadata를 context에 맞게 조정하고 verdict를 생성
- Modify: `src/tools/technical/components/*.py`
  - component별 `signal_metadata` 생성
- Modify: `src/tools/technical/scorer.py`
  - context builder, aggregator, score history를 연결
- Modify: `src/pipelines/quick_check.py`
  - adjusted score, verdict reason, 5거래일 trend 출력
- Modify: `src/llm/models.py`, `src/llm/analyzer.py`, `src/pipelines/deep_dive.py`
  - LLM technical summary 입력에 verdict와 score history를 전달
- Modify: `src/pipelines/analyze_decision.py`
  - `technical_verdict`가 있으면 factor assessment에 우선 반영
- Modify: `src/tools/brief/models.py`, `src/tools/brief/render.py`, `src/pipelines/brief.py`
  - brief 항목에 technical verdict와 score trend를 노출
- Create/Modify tests:
  - `tests/tools/technical/test_scoring_models.py`
  - `tests/tools/technical/test_market_context.py`
  - `tests/tools/technical/test_score_aggregator.py`
  - `tests/tools/technical/test_scorer.py`
  - `tests/tools/technical/test_scoring_regression.py`
  - `tests/pipelines/test_quick_check.py`
  - `tests/pipelines/test_analyze_decision.py`
  - `tests/pipelines/test_deep_dive.py`
  - `tests/pipelines/test_brief.py`
  - `tests/llm/test_analyzer.py`
  - `tests/llm/test_brief_narratives.py`
- Create fixtures:
  - `tests/fixtures/technical/scoring/panw_2026-03-01_2026-05-14.csv`
  - `tests/fixtures/technical/scoring/be_2026-06-01_2026-07-15.csv`
  - `tests/fixtures/technical/scoring/005930_ks_2026-06-01_2026-07-16.csv`
- Modify docs:
  - `docs/FEATURES.md`
  - `docs/changes/technical-scoring-redesign.md`
  - `docs/changes/INDEX.md`

---

### Task 1: Scoring Contract Models

**Files:**
- Modify: `src/tools/technical/models.py`
- Create: `tests/tools/technical/test_scoring_models.py`

**Interfaces:**
- Consumes: existing `ComponentResult`, `TechnicalResult`
- Produces:
  - `ComponentSignal`
  - `MarketContext`
  - `AggregationTraceEntry`
  - `TechnicalVerdict`
  - `ScoreHistoryPoint`
  - `ComponentResult.signal_metadata: list[ComponentSignal]`
  - `TechnicalResult.component_raw_total: int`
  - `TechnicalResult.adjusted_score: int`
  - `TechnicalResult.technical_verdict: TechnicalVerdict | None`
  - `TechnicalResult.score_history: list[ScoreHistoryPoint]`

- [ ] **Step 1: Write failing model tests**

```python
# tests/tools/technical/test_scoring_models.py
from datetime import UTC, datetime

from src.tools.technical.models import (
    AggregationTraceEntry,
    ComponentResult,
    ComponentSignal,
    IndicatorSnapshot,
    ScoreHistoryPoint,
    TechnicalResult,
    TechnicalVerdict,
)


def test_component_result_accepts_signal_metadata():
    result = ComponentResult(
        signals=["cRSI Hook Up"],
        evidence=["cRSI 하단밴드 상향 돌파"],
        metrics={"crsi": 21.5},
        score=20,
        signal_metadata=[
            ComponentSignal(
                signal_type="pullback",
                bias="bullish",
                intent="entry",
                severity="medium",
                entry_eligible=True,
                source="crsi",
                reason="상승 추세에서 pullback entry 후보",
            )
        ],
    )

    assert result.signal_metadata[0].signal_type == "pullback"
    assert result.signal_metadata[0].entry_eligible is True


def test_technical_result_defaults_keep_total_score_contract():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(UTC),
        snapshot=snapshot,
        components={},
        total_score=65,
    )

    assert result.total_score == 65
    assert result.component_raw_total == 65
    assert result.adjusted_score == 65
    assert result.technical_verdict is None
    assert result.score_history == []


def test_technical_result_accepts_adjusted_contract_fields():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)
    verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["추세는 유지"],
        cautions=["단기 과열"],
        invalidation_level=92.5,
        score_trend_summary="최근 5거래일 adjusted score가 70에서 62로 둔화",
    )

    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(UTC),
        snapshot=snapshot,
        components={},
        total_score=80,
        component_raw_total=80,
        adjusted_score=62,
        technical_verdict=verdict,
        score_history=[
            ScoreHistoryPoint(
                date="2026-07-16",
                close=100.0,
                component_raw_total=80,
                adjusted_score=62,
                verdict_action="hold",
                one_line_reason="과열로 신규 진입 제한",
            )
        ],
        aggregation_trace=[
            AggregationTraceEntry(
                rule="overextended_penalty",
                before=80,
                after=62,
                reason="RSI 과열",
            )
        ],
    )

    assert result.adjusted_score == 62
    assert result.technical_verdict.action == "hold"
    assert result.score_history[0].verdict_action == "hold"
    assert result.aggregation_trace[0].rule == "overextended_penalty"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_scoring_models.py -v`

Expected: FAIL with import errors for the new model names.

- [ ] **Step 3: Add model definitions**

Add these imports and models in `src/tools/technical/models.py` near `ComponentResult`.

```python
from typing import Literal, Self
```

```python
SignalType = Literal[
    "breakout",
    "pullback",
    "reversal",
    "breakdown",
    "overextension",
    "support",
    "resistance",
    "trend",
    "volume_confirmation",
]
SignalBias = Literal["bullish", "bearish", "neutral"]
SignalIntent = Literal["entry", "hold", "risk", "watch"]
SignalSeverity = Literal["low", "medium", "high"]
VerdictAction = Literal["buy", "add", "hold", "watch", "reduce", "avoid"]
VerdictConfidence = Literal["low", "medium", "high"]


class ComponentSignal(BaseModel):
    """Structured signal metadata consumed by ScoreAggregator."""

    signal_type: SignalType
    bias: SignalBias
    intent: SignalIntent
    severity: SignalSeverity = "medium"
    entry_eligible: bool = False
    source: str | None = None
    reason: str | None = None


class MarketContext(BaseModel):
    """Derived OHLCV state used for score aggregation."""

    close: float
    close_above_sma20: bool = False
    close_above_sma50: bool = False
    close_above_sma150: bool = False
    close_above_sma200: bool = False
    sma20_above_sma50: bool = False
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_10d: float | None = None
    distance_from_20d_high_pct: float | None = None
    distance_from_sma20_pct: float | None = None
    distance_from_sma50_pct: float | None = None
    volume_ratio_20d: float | None = None
    rsi: float | None = None
    atr_pct: float | None = None
    supertrend_direction: int | None = None
    supertrend_sell_transition: bool = False
    is_overextended: bool = False
    is_breakdown: bool = False
    is_uptrend: bool = False
    is_downtrend: bool = False
    nearest_support: float | None = None


class AggregationTraceEntry(BaseModel):
    """One score adjustment made by ScoreAggregator."""

    rule: str
    before: int
    after: int
    reason: str


class TechnicalVerdict(BaseModel):
    """Technical-only action hint. Playbook remains the final decision layer."""

    action: VerdictAction
    entry_mode: str
    confidence: VerdictConfidence
    new_entry_allowed: bool
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    invalidation_level: float | None = None
    score_trend_summary: str | None = None


class ScoreHistoryPoint(BaseModel):
    """Recent per-day score and verdict summary."""

    date: str
    close: float
    component_raw_total: int
    adjusted_score: int
    verdict_action: VerdictAction
    one_line_reason: str
```

Update `ComponentResult`:

```python
class ComponentResult(BaseModel):
    """Result from a technical analysis component."""

    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]
    score: int
    signal_metadata: list[ComponentSignal] = Field(default_factory=list)
```

Update `TechnicalResult`:

```python
class TechnicalResult(BaseModel):
    """Complete technical analysis result."""

    ticker: str | None
    timestamp: datetime
    snapshot: IndicatorSnapshot
    components: dict[str, dict]
    total_score: int = 0
    component_raw_total: int | None = None
    adjusted_score: int | None = None
    technical_verdict: TechnicalVerdict | None = None
    score_history: list[ScoreHistoryPoint] = Field(default_factory=list)
    score_history_warning: str | None = None
    aggregation_trace: list[AggregationTraceEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _backfill_score_contract_fields(self) -> Self:
        if self.component_raw_total is None:
            self.component_raw_total = self.total_score
        if self.adjusted_score is None:
            self.adjusted_score = self.total_score
        return self
```

Keep the existing `raw_dataframe`, legacy fields, `Config`, and `from_analysis` method under the new fields.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_scoring_models.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/models.py tests/tools/technical/test_scoring_models.py
git commit -m "feat: add technical scoring contract models"
```

---

### Task 2: MarketContext Builder

**Files:**
- Create: `src/tools/technical/context.py`
- Create: `tests/tools/technical/test_market_context.py`

**Interfaces:**
- Consumes: indicator-enriched `pd.DataFrame`
- Produces: `build_market_context(df: pd.DataFrame) -> MarketContext`

- [ ] **Step 1: Write failing context tests**

```python
# tests/tools/technical/test_market_context.py
import pandas as pd

from src.tools.technical.context import build_market_context


def _context_df(close_values: list[float]) -> pd.DataFrame:
    rows = []
    for idx, close in enumerate(close_values):
        rows.append(
            {
                "Open": close - 0.5,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 if idx < len(close_values) - 1 else 1_800_000,
                "SMA_20": close - 2.0,
                "SMA_50": close - 5.0,
                "SMA_150": close - 10.0,
                "SMA_200": close - 12.0,
                "Vol_SMA_20": 1_000_000,
                "RSI": 62.0,
                "ATR": 2.0,
                "SuperTrend_Dir": 1,
            }
        )
    return pd.DataFrame(rows)


def test_build_market_context_uptrend_state():
    df = _context_df([100 + i for i in range(30)])

    context = build_market_context(df)

    assert context.close == 129.0
    assert context.close_above_sma20 is True
    assert context.close_above_sma50 is True
    assert context.sma20_above_sma50 is True
    assert context.is_uptrend is True
    assert context.is_downtrend is False
    assert context.volume_ratio_20d == 1.8


def test_build_market_context_overextension_state():
    df = _context_df([100 + i for i in range(29)] + [150])
    df.loc[df.index[-1], "RSI"] = 78.0

    context = build_market_context(df)

    assert context.ret_1d is not None
    assert context.ret_1d >= 8.0
    assert context.is_overextended is True


def test_build_market_context_breakdown_state():
    df = _context_df([120 - i for i in range(30)])
    last = df.index[-1]
    prev = df.index[-2]
    df.loc[last, "Close"] = 80.0
    df.loc[last, "Low"] = 79.0
    df.loc[last, "SMA_20"] = 95.0
    df.loc[last, "SMA_50"] = 100.0
    df.loc[last, "SuperTrend_Dir"] = -1
    df.loc[prev, "SuperTrend_Dir"] = 1
    df.loc[last, "Volume"] = 2_000_000

    context = build_market_context(df)

    assert context.is_breakdown is True
    assert context.is_downtrend is True
    assert context.supertrend_sell_transition is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_market_context.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.technical.context'`.

- [ ] **Step 3: Implement context builder**

Create `src/tools/technical/context.py`.

```python
import pandas as pd

from src.tools.technical.models import MarketContext


def _safe_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _ret_pct(df: pd.DataFrame, days: int) -> float | None:
    if len(df) <= days:
        return None
    current = _safe_float(df.iloc[-1].get("Close"))
    previous = _safe_float(df.iloc[-days - 1].get("Close"))
    if current is None or previous in (None, 0):
        return None
    return round(((current - previous) / previous) * 100, 2)


def _distance_pct(close: float, reference: float | None) -> float | None:
    if reference in (None, 0):
        return None
    return round(((close - reference) / reference) * 100, 2)


def build_market_context(df: pd.DataFrame) -> MarketContext:
    """Build derived OHLCV state for ScoreAggregator."""
    if df.empty:
        return MarketContext(close=0.0)

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    close = _safe_float(latest.get("Close")) or 0.0

    sma20 = _safe_float(latest.get("SMA_20"))
    sma50 = _safe_float(latest.get("SMA_50"))
    sma150 = _safe_float(latest.get("SMA_150"))
    sma200 = _safe_float(latest.get("SMA_200"))
    volume = _safe_float(latest.get("Volume"))
    vol_sma20 = _safe_float(latest.get("Vol_SMA_20"))
    rsi = _safe_float(latest.get("RSI"))
    atr = _safe_float(latest.get("ATR"))
    supertrend_direction = latest.get("SuperTrend_Dir")
    previous_supertrend_direction = previous.get("SuperTrend_Dir")

    volume_ratio = None
    if volume is not None and vol_sma20 not in (None, 0):
        volume_ratio = round(volume / vol_sma20, 2)

    high_20 = _safe_float(df["High"].iloc[-20:].max()) if "High" in df.columns else None
    distance_from_20d_high_pct = None
    if high_20 not in (None, 0):
        distance_from_20d_high_pct = round(((close - high_20) / high_20) * 100, 2)

    atr_pct = None
    if atr is not None and close:
        atr_pct = round((atr / close) * 100, 2)

    supertrend_dir = None if pd.isna(supertrend_direction) else int(supertrend_direction)
    prev_supertrend_dir = (
        None if pd.isna(previous_supertrend_direction) else int(previous_supertrend_direction)
    )
    supertrend_sell_transition = prev_supertrend_dir == 1 and supertrend_dir == -1

    ret_1d = _ret_pct(df, 1)
    ret_5d = _ret_pct(df, 5)
    ret_10d = _ret_pct(df, 10)
    distance_sma20 = _distance_pct(close, sma20)
    distance_sma50 = _distance_pct(close, sma50)

    close_above_sma20 = sma20 is not None and close > sma20
    close_above_sma50 = sma50 is not None and close > sma50
    close_above_sma150 = sma150 is not None and close > sma150
    close_above_sma200 = sma200 is not None and close > sma200
    sma20_above_sma50 = sma20 is not None and sma50 is not None and sma20 > sma50

    is_overextended = any(
        [
            rsi is not None and rsi >= 75,
            ret_5d is not None and ret_5d >= 15,
            ret_1d is not None and ret_1d >= 8,
            distance_sma20 is not None and distance_sma20 >= 12,
        ]
    )
    is_breakdown = any(
        [
            close_above_sma50 is False and volume_ratio is not None and volume_ratio >= 1.3,
            supertrend_sell_transition,
            close_above_sma20 is False and close_above_sma50 is False and ret_10d is not None and ret_10d < 0,
        ]
    )
    is_uptrend = close_above_sma50 and sma20_above_sma50 and supertrend_dir != -1
    is_downtrend = (not close_above_sma50 and supertrend_dir == -1) or (
        sma20 is not None and sma50 is not None and sma20 < sma50 and close < sma50
    )

    support_candidates = [value for value in [sma20, sma50, sma150, sma200] if value and value < close]
    nearest_support = max(support_candidates) if support_candidates else None

    return MarketContext(
        close=close,
        close_above_sma20=close_above_sma20,
        close_above_sma50=close_above_sma50,
        close_above_sma150=close_above_sma150,
        close_above_sma200=close_above_sma200,
        sma20_above_sma50=sma20_above_sma50,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        ret_10d=ret_10d,
        distance_from_20d_high_pct=distance_from_20d_high_pct,
        distance_from_sma20_pct=distance_sma20,
        distance_from_sma50_pct=distance_sma50,
        volume_ratio_20d=volume_ratio,
        rsi=rsi,
        atr_pct=atr_pct,
        supertrend_direction=supertrend_dir,
        supertrend_sell_transition=supertrend_sell_transition,
        is_overextended=is_overextended,
        is_breakdown=is_breakdown,
        is_uptrend=is_uptrend,
        is_downtrend=is_downtrend,
        nearest_support=nearest_support,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_market_context.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/context.py tests/tools/technical/test_market_context.py
git commit -m "feat: add technical market context"
```

---

### Task 3: Component Signal Metadata

**Files:**
- Modify: `src/tools/technical/components/crsi.py`
- Modify: `src/tools/technical/components/divergence.py`
- Modify: `src/tools/technical/components/minervini.py`
- Modify: `src/tools/technical/components/patterns.py`
- Modify: `src/tools/technical/components/risk.py`
- Modify: `src/tools/technical/components/supertrend.py`
- Modify: `src/tools/technical/components/velocity.py`
- Modify: `src/tools/technical/components/volume.py`
- Modify: existing component tests under `tests/tools/technical/`

**Interfaces:**
- Consumes: `ComponentSignal`
- Produces: each `ComponentResult.signal_metadata`

- [ ] **Step 1: Write failing metadata tests**

Add assertions to existing component tests. Use these exact expected mappings:

```python
assert result.signal_metadata
assert result.signal_metadata[0].source == "crsi"
assert result.signal_metadata[0].signal_type == "pullback"
assert result.signal_metadata[0].intent == "entry"
```

Minimum test cases:

```text
tests/tools/technical/test_crsi_component.py
  - Hook Up returns pullback/bullish/entry/entry_eligible=True
  - Hook Down returns overextension/bearish/risk/entry_eligible=False

tests/tools/technical/test_divergence_component.py
  - bullish divergence returns reversal/bullish/watch/entry_eligible=False
  - bearish divergence returns reversal/bearish/risk/entry_eligible=False

tests/tools/technical/test_supertrend_component.py
  - Supertrend up returns trend/bullish/hold
  - Supertrend sell transition returns breakdown/bearish/risk/high

tests/tools/technical/test_volume_component.py
  - Pocket Pivot returns pullback/bullish/entry
  - price down volume surge returns breakdown/bearish/risk

tests/tools/technical/test_patterns_component.py
  - breakout returns breakout/bullish/entry
  - hammer or bullish engulfing returns reversal/bullish/watch

tests/tools/technical/test_risk_component.py
  - close below SMA50 adds breakdown/bearish/risk
  - support confluence adds support/bullish/hold
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/tools/technical/test_crsi_component.py \
  tests/tools/technical/test_divergence_component.py \
  tests/tools/technical/test_supertrend_component.py \
  tests/tools/technical/test_volume_component.py \
  tests/tools/technical/test_patterns_component.py \
  tests/tools/technical/test_risk_component.py \
  -v
```

Expected: FAIL because `signal_metadata` is empty.

- [ ] **Step 3: Add metadata construction**

Use this mapping table while editing components:

```text
minervini Stage 2 -> trend/bullish/hold/medium/entry_eligible=True
minervini above_50 but not Stage 2 -> trend/bullish/watch/low/entry_eligible=False
minervini weak -> breakdown/bearish/risk/medium/entry_eligible=False
velocity upturn -> trend/bullish/hold/medium/entry_eligible=False
velocity down turn -> breakdown/bearish/risk/medium/entry_eligible=False
crsi Hook Up -> pullback/bullish/entry/medium/entry_eligible=True
crsi Hook Down -> overextension/bearish/risk/medium/entry_eligible=False
volume Pocket Pivot -> pullback/bullish/entry/high/entry_eligible=True
volume Power Gap Up -> breakout/bullish/entry/high/entry_eligible=True
volume price up surge -> volume_confirmation/bullish/hold/medium/entry_eligible=False
volume price down surge -> breakdown/bearish/risk/high/entry_eligible=False
patterns VCP -> support/neutral/watch/medium/entry_eligible=False
patterns breakout -> breakout/bullish/entry/high/entry_eligible=True
patterns bullish candle -> reversal/bullish/watch/medium/entry_eligible=False
supertrend up -> trend/bullish/hold/medium/entry_eligible=False
supertrend buy transition -> breakout/bullish/entry/high/entry_eligible=True
supertrend down -> trend/bearish/risk/medium/entry_eligible=False
supertrend sell transition -> breakdown/bearish/risk/high/entry_eligible=False
divergence bullish -> reversal/bullish/watch/medium/entry_eligible=False
divergence bearish -> reversal/bearish/risk/medium/entry_eligible=False
risk support confluence -> support/bullish/hold/medium/entry_eligible=False
risk resistance confluence -> resistance/bearish/risk/medium/entry_eligible=False
risk below SMA50 or Supertrend down -> breakdown/bearish/risk/medium/entry_eligible=False
```

Example edit pattern:

```python
from src.tools.technical.models import ComponentResult, ComponentSignal


metadata: list[ComponentSignal] = []

if prev_crsi < crsi_low and crsi > crsi_low:
    signals.append("cRSI Hook Up (매수 시그널)")
    evidence.append(f"cRSI {prev_crsi:.1f} → {crsi:.1f}, 하단밴드 {crsi_low:.1f} 상향 돌파")
    score += 20
    metadata.append(
        ComponentSignal(
            signal_type="pullback",
            bias="bullish",
            intent="entry",
            severity="medium",
            entry_eligible=True,
            source="crsi",
            reason="cRSI Hook Up",
        )
    )

return ComponentResult(
    signals=signals,
    evidence=evidence,
    metrics=metrics,
    score=score,
    signal_metadata=metadata,
)
```

All early returns can omit `signal_metadata`; the model default keeps them as `[]`.

- [ ] **Step 4: Run component tests**

Run:

```bash
uv run pytest \
  tests/tools/technical/test_crsi_component.py \
  tests/tools/technical/test_divergence_component.py \
  tests/tools/technical/test_supertrend_component.py \
  tests/tools/technical/test_volume_component.py \
  tests/tools/technical/test_patterns_component.py \
  tests/tools/technical/test_risk_component.py \
  tests/tools/technical/test_minervini.py \
  tests/tools/technical/test_velocity.py \
  -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/components tests/tools/technical
git commit -m "feat: add structured technical component metadata"
```

---

### Task 4: ScoreAggregator

**Files:**
- Create: `src/tools/technical/aggregator.py`
- Create: `tests/tools/technical/test_score_aggregator.py`

**Interfaces:**
- Consumes:
  - `components: dict[str, dict]`
  - `context: MarketContext`
- Produces:
  - `ScoreAggregationResult.adjusted_score`
  - `ScoreAggregationResult.technical_verdict`
  - `ScoreAggregationResult.aggregation_trace`

- [ ] **Step 1: Write failing aggregator tests**

```python
# tests/tools/technical/test_score_aggregator.py
from src.tools.technical.aggregator import ScoreAggregator
from src.tools.technical.models import ComponentSignal, MarketContext


def _component(score: int, metadata: list[ComponentSignal]) -> dict:
    return {"score": score, "signals": [], "evidence": [], "metrics": {}, "signal_metadata": metadata}


def test_downtrend_reversal_is_capped_to_watch():
    components = {
        "divergence": _component(
            45,
            [
                ComponentSignal(
                    signal_type="reversal",
                    bias="bullish",
                    intent="watch",
                    severity="medium",
                    entry_eligible=False,
                    source="divergence",
                    reason="bullish divergence",
                )
            ],
        )
    }
    context = MarketContext(close=100, is_downtrend=True, rsi=35)

    result = ScoreAggregator().aggregate(components, context)

    assert result.adjusted_score <= 35
    assert result.technical_verdict.action == "watch"
    assert result.technical_verdict.new_entry_allowed is False
    assert any(trace.rule == "downtrend_reversal_cap" for trace in result.aggregation_trace)


def test_overextended_strong_trend_becomes_hold_not_buy():
    components = {
        "minervini": _component(
            40,
            [
                ComponentSignal(
                    signal_type="trend",
                    bias="bullish",
                    intent="hold",
                    severity="medium",
                    entry_eligible=True,
                    source="minervini",
                    reason="Stage 2",
                )
            ],
        ),
        "volume": _component(
            25,
            [
                ComponentSignal(
                    signal_type="breakout",
                    bias="bullish",
                    intent="entry",
                    severity="high",
                    entry_eligible=True,
                    source="volume",
                    reason="Power Gap Up",
                )
            ],
        ),
    }
    context = MarketContext(close=100, is_uptrend=True, is_overextended=True, rsi=78, ret_5d=18)

    result = ScoreAggregator().aggregate(components, context)

    assert result.technical_verdict.action == "hold"
    assert result.technical_verdict.new_entry_allowed is False
    assert result.technical_verdict.cautions


def test_volume_breakdown_overrides_positive_score():
    components = {
        "minervini": _component(40, []),
        "risk": _component(
            -10,
            [
                ComponentSignal(
                    signal_type="breakdown",
                    bias="bearish",
                    intent="risk",
                    severity="high",
                    entry_eligible=False,
                    source="risk",
                    reason="SMA50 break",
                )
            ],
        ),
    }
    context = MarketContext(close=100, is_breakdown=True, volume_ratio_20d=1.8, is_downtrend=True)

    result = ScoreAggregator().aggregate(components, context)

    assert result.technical_verdict.action in {"reduce", "avoid"}
    assert result.technical_verdict.new_entry_allowed is False
    assert result.adjusted_score < 40


def test_aggregator_does_not_parse_signal_strings():
    components = {
        "fake": {
            "score": 90,
            "signals": ["Supertrend 매도 전환", "SMA50 이탈"],
            "evidence": [],
            "metrics": {},
            "signal_metadata": [],
        }
    }
    context = MarketContext(close=100, is_uptrend=True)

    result = ScoreAggregator().aggregate(components, context)

    assert result.adjusted_score == 90
    assert result.technical_verdict.action in {"buy", "add", "hold"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_score_aggregator.py -v`

Expected: FAIL with missing `src.tools.technical.aggregator`.

- [ ] **Step 3: Implement aggregator**

Create `src/tools/technical/aggregator.py` with these public names:

```python
from dataclasses import dataclass, field

from src.tools.technical.models import (
    AggregationTraceEntry,
    ComponentSignal,
    MarketContext,
    TechnicalVerdict,
)


@dataclass
class ScoreAggregationResult:
    component_raw_total: int
    adjusted_score: int
    technical_verdict: TechnicalVerdict
    aggregation_trace: list[AggregationTraceEntry] = field(default_factory=list)


class ScoreAggregator:
    def aggregate(self, components: dict[str, dict], context: MarketContext) -> ScoreAggregationResult:
        raw_total = sum(int(component.get("score", 0)) for component in components.values())
        adjusted = raw_total
        trace: list[AggregationTraceEntry] = []
        metadata = _collect_metadata(components)
        reasons = _build_reasons(metadata, context, raw_total)
        cautions: list[str] = []
        new_entry_allowed = True
        forced_action: str | None = None

        if _has_volume_backed_breakdown(metadata, context):
            before = adjusted
            adjusted = min(adjusted, -40)
            forced_action = "avoid"
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="volume_backed_breakdown_override",
                    before=before,
                    after=adjusted,
                    reason="거래량 동반 breakdown",
                )
            )
            cautions.append("거래량이 동반된 이탈로 신규 진입 금지")
        elif context.supertrend_sell_transition:
            before = adjusted
            adjusted = min(adjusted, -25)
            forced_action = "reduce"
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="supertrend_sell_override",
                    before=before,
                    after=adjusted,
                    reason="Supertrend 매도 전환",
                )
            )
            cautions.append("Supertrend가 매도 전환")

        if context.is_downtrend and _has_bullish_reversal(metadata):
            before = adjusted
            adjusted = min(adjusted, 35)
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="downtrend_reversal_cap",
                    before=before,
                    after=adjusted,
                    reason="하락 추세의 반전 신호는 watch로 제한",
                )
            )
            cautions.append("하락 추세의 반전 신호라 확인 전 신규 진입 제한")

        if context.is_overextended:
            before = adjusted
            adjusted -= 15
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="overextended_penalty",
                    before=before,
                    after=adjusted,
                    reason="단기 과열로 신규 진입 제한",
                )
            )
            cautions.append("추세는 유지돼도 단기 과열 구간")

        action, entry_mode = _choose_action(
            adjusted=adjusted,
            context=context,
            metadata=metadata,
            forced_action=forced_action,
            new_entry_allowed=new_entry_allowed,
        )
        if action in {"hold", "watch", "reduce", "avoid"}:
            new_entry_allowed = False

        verdict = TechnicalVerdict(
            action=action,
            entry_mode=entry_mode,
            confidence=_confidence(adjusted, trace),
            new_entry_allowed=new_entry_allowed,
            reasons=reasons[:5],
            cautions=cautions[:5],
            invalidation_level=context.nearest_support,
        )
        return ScoreAggregationResult(
            component_raw_total=raw_total,
            adjusted_score=adjusted,
            technical_verdict=verdict,
            aggregation_trace=trace,
        )
```

Add helpers in the same file:

```python
def _collect_metadata(components: dict[str, dict]) -> list[ComponentSignal]:
    collected: list[ComponentSignal] = []
    for component in components.values():
        for item in component.get("signal_metadata", []):
            if isinstance(item, ComponentSignal):
                collected.append(item)
            elif isinstance(item, dict):
                collected.append(ComponentSignal(**item))
    return collected


def _has_bullish_reversal(metadata: list[ComponentSignal]) -> bool:
    return any(signal.signal_type == "reversal" and signal.bias == "bullish" for signal in metadata)


def _has_volume_backed_breakdown(metadata: list[ComponentSignal], context: MarketContext) -> bool:
    return (
        context.is_breakdown
        and context.volume_ratio_20d is not None
        and context.volume_ratio_20d >= 1.3
        and any(signal.signal_type == "breakdown" and signal.severity == "high" for signal in metadata)
    )


def _has_entry_signal(metadata: list[ComponentSignal], signal_type: str) -> bool:
    return any(
        signal.entry_eligible and signal.intent == "entry" and signal.signal_type == signal_type
        for signal in metadata
    )


def _choose_action(
    *,
    adjusted: int,
    context: MarketContext,
    metadata: list[ComponentSignal],
    forced_action: str | None,
    new_entry_allowed: bool,
) -> tuple[str, str]:
    if forced_action is not None:
        return forced_action, "risk_override"
    if adjusted < -25:
        return "avoid", "risk_override"
    if adjusted < 0:
        return "reduce", "risk_control"
    if not new_entry_allowed and adjusted >= 45:
        return "hold", "extended_hold"
    if adjusted >= 75 and new_entry_allowed and _has_entry_signal(metadata, "breakout"):
        return "buy", "breakout_entry"
    if adjusted >= 55 and new_entry_allowed and _has_entry_signal(metadata, "pullback"):
        return "add", "pullback_add"
    if adjusted >= 40 and context.is_uptrend:
        return "hold", "trend_hold"
    return "watch", "confirmation_needed"


def _confidence(adjusted: int, trace: list[AggregationTraceEntry]) -> str:
    if abs(adjusted) >= 60 and len(trace) <= 1:
        return "high"
    if abs(adjusted) >= 30:
        return "medium"
    return "low"


def _build_reasons(
    metadata: list[ComponentSignal],
    context: MarketContext,
    raw_total: int,
) -> list[str]:
    reasons: list[str] = []
    if context.is_uptrend:
        reasons.append("가격이 주요 이동평균 위에서 상승 추세를 유지")
    if context.volume_ratio_20d is not None and context.volume_ratio_20d >= 1.5:
        reasons.append(f"거래량이 20일 평균 대비 {context.volume_ratio_20d:.1f}배")
    for signal in metadata:
        if signal.reason and signal.bias == "bullish" and len(reasons) < 5:
            reasons.append(signal.reason)
    if not reasons:
        reasons.append(f"component raw total {raw_total}점")
    return reasons
```

- [ ] **Step 4: Run aggregator tests**

Run: `uv run pytest tests/tools/technical/test_score_aggregator.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/aggregator.py tests/tools/technical/test_score_aggregator.py
git commit -m "feat: add technical score aggregator"
```

---

### Task 5: TechnicalScorer Wiring and Score History

**Files:**
- Modify: `src/tools/technical/scorer.py`
- Modify: `tests/tools/technical/test_scorer.py`
- Modify: `tests/tools/technical/test_tool_scorer_integration.py`

**Interfaces:**
- Consumes:
  - `build_market_context(df)`
  - `ScoreAggregator.aggregate(components, context)`
- Produces:
  - `TechnicalScorer.score(df, ticker=None, include_history=True, history_days=5)`
  - `_score_current(df, ticker=None) -> TechnicalResult`

- [ ] **Step 1: Write failing scorer tests**

Add to `tests/tools/technical/test_scorer.py`:

```python
def test_technical_scorer_preserves_total_score_as_component_sum(sample_df):
    scorer = TechnicalScorer()
    result = scorer.score(sample_df, include_history=False)

    expected_total = sum(comp["score"] for comp in result.components.values())

    assert result.total_score == expected_total
    assert result.component_raw_total == expected_total
    assert isinstance(result.adjusted_score, int)
    assert result.technical_verdict is not None


def test_technical_scorer_score_history_uses_recent_trading_days(sample_df):
    scorer = TechnicalScorer()
    result = scorer.score(sample_df, ticker="AAPL", history_days=5)

    assert len(result.score_history) == 5
    assert all(point.verdict_action for point in result.score_history)
    assert result.technical_verdict.score_trend_summary is not None


def test_score_history_does_not_use_future_rows(sample_df):
    scorer = TechnicalScorer()
    baseline = scorer.score(sample_df, ticker="AAPL", history_days=5)

    changed = sample_df.copy()
    changed.loc[changed.index[-1], "Close"] = changed.loc[changed.index[-1], "Close"] * 1.5
    changed.loc[changed.index[-1], "Volume"] = changed.loc[changed.index[-1], "Volume"] * 4
    mutated = scorer.score(changed, ticker="AAPL", history_days=5)

    assert baseline.score_history[-2] == mutated.score_history[-2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/tools/technical/test_scorer.py tests/tools/technical/test_tool_scorer_integration.py -v`

Expected: FAIL because `include_history` and score history wiring are not implemented.

- [ ] **Step 3: Refactor scorer into current-score and history paths**

Update `src/tools/technical/scorer.py`:

```python
from src.tools.technical.aggregator import ScoreAggregator
from src.tools.technical.context import build_market_context
from src.tools.technical.models import ScoreHistoryPoint, TechnicalResult
```

Add `self.aggregator = ScoreAggregator()` in `__init__`.

Replace `score` with this shape:

```python
def score(
    self,
    df: pd.DataFrame,
    ticker: str | None = None,
    include_history: bool = True,
    history_days: int = 5,
) -> TechnicalResult:
    """Calculate technical score from OHLCV data."""
    result = self._score_current(df, ticker=ticker)
    if include_history and history_days > 0:
        history, warning = self._build_score_history(df, ticker=ticker, history_days=history_days)
        result.score_history = history
        result.score_history_warning = warning
        if result.technical_verdict is not None:
            result.technical_verdict.score_trend_summary = _summarize_score_history(history)
    return result
```

Create `_score_current` by moving the existing component analyzer code into it, then add:

```python
component_raw_total = sum(comp["score"] for comp in components.values())
snapshot = self.calculator.create_snapshot(df)
context = build_market_context(df)
aggregation = self.aggregator.aggregate(components, context)

return TechnicalResult.from_analysis(
    df,
    ticker=ticker,
    timestamp=datetime.now(UTC),
    snapshot=snapshot,
    components=components,
    total_score=component_raw_total,
    component_raw_total=aggregation.component_raw_total,
    adjusted_score=aggregation.adjusted_score,
    technical_verdict=aggregation.technical_verdict,
    aggregation_trace=aggregation.aggregation_trace,
)
```

Add history helpers:

```python
def _build_score_history(
    self,
    df: pd.DataFrame,
    ticker: str | None,
    history_days: int,
) -> tuple[list[ScoreHistoryPoint], str | None]:
    valid_df = df.dropna(subset=["Close"])
    recent_dates = list(valid_df.index[-history_days:])
    history: list[ScoreHistoryPoint] = []
    failures: list[str] = []

    for date in recent_dates:
        try:
            sliced = df.loc[:date].copy()
            daily = self._score_current(sliced, ticker=ticker)
            first_reason = (
                daily.technical_verdict.reasons[0]
                if daily.technical_verdict and daily.technical_verdict.reasons
                else "핵심 reason 없음"
            )
            history.append(
                ScoreHistoryPoint(
                    date=str(date.date()) if hasattr(date, "date") else str(date),
                    close=float(sliced.dropna(subset=["Close"]).iloc[-1]["Close"]),
                    component_raw_total=daily.component_raw_total,
                    adjusted_score=daily.adjusted_score,
                    verdict_action=daily.technical_verdict.action,
                    one_line_reason=first_reason,
                )
            )
        except Exception as exc:
            failures.append(f"{date}: {exc}")

    warning = "; ".join(failures) if failures else None
    return history, warning


def _summarize_score_history(history: list[ScoreHistoryPoint]) -> str | None:
    if len(history) < 2:
        return None
    first = history[0].adjusted_score
    last = history[-1].adjusted_score
    direction = "개선" if last > first else "악화" if last < first else "정체"
    return f"최근 {len(history)}거래일 adjusted score는 {first}에서 {last}로 {direction}"
```

- [ ] **Step 4: Run scorer tests**

Run: `uv run pytest tests/tools/technical/test_scorer.py tests/tools/technical/test_tool_scorer_integration.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/scorer.py tests/tools/technical/test_scorer.py tests/tools/technical/test_tool_scorer_integration.py
git commit -m "feat: wire adjusted technical scoring"
```

---

### Task 6: Quick Check Output

**Files:**
- Modify: `src/pipelines/quick_check.py`
- Modify: `tests/pipelines/test_quick_check.py`

**Interfaces:**
- Consumes: `TechnicalResult.adjusted_score`, `technical_verdict`, `score_history`
- Produces: quick check result dict and formatted markdown sections

- [ ] **Step 1: Write failing quick_check tests**

Add to `tests/pipelines/test_quick_check.py`:

```python
from src.tools.technical.models import ScoreHistoryPoint, TechnicalVerdict


@pytest.mark.asyncio
async def test_quick_check_run_includes_verdict_and_score_history(mock_technical_tool):
    tech = mock_technical_tool.execute.return_value.data
    tech.adjusted_score = 62
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=170.0,
        score_trend_summary="최근 5거래일 adjusted score는 70에서 62로 악화",
    )
    tech.score_history = [
        ScoreHistoryPoint(
            date="2026-07-10",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]

    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")

    assert result["adjusted_score"] == 62
    assert result["technical_verdict"]["action"] == "hold"
    assert result["score_history"][0]["adjusted_score"] == 62


@pytest.mark.asyncio
async def test_quick_check_format_output_shows_verdict_reasons_and_history(mock_technical_tool):
    tech = mock_technical_tool.execute.return_value.data
    tech.adjusted_score = 62
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=170.0,
        score_trend_summary="최근 5거래일 adjusted score는 70에서 62로 악화",
    )
    tech.score_history = [
        ScoreHistoryPoint(
            date="2026-07-10",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]

    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    output = pipeline.format_output(await pipeline.run("AAPL"))

    assert "Adjusted Score" in output
    assert "상승 추세 유지" in output
    assert "최근 5거래일" in output
    assert "2026-07-10" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pipelines/test_quick_check.py -v`

Expected: FAIL because quick check does not include new fields.

- [ ] **Step 3: Update quick_check result dict and formatter**

In `QuickCheckPipeline.run`, add:

```python
verdict = tech.technical_verdict.model_dump() if tech.technical_verdict else None

result_payload = {
    "ticker": ticker,
    "success": True,
    "price": snapshot.price,
    "change_pct": snapshot.change_pct,
    "total_score": tech.total_score,
    "component_raw_total": tech.component_raw_total,
    "adjusted_score": tech.adjusted_score,
    "technical_verdict": verdict,
    "score_history": [point.model_dump() for point in tech.score_history],
    "score_history_warning": tech.score_history_warning,
    "assessment": tech.overall_assessment or "N/A",
    "confidence": tech.confidence_score or 0,
    "signals": signals[:10],
    "warnings": tech.warnings or [],
    "indicators": {
        "sma_20": snapshot.sma_20,
        "sma_50": snapshot.sma_50,
        "sma_150": snapshot.sma_150,
        "rsi": snapshot.rsi,
        "adx": snapshot.adx,
        "crsi": snapshot.crsi,
    },
    "components": components_list,
}
return result_payload
```

In `format_output`, after total score lines:

```python
if result.get("adjusted_score") is not None:
    lines.append(f"**Adjusted Score**: {result['adjusted_score']}")

verdict = result.get("technical_verdict")
if verdict:
    lines.extend(
        [
            "",
            "### Technical Verdict",
            f"- Action: {verdict['action']} ({verdict['entry_mode']}, confidence={verdict['confidence']})",
            f"- 신규 진입 가능: {'yes' if verdict['new_entry_allowed'] else 'no'}",
        ]
    )
    if verdict.get("reasons"):
        lines.append("- Reasons:")
        lines.extend(f"  - {reason}" for reason in verdict["reasons"])
    if verdict.get("cautions"):
        lines.append("- Cautions:")
        lines.extend(f"  - {caution}" for caution in verdict["cautions"])
    if verdict.get("invalidation_level") is not None:
        lines.append(f"- Invalidation: {verdict['invalidation_level']:.2f}")
    if verdict.get("score_trend_summary"):
        lines.append(f"- Trend: {verdict['score_trend_summary']}")

history = result.get("score_history") or []
if history:
    lines.extend(["", "### 최근 점수 추이"])
    for point in history:
        lines.append(
            f"- {point['date']}: close {point['close']:.2f}, "
            f"raw {point['component_raw_total']}, adjusted {point['adjusted_score']}, "
            f"{point['verdict_action']} — {point['one_line_reason']}"
        )
if result.get("score_history_warning"):
    lines.append(f"- score history warning: {result['score_history_warning']}")
```

- [ ] **Step 4: Run quick_check tests**

Run: `uv run pytest tests/pipelines/test_quick_check.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/quick_check.py tests/pipelines/test_quick_check.py
git commit -m "feat: show technical verdict in quick check"
```

---

### Task 7: Deep Dive and Analyze Decision Integration

**Files:**
- Modify: `src/llm/models.py`
- Modify: `src/llm/analyzer.py`
- Modify: `src/pipelines/deep_dive.py`
- Modify: `src/pipelines/analyze_decision.py`
- Modify: `tests/llm/test_analyzer.py`
- Modify: `tests/pipelines/test_deep_dive.py`
- Modify: `tests/pipelines/test_analyze_decision.py`

**Interfaces:**
- Consumes: `technical_data.technical_verdict`, `technical_data.score_history`, `technical_data.aggregation_trace`
- Produces: LLM technical summary input with rule facts and decision bundle technical assessment using verdict first

- [ ] **Step 1: Write failing tests**

Add to `tests/pipelines/test_analyze_decision.py`:

```python
def test_build_analyze_decision_bundle_uses_technical_verdict_when_present():
    technical_data = _technical_result(total_score=120)
    technical_data.adjusted_score = 35
    technical_data.technical_verdict = TechnicalVerdict(
        action="watch",
        entry_mode="confirmation_needed",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["하락 추세의 반전 신호"],
        cautions=["신규 진입 제한"],
        invalidation_level=None,
    )

    bundle = build_analyze_decision_bundle(
        technical_data=technical_data,
        technical_summary=None,
        news_articles=[],
        news_analysis=None,
        fundamental_summary=None,
        disclosure_items=[],
        flow_data=None,
        chart_patterns={},
        price_levels=None,
    )

    technical = next(a for a in bundle.factor_assessments if a.factor_type == "technical")
    assert technical.total_score <= 6
    assert "하락 추세의 반전 신호" in technical.evidence
```

Add to `tests/pipelines/test_deep_dive.py`:

```python
from src.tools.technical.models import ScoreHistoryPoint, TechnicalVerdict


@pytest.mark.asyncio
async def test_deep_dive_passes_verdict_and_score_history_to_technical_summary(
    mock_technical_tool,
    mock_news_tool,
    mock_llm,
):
    tech = mock_technical_tool.execute.return_value.data
    tech.adjusted_score = 62
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=170.0,
        score_trend_summary="최근 5거래일 adjusted score는 70에서 62로 악화",
    )
    tech.score_history = [
        ScoreHistoryPoint(
            date="2026-07-16",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]

    with (
        patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
        patch("src.pipelines.deep_dive.StructureZoneDetector") as mock_zone_detector_cls,
        patch("src.pipelines.deep_dive.compose_level_payload") as mock_compose_levels,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["상승 추세 유지"],
            recommendation="중립",
            confidence=0.7,
            rationale="rule output 설명",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="중립",
            confidence=0.5,
            key_themes=[],
            summary="뉴스 제한적",
            impact_assessment="영향 제한",
        )
        mock_signal.return_value = ActionableSignalOutput(
            action="관망",
            timing="보류",
            signal_strength=5,
            headline="관망",
            primary_reason="단기 과열",
            supporting_reasons=["상승 추세 유지"],
            risks=["추격 매수 리스크"],
            confidence=0.7,
        )
        mock_zone_detector_cls.return_value.detect.return_value = object()
        mock_compose_levels.return_value = LevelPayload(
            structure_levels=StructureLevelsPayloadV2(
                summary_label="no_clear_structure",
                headline="명확한 구조 없음",
                why="테스트 기본값",
            ),
            execution_levels=[],
            structure_summary="명확한 구조 없음",
            execution_summary="실행 레벨 없음",
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )
        await pipeline.run("AAPL")

    input_data = mock_tech_summary.call_args.args[0]
    assert input_data.technical_verdict["action"] == "hold"
    assert input_data.score_history[0]["adjusted_score"] == 62
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/pipelines/test_analyze_decision.py tests/pipelines/test_deep_dive.py tests/llm/test_analyzer.py -v
```

Expected: FAIL because the models and pipeline do not pass verdict fields.

- [ ] **Step 3: Extend LLM technical summary input**

In `src/llm/models.py`, update `TechnicalSummaryInput`:

```python
class TechnicalSummaryInput(BaseModel):
    """Input for technical summary."""

    ticker: str
    price: float
    change_pct: float
    strategies: list[dict[str, Any]]
    indicators: dict[str, float]
    technical_verdict: dict[str, Any] | None = None
    score_history: list[dict[str, Any]] = Field(default_factory=list)
    score_history_warning: str | None = None
    aggregation_trace: list[dict[str, Any]] = Field(default_factory=list)
```

In `src/llm/analyzer.py`, add these facts to the technical summary prompt user message:

```text
**Rule-based technical verdict**:
{technical_verdict}

**Recent score history**:
{score_history}

Use these fields as fixed rule output. Do not change the score or action. Explain them in Korean.
```

Pass variables in `chain.ainvoke`.

- [ ] **Step 4: Pass fields in deep_dive**

In `DeepDivePipeline._generate_technical_summary`, add to `TechnicalSummaryInput`:

```python
technical_verdict=(
    technical_data.technical_verdict.model_dump()
    if technical_data.technical_verdict is not None
    else None
),
score_history=[point.model_dump() for point in technical_data.score_history],
score_history_warning=technical_data.score_history_warning,
aggregation_trace=[entry.model_dump() for entry in technical_data.aggregation_trace],
```

- [ ] **Step 5: Use verdict in analyze_decision**

Add helper in `src/pipelines/analyze_decision.py`:

```python
def _technical_factor_score_from_verdict(technical_data) -> int | None:
    verdict = getattr(technical_data, "technical_verdict", None)
    if verdict is None:
        return None
    adjusted = getattr(technical_data, "adjusted_score", None)
    if verdict.action in {"avoid", "reduce"}:
        return 8
    if verdict.action in {"buy", "add"} and adjusted is not None and adjusted >= 55:
        return 11 if adjusted >= 75 else 8
    if verdict.action == "hold":
        return 6
    if verdict.action == "watch":
        return 4
    return None
```

Update `build_analyze_decision_bundle` immediately after the existing `build_technical_assessment` call:

```python
verdict_score = _technical_factor_score_from_verdict(technical_data)
verdict = getattr(technical_data, "technical_verdict", None)
if verdict is not None and verdict_score is not None:
    technical_assessment = technical_assessment.model_copy(
        update={
            "total_score": verdict_score,
            "role": "보조" if verdict_score >= 7 else "참고",
            "headline": f"technical verdict: {verdict.action}",
            "summary": verdict.reasons[0] if verdict.reasons else technical_assessment.summary,
            "role_reason": "technical_verdict를 우선 반영",
            "evidence": technical_assessment.evidence + verdict.reasons + verdict.cautions,
            "bias": "bearish" if verdict.action in {"reduce", "avoid"} else "bullish" if verdict.action in {"buy", "add"} else "neutral",
        }
    )
```

- [ ] **Step 6: Run integration tests**

Run:

```bash
uv run pytest tests/pipelines/test_analyze_decision.py tests/pipelines/test_deep_dive.py tests/llm/test_analyzer.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/llm/models.py src/llm/analyzer.py src/pipelines/deep_dive.py src/pipelines/analyze_decision.py tests/llm/test_analyzer.py tests/pipelines/test_deep_dive.py tests/pipelines/test_analyze_decision.py
git commit -m "feat: pass technical verdict to analysis pipelines"
```

---

### Task 8: Brief Pipeline Verdict Facts

**Files:**
- Modify: `src/tools/brief/models.py`
- Modify: `src/tools/brief/render.py`
- Modify: `src/pipelines/brief.py`
- Modify: `src/llm/analyzer.py`
- Modify: `tests/pipelines/test_brief.py`
- Modify: `tests/tools/brief/test_render.py`
- Modify: `tests/llm/test_brief_narratives.py`

**Interfaces:**
- Consumes: `TechnicalResult.technical_verdict`
- Produces: `BriefItem.technical_verdict`, `BriefItem.score_history`

- [ ] **Step 1: Write failing brief tests**

Add to `tests/tools/brief/test_render.py`:

```python
def test_render_markdown_shows_technical_verdict_reason():
    item = _brief_item("AAPL")
    item.technical_verdict = {
        "action": "hold",
        "reasons": ["상승 추세 유지"],
        "cautions": ["단기 과열"],
        "score_trend_summary": "최근 5거래일 adjusted score 둔화",
    }
    item.score_history = [
        {
            "date": "2026-07-16",
            "close": 100.0,
            "component_raw_total": 80,
            "adjusted_score": 62,
            "verdict_action": "hold",
            "one_line_reason": "단기 과열",
        }
    ]

    output = render_markdown(datetime(2026, 7, 16), None, [item])

    assert "상승 추세 유지" in output
    assert "최근 5거래일" in output
```

Use the local helper style already present in `tests/tools/brief/test_render.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/pipelines/test_brief.py tests/tools/brief/test_render.py tests/llm/test_brief_narratives.py -v
```

Expected: FAIL because `BriefItem` does not expose verdict fields.

- [ ] **Step 3: Add fields to BriefItem**

In `src/tools/brief/models.py`:

```python
technical_verdict: dict[str, Any] | None = None
score_history: list[dict[str, Any]] = field(default_factory=list)
score_history_warning: str | None = None
```

- [ ] **Step 4: Populate fields in BriefPipeline**

In `_analyze_target`, when returning `BriefItem`, add:

```python
technical_verdict=(
    technical.technical_verdict.model_dump()
    if technical.technical_verdict is not None
    else None
),
score_history=[point.model_dump() for point in technical.score_history],
score_history_warning=technical.score_history_warning,
```

In `_facts_for`, add:

```python
"technical_verdict": item.technical_verdict,
"score_history": item.score_history,
"score_history_warning": item.score_history_warning,
```

In `generate_brief_narratives` prompt, add:

```text
technical_verdict와 score_history가 있으면 technical_note와 next_check에 반영하라. 제공된 score와 action을 바꾸지 마라.
```

- [ ] **Step 5: Render verdict and trend**

In `_item_section`, after `가격/기술` line:

```python
if item.technical_verdict:
    verdict = item.technical_verdict
    reasons = verdict.get("reasons") or []
    cautions = verdict.get("cautions") or []
    trend = verdict.get("score_trend_summary")
    detail_parts = []
    if reasons:
        detail_parts.append(reasons[0])
    if cautions:
        detail_parts.append(f"주의: {cautions[0]}")
    if trend:
        detail_parts.append(trend)
    if detail_parts:
        lines.append(f"- **기술 Verdict**: {verdict.get('action')} — {' / '.join(detail_parts)}")
```

- [ ] **Step 6: Run brief tests**

Run:

```bash
uv run pytest tests/pipelines/test_brief.py tests/tools/brief/test_render.py tests/llm/test_brief_narratives.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/tools/brief/models.py src/tools/brief/render.py src/pipelines/brief.py src/llm/analyzer.py tests/pipelines/test_brief.py tests/tools/brief/test_render.py tests/llm/test_brief_narratives.py
git commit -m "feat: include technical verdict in brief"
```

---

### Task 9: Real Regression Fixtures

**Files:**
- Create: `tests/fixtures/technical/scoring/*.csv`
- Create: `tests/tools/technical/test_scoring_regression.py`

**Interfaces:**
- Consumes: saved OHLCV CSV fixtures
- Produces: regression assertions for PANW, BE, 005930.KS behavior

- [ ] **Step 1: Create fixture directory and fetch raw OHLCV once**

Run this command from repo root:

```bash
mkdir -p tests/fixtures/technical/scoring
uv run python - <<'PY'
from pathlib import Path

import yfinance as yf

targets = [
    ("PANW", "2026-03-01", "2026-05-15", "panw_2026-03-01_2026-05-14.csv"),
    ("BE", "2026-06-01", "2026-07-16", "be_2026-06-01_2026-07-15.csv"),
    ("005930.KS", "2026-06-01", "2026-07-17", "005930_ks_2026-06-01_2026-07-16.csv"),
]
out_dir = Path("tests/fixtures/technical/scoring")
for ticker, start, end, filename in targets:
    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if df.empty:
        raise SystemExit(f"empty fixture for {ticker}")
    if isinstance(df.columns, type(df.columns)) and getattr(df.columns, "nlevels", 1) > 1:
        df.columns = df.columns.get_level_values(0)
    keep = [c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in df.columns]
    df[keep].to_csv(out_dir / filename, index_label="Date")
    print(filename, len(df))
PY
```

Expected: three CSV files are created and each has more than 20 rows.

- [ ] **Step 2: Write regression tests**

```python
# tests/tools/technical/test_scoring_regression.py
from pathlib import Path

import pandas as pd

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer


FIXTURE_DIR = Path("tests/fixtures/technical/scoring")


def _load_fixture(name: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_DIR / name, parse_dates=["Date"], index_col="Date")
    return IndicatorCalculator().calculate(df)


def _score_until(df: pd.DataFrame, date: str):
    sliced = df.loc[:pd.Timestamp(date)]
    return TechnicalScorer().score(sliced, include_history=False)


def test_panw_entry_window_regression():
    df = _load_fixture("panw_2026-03-01_2026-05-14.csv")

    april_22 = _score_until(df, "2026-04-22")
    april_30 = _score_until(df, "2026-04-30")

    assert april_22.technical_verdict.action in {"buy", "add", "watch"}
    assert april_22.technical_verdict.action != "avoid"
    assert april_30.technical_verdict.action in {"add", "hold", "buy"}
    assert april_30.adjusted_score >= 35


def test_be_overextension_then_breakdown_regression():
    df = _load_fixture("be_2026-06-01_2026-07-15.csv")

    june_18 = _score_until(df, "2026-06-18")
    june_26 = _score_until(df, "2026-06-26")

    assert june_18.technical_verdict.action in {"hold", "watch"}
    assert june_18.technical_verdict.new_entry_allowed is False
    assert june_26.technical_verdict.action in {"reduce", "avoid", "watch"}


def test_samsung_breakdown_regression():
    df = _load_fixture("005930_ks_2026-06-01_2026-07-16.csv")

    july_02 = _score_until(df, "2026-07-02")

    assert july_02.technical_verdict.action in {"reduce", "avoid", "watch"}
    assert july_02.technical_verdict.new_entry_allowed is False
```

These assertions intentionally allow nearby verdicts. They pin the risk class and entry eligibility first, not exact score optimization.

- [ ] **Step 3: Run regression tests**

Run: `uv run pytest tests/tools/technical/test_scoring_regression.py -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/technical/scoring tests/tools/technical/test_scoring_regression.py
git commit -m "test: add technical scoring regression fixtures"
```

---

### Task 10: Documentation and Full Verification

**Files:**
- Modify: `docs/FEATURES.md`
- Create: `docs/changes/technical-scoring-redesign.md`
- Modify: `docs/changes/INDEX.md`

**Interfaces:**
- Consumes: implemented behavior and ADR-0010
- Produces: current-state docs and change record

- [ ] **Step 1: Update FEATURES**

Add a concise current-state entry under the technical analysis section:

```markdown
- 기술 점수는 component raw 합계(`component_raw_total`)와 context 조정 점수(`adjusted_score`)를 함께 제공한다. `technical_verdict`는 `buy/add/hold/watch/reduce/avoid` technical-only hint와 판단 이유, 주의점, 무효화 가격, 최근 5거래일 점수 추이를 포함한다.
```

- [ ] **Step 2: Add change record**

Create `docs/changes/technical-scoring-redesign.md`:

```markdown
# Technical Scoring Redesign

Status: In Progress
Date: 2026-07-16
PRs: -
Type: feat

## Why

기존 `total_score`는 component 단순합이라 추세 강도, 신규 진입 가능성, 보유 관리 신호가 한 숫자에 섞였다. 같은 높은 점수라도 신규 매수와 과열 보유의 의미가 달라질 수 있어 기술 점수의 행동 의미를 분리했다.

## Changes

### Added

- `component_raw_total`, `adjusted_score`, `technical_verdict`, `score_history`를 `TechnicalResult`에 추가했다.
- OHLCV derived state인 `MarketContext`와 context 기반 `ScoreAggregator`를 추가했다.
- ticker 분석 출력에 최종 technical verdict reason과 최근 5거래일 점수 추이를 추가했다.

### Changed

- `quick_check`, `deep_dive`, `brief`, `analyze_decision`이 `technical_verdict`를 우선 참고하되 기존 `total_score` fallback을 유지한다.

## Constraints

- raw OHLCV 별도 score는 만들지 않는다. (→ ADR-0010)
- `total_score`는 1차 구현에서 기존 component 단순합 계약을 유지한다. (→ ADR-0010)
- LLM은 점수와 verdict를 재판단하지 않고 설명만 한다. (→ ADR-0010)

## Tests

- `uv run pytest tests/tools/technical/test_scoring_models.py tests/tools/technical/test_market_context.py tests/tools/technical/test_score_aggregator.py tests/tools/technical/test_scorer.py tests/tools/technical/test_scoring_regression.py -v`
- `uv run pytest tests/pipelines/test_quick_check.py tests/pipelines/test_analyze_decision.py tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py -v`

## ADR

- `docs/adr/0010-technical-scoring-adjusted-verdict.md`
```

Add it to `docs/changes/INDEX.md` using the existing table/list format.

- [ ] **Step 3: Run focused test suite**

Run:

```bash
uv run pytest \
  tests/tools/technical/test_scoring_models.py \
  tests/tools/technical/test_market_context.py \
  tests/tools/technical/test_score_aggregator.py \
  tests/tools/technical/test_scorer.py \
  tests/tools/technical/test_tool_scorer_integration.py \
  tests/tools/technical/test_scoring_regression.py \
  tests/pipelines/test_quick_check.py \
  tests/pipelines/test_analyze_decision.py \
  tests/pipelines/test_deep_dive.py \
  tests/pipelines/test_brief.py \
  tests/tools/brief/test_render.py \
  tests/llm/test_analyzer.py \
  tests/llm/test_brief_narratives.py \
  -v
```

Expected: PASS.

- [ ] **Step 4: Run lint and full tests**

Run:

```bash
uv run ruff check src tests
uv run pytest
```

Expected: both PASS.

- [ ] **Step 5: Commit docs**

```bash
git add docs/FEATURES.md docs/changes/technical-scoring-redesign.md docs/changes/INDEX.md
git commit -m "docs: document technical scoring redesign"
```

---

## Self-Review Checklist

- Spec coverage:
  - `MarketContext`: Task 2
  - component metadata without string parsing: Task 3 and Task 4
  - `component_raw_total` and `adjusted_score`: Task 1 and Task 5
  - technical-only verdict: Task 1, Task 4, Task 7
  - reason/caution/invalidation fields: Task 1, Task 4, Task 6
  - recent 5거래일 score history: Task 5, Task 6, Task 8
  - quick_check/deep_dive/brief/analyze_decision wiring: Task 6, Task 7, Task 8
  - real regression fixtures: Task 9
  - docs and ADR linkage: Task 10
- Type consistency:
  - `signal_metadata` is the only structured component metadata field consumed by `ScoreAggregator`.
  - `total_score` remains component raw sum during compatibility period.
  - `TechnicalVerdict.action` uses English machine values: `buy`, `add`, `hold`, `watch`, `reduce`, `avoid`.
  - `score_history` stores machine values and one human-readable reason per date.
- Verification:
  - Task-local tests pass before each commit.
  - Focused suite and full suite pass before final handoff.
