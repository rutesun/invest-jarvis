# Chart Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance chart visualization with telegram-style indicators while standardizing column names across the codebase.

**Architecture:** Standardize DataFrame column names (SMA_20, SuperTrend_Dir, MACD) while keeping Pydantic snake_case, add Stage2 detection, integrate telegram charting logic (5 MAs, Supertrend signals, MACD/cRSI panels).

**Tech Stack:** pandas_ta, mplfinance, pandas, numpy

---

## File Structure

**Modify**:
- `src/tools/technical/indicators.py` - Column name standardization + Stage2 detection
- `src/tools/technical/components/supertrend.py` - Update SuperTrend_Dir column reference
- `src/tools/technical/components/divergence.py` - Update MACD column references
- `src/tools/technical/scorer.py` - Update column references
- `src/tools/technical/charting.py` - Add telegram-style rendering logic
- `tests/tools/technical/test_indicators.py` - Update column name expectations
- `tests/tools/technical/test_charting.py` - Update indicator expectations
- `docs/FEATURES.md` - Document chart enhancements

---

## Task 1: Standardize Column Names in indicators.py

**Files:**
- Modify: `src/tools/technical/indicators.py`
- Test: `tests/tools/technical/test_indicators.py`

### Step 1.1: Write failing test for MACD column renaming

- [ ] **Add test case for MACD column names**

```python
def test_macd_column_names():
    """Test that MACD columns use clear names."""
    calc = IndicatorCalculator()
    df = pd.DataFrame({
        'Open': [100, 101, 102],
        'High': [102, 103, 104],
        'Low': [99, 100, 101],
        'Close': [101, 102, 103],
        'Volume': [1000, 1100, 1200],
    })
    
    result = calc.calculate(df)
    
    # Check new column names
    assert "MACD" in result.columns
    assert "MACD_Signal" in result.columns
    assert "MACD_Hist" in result.columns
    
    # Check old names don't exist
    assert "MACD_12_26_9" not in result.columns
    assert "MACDs_12_26_9" not in result.columns
    assert "MACDh_12_26_9" not in result.columns
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_macd_column_names -v`  
Expected: FAIL with KeyError "MACD not in columns"

- [ ] **Step 1.3: Update calculate() to rename MACD columns**

In `src/tools/technical/indicators.py`, update the MACD section:

```python
# MACD
macd = ta.macd(df["Close"])
if macd is not None:
    df = pd.concat([df, macd], axis=1)
    # Rename to clear names
    if "MACD_12_26_9" in df.columns:
        df["MACD"] = df["MACD_12_26_9"]
        df["MACD_Signal"] = df["MACDs_12_26_9"]
        df["MACD_Hist"] = df["MACDh_12_26_9"]
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_macd_column_names -v`  
Expected: PASS

### Step 1.5: Add failing test for Fast MACD column renaming

- [ ] **Add test case for Fast MACD columns**

```python
def test_fast_macd_column_names():
    """Test that Fast MACD columns use clear names."""
    calc = IndicatorCalculator()
    df = pd.DataFrame({
        'Open': [100] * 50,
        'High': [102] * 50,
        'Low': [99] * 50,
        'Close': list(range(100, 150)),
        'Volume': [1000] * 50,
    })
    
    result = calc.calculate(df)
    
    assert "MACD_Fast" in result.columns
    assert "MACD_Fast_Signal" in result.columns
    assert "MACD_Fast_Hist" in result.columns
    
    assert "MACD_5_35_5" not in result.columns
```

- [ ] **Step 1.6: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_fast_macd_column_names -v`  
Expected: FAIL

- [ ] **Step 1.7: Update calculate() to rename Fast MACD columns**

```python
# Fast MACD (5/35/5)
macd_fast = ta.macd(df["Close"], fast=5, slow=35, signal=5)
if macd_fast is not None:
    df = pd.concat([df, macd_fast], axis=1)
    # Rename to clear names
    if "MACD_5_35_5" in df.columns:
        df["MACD_Fast"] = df["MACD_5_35_5"]
        df["MACD_Fast_Signal"] = df["MACDs_5_35_5"]
        df["MACD_Fast_Hist"] = df["MACDh_5_35_5"]
```

- [ ] **Step 1.8: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_fast_macd_column_names -v`  
Expected: PASS

### Step 1.9: Add failing test for SuperTrend column renaming

- [ ] **Add test case for SuperTrend columns**

```python
def test_supertrend_column_names():
    """Test that Supertrend columns use clear names."""
    calc = IndicatorCalculator()
    df = pd.DataFrame({
        'Open': [100] * 30,
        'High': [102] * 30,
        'Low': [99] * 30,
        'Close': list(range(100, 130)),
        'Volume': [1000] * 30,
    })
    
    result = calc.calculate(df)
    
    assert "SuperTrend_Up" in result.columns
    assert "SuperTrend_Dn" in result.columns
    assert "SuperTrend_Dir" in result.columns
    
    assert "SUPERTl_10_3.0" not in result.columns
    assert "SUPERTd_10_3.0" not in result.columns
```

