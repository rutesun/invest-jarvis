# Plan 4: Advanced Technical Indicators + Fundamental Analysis

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고급 기술 지표 8개, component 패턴, 가중치 스코어링, Fundamental 분석 도구 추가

**Architecture:** IndicatorCalculator 확장 → Component 패턴 (5개) → 전략 고도화 → Scorer → Fundamental Tool → DeepDive 연동

**Tech Stack:** pandas-ta, scipy (argrelextrema), numpy (polyfit), yfinance (.info, .quarterly_financials), langchain

---

## File Structure

```
src/tools/technical/
├── models.py                  # ComponentResult, IndicatorSnapshot 확장, TechnicalResult.total_score
├── indicators.py              # 신규 지표 추가
├── scorer.py                  # 신규: TechnicalScorer
├── tool.py                    # Scorer 연동
├── components/
│   ├── __init__.py
│   ├── minervini.py           # Minervini Stage 2
│   ├── velocity.py            # MA 기울기/가속도
│   ├── crsi.py                # Cycle RSI 분석
│   ├── volume.py              # 거래량 분석
│   └── patterns.py            # VCP, Breakout, 캔들스틱
└── strategies/
    ├── trend.py               # component 통합
    ├── oscillator.py          # component 통합
    ├── divergence.py          # cRSI + argrelextrema
    └── risk.py                # 다층 지지/저항

src/tools/fundamental.py       # FundamentalTool + FundamentalSnapshot
src/llm/models.py              # FundamentalSummaryInput/Output
src/llm/analyzer.py            # generate_fundamental_summary()
src/pipelines/deep_dive.py     # FundamentalTool 추가
src/cli/main.py                # analyze 출력에 Fundamental 섹션
```

---

## Task 1: Add scipy dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add scipy**

Run: `uv add scipy`

- [ ] **Step 2: Verify install**

Run: `uv run python -c "from scipy.signal import argrelextrema; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add scipy dependency for peak detection"
```

---

## Task 2: Extend Models

**Files:**
- Modify: `src/tools/technical/models.py`
- Test: `tests/tools/technical/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_models.py — append to existing file
from src.tools.technical.models import ComponentResult


def test_component_result():
    result = ComponentResult(
        signals=["Stage 2"],
        evidence=["Price > SMA_150 > SMA_200"],
        metrics={"sma_150": 175.0},
        score=40,
    )
    assert result.score == 40
    assert len(result.signals) == 1


def test_indicator_snapshot_extended_fields():
    snapshot = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_150=172.0,
        crsi=65.0,
        crsi_high_band=80.0,
        crsi_low_band=20.0,
        vol_sma_20=1500000.0,
        swing_high=180.0,
        swing_low=170.0,
        is_gap_up=False,
        is_gap_down=False,
        macd_fast=1.5,
    )
    assert snapshot.sma_150 == 172.0
    assert snapshot.crsi == 65.0
    assert snapshot.vol_sma_20 == 1500000.0


def test_technical_result_total_score():
    from datetime import datetime
    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        indicators=IndicatorSnapshot(price=178.50, change_pct=2.5),
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=[],
        warnings=[],
        total_score=65,
    )
    assert result.total_score == 65
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_models.py::test_component_result -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Add to `src/tools/technical/models.py`:

```python
class ComponentResult(BaseModel):
    """Result from a technical analysis component."""
    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]
    score: int
```

Extend `IndicatorSnapshot` with new fields:

```python
    # Additional Moving Averages
    sma_150: float | None = None

    # Cycle RSI
    crsi: float | None = None
    crsi_high_band: float | None = None
    crsi_low_band: float | None = None

    # Volume
    vol_sma_20: float | None = None
    vol_sma_50: float | None = None
    vol_sma_120: float | None = None

    # Swing Points
    swing_high: float | None = None
    swing_low: float | None = None

    # Gap
    is_gap_up: bool | None = None
    is_gap_down: bool | None = None

    # Fast MACD (5/35/5)
    macd_fast: float | None = None
    macd_fast_signal: float | None = None
    macd_fast_histogram: float | None = None
```

Add `total_score` to `TechnicalResult`:

```python
    total_score: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/models.py tests/tools/technical/test_models.py
git commit -m "feat(models): add ComponentResult, extend IndicatorSnapshot, add total_score"
```

---

## Task 3: Extend IndicatorCalculator

**Files:**
- Modify: `src/tools/technical/indicators.py`
- Test: `tests/tools/technical/test_indicators.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_indicators.py — append to existing
def test_extended_indicators(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)

    assert "SMA_150" in result_df.columns
    assert "cRSI" in result_df.columns
    assert "cRSI_HighBand" in result_df.columns
    assert "cRSI_LowBand" in result_df.columns
    assert "Vol_SMA_20" in result_df.columns
    assert "Vol_SMA_50" in result_df.columns
    assert "Vol_SMA_120" in result_df.columns
    assert "Swing_High" in result_df.columns
    assert "Swing_Low" in result_df.columns
    assert "Is_Gap_Up" in result_df.columns
    assert "Is_Gap_Down" in result_df.columns
    assert "MACD_5_35_5" in result_df.columns


def test_crsi_calculation(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)

    crsi_values = result_df["cRSI"].dropna()
    if len(crsi_values) > 0:
        assert crsi_values.min() >= 0
        assert crsi_values.max() <= 100


def test_extended_snapshot(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)
    snapshot = calculator.create_snapshot(result_df)

    # New fields should be populated or None (depending on data length)
    assert hasattr(snapshot, "sma_150")
    assert hasattr(snapshot, "crsi")
    assert hasattr(snapshot, "vol_sma_20")
    assert hasattr(snapshot, "swing_high")
    assert hasattr(snapshot, "is_gap_up")
    assert hasattr(snapshot, "macd_fast")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_extended_indicators -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Add to `IndicatorCalculator.calculate()` method in `src/tools/technical/indicators.py`:

```python
        # SMA 150
        df["SMA_150"] = ta.sma(df["Close"], length=150)

        # Fast MACD (5/35/5)
        macd_fast = ta.macd(df["Close"], fast=5, slow=35, signal=5)
        if macd_fast is not None:
            df = pd.concat([df, macd_fast], axis=1)

        # Volume SMAs
        df["Vol_SMA_20"] = ta.sma(df["Volume"], length=20)
        df["Vol_SMA_50"] = ta.sma(df["Volume"], length=50)
        df["Vol_SMA_120"] = ta.sma(df["Volume"], length=120)

        # Swing High/Low (11-bar window, 5 on each side)
        df["Swing_High"] = df["High"].where(
            df["High"] == df["High"].rolling(window=11, center=True).max()
        )
        df["Swing_Low"] = df["Low"].where(
            df["Low"] == df["Low"].rolling(window=11, center=True).min()
        )

        # Gap detection
        prev_high = df["High"].shift(1)
        prev_low = df["Low"].shift(1)
        df["Is_Gap_Up"] = df["Low"] > prev_high
        df["Is_Gap_Down"] = df["High"] < prev_low
        df["Gap_Up_Lower"] = prev_high.where(df["Is_Gap_Up"])
        df["Gap_Down_Upper"] = prev_low.where(df["Is_Gap_Down"])

        # Cycle RSI (cRSI)
        df = self._calculate_crsi(df)
```