- [ ] **Step 1.10: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_supertrend_column_names -v`  
Expected: FAIL

- [ ] **Step 1.11: Update calculate() to rename Supertrend columns**

```python
# Supertrend
st = ta.supertrend(df["High"], df["Low"], df["Close"], length=10, multiplier=3.0)
if st is not None:
    df = pd.concat([df, st], axis=1)
    # Rename to clear names
    if "SUPERTl_10_3.0" in df.columns:
        df["SuperTrend_Up"] = df["SUPERTl_10_3.0"]
        df["SuperTrend_Dn"] = df["SUPERTs_10_3.0"]
        df["SuperTrend_Dir"] = df["SUPERTd_10_3.0"]
```

- [ ] **Step 1.12: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_supertrend_column_names -v`  
Expected: PASS

### Step 1.13: Add failing test for Bollinger Bands column renaming

- [ ] **Add test case for BB columns**

```python
def test_bollinger_bands_column_names():
    """Test that Bollinger Bands use clear names."""
    calc = IndicatorCalculator()
    df = pd.DataFrame({
        'Open': [100] * 25,
        'High': [102] * 25,
        'Low': [99] * 25,
        'Close': list(range(100, 125)),
        'Volume': [1000] * 25,
    })
    
    result = calc.calculate(df)
    
    assert "BB_Upper" in result.columns
    assert "BB_Lower" in result.columns
    
    assert "BBU_20_2.0" not in result.columns
    assert "BBL_20_2.0" not in result.columns
```

- [ ] **Step 1.14: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_bollinger_bands_column_names -v`  
Expected: FAIL

- [ ] **Step 1.15: Update calculate() to rename BB columns**

```python
# Bollinger Bands
bb = ta.bbands(df["Close"], length=20)
if bb is not None:
    df = pd.concat([df, bb], axis=1)
    # Rename to clear names
    if "BBU_20_2.0" in df.columns:
        df["BB_Upper"] = df["BBU_20_2.0"]
        df["BB_Lower"] = df["BBL_20_2.0"]
```

- [ ] **Step 1.16: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_bollinger_bands_column_names -v`  
Expected: PASS

### Step 1.17: Add failing test for ADX column renaming

- [ ] **Add test case for ADX column**

```python
def test_adx_column_name():
    """Test that ADX uses clear name."""
    calc = IndicatorCalculator()
    df = pd.DataFrame({
        'Open': [100] * 20,
        'High': [102] * 20,
        'Low': [99] * 20,
        'Close': list(range(100, 120)),
        'Volume': [1000] * 20,
    })
    
    result = calc.calculate(df)
    
    assert "ADX" in result.columns
    assert "ADX_14" not in result.columns
```

- [ ] **Step 1.18: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_adx_column_name -v`  
Expected: FAIL

- [ ] **Step 1.19: Update calculate() to rename ADX column**

```python
# ADX
adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
if adx is not None:
    df = pd.concat([df, adx], axis=1)
    # Rename to clear name
    if "ADX_14" in df.columns:
        df["ADX"] = df["ADX_14"]
```

- [ ] **Step 1.20: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_adx_column_name -v`  
Expected: PASS

### Step 1.21: Update create_snapshot() mapping

- [ ] **Update create_snapshot() to use new column names**

In `src/tools/technical/indicators.py`, update the `create_snapshot()` method:

```python
def create_snapshot(self, df: pd.DataFrame) -> IndicatorSnapshot:
    """Create indicator snapshot from latest row."""
    if df.empty:
        return IndicatorSnapshot(price=0, change_pct=0)

    # Drop rows with NaN Close values to get valid latest data
    df_clean = df.dropna(subset=["Close"])
    if df_clean.empty:
        return IndicatorSnapshot(price=0, change_pct=0)

    latest = df_clean.iloc[-1]
    prev_close = df_clean.iloc[-2]["Close"] if len(df_clean) > 1 else latest["Close"]
    change_pct = ((latest["Close"] - prev_close) / prev_close) * 100

    # Calculate performance over different periods
    current_price = float(latest["Close"])
    perf_1m = self._calculate_performance(df_clean, current_price, days=21)
    perf_3m = self._calculate_performance(df_clean, current_price, days=63)
    perf_6m = self._calculate_performance(df_clean, current_price, days=126)
    perf_1y = self._calculate_performance(df_clean, current_price, days=252)

    def safe_get(key: str) -> float | None:
        val = latest.get(key)
        if pd.isna(val):
            return None
        return float(val)

    return IndicatorSnapshot(
        price=float(latest["Close"]),
        change_pct=round(change_pct, 2),
        perf_1m=perf_1m,
        perf_3m=perf_3m,
        perf_6m=perf_6m,
        perf_1y=perf_1y,
        sma_10=safe_get("SMA_10"),
        sma_20=safe_get("SMA_20"),
        sma_50=safe_get("SMA_50"),
        sma_120=safe_get("SMA_120"),
        sma_200=safe_get("SMA_200"),
        rsi=safe_get("RSI"),
        macd=safe_get("MACD"),
        macd_signal=safe_get("MACD_Signal"),
        macd_histogram=safe_get("MACD_Hist"),
        atr=safe_get("ATR"),
        bb_upper=safe_get("BB_Upper"),
        bb_lower=safe_get("BB_Lower"),
        adx=safe_get("ADX"),
        supertrend_direction=int(safe_get("SuperTrend_Dir") or 0)
        if safe_get("SuperTrend_Dir")
        else None,
        disparity_20=safe_get("Disparity_20"),
        disparity_50=safe_get("Disparity_50"),
        disparity_120=safe_get("Disparity_120"),
        pivot=safe_get("Pivot"),
        support_s1=safe_get("S1"),
        resistance_r1=safe_get("R1"),
        high_52w=safe_get("High_52w"),
        low_52w=safe_get("Low_52w"),
        sma_150=safe_get("SMA_150"),
        crsi=safe_get("cRSI"),
        crsi_high_band=safe_get("cRSI_HighBand"),
        crsi_low_band=safe_get("cRSI_LowBand"),
        vol_sma_20=safe_get("Vol_SMA_20"),
        vol_sma_50=safe_get("Vol_SMA_50"),
        vol_sma_120=safe_get("Vol_SMA_120"),
        swing_high=safe_get("Swing_High"),
        swing_low=safe_get("Swing_Low"),
        is_gap_up=bool(latest.get("Is_Gap_Up"))
        if not pd.isna(latest.get("Is_Gap_Up"))
        else None,
        is_gap_down=bool(latest.get("Is_Gap_Down"))
        if not pd.isna(latest.get("Is_Gap_Down"))
        else None,
        macd_fast=safe_get("MACD_Fast"),
        macd_fast_signal=safe_get("MACD_Fast_Signal"),
        macd_fast_histogram=safe_get("MACD_Fast_Hist"),
    )
```

- [ ] **Step 1.22: Run full indicators test suite**

Run: `uv run pytest tests/tools/technical/test_indicators.py -v`  
Expected: All PASS

- [ ] **Step 1.23: Commit column name standardization**

```bash
git add src/tools/technical/indicators.py tests/tools/technical/test_indicators.py
git commit -m "refactor(technical): Standardize indicator column names to clear naming

- MACD_12_26_9 → MACD, MACD_Signal, MACD_Hist
- MACD_5_35_5 → MACD_Fast, MACD_Fast_Signal, MACD_Fast_Hist
- SUPERTl/s/d_10_3.0 → SuperTrend_Up/Dn/Dir
- BBU/L_20_2.0 → BB_Upper/Lower
- ADX_14 → ADX
- Update create_snapshot() mapping (DataFrame → Pydantic)"
```

---

## Task 2: Add Stage2 Detection

**Files:**
- Modify: `src/tools/technical/indicators.py`
- Test: `tests/tools/technical/test_indicators.py`

### Step 2.1: Write failing test for _calculate_stage2()

- [ ] **Add test case for Stage2 detection**

```python
def test_calculate_stage2():
    """Test Stage2 detection logic."""
    calc = IndicatorCalculator()
    
    # Create sample data that meets Stage2 criteria
    df = pd.DataFrame({
        'Open': [100] * 300,
        'High': [102] * 300,
        'Low': [99] * 300,
        'Close': list(range(100, 400)),  # Rising trend
        'Volume': [1000] * 300,
    })
    
    # Calculate indicators first
    df = calc.calculate(df)
    
    # Stage2 conditions:
    # 1. Close > SMA_150 > SMA_200
    # 2. SMA_150/200 rising (20-day lookback)
    # 3. Close >= Low_52w * 1.3
    # 4. Close >= High_52w * 0.75
    
    # Check Is_Stage2 column exists
    assert "Is_Stage2" in df.columns
    
    # Last rows should be in Stage2
    assert df["Is_Stage2"].iloc[-1] == True
    
    # Early rows should NOT be in Stage2 (SMA not stabilized)
    assert df["Is_Stage2"].iloc[0] == False
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_calculate_stage2 -v`  
Expected: FAIL with KeyError "Is_Stage2 not in columns"

- [ ] **Step 2.3: Implement _calculate_stage2() method**

In `src/tools/technical/indicators.py`, add the method:

```python
def _calculate_stage2(self, df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Minervini Stage2 flag (상승 추세 구간).
    
    Stage2 조건:
    1. Price > SMA_150 > SMA_200
    2. SMA_150, SMA_200 상승 중 (20일 lookback)
    3. Price >= Low_52w * 1.3
    4. Price >= High_52w * 0.75
    """
    df["Is_Stage2"] = False  # default
    
    required_cols = ["SMA_150", "SMA_200", "High_52w", "Low_52w", "Close"]
    if not all(col in df.columns for col in required_cols):
        return df
    
    # 조건 1: Price > SMA_150 > SMA_200
    cond1 = (df["Close"] > df["SMA_150"]) & (df["SMA_150"] > df["SMA_200"])
    
    # 조건 2: SMA_150, SMA_200 상승 중 (20일 lookback)
    lookback = 20
    sma150_rising = df["SMA_150"] > df["SMA_150"].shift(lookback)
    sma200_rising = df["SMA_200"] > df["SMA_200"].shift(lookback)
    cond2 = sma150_rising & sma200_rising
    
    # 조건 3: Price >= Low_52w * 1.3
    cond3 = df["Close"] >= (df["Low_52w"] * 1.3)
    
    # 조건 4: Price >= High_52w * 0.75
    cond4 = df["Close"] >= (df["High_52w"] * 0.75)
    
    df["Is_Stage2"] = cond1 & cond2 & cond3 & cond4
    return df
```