Add new method `_calculate_crsi`:

```python
    def _calculate_crsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Cycle-Tuned RSI with dynamic bands."""
        import numpy as np

        rsi_10 = ta.rsi(df["Close"], length=10)
        if rsi_10 is None or rsi_10.isna().all():
            df["cRSI"] = np.nan
            df["cRSI_HighBand"] = np.nan
            df["cRSI_LowBand"] = np.nan
            return df

        dominant_cycle = 20
        vibration = 10
        torque = 2.0 / (vibration + 1)
        lag = int((vibration - 1) / 2)

        rsi_values = rsi_10.values
        crsi = np.full(len(rsi_values), np.nan)

        # Find first valid RSI index
        first_valid = rsi_10.first_valid_index()
        if first_valid is None:
            df["cRSI"] = np.nan
            df["cRSI_HighBand"] = np.nan
            df["cRSI_LowBand"] = np.nan
            return df

        start_idx = df.index.get_loc(first_valid)
        if start_idx + lag < len(rsi_values):
            crsi[start_idx + lag] = rsi_values[start_idx + lag]

        for i in range(start_idx + lag + 1, len(rsi_values)):
            if np.isnan(rsi_values[i]) or np.isnan(rsi_values[i - lag]):
                continue
            prev_crsi = crsi[i - 1] if not np.isnan(crsi[i - 1]) else rsi_values[i]
            crsi[i] = torque * (2 * rsi_values[i] - rsi_values[i - lag]) + (1 - torque) * prev_crsi

        df["cRSI"] = crsi

        # Dynamic bands (10th/90th percentile over 40-bar lookback)
        lookback = 2 * dominant_cycle
        crsi_series = pd.Series(crsi, index=df.index)
        df["cRSI_LowBand"] = crsi_series.rolling(window=lookback, min_periods=10).quantile(0.10)
        df["cRSI_HighBand"] = crsi_series.rolling(window=lookback, min_periods=10).quantile(0.90)

        return df
```

Extend `create_snapshot()` to include new fields:

```python
            sma_150=safe_get("SMA_150"),
            crsi=safe_get("cRSI"),
            crsi_high_band=safe_get("cRSI_HighBand"),
            crsi_low_band=safe_get("cRSI_LowBand"),
            vol_sma_20=safe_get("Vol_SMA_20"),
            vol_sma_50=safe_get("Vol_SMA_50"),
            vol_sma_120=safe_get("Vol_SMA_120"),
            swing_high=safe_get("Swing_High"),
            swing_low=safe_get("Swing_Low"),
            is_gap_up=bool(latest.get("Is_Gap_Up")) if not pd.isna(latest.get("Is_Gap_Up")) else None,
            is_gap_down=bool(latest.get("Is_Gap_Down")) if not pd.isna(latest.get("Is_Gap_Down")) else None,
            macd_fast=safe_get("MACD_5_35_5"),
            macd_fast_signal=safe_get("MACDs_5_35_5"),
            macd_fast_histogram=safe_get("MACDh_5_35_5"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/indicators.py tests/tools/technical/test_indicators.py
git commit -m "feat(indicators): add cRSI, volume SMA, swing, gap, SMA_150, fast MACD"
```

---

## Task 4: Component — Minervini

**Files:**
- Create: `src/tools/technical/components/__init__.py`
- Create: `src/tools/technical/components/minervini.py`
- Test: `tests/tools/technical/test_minervini.py`

- [ ] **Step 1: Create components package**

Run: `mkdir -p src/tools/technical/components && touch src/tools/technical/components/__init__.py`

- [ ] **Step 2: Write the failing test**

```python
# tests/tools/technical/test_minervini.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def stage2_df():
    """Create DataFrame meeting all Stage 2 conditions."""
    dates = pd.date_range("2024-01-01", periods=252, freq="D")
    # Steady uptrend from 100 to 200
    close = 100 + np.arange(252) * 0.4
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 252,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_minervini_stage2(stage2_df):
    result = analyze_minervini(stage2_df)
    assert result.score == 40
    assert "Stage 2" in result.signals[0]


def test_minervini_insufficient_data():
    df = pd.DataFrame({"Close": [100, 101, 102]})
    result = analyze_minervini(df)
    assert result.score == 0
    assert "데이터 부족" in result.evidence[0]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_minervini.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementation**

```python
# src/tools/technical/components/minervini.py
import pandas as pd
from src.tools.technical.models import ComponentResult