- [ ] **Step 2.4: Integrate _calculate_stage2() into calculate()**

In `src/tools/technical/indicators.py`, add call at the end of `calculate()`:

```python
def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to DataFrame."""
    if df.empty:
        return df

    df = df.copy()
    
    # ... (all existing indicator calculations) ...
    
    # Cycle RSI (cRSI)
    df = self._calculate_crsi(df)
    
    # Stage2 detection (ADD THIS)
    df = self._calculate_stage2(df)

    return df
```

- [ ] **Step 2.5: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_calculate_stage2 -v`  
Expected: PASS

- [ ] **Step 2.6: Add edge case test for Stage2**

```python
def test_calculate_stage2_missing_columns():
    """Test Stage2 handles missing required columns gracefully."""
    calc = IndicatorCalculator()
    
    # Minimal data without enough history for 52w high/low
    df = pd.DataFrame({
        'Open': [100] * 10,
        'High': [102] * 10,
        'Low': [99] * 10,
        'Close': [101] * 10,
        'Volume': [1000] * 10,
    })
    
    df = calc.calculate(df)
    
    # Should have Is_Stage2 column
    assert "Is_Stage2" in df.columns
    
    # All should be False (insufficient data)
    assert df["Is_Stage2"].sum() == 0
```

- [ ] **Step 2.7: Run edge case test**

Run: `uv run pytest tests/tools/technical/test_indicators.py::test_calculate_stage2_missing_columns -v`  
Expected: PASS

- [ ] **Step 2.8: Run full test suite**

Run: `uv run pytest tests/tools/technical/test_indicators.py -v`  
Expected: All PASS

- [ ] **Step 2.9: Commit Stage2 detection**

```bash
git add src/tools/technical/indicators.py tests/tools/technical/test_indicators.py
git commit -m "feat(technical): Add Stage2 detection flag for Minervini analysis

- Add _calculate_stage2() method
- Is_Stage2 column based on:
  - Price > SMA150 > SMA200
  - SMA150/200 rising (20-day lookback)
  - Price >= Low_52w * 1.3
  - Price >= High_52w * 0.75