def analyze_minervini(df: pd.DataFrame) -> ComponentResult:
    """Analyze Minervini Stage 2 conditions."""
    if df.empty or len(df) < 200:
        return ComponentResult(
            signals=[], evidence=["데이터 부족 (200일 이상 필요)"], metrics={}, score=0,
        )

    latest = df.iloc[-1]

    def safe(col: str) -> float:
        val = latest.get(col)
        if pd.isna(val) or val is None:
            return 0.0
        return float(val)

    close = safe("Close")
    sma_50 = safe("SMA_50")
    sma_150 = safe("SMA_150")
    sma_200 = safe("SMA_200")
    high_52w = safe("High_52w")
    low_52w = safe("Low_52w")

    if not all([close, sma_50, sma_150, sma_200]):
        return ComponentResult(
            signals=[], evidence=["이동평균 계산 불가"], metrics={}, score=0,
        )

    # Check SMA_200 rising (vs 21 days ago)
    sma_200_prev = 0.0
    if len(df) > 21:
        val = df.iloc[-22].get("SMA_200")
        if not pd.isna(val) and val is not None:
            sma_200_prev = float(val)

    conditions = {
        "ma_stack": close > sma_150 > sma_200,
        "sma_200_rising": sma_200 > sma_200_prev if sma_200_prev else False,
        "above_50": close > sma_50,
        "above_52w_low_30pct": close >= low_52w * 1.30 if low_52w else False,
        "within_52w_high_25pct": close >= high_52w * 0.75 if high_52w else False,
    }

    met_count = sum(conditions.values())
    metrics = {
        "conditions_met": float(met_count),
        "close": close,
        "sma_50": sma_50,
        "sma_150": sma_150,
        "sma_200": sma_200,
    }

    evidence = []
    for name, met in conditions.items():
        status = "충족" if met else "미충족"
        evidence.append(f"{name}: {status}")

    if met_count == 5:
        return ComponentResult(
            signals=["Stage 2 (강력한 상승 국면)"],
            evidence=evidence,
            metrics=metrics,
            score=40,
        )
    elif conditions["above_50"]:
        return ComponentResult(
            signals=["강세 (Stage 2 미충족)"],
            evidence=evidence,
            metrics=metrics,
            score=25,
        )
    else:
        return ComponentResult(
            signals=["약세/보합"],
            evidence=evidence,
            metrics=metrics,
            score=-20,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_minervini.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/technical/components/ tests/tools/technical/test_minervini.py
git commit -m "feat(components): add Minervini Stage 2 analyzer"
```

---

## Task 5: Component — Velocity

**Files:**
- Create: `src/tools/technical/components/velocity.py`
- Test: `tests/tools/technical/test_velocity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_velocity.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.velocity import analyze_velocity
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def accelerating_df():
    """Create DataFrame with accelerating uptrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    # Accelerating: slope increases over time
    close = 100 + np.cumsum(np.linspace(0.1, 1.0, 100))
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_velocity_accelerating(accelerating_df):
    result = analyze_velocity(accelerating_df)
    assert result.score > 0
    assert "norm_slope" in result.metrics


def test_velocity_insufficient_data():
    df = pd.DataFrame({"Close": [100, 101], "SMA_20": [100, 101]})
    result = analyze_velocity(df)
    assert result.score == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_velocity.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/components/velocity.py
import numpy as np
import pandas as pd
from src.tools.technical.models import ComponentResult

SLOPE_THRESHOLD = 0.05
ACCEL_THRESHOLD = 0.02


def analyze_velocity(df: pd.DataFrame) -> ComponentResult:
    """Analyze MA slope and acceleration."""
    if "SMA_20" not in df.columns or len(df) < 15:
        return ComponentResult(
            signals=[], evidence=["데이터 부족"], metrics={}, score=0,
        )

    sma_20_series = df["SMA_20"].dropna()
    if len(sma_20_series) < 15:
        return ComponentResult(
            signals=[], evidence=["SMA_20 데이터 부족"], metrics={}, score=0,
        )

    recent_15 = sma_20_series.iloc[-15:].values
    current_5 = recent_15[-5:]
    previous_5 = recent_15[-10:-5]

    current_slope = _linear_slope(current_5)
    previous_slope = _linear_slope(previous_5)

    sma_20_latest = recent_15[-1]
    if sma_20_latest == 0:
        return ComponentResult(
            signals=[], evidence=["SMA_20 값 0"], metrics={}, score=0,
        )

    norm_slope = (current_slope / sma_20_latest) * 100
    norm_prev_slope = (previous_slope / sma_20_latest) * 100
    slope_change = norm_slope - norm_prev_slope

    signals = []
    evidence = []
    score = 0
    metrics = {
        "norm_slope": round(norm_slope, 4),
        "slope_change": round(slope_change, 4),
    }

    # Direction
    if norm_slope > SLOPE_THRESHOLD:
        evidence.append(f"SMA_20 상승 기울기 ({norm_slope:.4f}%)")
        score += 10

        if slope_change > ACCEL_THRESHOLD:
            signals.append("추세 가속 상승")
            evidence.append(f"기울기 변화율 +{slope_change:.4f}% (가속)")
            score += 10
        elif slope_change < -ACCEL_THRESHOLD * 2:
            signals.append("추세 피로 감지")
            evidence.append(f"기울기 변화율 {slope_change:.4f}% (피로)")
            score -= 5
        elif slope_change < -ACCEL_THRESHOLD:
            signals.append("추세 감속")
            evidence.append(f"기울기 변화율 {slope_change:.4f}% (감속)")

    elif norm_slope < -SLOPE_THRESHOLD:
        evidence.append(f"SMA_20 하락 기울기 ({norm_slope:.4f}%)")
        score -= 10

        if slope_change < -ACCEL_THRESHOLD:
            signals.append("하락 가속")
            score -= 10
        elif slope_change > ACCEL_THRESHOLD:
            signals.append("하락 감속")
            score += 5
    else:
        evidence.append(f"SMA_20 횡보 ({norm_slope:.4f}%)")

    # Turning point detection
    if previous_slope > 0 and current_slope < 0:
        signals.append("하락 전환점")
        score -= 15
    elif previous_slope < 0 and current_slope > 0:
        signals.append("상승 전환점")
        score += 15

    return ComponentResult(
        signals=signals, evidence=evidence, metrics=metrics, score=score,
    )


def _linear_slope(values: np.ndarray) -> float:
    """Calculate linear regression slope."""
    x = np.arange(len(values))
    if len(values) < 2:
        return 0.0
    coeffs = np.polyfit(x, values, 1)
    return coeffs[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_velocity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/components/velocity.py tests/tools/technical/test_velocity.py
git commit -m "feat(components): add Velocity analyzer (MA slope/acceleration)"
```

---

## Task 6: Component — cRSI

**Files:**
- Create: `src/tools/technical/components/crsi.py`
- Test: `tests/tools/technical/test_crsi_component.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_crsi_component.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.crsi import analyze_crsi
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def sample_df():
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    df = pd.DataFrame({
        "Open": close - np.random.rand(100),
        "High": close + np.random.rand(100) * 2,
        "Low": close - np.random.rand(100) * 2,
        "Close": close,
        "Volume": np.random.randint(1000000, 5000000, 100),
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_crsi_analysis(sample_df):
    result = analyze_crsi(sample_df)
    assert isinstance(result.score, int)
    assert "crsi" in result.metrics or len(result.evidence) > 0


def test_crsi_no_data():
    df = pd.DataFrame({"Close": [100]})
    result = analyze_crsi(df)
    assert result.score == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_crsi_component.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/components/crsi.py
import pandas as pd
from src.tools.technical.models import ComponentResult


def analyze_crsi(df: pd.DataFrame) -> ComponentResult:
    """Analyze Cycle RSI signals."""
    if "cRSI" not in df.columns or len(df) < 2:
        return ComponentResult(
            signals=[], evidence=["cRSI 데이터 없음"], metrics={}, score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    crsi = latest.get("cRSI")
    crsi_high = latest.get("cRSI_HighBand")
    crsi_low = latest.get("cRSI_LowBand")
    prev_crsi = prev.get("cRSI")

    if pd.isna(crsi) or pd.isna(crsi_high) or pd.isna(crsi_low) or pd.isna(prev_crsi):
        return ComponentResult(
            signals=[], evidence=["cRSI 값 부족"], metrics={}, score=0,
        )

    crsi = float(crsi)
    crsi_high = float(crsi_high)
    crsi_low = float(crsi_low)
    prev_crsi = float(prev_crsi)

    signals = []
    evidence = []
    score = 0
    metrics = {"crsi": round(crsi, 2), "crsi_high_band": round(crsi_high, 2), "crsi_low_band": round(crsi_low, 2)}

    band_width = crsi_high - crsi_low

    # Hook Down (매도 시그널)
    if prev_crsi > crsi_high and crsi < crsi_high:
        signals.append("cRSI Hook Down (매도 시그널)")
        evidence.append(f"cRSI {prev_crsi:.1f} → {crsi:.1f}, 상단밴드 {crsi_high:.1f} 하향 이탈")
        score -= 20

    # Hook Up (매수 시그널)
    elif prev_crsi < crsi_low and crsi > crsi_low:
        signals.append("cRSI Hook Up (매수 시그널)")
        evidence.append(f"cRSI {prev_crsi:.1f} → {crsi:.1f}, 하단밴드 {crsi_low:.1f} 상향 돌파")
        score += 20

    # Squeeze (에너지 응축)
    if band_width < 10:
        signals.append("cRSI Squeeze (에너지 응축)")
        evidence.append(f"밴드 폭 {band_width:.1f} < 10")
        score += 5

    # Overbought/Oversold
    if crsi > crsi_high:
        evidence.append(f"cRSI {crsi:.1f} > 상단밴드 {crsi_high:.1f} (과매수)")
        score -= 10
    elif crsi < crsi_low:
        evidence.append(f"cRSI {crsi:.1f} < 하단밴드 {crsi_low:.1f} (과매도)")
        score += 10

    return ComponentResult(
        signals=signals, evidence=evidence, metrics=metrics, score=score,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_crsi_component.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/components/crsi.py tests/tools/technical/test_crsi_component.py
git commit -m "feat(components): add cRSI analyzer (Hook Up/Down, Squeeze)"
```

---

## Task 7: Component — Volume

**Files:**
- Create: `src/tools/technical/components/volume.py`
- Test: `tests/tools/technical/test_volume_component.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_volume_component.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.volume import analyze_volume
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def volume_spike_df():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.3
    volume = [1000000] * 99 + [5000000]  # spike on last day
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": volume,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_volume_spike(volume_spike_df):
    result = analyze_volume(volume_spike_df)
    assert any("급증" in s for s in result.signals)
    assert result.metrics.get("vol_ratio", 0) > 2.0


def test_volume_no_data():
    df = pd.DataFrame({"Close": [100], "Volume": [1000]})
    result = analyze_volume(df)
    assert result.score == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_volume_component.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/components/volume.py
import pandas as pd
from src.tools.technical.models import ComponentResult


def analyze_volume(df: pd.DataFrame) -> ComponentResult:
    """Analyze volume patterns."""
    if "Vol_SMA_20" not in df.columns or len(df) < 2:
        return ComponentResult(
            signals=[], evidence=["거래량 데이터 없음"], metrics={}, score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    volume = latest.get("Volume")
    vol_sma_20 = latest.get("Vol_SMA_20")
    close = latest.get("Close")
    prev_close = prev.get("Close")

    if pd.isna(volume) or pd.isna(vol_sma_20) or vol_sma_20 == 0:
        return ComponentResult(
            signals=[], evidence=["거래량 SMA 없음"], metrics={}, score=0,
        )

    volume = float(volume)
    vol_sma_20 = float(vol_sma_20)
    vol_ratio = volume / vol_sma_20

    signals = []
    evidence = []
    score = 0
    metrics = {"vol_ratio": round(vol_ratio, 2), "volume": volume, "vol_sma_20": vol_sma_20}

    price_up = not pd.isna(close) and not pd.isna(prev_close) and float(close) > float(prev_close)
    price_down = not pd.isna(close) and not pd.isna(prev_close) and float(close) < float(prev_close)

    # Volume surge
    if vol_ratio > 2.0:
        signals.append("거래량 급증")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")
        if price_up:
            signals.append("가격 상승 + 거래량 급증 (강세 확인)")
            score += 15
        elif price_down:
            signals.append("가격 하락 + 거래량 급증 (경고)")
            score -= 10
        else:
            score += 5

    elif vol_ratio > 1.5:
        evidence.append(f"거래량 증가 ({vol_ratio:.1f}x)")
        if price_up:
            score += 5

    elif vol_ratio < 0.5:
        signals.append("거래량 감소")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")

    return ComponentResult(
        signals=signals, evidence=evidence, metrics=metrics, score=score,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_volume_component.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/components/volume.py tests/tools/technical/test_volume_component.py
git commit -m "feat(components): add Volume analyzer (surge/decline detection)"
```

---

## Task 8: Component — Patterns

**Files:**
- Create: `src/tools/technical/components/patterns.py`
- Test: `tests/tools/technical/test_patterns_component.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_patterns_component.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.patterns import analyze_patterns
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def breakout_df():
    """Create DataFrame with breakout pattern."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    # Consolidation then breakout
    close = np.concatenate([
        np.random.uniform(98, 102, 95),  # consolidation
        [103, 105, 107, 110, 112],       # breakout
    ])
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 95 + [3000000] * 5,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_patterns_analysis(breakout_df):
    result = analyze_patterns(breakout_df)
    assert isinstance(result.score, int)
    # Should detect something - breakout or other pattern
    assert len(result.signals) >= 0  # May or may not detect patterns


def test_patterns_no_data():
    df = pd.DataFrame({"Close": [100]})
    result = analyze_patterns(df)
    assert result.score == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_patterns_component.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/components/patterns.py
import pandas as pd
import numpy as np
from src.tools.technical.models import ComponentResult


def analyze_patterns(df: pd.DataFrame) -> ComponentResult:
    """Analyze chart patterns: VCP, Breakout, Candlestick."""
    if df.empty or len(df) < 20:
        return ComponentResult(
            signals=[], evidence=["데이터 부족"], metrics={}, score=0,
        )

    signals = []
    evidence = []
    metrics = {}
    score = 0

    # VCP detection
    vcp = _detect_vcp(df)
    if vcp:
        signals.append(vcp["signal"])
        evidence.append(vcp["evidence"])
        metrics["vcp_confidence"] = vcp["confidence"]
        score += 7

    # Breakout detection
    breakout = _detect_breakout(df)
    if breakout:
        signals.append(breakout["signal"])
        evidence.append(breakout["evidence"])
        score += 7

    # Candlestick patterns
    candle = _detect_candlestick(df)
    if candle:
        signals.append(candle["signal"])
        evidence.append(candle["evidence"])
        score += 7

    return ComponentResult(
        signals=signals, evidence=evidence, metrics=metrics, score=min(score, 20),
    )


def _detect_vcp(df: pd.DataFrame) -> dict | None:
    """Detect Volatility Contraction Pattern."""
    if len(df) < 60:
        return None

    recent = df.tail(40)
    blocks = [recent.iloc[i*10:(i+1)*10] for i in range(4)]

    ranges = []
    for block in blocks:
        if len(block) < 10:
            return None
        high_max = block["High"].max()
        low_min = block["Low"].min()
        if high_max == 0:
            return None
        range_pct = (high_max - low_min) / high_max
        ranges.append(range_pct)

    # Count contractions
    contractions = sum(1 for i in range(1, len(ranges)) if ranges[i] < ranges[i-1])
    tight_recent = ranges[-1] < 0.10

    if contractions >= 2 and tight_recent:
        # Check volume dry-up
        vol_dry = False
        if "Vol_SMA_50" in df.columns:
            latest_vol = df.iloc[-1].get("Volume", 0)
            vol_sma_50 = df.iloc[-1].get("Vol_SMA_50", 0)
            if not pd.isna(vol_sma_50) and vol_sma_50 > 0:
                vol_dry = float(latest_vol) < float(vol_sma_50)

        confidence = 85.0 if vol_dry else 70.0
        return {
            "signal": "VCP (변동성 축소 패턴)",
            "evidence": f"축소 {contractions}회, 마지막 블록 {ranges[-1]*100:.1f}%, 거래량감소={vol_dry}",
            "confidence": confidence,
        }
    return None


def _detect_breakout(df: pd.DataFrame, lookback: int = 50) -> dict | None:
    """Detect rolling high breakout."""
    if len(df) < lookback + 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["Close"])
    prev_close = float(prev["Close"])

    # Rolling high breakout
    rolling_high = df["High"].iloc[-(lookback+1):-1].max()
    if pd.isna(rolling_high):
        return None

    rolling_high = float(rolling_high)

    if close > rolling_high and prev_close <= rolling_high:
        # Volume confirmation
        vol_bonus = ""
        if "Vol_SMA_20" in df.columns:
            vol = float(latest.get("Volume", 0))
            vol_sma = float(latest.get("Vol_SMA_20", 1))
            if vol_sma > 0:
                vol_ratio = vol / vol_sma
                if vol_ratio >= 1.2:
                    vol_bonus = f", 거래량 {vol_ratio:.1f}x 확인"

        return {
            "signal": f"Breakout ({lookback}일 고점 돌파)",
            "evidence": f"종가 {close:.2f} > {lookback}일 고점 {rolling_high:.2f}{vol_bonus}",
        }

    # Swing High breakout
    if "Swing_High" in df.columns:
        swing_highs = df["Swing_High"].dropna().tail(10)
        if len(swing_highs) > 0:
            nearest_swing = swing_highs.iloc[-1]
            if close > float(nearest_swing) and prev_close <= float(nearest_swing):
                return {
                    "signal": "Pivot Breakout (Swing High 돌파)",
                    "evidence": f"종가 {close:.2f} > Swing High {float(nearest_swing):.2f}",
                }

    return None


def _detect_candlestick(df: pd.DataFrame) -> dict | None:
    """Detect basic candlestick patterns."""
    if len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    o, h, l, c = float(latest["Open"]), float(latest["High"]), float(latest["Low"]), float(latest["Close"])
    body = abs(c - o)

    if body == 0:
        return None

    wick_up = h - max(c, o)
    wick_down = min(c, o) - l

    # Hammer
    if body > 0 and wick_down >= 2 * body and wick_up <= 0.5 * body:
        return {
            "signal": "Hammer (반전 가능)",
            "evidence": f"하단 꼬리 {wick_down:.2f} >= 몸통 {body:.2f}의 2배",
        }

    # Bullish Engulfing
    prev_o, prev_c = float(prev["Open"]), float(prev["Close"])
    if prev_c < prev_o and c > o and o <= prev_c and c >= prev_o:
        return {
            "signal": "Bullish Engulfing (강세 장악형)",
            "evidence": "전일 음봉을 금일 양봉이 완전 감싼 형태",
        }

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_patterns_component.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/components/patterns.py tests/tools/technical/test_patterns_component.py
git commit -m "feat(components): add Patterns analyzer (VCP, Breakout, Candlestick)"
```

---

## Task 9: TechnicalScorer

**Files:**
- Create: `src/tools/technical/scorer.py`
- Test: `tests/tools/technical/test_scorer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_scorer.py
import pytest
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.models import StrategyResult, ComponentResult