- Integrate into calculate() pipeline"
```

---

## Task 3: Update Components to Use New Column Names

**Files:**
- Modify: `src/tools/technical/components/supertrend.py`
- Modify: `src/tools/technical/components/divergence.py`
- Modify: `src/tools/technical/scorer.py`

### Step 3.1: Update supertrend.py column references

- [ ] **Update SuperTrend column names in supertrend.py**

In `src/tools/technical/components/supertrend.py`, update column references:

```python
def analyze_supertrend(df: pd.DataFrame) -> ComponentResult:
    """Analyze Supertrend signals."""
    if df.empty or len(df) < 2:
        return ComponentResult(
            signals=[],
            evidence=[],
            metrics={},
            score=0,
        )

    # Check for Supertrend columns (UPDATE THIS)
    if "SuperTrend_Dir" not in df.columns:
        return ComponentResult(
            signals=[],
            evidence=["Supertrend 데이터 없음"],
            metrics={},
            score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    # UPDATE THESE
    supertrend_dir = latest.get("SuperTrend_Dir")
    prev_supertrend_dir = prev.get("SuperTrend_Dir")
    supertrend_value = latest.get("SuperTrend_Up") if supertrend_dir == 1 else latest.get("SuperTrend_Dn")
    close = latest.get("Close")

    if pd.isna(supertrend_dir):
        return ComponentResult(
            signals=[],
            evidence=["Supertrend 값 없음"],
            metrics={},
            score=0,
        )

    # ... rest of the logic remains the same ...
```

- [ ] **Step 3.2: Update divergence.py column references**

In `src/tools/technical/components/divergence.py`, update MACD column names:

```python
def analyze_divergence(df: pd.DataFrame) -> ComponentResult:
    """Analyze price-indicator divergences."""
    if df.empty or len(df) < 20:
        return ComponentResult(
            signals=[],
            evidence=[],
            metrics={},
            score=0,
        )

    # UPDATE THESE
    required_cols = ["Close", "RSI", "MACD"]
    if not all(col in df.columns for col in required_cols):
        return ComponentResult(
            signals=[],
            evidence=["필수 지표 데이터 없음"],
            metrics={},
            score=0,
        )

    # ... (find all references to MACD_12_26_9 and replace with MACD) ...
```

- [ ] **Step 3.3: Update scorer.py column references**

In `src/tools/technical/scorer.py`, update all column references:

```python
# Find and replace:
# "MACD_12_26_9" → "MACD"
# "MACDs_12_26_9" → "MACD_Signal"
# "MACDh_12_26_9" → "MACD_Hist"
# "SUPERTd_10_3.0" → "SuperTrend_Dir"
# "MACD_5_35_5" → "MACD_Fast"
# "BBU_20_2.0" → "BB_Upper"
# "BBL_20_2.0" → "BB_Lower"
# "ADX_14" → "ADX"
```

- [ ] **Step 3.4: Run components tests**

Run: `uv run pytest tests/tools/technical/ -v`  
Expected: All PASS

- [ ] **Step 3.5: Verify no old column names remain**

Run grep to check for old column names:

```bash
grep -r "MACD_12_26_9" src/tools/technical/
grep -r "SUPERTd_10_3.0" src/tools/technical/
grep -r "BBU_20_2.0" src/tools/technical/
grep -r "ADX_14" src/tools/technical/
```

Expected: No matches

- [ ] **Step 3.6: Commit component updates**

```bash
git add src/tools/technical/components/ src/tools/technical/scorer.py
git commit -m "refactor(technical): Update components to use new column names

- components/supertrend.py: SuperTrend_Dir
- components/divergence.py: MACD, MACD_Signal
- scorer.py: all column references standardized"
```

---

## Task 4: Enhance charting.py with Telegram-Style Indicators

**Files:**
- Modify: `src/tools/technical/charting.py`
- Test: Manual test with `uv run jarvis analyze AAPL`

### Step 4.1: Add _shade_stage2() helper function

- [ ] **Add Stage2 shading function**

In `src/tools/technical/charting.py`, add this function after `_badge()`:

```python
def _shade_stage2(ax: Any, df: pd.DataFrame) -> None:
    """Stage2 조건 충족 구간을 배경 음영으로 표시."""
    if "Is_Stage2" not in df.columns:
        return
    
    mask = df["Is_Stage2"].astype(bool).fillna(False).to_numpy()
    if mask.size == 0 or not mask.any():
        return
    
    idx = df.index.to_list()
    start_i: int | None = None
    
    # 연속된 True 구간을 찾아 음영 처리
    for i, v in enumerate(mask):
        if v and start_i is None:
            start_i = i
        if (not v or i == len(mask) - 1) and start_i is not None:
            end_i = i if v and i == len(mask) - 1 else i - 1
            ax.axvspan(idx[start_i], idx[end_i], facecolor="green", alpha=0.08, zorder=0)
            start_i = None
```

### Step 4.2: Update _right_value_labels() for 5 MAs

- [ ] **Update MA labels to include MA10 and MA150**

Replace the existing `_right_value_labels()` function:

```python
def _right_value_labels(ax: Any, df: pd.DataFrame) -> None:
    """Display moving average labels on the right side of price panel."""
    if df.empty:
        return
    x = df.index[-1]
    labels = [
        ("MA50", "SMA_50", "#00D1FF", 0),      # 최상단
        ("MA200", "SMA_200", "#FF2D55", -10),
        ("MA120", "SMA_120", "#FF8C00", -20),
        ("MA20", "SMA_20", "#4DA3FF", 10),
        ("MA10", "SMA_10", "#B0B0B0", 20),
        ("MA150", "SMA_150", "#8A8A8A", 30),   # 최하단
    ]
    for name, col, color, dy in labels:
        if col not in df.columns:
            continue
        try:
            y = float(df[col].iloc[-1])
        except Exception:
            continue
        if pd.isna(y):
            continue
        ax.annotate(
            name,
            xy=(x, y),
            xytext=(-6, dy),
            textcoords="offset points",
            ha="right",
            va="center",
            fontsize=8.0,
            color=color,
            bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": color, "alpha": 0.8},
            zorder=6,
        )
```

### Step 4.3: Update render_technical_chart() - Moving Averages

- [ ] **Add 6 moving averages with priority styling**

In `render_technical_chart()`, update the moving averages section:

```python
# Moving averages (6개, 우선순위별 스타일)
if _has_values("SMA_10"):
    addplots.append(mpf.make_addplot(df_plot["SMA_10"], color="#B0B0B0", width=1.0))  # 연한 회색
if _has_values("SMA_20"):
    addplots.append(mpf.make_addplot(df_plot["SMA_20"], color="#4DA3FF", width=1.8))  # 밝은 파랑
if _has_values("SMA_50"):
    addplots.append(mpf.make_addplot(df_plot["SMA_50"], color="#00D1FF", width=3.0))  # 밝은 청록 (최고 강조)
if _has_values("SMA_120"):
    addplots.append(mpf.make_addplot(df_plot["SMA_120"], color="#FF8C00", width=2.0))  # 주황
if _has_values("SMA_150"):
    addplots.append(mpf.make_addplot(df_plot["SMA_150"], color="#8A8A8A", width=0.9))  # 회색
if _has_values("SMA_200"):
    addplots.append(mpf.make_addplot(df_plot["SMA_200"], color="#FF2D55", width=2.8))  # 진한 빨강
```

### Step 4.4: Update render_technical_chart() - Supertrend with Signals

- [ ] **Add Supertrend with buy/sell signal markers**

Replace the existing Supertrend section:

```python
# Supertrend with signal markers
if {"SuperTrend_Up", "SuperTrend_Dn", "SuperTrend_Dir"}.issubset(df_plot.columns):
    st_dir = df_plot["SuperTrend_Dir"].astype("int64")
    st_up = df_plot["SuperTrend_Up"].where(st_dir == 1)
    st_dn = df_plot["SuperTrend_Dn"].where(st_dir == -1)
    
    if st_up.notna().any():
        addplots.append(mpf.make_addplot(st_up, color="green", width=2, secondary_y=False))
    if st_dn.notna().any():
        addplots.append(mpf.make_addplot(st_dn, color="red", width=2, secondary_y=False))
    
    # Buy/Sell signal markers
    buy_signal = (st_dir == 1) & (st_dir.shift(1) == -1)
    sell_signal = (st_dir == -1) & (st_dir.shift(1) == 1)
    
    buy_y = df_plot["SuperTrend_Up"].where(buy_signal)
    sell_y = df_plot["SuperTrend_Dn"].where(sell_signal)
    
    if buy_y.notna().any():
        addplots.append(
            mpf.make_addplot(
                buy_y,
                type="scatter",
                marker="o",
                markersize=35,
                color="green",
            )
        )
    if sell_y.notna().any():
        addplots.append(
            mpf.make_addplot(
                sell_y,
                type="scatter",
                marker="o",
                markersize=35,
                color="red",
            )
        )
```

### Step 4.5: Update render_technical_chart() - Volume MA50

- [ ] **Add Volume MA50 overlay**

Replace the volume SMA section:

```python
# Volume MA50 (change from Vol_SMA_20 to Vol_SMA_50)
if _has_values("Vol_SMA_50"):
    addplots.append(mpf.make_addplot(df_plot["Vol_SMA_50"], panel=1, color="gold", width=1))
```

### Step 4.6: Update render_technical_chart() - MACD Panel

- [ ] **Update MACD to use new column names**

Replace MACD section:

```python
# MACD panel
has_macd = {"MACD", "MACD_Signal", "MACD_Hist"}.issubset(df_plot.columns) and any(
    _has_values(c) for c in ["MACD", "MACD_Signal", "MACD_Hist"]
)
if has_macd:
    panel_ratios = (*panel_ratios, 2)
    addplots.append(
        mpf.make_addplot(
            df_plot["MACD_Hist"],
            panel=2,
            type="bar",
            color="#888888",
            alpha=0.55,
            width=0.7,
        )
    )
    addplots.append(mpf.make_addplot(df_plot["MACD"], panel=2, color="#4DA3FF", width=1.3))
    addplots.append(
        mpf.make_addplot(df_plot["MACD_Signal"], panel=2, color="#FF8C00", width=1.1)
    )
```

### Step 4.7: Update render_technical_chart() - cRSI Panel

- [ ] **Add cRSI panel with dynamic bands and reference lines**

Add after MACD section:

```python
# cRSI panel
has_crsi = {"cRSI", "cRSI_HighBand", "cRSI_LowBand"}.issubset(df_plot.columns) and (
    _has_values("cRSI") or _has_values("cRSI_HighBand") or _has_values("cRSI_LowBand")
)
if has_crsi:
    crsi_panel = 3 if has_macd else 2
    panel_ratios = (*panel_ratios, 2)
    
    # cRSI line
    addplots.append(
        mpf.make_addplot(
            df_plot["cRSI"],
            panel=crsi_panel,
            color="#FF00FF",
            width=1.2,
            ylim=(0, 100),
        )
    )
    
    # Dynamic bands
    addplots.append(
        mpf.make_addplot(
            df_plot["cRSI_LowBand"],
            panel=crsi_panel,
            color="#00FFFF",
            width=1.0,
            alpha=0.9,
        )
    )
    addplots.append(
        mpf.make_addplot(
            df_plot["cRSI_HighBand"],
            panel=crsi_panel,
            color="#00FFFF",
            width=1.0,
            alpha=0.9,
        )
    )
    
    # 30/70 reference lines
    addplots.append(
        mpf.make_addplot(
            pd.Series(30.0, index=df_plot.index),
            panel=crsi_panel,
            color="#B0B0B0",
            width=0.8,
            linestyle="dashed",
            alpha=0.7,
        )
    )
    addplots.append(
        mpf.make_addplot(
            pd.Series(70.0, index=df_plot.index),
            panel=crsi_panel,
            color="#B0B0B0",
            width=0.8,
            linestyle="dashed",
            alpha=0.7,
        )
    )
```

### Step 4.8: Update render_technical_chart() - Panel Badges

- [ ] **Update badge labels for all panels**

Update the panel badges section:

```python
# Panel badges
if len(panels) >= 2:
    _badge(panels[1], "VOL + VOL_MA50", xy=(0.01, 0.92))
if has_macd and len(panels) >= 3:
    _badge(panels[2], "MACD(12,26,9)", xy=(0.01, 0.92))
if has_crsi:
    crsi_panel_i = 3 if has_macd else 2
    if len(panels) > crsi_panel_i:
        _badge(panels[crsi_panel_i], "cRSI(dc=20,vib=10,lvl=10%)", xy=(0.01, 0.92))
```

### Step 4.9: Update render_technical_chart() - Stage2 Shading

- [ ] **Add Stage2 shading call**

After `_right_value_labels(ax_price, df_plot)`, add:

```python
_right_value_labels(ax_price, df_plot)

# Stage2 shading
_shade_stage2(ax_price, df_plot)

# Draw support/resistance levels
```

### Step 4.10: Update TechnicalResult column filter

- [ ] **Update column filter in models.py**

In `src/tools/technical/models.py`, update the `from_analysis` method to include new column names:

```python
@classmethod
def from_analysis(cls, df: pd.DataFrame, **kwargs):
    """메모리 최적화: OHLCV + 지표 컬럼만 저장"""
    # Flatten MultiIndex columns (yfinance single ticker returns MultiIndex)
    df_copy = df.copy()
    if isinstance(df_copy.columns, pd.MultiIndex):
        df_copy.columns = df_copy.columns.get_level_values(0)

    # Include Volume for charting, plus indicator columns
    base_cols = ["Open", "High", "Low", "Close", "Volume"]
    indicator_cols = [
        col
        for col in df_copy.columns
        if col.startswith(("SMA_", "SuperTrend_", "MACD", "cRSI", "Vol_SMA_", "Is_Stage2"))
    ]
    keep_cols = [c for c in base_cols + indicator_cols if c in df_copy.columns]

    slim_df = df_copy[keep_cols].copy()
    return cls(raw_dataframe=slim_df, **kwargs)
```

### Step 4.11: Test chart rendering with real data

- [ ] **Test with AAPL**

Run: `uv run jarvis analyze AAPL`

Expected:
- Chart generated at `charts/AAPL_technical.png`
- 6 moving averages visible with correct styling
- Supertrend with buy/sell markers
- Stage2 shading (if conditions met)
- Volume with MA50 overlay
- MACD panel with histogram
- cRSI panel with bands and reference lines
- Panel badges visible

- [ ] **Test with Korean stock**

Run: `uv run jarvis analyze 삼성전자`

Expected: Similar chart with Korean font rendering correctly

- [ ] **Verify chart file**

Run: `ls -lh charts/`

Expected: PNG files created with reasonable size (100-300KB)

### Step 4.12: Commit charting enhancements

```bash
git add src/tools/technical/charting.py src/tools/technical/models.py
git commit -m "feat(charting): Enhance chart with telegram-style technical indicators

- Add _shade_stage2() for Stage2 background shading
- Update _right_value_labels() for 6 MAs (10/20/50/120/150/200)
- 6 moving averages with priority styling:
  - MA50: #00D1FF, width=3.0 (최고 강조)
  - MA200: #FF2D55, width=2.8
  - MA120: #FF8C00, width=2.0
  - MA20: #4DA3FF, width=1.8
  - MA10: #B0B0B0, width=1.0
  - MA150: #8A8A8A, width=0.9
- Supertrend with buy/sell signal markers (markersize=35)
- Stage2 shading (green background, alpha=0.08)
- Volume MA50 overlay (gold line)
- MACD panel with new column names
- cRSI panel with dynamic bands + 30/70 reference lines
- Panel badges updated
- Update TechnicalResult column filter"
```

---

## Task 5: Update Tests and Documentation

**Files:**
- Modify: `tests/tools/technical/test_charting.py`
- Modify: `docs/FEATURES.md`

### Step 5.1: Update test_charting.py expectations

- [ ] **Update charting test column expectations**

In `tests/tools/technical/test_charting.py`, update all column name references:

```python
# Find and replace in tests:
# "sma_20" → "SMA_20"
# "sma_50" → "SMA_50"
# "supertrend_direction" → "SuperTrend_Dir"
# "macd" → "MACD"
# "macd_signal" → "MACD_Signal"

# Add test for new columns
def test_chart_has_required_columns():
    """Test that dataframe has all required columns for charting."""
    # ... create sample df with indicators ...
    
    required_cols = [
        "SMA_20", "SMA_50", "SMA_120", "SMA_150", "SMA_200",
        "SuperTrend_Dir", "SuperTrend_Up", "SuperTrend_Dn",
        "MACD", "MACD_Signal", "MACD_Hist",
        "cRSI", "cRSI_HighBand", "cRSI_LowBand",
        "Vol_SMA_50",
        "Is_Stage2",
    ]
    
    for col in required_cols:
        assert col in df.columns, f"Missing required column: {col}"
```

- [ ] **Step 5.2: Run charting tests**

Run: `uv run pytest tests/tools/technical/test_charting.py -v`  
Expected: All PASS

- [ ] **Step 5.3: Run full test suite**

Run: `uv run pytest`  
Expected: All PASS

### Step 5.4: Update FEATURES.md documentation

- [ ] **Add chart visualization section to FEATURES.md**

In `docs/FEATURES.md`, add or update section 1.1:

```markdown
## 1.1 차트 시각화

invest-jarvis는 기술적 분석 결과를 시각적으로 표현하는 전문적인 차트를 생성합니다.

### 주요 기능

**가격 패널**:
- 캔들스틱 차트
- 6개 이동평균선 (10/20/50/120/150/200일)
  - 우선순위별 스타일링: 50일/200일 가장 굵게 (width=3.0/2.8)
  - 50일(청록), 200일(빨강), 120일(주황), 20일(파랑), 10일/150일(회색)
- Supertrend 추세 지표
  - 매수/매도 전환 시그널 마커 (큰 원형 마커)
- Stage2 구간 음영 (Minervini 기준 상승 추세, 초록 배경)
- 차트 패턴 마커 (Cup & Handle, Double Bottom 등)
- 지지선/저항선 (Fibonacci, Swing levels)
- 우측 MA 값 라벨

**보조지표 패널**:
- 거래량 (Volume MA50 오버레이, 골드 라인)
- MACD(12,26,9) - 히스토그램 + 시그널 라인
- cRSI - 동적 밴드 (10th/90th percentile) + 30/70 참조선

### 사용법

```bash
# analyze 명령 시 자동 생성
uv run jarvis analyze AAPL

# 차트 저장 위치
charts/AAPL_technical.png
```

### 기술 명세

- **렌더링**: mplfinance
- **해상도**: 130 DPI
- **패널 비율**: (6, 2, 2, 2) - 가격:거래량:MACD:cRSI
- **한글 폰트 지원**: Noto Sans CJK KR, AppleGothic, NanumGothic 등
- **Stage2 조건**:
  - Price > SMA_150 > SMA_200
  - SMA_150/200 상승 중 (20일 lookback)
  - Price >= Low_52w * 1.3
  - Price >= High_52w * 0.75

### 컬럼명 표준화

기술 지표 컬럼은 명확한 이름을 사용합니다:
- `MACD`, `MACD_Signal`, `MACD_Hist` (기존: MACD_12_26_9)
- `SuperTrend_Up`, `SuperTrend_Dn`, `SuperTrend_Dir` (기존: SUPERTl_10_3.0)
- `BB_Upper`, `BB_Lower` (기존: BBU_20_2.0)
- `ADX` (기존: ADX_14)
- `Is_Stage2` (Minervini Stage2 플래그)
```

### Step 5.5: Commit tests and documentation

```bash
git add tests/tools/technical/test_charting.py docs/FEATURES.md
git commit -m "test: Update technical tests for new column names

- test_charting.py: update all column name expectations
- Add test for required chart columns

docs: Update FEATURES.md for chart enhancements

- Document 6 MA styling and colors
- Document Supertrend signal markers
- Document Stage2 shading conditions
- Document cRSI panel with dynamic bands
- Document column name standardization"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Column name standardization (Section 2)
- [x] Stage2 detection logic (Section 3)
- [x] Chart panel structure (Section 4.1)
- [x] Moving averages styling (Section 4.2)
- [x] Supertrend visualization (Section 4.3)
- [x] Volume MA50 (Section 4.4)
- [x] MACD panel (Section 4.5)
- [x] cRSI panel (Section 4.6)
- [x] Panel badges (Section 4.7)
- [x] Components update (Section 5.2)
- [x] Tests update (Section 5.5)
- [x] Documentation (Section 6.4)

**Placeholder scan:**
- [x] No "TBD", "TODO", "implement later"
- [x] All test code includes assertions
- [x] All implementation code is complete

**Type consistency:**
- [x] Column names consistent: MACD, MACD_Signal, MACD_Hist
- [x] SuperTrend_Up/Dn/Dir consistent across files
- [x] Is_Stage2 (not is_stage2 or IsStage2)

**No gaps found.**

---

## Post-Implementation Verification

After completing all tasks, run these verification steps:

```bash
# 1. Run full test suite
uv run pytest -v

# 2. Test with multiple tickers
uv run jarvis analyze AAPL
uv run jarvis analyze MSFT
uv run jarvis analyze 삼성전자
uv run jarvis analyze NVDA

# 3. Verify charts generated
ls -lh charts/

# 4. Check for old column names (should be none)
grep -r "MACD_12_26_9" src/
grep -r "SUPERTd_10_3.0" src/
grep -r "BBU_20_2.0" src/

# 5. Create PR
git push origin feature/chart-enhancement
gh pr create --title "feat: Enhance chart with telegram-style indicators" \
  --body "See design spec: docs/superpowers/specs/2026-04-25-chart-enhancement-design.md"
```

---

**Plan complete!**