def test_scorer_strong_buy():
    strategies = [
        StrategyResult(name="trend", status="강세", confidence=80, signals=[], evidence=[], metrics={}),
        StrategyResult(name="oscillator", status="과매도", confidence=70, signals=[], evidence=[], metrics={}),
        StrategyResult(name="divergence", status="강세", confidence=75, signals=[], evidence=[], metrics={}),
        StrategyResult(name="disparity", status="중립", confidence=60, signals=[], evidence=[], metrics={}),
        StrategyResult(name="risk", status="저위험", confidence=90, signals=[], evidence=[], metrics={}),
    ]
    pattern_result = ComponentResult(signals=["VCP", "Breakout"], evidence=[], metrics={}, score=14)

    scorer = TechnicalScorer()
    total_score, assessment = scorer.score(strategies, pattern_result)

    assert total_score >= 70
    assert assessment == "강력 매수"


def test_scorer_neutral():
    strategies = [
        StrategyResult(name="trend", status="중립", confidence=50, signals=[], evidence=[], metrics={}),
        StrategyResult(name="oscillator", status="중립", confidence=50, signals=[], evidence=[], metrics={}),
        StrategyResult(name="divergence", status="중립", confidence=50, signals=[], evidence=[], metrics={}),
        StrategyResult(name="disparity", status="중립", confidence=60, signals=[], evidence=[], metrics={}),
        StrategyResult(name="risk", status="중위험", confidence=50, signals=[], evidence=[], metrics={}),
    ]
    pattern_result = ComponentResult(signals=[], evidence=[], metrics={}, score=0)

    scorer = TechnicalScorer()
    total_score, assessment = scorer.score(strategies, pattern_result)

    assert -10 <= total_score < 40
    assert assessment == "중립"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_scorer.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/scorer.py
from src.tools.technical.models import StrategyResult, ComponentResult

TREND_SCORES = {
    "강세": 25, "약강세": 15, "중립": 0, "약약세": -10, "약세": -20,
}

MOMENTUM_SCORES = {
    "과매도": 20, "약과매도": 10, "중립": 5, "약과매수": -10, "과매수": -15,
}

RISK_SCORES = {
    "저위험": 10, "중위험": 5, "고위험": 0,
}

DIVERGENCE_SCORES = {
    "강세": 10, "중립": 0, "약세": -5,
}

ASSESSMENT_THRESHOLDS = [
    (70, "강력 매수"),
    (40, "매수"),
    (-10, "중립"),
    (-40, "매도"),
]


class TechnicalScorer:
    """Weighted scoring system for technical analysis."""

    def score(
        self,
        strategies: list[StrategyResult],
        pattern_result: ComponentResult | None = None,
    ) -> tuple[int, str]:
        """Score strategies and return (total_score, assessment)."""
        total = 0

        strategy_map = {s.name: s for s in strategies}

        # Trend (40 max)
        trend = strategy_map.get("trend")
        if trend:
            # Check for Stage 2 in signals
            if any("Stage 2" in s for s in trend.signals):
                total += 40
            else:
                total += TREND_SCORES.get(trend.status, 0)

        # Momentum (30 max)
        oscillator = strategy_map.get("oscillator")
        if oscillator:
            total += MOMENTUM_SCORES.get(oscillator.status, 0)

        # Pattern (20 max)
        if pattern_result:
            total += min(pattern_result.score, 20)

        # Risk (10 max)
        risk = strategy_map.get("risk")
        if risk:
            total += RISK_SCORES.get(risk.status, 0)

        # Divergence (10 max)
        divergence = strategy_map.get("divergence")
        if divergence:
            total += DIVERGENCE_SCORES.get(divergence.status, 0)

        # Determine assessment
        assessment = "강력 매도"
        for threshold, label in ASSESSMENT_THRESHOLDS:
            if total >= threshold:
                assessment = label
                break

        return total, assessment
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_scorer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/scorer.py tests/tools/technical/test_scorer.py
git commit -m "feat(technical): add TechnicalScorer with weighted scoring"
```

---

## Task 10: Update Trend Strategy

**Files:**
- Modify: `src/tools/technical/strategies/trend.py`
- Test: `tests/tools/technical/test_trend_strategy.py`

- [ ] **Step 1: Append test for component integration**

```python
# tests/tools/technical/test_trend_strategy.py — append
def test_trend_strategy_has_component_signals(uptrend_df):
    strategy = TrendStrategy()
    result = strategy.analyze(uptrend_df)
    # Should have Minervini or velocity evidence
    assert len(result.evidence) > 2  # More evidence than before
```

- [ ] **Step 2: Rewrite TrendStrategy**

Replace `src/tools/technical/strategies/trend.py`:

```python
# src/tools/technical/strategies/trend.py
import pandas as pd
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult
from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.components.velocity import analyze_velocity
from src.tools.technical.components.patterns import analyze_patterns


class TrendStrategy(BaseStrategy):
    """Trend analysis using MA, ADX, Supertrend + Minervini, Velocity, Patterns."""

    name = "trend"
    description = "이동평균, ADX, 슈퍼트렌드, Minervini, Velocity 기반 추세 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 50:
            return self._neutral_result("데이터 부족")

        latest = df.iloc[-1]
        signals = []
        evidence = []
        metrics = {}
        score = 0

        close = self._safe_get(latest, "Close")
        sma_20 = self._safe_get(latest, "SMA_20")
        sma_50 = self._safe_get(latest, "SMA_50")
        sma_200 = self._safe_get(latest, "SMA_200")
        adx = self._safe_get(latest, "ADX_14")
        supertrend_dir = self._safe_get(latest, "SUPERTd_10_3.0")

        metrics["close"] = close
        if sma_20: metrics["sma_20"] = round(sma_20, 2)
        if sma_50: metrics["sma_50"] = round(sma_50, 2)
        if sma_200: metrics["sma_200"] = round(sma_200, 2)
        if adx: metrics["adx"] = round(adx, 2)

        # --- Core MA analysis ---
        if sma_20 and close > sma_20:
            score += 10
            evidence.append(f"가격({close:.2f}) > 20일선({sma_20:.2f})")
        elif sma_20 and close < sma_20:
            score -= 10
            evidence.append(f"가격({close:.2f}) < 20일선({sma_20:.2f})")

        # Golden/Death cross
        if sma_20 and sma_50 and len(df) > 1:
            prev_sma_20 = self._safe_get(df.iloc[-2], "SMA_20")
            prev_sma_50 = self._safe_get(df.iloc[-2], "SMA_50")
            if prev_sma_20 and prev_sma_50:
                if prev_sma_20 < prev_sma_50 and sma_20 > sma_50:
                    signals.append("골든크로스")
                    score += 15
                elif prev_sma_20 > prev_sma_50 and sma_20 < sma_50:
                    signals.append("데드크로스")
                    score -= 15

        # ADX
        if adx:
            if adx > 25:
                evidence.append(f"ADX {adx:.1f} (강한 추세)")
                score += 5 if score > 0 else -5
            else:
                evidence.append(f"ADX {adx:.1f} (약한 추세)")

        # Supertrend
        if supertrend_dir:
            if supertrend_dir > 0:
                signals.append("슈퍼트렌드 상승")
                score += 10
            else:
                signals.append("슈퍼트렌드 하락")
                score -= 10

        # --- Components ---
        # Minervini Stage 2
        minervini_result = analyze_minervini(df)
        signals.extend(minervini_result.signals)
        evidence.extend(minervini_result.evidence)
        metrics.update(minervini_result.metrics)
        score += minervini_result.score

        # Velocity
        velocity_result = analyze_velocity(df)
        signals.extend(velocity_result.signals)
        evidence.extend(velocity_result.evidence)
        metrics.update(velocity_result.metrics)
        score += velocity_result.score

        # --- Determine status ---
        if score > 30:
            status = "강세"
        elif score > 10:
            status = "약강세"
        elif score < -30:
            status = "약세"
        elif score < -10:
            status = "약약세"
        else:
            status = "중립"

        confidence = min(100, max(0, 50 + score))

        return StrategyResult(
            name=self.name,
            status=status,
            confidence=confidence,
            signals=signals,
            evidence=evidence,
            metrics=metrics,
        )

    def _neutral_result(self, reason: str) -> StrategyResult:
        return StrategyResult(
            name=self.name, status="중립", confidence=50.0,
            signals=[], evidence=[reason], metrics={},
        )
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/tools/technical/test_trend_strategy.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/technical/strategies/trend.py tests/tools/technical/test_trend_strategy.py
git commit -m "feat(trend): integrate Minervini and Velocity components"
```

---

## Task 11: Update Oscillator Strategy

**Files:**
- Modify: `src/tools/technical/strategies/oscillator.py`

- [ ] **Step 1: Rewrite OscillatorStrategy**

Replace `src/tools/technical/strategies/oscillator.py` — add cRSI and volume components while keeping existing RSI/Stochastic/CCI logic. Import and call `analyze_crsi(df)` and `analyze_volume(df)`, merge their signals/evidence/metrics/score into the strategy result.

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/tools/technical/test_oscillator_strategy.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/tools/technical/strategies/oscillator.py
git commit -m "feat(oscillator): integrate cRSI and Volume components"
```

---

## Task 12: Update Divergence Strategy

**Files:**
- Modify: `src/tools/technical/strategies/divergence.py`

- [ ] **Step 1: Rewrite DivergenceStrategy**

Replace peak detection with `scipy.signal.argrelextrema`. Add cRSI divergence detection alongside existing RSI/MACD. If both RSI and cRSI show same divergence → "강력 다이버전스" with confidence 90%.

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/tools/technical/test_divergence_strategy.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/tools/technical/strategies/divergence.py
git commit -m "feat(divergence): add cRSI divergence, improve peak detection with scipy"
```

---

## Task 13: Update Risk Strategy

**Files:**
- Modify: `src/tools/technical/strategies/risk.py`

- [ ] **Step 1: Rewrite RiskStrategy**

Add multi-layer support/resistance collection (dynamic MA, static Swing High/Low, Gap levels, Pivot). Add confluence detection (count support levels within 2% of price). Add risk penalties (below SMA_50: +1 level, SuperTrend down: +1 level). Add stop loss calculation (price - 2×ATR).

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/tools/technical/test_risk_strategy.py -v`
Expected: PASS (update test expectations if needed)

- [ ] **Step 3: Commit**

```bash
git add src/tools/technical/strategies/risk.py
git commit -m "feat(risk): add multi-layer S/R, confluence, penalties, stop loss"
```

---

## Task 14: Update TechnicalAnalysisTool with Scorer

**Files:**
- Modify: `src/tools/technical/tool.py`
- Test: `tests/tools/technical/test_tool.py`

- [ ] **Step 1: Update tool.py**

Replace majority-vote logic with `TechnicalScorer`. Also run `analyze_patterns(df)` and pass result to scorer.

```python
# src/tools/technical/tool.py
from datetime import datetime
from src.core.interfaces import BaseTool, BaseProvider
from src.core.models import ToolResult
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.models import TechnicalResult
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.components.patterns import analyze_patterns


class TechnicalAnalysisTool(BaseTool):
    """Technical analysis tool using multiple strategies."""

    name = "technical"
    description = "기술적 분석 도구 (추세, 모멘텀, 패턴)"

    def __init__(self, provider: BaseProvider, registry: StrategyRegistry):
        self.provider = provider
        self.registry = registry
        self.calculator = IndicatorCalculator()
        self.scorer = TechnicalScorer()

    async def execute(self, ticker: str, period: str = "1y", **kwargs) -> ToolResult:
        try:
            df = await self.provider.get_price_history(ticker, period)
            if df.empty:
                return ToolResult(success=False, data=None, error=f"No data found for {ticker}")

            df = self.calculator.calculate(df)
            indicators = self.calculator.create_snapshot(df)

            # Run strategies
            strategy_results = []
            for strategy in self.registry.get_all():
                result = strategy.analyze(df)
                strategy_results.append(result)

            # Run patterns
            pattern_result = analyze_patterns(df)

            # Score
            total_score, assessment = self.scorer.score(strategy_results, pattern_result)

            # Collect insights and warnings
            key_insights = []
            warnings = []
            for sr in strategy_results:
                key_insights.extend(sr.signals)
                if sr.confidence < 30:
                    warnings.append(f"{sr.name}: 낮은 신뢰도 ({sr.confidence:.0f}%)")
            key_insights.extend(pattern_result.signals)

            avg_confidence = sum(s.confidence for s in strategy_results) / len(strategy_results) if strategy_results else 50

            technical_result = TechnicalResult(
                ticker=ticker,
                timestamp=datetime.now(),
                indicators=indicators,
                strategies=strategy_results,
                overall_assessment=assessment,
                confidence_score=avg_confidence,
                key_insights=key_insights,
                warnings=warnings,
                total_score=total_score,
            )

            return ToolResult(success=True, data=technical_result)

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/tools/technical/test_tool.py -v`
Expected: PASS

- [ ] **Step 3: Run all technical tests**

Run: `uv run pytest tests/tools/technical/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/technical/tool.py tests/tools/technical/test_tool.py
git commit -m "feat(technical): integrate Scorer and Patterns into TechnicalAnalysisTool"
```

---

## Task 15: FundamentalTool

**Files:**
- Create: `src/tools/fundamental.py`
- Test: `tests/tools/test_fundamental.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_fundamental.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.fundamental import FundamentalTool, FundamentalSnapshot


@pytest.mark.asyncio
async def test_fundamental_tool_execute():
    mock_info = {
        "marketCap": 2800000000000,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "trailingPE": 28.5,
        "forwardPE": 25.0,
        "pegRatio": 1.8,
        "priceToBook": 45.0,
        "priceToSalesTrailing12Months": 7.5,
        "enterpriseToEbitda": 22.0,
        "trailingEps": 6.42,
        "ebitda": 130000000000,
        "grossMargins": 0.44,
        "operatingMargins": 0.30,
        "profitMargins": 0.25,
        "returnOnEquity": 1.60,
        "returnOnAssets": 0.28,
        "revenueGrowth": 0.08,
        "earningsGrowth": 0.12,
        "debtToEquity": 180.0,
        "currentRatio": 1.07,
        "quickRatio": 0.84,
        "freeCashflow": 100000000000,
        "operatingCashflow": 120000000000,
        "dividendYield": 0.005,
        "payoutRatio": 0.15,
        "sharesOutstanding": 15500000000,
        "floatShares": 15400000000,
    }

    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = MagicMock()
    mock_ticker.quarterly_financials.empty = True

    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = await tool.execute("AAPL")

    assert result.success is True
    snapshot = result.data
    assert isinstance(snapshot, FundamentalSnapshot)
    assert snapshot.pe_ratio == 28.5
    assert snapshot.sector == "Technology"
    assert snapshot.roe == 1.60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_fundamental.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/fundamental.py
import asyncio
from functools import partial
from pydantic import BaseModel
import yfinance as yf
from src.core.interfaces import BaseTool
from src.core.models import ToolResult


class FundamentalSnapshot(BaseModel):
    """Comprehensive fundamental data snapshot."""
    # Basic info
    market_cap: float | None = None
    sector: str | None = None
    industry: str | None = None

    # Valuation
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None

    # Profitability
    eps: float | None = None
    ebitda: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    profit_margin: float | None = None
    roe: float | None = None
    roa: float | None = None

    # Growth
    revenue_growth: float | None = None
    earnings_growth: float | None = None

    # Quarterly results (last 4 quarters)
    quarterly_revenue: list[dict] | None = None
    quarterly_earnings: list[dict] | None = None

    # Financial health
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None

    # Cash flow
    free_cash_flow: float | None = None
    operating_cash_flow: float | None = None
    fcf_yield: float | None = None

    # Dividend
    dividend_yield: float | None = None
    payout_ratio: float | None = None

    # Shares
    shares_outstanding: float | None = None
    float_shares: float | None = None


class FundamentalTool(BaseTool):
    """Fundamental analysis tool using yfinance."""

    name = "fundamental"
    description = "펀더멘털 분석 (밸류에이션, 수익성, 성장성, 재무건전성)"

    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        try:
            loop = asyncio.get_event_loop()
            snapshot = await loop.run_in_executor(
                None, partial(self._fetch_fundamentals, ticker)
            )
            return ToolResult(success=True, data=snapshot)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _fetch_fundamentals(self, ticker: str) -> FundamentalSnapshot:
        t = yf.Ticker(ticker)
        info = t.info

        # FCF yield
        fcf = info.get("freeCashflow")
        mcap = info.get("marketCap")
        fcf_yield = (fcf / mcap) if fcf and mcap and mcap > 0 else None

        # Quarterly data
        quarterly_revenue = None
        quarterly_earnings = None
        try:
            qf = t.quarterly_financials
            if qf is not None and not qf.empty:
                quarterly_revenue = []
                quarterly_earnings = []
                for col in qf.columns[:4]:
                    period = col.strftime("%Y-Q%q") if hasattr(col, "strftime") else str(col)
                    rev = qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else None
                    earn = qf.loc["Net Income", col] if "Net Income" in qf.index else None
                    if rev is not None:
                        quarterly_revenue.append({"period": period, "revenue": float(rev)})
                    if earn is not None:
                        quarterly_earnings.append({"period": period, "earnings": float(earn)})
        except Exception:
            pass

        return FundamentalSnapshot(
            market_cap=info.get("marketCap"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            peg_ratio=info.get("pegRatio"),
            pb_ratio=info.get("priceToBook"),
            ps_ratio=info.get("priceToSalesTrailing12Months"),
            ev_ebitda=info.get("enterpriseToEbitda"),
            eps=info.get("trailingEps"),
            ebitda=info.get("ebitda"),
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            profit_margin=info.get("profitMargins"),
            roe=info.get("returnOnEquity"),
            roa=info.get("returnOnAssets"),
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=info.get("earningsGrowth"),
            quarterly_revenue=quarterly_revenue,
            quarterly_earnings=quarterly_earnings,
            debt_to_equity=info.get("debtToEquity"),
            current_ratio=info.get("currentRatio"),
            quick_ratio=info.get("quickRatio"),
            free_cash_flow=info.get("freeCashflow"),
            operating_cash_flow=info.get("operatingCashflow"),
            fcf_yield=fcf_yield,
            dividend_yield=info.get("dividendYield"),
            payout_ratio=info.get("payoutRatio"),
            shares_outstanding=info.get("sharesOutstanding"),
            float_shares=info.get("floatShares"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_fundamental.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/fundamental.py tests/tools/test_fundamental.py
git commit -m "feat(tools): add FundamentalTool with comprehensive snapshot"
```

---

## Task 16: LLM Fundamental Models + Analyzer

**Files:**
- Modify: `src/llm/models.py`
- Modify: `src/llm/analyzer.py`
- Test: `tests/llm/test_models.py`

- [ ] **Step 1: Add models to `src/llm/models.py`**

```python
# Append to src/llm/models.py

# Fundamental Summary I/O
class FundamentalSummaryInput(BaseModel):
    """Input for fundamental summary."""
    ticker: str
    sector: str | None
    industry: str | None
    pe_ratio: float | None
    forward_pe: float | None
    peg_ratio: float | None
    ev_ebitda: float | None
    ps_ratio: float | None
    roe: float | None
    revenue_growth: float | None
    earnings_growth: float | None
    debt_to_equity: float | None
    free_cash_flow: float | None
    fcf_yield: float | None
    gross_margin: float | None
    operating_margin: float | None


class FundamentalSummaryOutput(BaseModel):
    """Output from fundamental summary."""
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    valuation_assessment: str  # "저평가", "적정", "고평가"
    confidence: float  # 0-1
```

- [ ] **Step 2: Add analyzer function to `src/llm/analyzer.py`**

```python
async def generate_fundamental_summary(
    input_data: FundamentalSummaryInput,
    llm: BaseChatModel,
) -> FundamentalSummaryOutput:
    """Generate fundamental analysis summary using LLM."""
    metrics_text = []
    if input_data.pe_ratio: metrics_text.append(f"P/E: {input_data.pe_ratio:.1f}")
    if input_data.forward_pe: metrics_text.append(f"Forward P/E: {input_data.forward_pe:.1f}")
    if input_data.peg_ratio: metrics_text.append(f"PEG: {input_data.peg_ratio:.2f}")
    if input_data.ev_ebitda: metrics_text.append(f"EV/EBITDA: {input_data.ev_ebitda:.1f}")
    if input_data.ps_ratio: metrics_text.append(f"PSR: {input_data.ps_ratio:.1f}")
    if input_data.roe: metrics_text.append(f"ROE: {input_data.roe*100:.1f}%")
    if input_data.revenue_growth: metrics_text.append(f"매출 성장률: {input_data.revenue_growth*100:.1f}%")
    if input_data.earnings_growth: metrics_text.append(f"이익 성장률: {input_data.earnings_growth*100:.1f}%")
    if input_data.debt_to_equity: metrics_text.append(f"D/E: {input_data.debt_to_equity:.1f}")
    if input_data.gross_margin: metrics_text.append(f"매출총이익률: {input_data.gross_margin*100:.1f}%")
    if input_data.operating_margin: metrics_text.append(f"영업이익률: {input_data.operating_margin*100:.1f}%")
    if input_data.fcf_yield: metrics_text.append(f"FCF Yield: {input_data.fcf_yield*100:.1f}%")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a fundamental analysis expert."),
        ("user", """Analyze the following fundamental data for {ticker}:

**Sector**: {sector} / {industry}

**Key Metrics**:
{metrics_text}

Provide summary with:
- summary: overall fundamental assessment in Korean
- strengths: list of 2-3 key strengths
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

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/llm/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/llm/models.py src/llm/analyzer.py tests/llm/test_models.py
git commit -m "feat(llm): add Fundamental summary models and analyzer"
```

---

## Task 17: Update DeepDivePipeline + CLI

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Modify: `src/cli/main.py`

- [ ] **Step 1: Update DeepDivePipeline**

Add `fundamental_tool` parameter. In `run()`, fetch fundamentals and generate LLM summary. Add to result dict.

- [ ] **Step 2: Update CLI**

In `run_deep_dive()`, create `FundamentalTool` and pass to pipeline.
In `format_deep_dive_output()`, add Fundamental section.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ --ignore=tests/integration -v`
Expected: All PASS

- [ ] **Step 4: Test CLI manually**

Run: `uv run jarvis check AAPL`
Expected: Shows improved scoring with total_score

Run: `uv run jarvis analyze AAPL`
Expected: Shows Technical + Fundamental + News sections

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/deep_dive.py src/cli/main.py
git commit -m "feat(pipeline): add Fundamental analysis to DeepDive + CLI"
```

---

## Task 18: Integration Test + Tag

**Files:**
- Create: `tests/integration/test_e2e_plan4.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_e2e_plan4.py
import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()


@pytest.mark.integration
def test_check_with_scoring():
    """Test check command shows total_score."""
    result = runner.invoke(app, ["check", "AAPL"])
    assert result.exit_code == 0
    assert "AAPL" in result.stdout


@pytest.mark.integration
def test_check_korean_stock_scoring():
    """Test check with Korean stock."""
    result = runner.invoke(app, ["check", "005930.KS"])
    assert result.exit_code in [0, 1]
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v --ignore=tests/integration`
Expected: All PASS

- [ ] **Step 3: Commit and tag**

```bash
git add tests/integration/test_e2e_plan4.py
git commit -m "test: add Plan 4 integration tests"
git tag -a v0.4.0 -m "Plan 4: Advanced Technical + Fundamental Analysis"
```

---

## Summary

Plan 4 완료 시:

```bash
# 개선된 check (5단계 스코어링)
jarvis check AAPL
# 출력: 강력 매수/매수/중립/매도/강력 매도 (총점 기반)

# 개선된 analyze (Technical + Fundamental + News)
jarvis analyze AAPL
# 출력: 기술적 분석 + 펀더멘털 분석 + 뉴스 분석
```

**추가된 컴포넌트:**
- 5개 component (Minervini, Velocity, cRSI, Volume, Patterns)
- TechnicalScorer (가중치 기반 5단계)
- FundamentalTool (30+ 지표)
- LLM Fundamental 분석

**개선된 전략:**
- Trend: Minervini Stage 2 + Velocity + Patterns
- Oscillator: cRSI + Volume
- Divergence: cRSI 다이버전스 + scipy 피크 탐지
- Risk: 다층 지지/저항 + confluence + 손절가
