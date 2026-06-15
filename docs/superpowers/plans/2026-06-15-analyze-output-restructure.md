# Analyze 출력 재구성 Implementation Plan (플랜 A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `analyze`(deep_dive)를 **수집 → 가공 → 렌더링**만 하는 순수 파이프라인으로 재구성한다. 판정·논쟁·가중치는 일절 없다(전부 플랜 B). 신규 차트 사건 감지를 Tool로 추가하고, 출력을 7개 구조화 섹션으로 만들되 렌더 로직은 main.py에서 분리한다.

**Architecture (레이어 경계 — spec §3.0):**
- **Tool** = 도메인 계산. 사건 감지(`src/tools/technical/events.py`)는 차트 한 재료를 가공하므로 Tool. RS 전환은 playbook의 `relative_strength.py`.
- **Pipeline** = 조율. `deep_dive.py`는 tool을 호출해 result dict에 담기만 한다(계산 안 함).
- **CLI** = 렌더. 섹션 포맷·조립은 `src/cli/analyze_render.py`로 분리. `main.py`는 Typer 커맨드만.
- 종합 판정/판단요약/가중치/논쟁은 이 플랜에 없다. `format_deep_dive_output`은 결론 없는 증거 리포트를 만든다. (플랜 B가 debate 섹션을 별도로 삽입)

**Tech Stack:** Python 3.12, pandas, pydantic v2, pytest, uv

---

## File Structure

| 파일 | 역할 | 신규/수정 | 레이어 |
|------|------|-----------|--------|
| `src/tools/technical/events_models.py` | 사건 결과 pydantic 모델 | 신규 | Tool |
| `src/tools/technical/events.py` | 시계열 사건 감지(순수 함수) | 신규 | Tool |
| `src/tools/criteria/relative_strength.py` | RS 음↔양 전환 날짜 | 수정 | Tool |
| `src/tools/criteria/models.py` | `RelativeStrengthResult` 전환 필드 | 수정 | Tool |
| `src/pipelines/deep_dive.py` | events tool 호출 → result 조립 | 수정 | Pipeline |
| `src/cli/analyze_render.py` | deep_dive 출력 렌더 전체 | 신규 | CLI |
| `src/cli/main.py` | 렌더를 analyze_render로 분리·import, 판단요약 제거 | 수정 | CLI |
| `tests/tools/technical/test_events.py` | 사건 감지 테스트 | 신규 | — |
| `tests/tools/criteria/test_relative_strength.py` | RS 전환 테스트 | 수정 | — |
| `tests/cli/test_analyze_render.py` | 섹션 포맷 + 통합 렌더 테스트 | 신규 | — |
| `tests/cli/test_analyze_output.py` | 기존 출력 테스트 → 새 레이아웃 마이그레이션 | 수정 | — |
| `docs/FEATURES.md` | 기능 문서 | 수정 | — |

**데이터 출처 (재계산 금지, 읽기만):** 게이트/CAN SLIM/포지션플랜 → `result["criteria_verdict"]`; SMA·RSI·MACD·ADX·Supertrend·52주고저·Pivot·ATR·vol_sma → `result["technical"].snapshot`; Mansfield RS → `criteria_verdict.relative_strength`; 차트패턴 → `result["chart_patterns"]`; 구조 zone → `result["structure_levels"]`/`presented_structure`.

---

## Task 1: 사건 결과 모델 (Tool)

**Files:**
- Create: `src/tools/technical/events_models.py`
- Test: `tests/tools/technical/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_events.py
def test_momentum_events_model_defaults():
    from src.tools.technical.events_models import MomentumEvents

    ev = MomentumEvents()
    assert ev.macd_cross is None
    assert ev.rsi_divergence is None
    assert ev.ud_volume_ratio is None
    assert ev.volume_trend is None
    assert ev.price_events == []
    assert ev.rs_event is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_events.py::test_momentum_events_model_defaults -v`
Expected: FAIL with "No module named 'src.tools.technical.events_models'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/technical/events_models.py
from __future__ import annotations

from pydantic import BaseModel, Field


class MacdCross(BaseModel):
    """MACD 라인과 시그널선의 최근 교차 사건."""

    cross_type: str  # "golden" | "dead"
    date: str  # ISO date (YYYY-MM-DD)
    days_ago: int
    macd: float
    signal: float


class RsiDivergence(BaseModel):
    """가격과 RSI 간 다이버전스 사건."""

    divergence_type: str  # "bullish" | "bearish"
    date: str
    days_ago: int
    detail: str  # "가격 고점 상승, RSI 고점 하락 (72→68)"


class PriceEvent(BaseModel):
    """가격/구조 사건 (신고가 돌파/실패, 스윙로우 이탈/유지)."""

    code: str  # "NEW_HIGH_BREAKOUT" | "NEW_HIGH_FAIL" | "SWING_LOW_BREAK" | "SWING_LOW_HELD"
    side: str  # "bull" | "bear" | "neutral"
    headline: str
    detail: str
    date: str | None = None
    days_ago: int | None = None


class RsEvent(BaseModel):
    """상대강도(Mansfield RS) 음↔양 전환 사건."""

    cross_type: str  # "양전환" | "음전환"
    date: str
    days_ago: int
    detail: str


class MomentumEvents(BaseModel):
    """deep_dive가 result dict에 싣는 신규 사건 묶음."""

    macd_cross: MacdCross | None = None
    rsi_divergence: RsiDivergence | None = None
    ud_volume_ratio: float | None = None
    volume_trend: str | None = None  # "증가" | "감소" | "횡보"
    price_events: list[PriceEvent] = Field(default_factory=list)
    rs_event: RsEvent | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_events.py::test_momentum_events_model_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/events_models.py tests/tools/technical/test_events.py
git commit -m "feat(technical): add momentum event models"
```

---

## Task 2: U/D Volume Ratio + 거래량 추세 (Tool)

**Files:**
- Create: `src/tools/technical/events.py`
- Test: `tests/tools/technical/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_events.py (append)
import pandas as pd


def _df(closes, volumes):
    return pd.DataFrame(
        {"Close": closes, "Volume": volumes},
        index=pd.date_range("2026-01-01", periods=len(closes), freq="D"),
    )


def test_ud_volume_ratio_buy_pressure():
    from src.tools.technical.events import compute_ud_volume_ratio

    # closes 10,11,10,11,10,11 → 상승일 3개(vol 200×3=600), 하락일 2개(vol 100×2=200) → 3.0
    closes = [10, 11, 10, 11, 10, 11]
    volumes = [100, 200, 100, 200, 100, 200]
    assert compute_ud_volume_ratio(_df(closes, volumes), window=10) == 3.0


def test_ud_volume_ratio_no_down_days_returns_none():
    from src.tools.technical.events import compute_ud_volume_ratio

    assert compute_ud_volume_ratio(_df([10, 11, 12, 13], [100, 100, 100, 100]), window=10) is None


def test_volume_trend_rising():
    from src.tools.technical.events import compute_volume_trend

    assert compute_volume_trend(vol_sma_20=1_800_000, vol_sma_50=1_500_000) == "증가"
    assert compute_volume_trend(vol_sma_20=1_400_000, vol_sma_50=1_500_000) == "감소"
    assert compute_volume_trend(vol_sma_20=None, vol_sma_50=1_500_000) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_events.py -k "ud_volume or volume_trend" -v`
Expected: FAIL with "No module named 'src.tools.technical.events'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/technical/events.py
from __future__ import annotations

import pandas as pd

from src.tools.technical.events_models import (
    MacdCross,
    MomentumEvents,
    PriceEvent,
    RsiDivergence,
)


def compute_ud_volume_ratio(df: pd.DataFrame, window: int = 50) -> float | None:
    """최근 window일 상승일 거래량 합 ÷ 하락일 거래량 합. 하락일 없으면 None."""
    if "Close" not in df.columns or "Volume" not in df.columns or len(df) < 2:
        return None
    recent = df.tail(window)
    prev_close = recent["Close"].shift(1)
    up_vol = float(recent.loc[recent["Close"] > prev_close, "Volume"].sum())
    down_vol = float(recent.loc[recent["Close"] < prev_close, "Volume"].sum())
    if down_vol == 0:
        return None
    return round(up_vol / down_vol, 2)


def compute_volume_trend(vol_sma_20: float | None, vol_sma_50: float | None) -> str | None:
    """거래량 추세: 20일 평균 vs 50일 평균. ±2% 이내는 횡보."""
    if vol_sma_20 is None or vol_sma_50 is None or vol_sma_50 == 0:
        return None
    ratio = vol_sma_20 / vol_sma_50
    if ratio > 1.02:
        return "증가"
    if ratio < 0.98:
        return "감소"
    return "횡보"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_events.py -k "ud_volume or volume_trend" -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/events.py tests/tools/technical/test_events.py
git commit -m "feat(technical): add U/D volume ratio and volume trend"
```

---

## Task 3: MACD 골든/데드 크로스 (Tool)

**Files:**
- Modify: `src/tools/technical/events.py`
- Test: `tests/tools/technical/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_events.py (append)
def test_macd_golden_cross_with_date():
    from src.tools.technical.events import detect_macd_cross

    df = pd.DataFrame(
        {"MACD": [-1.0, -0.5, -0.2, 0.3, 0.5], "MACD_Signal": [0.0] * 5},
        index=pd.date_range("2026-06-01", periods=5, freq="D"),
    )
    cross = detect_macd_cross(df, lookback=10)
    assert cross is not None
    assert cross.cross_type == "golden"
    assert cross.date == "2026-06-04"
    assert cross.days_ago == 1


def test_macd_no_cross_returns_none():
    from src.tools.technical.events import detect_macd_cross

    df = pd.DataFrame(
        {"MACD": [1.0, 1.1, 1.2], "MACD_Signal": [0.0] * 3},
        index=pd.date_range("2026-06-01", periods=3, freq="D"),
    )
    assert detect_macd_cross(df, lookback=10) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_events.py -k "macd" -v`
Expected: FAIL with "has no attribute 'detect_macd_cross'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/technical/events.py (append)
def detect_macd_cross(df: pd.DataFrame, lookback: int = 60) -> MacdCross | None:
    """최근 lookback일 내 가장 최근 MACD-시그널 교차. 없으면 None."""
    if "MACD" not in df.columns or "MACD_Signal" not in df.columns:
        return None
    recent = df.tail(lookback).dropna(subset=["MACD", "MACD_Signal"])
    if len(recent) < 2:
        return None
    diff = recent["MACD"] - recent["MACD_Signal"]
    sign = diff.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    for i in range(len(sign) - 1, 0, -1):
        cur, prev = sign.iloc[i], sign.iloc[i - 1]
        if cur != 0 and prev != 0 and cur != prev:
            cross_date = recent.index[i]
            days_ago = len(df) - 1 - df.index.get_loc(cross_date)
            return MacdCross(
                cross_type="golden" if cur > 0 else "dead",
                date=cross_date.strftime("%Y-%m-%d"),
                days_ago=int(days_ago),
                macd=round(float(recent["MACD"].iloc[i]), 4),
                signal=round(float(recent["MACD_Signal"].iloc[i]), 4),
            )
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_events.py -k "macd" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/events.py tests/tools/technical/test_events.py
git commit -m "feat(technical): detect MACD golden/dead cross with date"
```

---

## Task 4: 가격 사건 (신고가/스윙로우) (Tool)

**Files:**
- Modify: `src/tools/technical/events.py`
- Test: `tests/tools/technical/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_events.py (append)
def test_price_events_new_high_breakout():
    from src.tools.technical.events import detect_price_events

    n = 60
    closes = [100.0] * (n - 1) + [115.0]
    df = pd.DataFrame(
        {
            "Close": closes,
            "High": [c + 1 for c in closes],
            "High_52w": [110.0] * n,
            "Swing_Low": [float("nan")] * (n - 1) + [90.0],
        },
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )
    events = detect_price_events(df)
    breakout = next(e for e in events if e.code == "NEW_HIGH_BREAKOUT")
    assert breakout.side == "bull"


def test_price_events_swing_low_break():
    from src.tools.technical.events import detect_price_events

    n = 60
    closes = [100.0] * (n - 1) + [85.0]
    df = pd.DataFrame(
        {
            "Close": closes,
            "High": [c + 1 for c in closes],
            "High_52w": [130.0] * n,
            "Swing_Low": [float("nan")] * (n - 2) + [90.0, float("nan")],
        },
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )
    events = detect_price_events(df)
    brk = next(e for e in events if e.code == "SWING_LOW_BREAK")
    assert brk.side == "bear"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_events.py -k "price_events" -v`
Expected: FAIL with "has no attribute 'detect_price_events'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/technical/events.py (append)
def detect_price_events(df: pd.DataFrame) -> list[PriceEvent]:
    """신고가 돌파/실패 + 스윙로우 이탈/유지 사건. raw_dataframe 컬럼 사용."""
    events: list[PriceEvent] = []
    if "Close" not in df.columns or len(df) < 2:
        return events

    last_close = float(df["Close"].iloc[-1])
    last_date = df.index[-1].strftime("%Y-%m-%d")

    if "High_52w" in df.columns and not pd.isna(df["High_52w"].iloc[-2]):
        prev_high_52w = float(df["High_52w"].iloc[-2])
        if last_close > prev_high_52w:
            events.append(PriceEvent(
                code="NEW_HIGH_BREAKOUT", side="bull", headline="52주 신고가 돌파",
                detail=f"종가 {last_close:.2f} > 직전 52주 고가 {prev_high_52w:.2f}",
                date=last_date, days_ago=0,
            ))
        elif "High" in df.columns:
            last_high = float(df["High"].iloc[-1])
            if last_high > prev_high_52w >= last_close:
                events.append(PriceEvent(
                    code="NEW_HIGH_FAIL", side="bear", headline="신고가 돌파 실패",
                    detail=f"장중 {last_high:.2f} 신고가 터치 후 종가 {last_close:.2f} 마감",
                    date=last_date, days_ago=0,
                ))

    if "Swing_Low" in df.columns:
        swing_lows = df["Swing_Low"].dropna()
        if not swing_lows.empty:
            recent_swing_low = float(swing_lows.iloc[-1])
            if last_close < recent_swing_low:
                events.append(PriceEvent(
                    code="SWING_LOW_BREAK", side="bear", headline="스윙로우 이탈",
                    detail=f"종가 {last_close:.2f} < 스윙로우 {recent_swing_low:.2f}",
                    date=last_date, days_ago=0,
                ))
            else:
                pct = (last_close - recent_swing_low) / recent_swing_low * 100
                events.append(PriceEvent(
                    code="SWING_LOW_HELD", side="neutral", headline="스윙로우 유지",
                    detail=f"스윙로우 {recent_swing_low:.2f} 대비 {pct:+.1f}% (이탈 없음)",
                    date=swing_lows.index[-1].strftime("%Y-%m-%d"),
                ))

    return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_events.py -k "price_events" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/events.py tests/tools/technical/test_events.py
git commit -m "feat(technical): detect new-high and swing-low events"
```

---

## Task 5: RSI 다이버전스 (plateau 대응) (Tool)

**Files:**
- Modify: `src/tools/technical/events.py`
- Test: `tests/tools/technical/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_events.py (append)
def test_rsi_bearish_divergence_with_date():
    from src.tools.technical.events import detect_rsi_divergence

    close = [100, 105, 101, 108, 102] + [101] * 15
    rsi = [60, 72, 64, 68, 62] + [60] * 15
    df = pd.DataFrame(
        {"Close": close, "RSI": rsi},
        index=pd.date_range("2026-05-01", periods=len(close), freq="D"),
    )
    div = detect_rsi_divergence(df)
    assert div is not None
    assert div.divergence_type == "bearish"


def test_rsi_no_divergence_returns_none():
    from src.tools.technical.events import detect_rsi_divergence

    df = pd.DataFrame(
        {"Close": list(range(100, 130)), "RSI": list(range(40, 70))},
        index=pd.date_range("2026-05-01", periods=30, freq="D"),
    )
    assert detect_rsi_divergence(df) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_events.py -k "rsi" -v`
Expected: FAIL with "has no attribute 'detect_rsi_divergence'"

- [ ] **Step 3: Write minimal implementation**

리뷰 반영: 평탄한 고점(plateau) 누락을 줄이기 위해 한쪽 비교에 `>=`를 허용하고, 보고 날짜는 가격 봉우리(actionable) 기준으로 한다.

```python
# src/tools/technical/events.py (append)
def _find_peaks(values: list[float]) -> list[int]:
    """local maxima 인덱스. plateau 대응: 왼쪽은 >, 오른쪽은 >= 로 평탄한 고점도 포착."""
    peaks = []
    for i in range(1, len(values) - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            peaks.append(i)
    return peaks


def detect_rsi_divergence(df: pd.DataFrame, window: int = 20) -> RsiDivergence | None:
    """최근 window일 가격-RSI 다이버전스 + 가격 봉우리 날짜."""
    if "RSI" not in df.columns or "Close" not in df.columns or len(df) < window:
        return None
    recent = df.tail(window).reset_index()
    date_col = recent.columns[0]
    price_peaks = _find_peaks(recent["Close"].tolist())
    rsi_peaks = _find_peaks(recent["RSI"].tolist())
    if len(price_peaks) < 2 or len(rsi_peaks) < 2:
        return None

    p_last, p_prev = price_peaks[-1], price_peaks[-2]
    r_last, r_prev = rsi_peaks[-1], rsi_peaks[-2]
    price_hi = recent["Close"].iloc[p_last] > recent["Close"].iloc[p_prev]
    price_lo = recent["Close"].iloc[p_last] < recent["Close"].iloc[p_prev]
    rsi_lower = recent["RSI"].iloc[r_last] < recent["RSI"].iloc[r_prev]
    rsi_higher = recent["RSI"].iloc[r_last] > recent["RSI"].iloc[r_prev]

    # 보고 날짜·days_ago 는 가격 봉우리(actionable) 기준
    peak_date = recent[date_col].iloc[p_last]
    days_ago = window - 1 - p_last

    if price_hi and rsi_lower:
        return RsiDivergence(
            divergence_type="bearish", date=peak_date.strftime("%Y-%m-%d"), days_ago=int(days_ago),
            detail=f"가격 고점 상승, RSI 고점 하락 ({recent['RSI'].iloc[r_prev]:.0f}→{recent['RSI'].iloc[r_last]:.0f})",
        )
    if price_lo and rsi_higher:
        return RsiDivergence(
            divergence_type="bullish", date=peak_date.strftime("%Y-%m-%d"), days_ago=int(days_ago),
            detail=f"가격 저점 하락, RSI 저점 상승 ({recent['RSI'].iloc[r_prev]:.0f}→{recent['RSI'].iloc[r_last]:.0f})",
        )
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_events.py -k "rsi" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/events.py tests/tools/technical/test_events.py
git commit -m "feat(technical): detect RSI divergence with plateau handling"
```

---

## Task 6: 사건 묶음 빌더 (Tool)

**Files:**
- Modify: `src/tools/technical/events.py`
- Test: `tests/tools/technical/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_events.py (append)
def test_build_momentum_events_assembles():
    from src.tools.technical.events import build_momentum_events
    from src.tools.technical.events_models import MomentumEvents

    n = 60
    closes = [100.0 + i * 0.1 for i in range(n)]
    df = pd.DataFrame(
        {
            "Close": closes, "High": [c + 1 for c in closes],
            "Volume": [100 + (i % 2) * 100 for i in range(n)],
            "MACD": [0.1] * n, "MACD_Signal": [0.0] * n, "RSI": [55.0] * n,
            "High_52w": [120.0] * n, "Swing_Low": [float("nan")] * (n - 1) + [95.0],
        },
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )
    ev = build_momentum_events(df, vol_sma_20=1800.0, vol_sma_50=1500.0)
    assert isinstance(ev, MomentumEvents)
    assert ev.ud_volume_ratio is not None
    assert ev.volume_trend == "증가"
    assert ev.rs_event is None  # RS 전환은 deep_dive 가 주입
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_events.py -k "build_momentum" -v`
Expected: FAIL with "has no attribute 'build_momentum_events'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/technical/events.py (append)
def build_momentum_events(
    df: pd.DataFrame, *, vol_sma_20: float | None, vol_sma_50: float | None
) -> MomentumEvents:
    """raw_dataframe + 거래량 SMA로 신규 사건 일괄 감지. RS 전환은 deep_dive 가 주입."""
    return MomentumEvents(
        macd_cross=detect_macd_cross(df),
        rsi_divergence=detect_rsi_divergence(df),
        ud_volume_ratio=compute_ud_volume_ratio(df),
        volume_trend=compute_volume_trend(vol_sma_20, vol_sma_50),
        price_events=detect_price_events(df),
        rs_event=None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_events.py -k "build_momentum" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/events.py tests/tools/technical/test_events.py
git commit -m "feat(technical): add momentum events assembler"
```

---

## Task 7: RS 음↔양 전환 날짜 (Tool — playbook)

**Files:**
- Modify: `src/tools/criteria/models.py` (RelativeStrengthResult)
- Modify: `src/tools/criteria/relative_strength.py`
- Test: `tests/tools/criteria/test_relative_strength.py`

- [ ] **Step 1: Write the failing test**

리뷰 반영: 종목이 먼저 **언더퍼폼**(mansfield<0)했다가 아웃퍼폼(mansfield>0)하는 진짜 −1→+1 전환을 만들고, `if` 가드 없이 단언한다.

```python
# tests/tools/criteria/test_relative_strength.py (append)
import pandas as pd


def test_rs_cross_positive_detected():
    from src.tools.criteria.relative_strength import compute_relative_strength

    n = 320
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    index = [100.0] * n
    # 전반부 종목이 지수보다 약함(언더퍼폼) → mansfield<0, 후반부 급등 → mansfield>0
    stock = [100.0 - i * 0.1 for i in range(n - 60)] + [
        (100.0 - (n - 60) * 0.1) + j * 1.5 for j in range(60)
    ]
    result = compute_relative_strength(
        pd.DataFrame({"Close": stock}, index=idx),
        pd.DataFrame({"Close": index}, index=idx),
        "^GSPC",
    )
    assert result.rs_cross_type == "양전환"
    assert result.rs_cross_date is not None
    assert result.rs_cross_days_ago is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/criteria/test_relative_strength.py::test_rs_cross_positive_detected -v`
Expected: FAIL with "'RelativeStrengthResult' object has no attribute 'rs_cross_type'"

- [ ] **Step 3: Write minimal implementation**

`src/tools/criteria/models.py` — `RelativeStrengthResult`에 필드 추가 (`index_symbol` 다음, `is_strong` computed_field 위):

```python
    # RS 음↔양 전환 사건 (최근 lookback 내). 없으면 None.
    rs_cross_type: str | None = None  # "양전환" | "음전환"
    rs_cross_date: str | None = None  # ISO date
    rs_cross_days_ago: int | None = None
```

`src/tools/criteria/relative_strength.py` — 헬퍼 추가 + `compute_relative_strength` 확장:

```python
def _detect_rs_cross(mansfield_series: pd.Series, lookback: int = 60):
    """최근 lookback 내 mansfield 부호 전환. (type, ISO date, days_ago). 진짜 -1↔+1 만."""
    s = mansfield_series.dropna()
    if len(s) < 2:
        return None, None, None
    recent = s.tail(lookback)
    sign = recent.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    for i in range(len(sign) - 1, 0, -1):
        cur, prev = sign.iloc[i], sign.iloc[i - 1]
        if cur != 0 and prev != 0 and cur != prev:
            cross_date = recent.index[i]
            days_ago = len(s) - 1 - s.index.get_loc(cross_date)
            return ("양전환" if cur > 0 else "음전환", cross_date.strftime("%Y-%m-%d"), int(days_ago))
    return None, None, None
```

`compute_relative_strength` 내부, `mansfield` 단일값 계산 직후 시계열 + 전환 감지를 넣고 return을 확장:

```python
    mansfield = ((last_rp / last_sma) - 1.0) * 100.0 if last_sma else 0.0

    mansfield_series = ((rp / rp_sma) - 1.0) * 100.0
    cross_type, cross_date, cross_days_ago = _detect_rs_cross(mansfield_series)

    slope_n = min(_SLOPE_DAYS, len(rp) - 1)
    rp_slope = float(rp.iloc[-1] - rp.iloc[-1 - slope_n])

    def _perf(series: pd.Series) -> float:
        n = min(_PERF_DAYS, len(series) - 1)
        past = float(series.iloc[-1 - n])
        return ((float(series.iloc[-1]) - past) / past) * 100.0 if past else 0.0

    outperform = _perf(s.loc[common]) - _perf(i.loc[common])

    return RelativeStrengthResult(
        mansfield_rs=round(mansfield, 2),
        outperform_6m=round(outperform, 2),
        rp_slope_4w=round(rp_slope, 6),
        index_symbol=index_symbol,
        rs_cross_type=cross_type,
        rs_cross_date=cross_date,
        rs_cross_days_ago=cross_days_ago,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/criteria/test_relative_strength.py -v`
Expected: PASS (기존 포함 전부)

- [ ] **Step 5: Commit**

```bash
git add src/tools/criteria/models.py src/tools/criteria/relative_strength.py tests/tools/criteria/test_relative_strength.py
git commit -m "feat(playbook): detect RS positive/negative cross with date"
```

---

## Task 8: deep_dive 배선 (Pipeline — 조율만)

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Test: `tests/pipelines/test_deep_dive_events.py` (신규)

- [ ] **Step 1: Write the failing test**

```python
# tests/pipelines/test_deep_dive_events.py
def test_rs_event_from_verdict():
    from src.pipelines.deep_dive import _rs_event_from_verdict
    from src.tools.criteria.models import RelativeStrengthResult

    rs = RelativeStrengthResult(
        mansfield_rs=2.1, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC",
        rs_cross_type="양전환", rs_cross_date="2026-06-01", rs_cross_days_ago=10,
    )
    event = _rs_event_from_verdict(rs)
    assert event is not None
    assert event.cross_type == "양전환"
    assert event.date == "2026-06-01"


def test_rs_event_none_when_no_cross():
    from src.pipelines.deep_dive import _rs_event_from_verdict
    from src.tools.criteria.models import RelativeStrengthResult

    rs = RelativeStrengthResult(
        mansfield_rs=2.1, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC"
    )
    assert _rs_event_from_verdict(rs) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/test_deep_dive_events.py -v`
Expected: FAIL with "cannot import name '_rs_event_from_verdict'"

- [ ] **Step 3: Write minimal implementation**

`src/pipelines/deep_dive.py` import 추가 (Tool 호출 — Pipeline은 계산 안 하고 호출만):

```python
from src.tools.technical.events import build_momentum_events
from src.tools.technical.events_models import MomentumEvents, RsEvent
```

모듈 레벨 헬퍼 (`_compute_eps_cagr` 아래):

```python
def _rs_event_from_verdict(relative_strength) -> RsEvent | None:
    """criteria_verdict.relative_strength 의 전환 필드 → RsEvent."""
    if relative_strength is None:
        return None
    cross_type = getattr(relative_strength, "rs_cross_type", None)
    if cross_type is None:
        return None
    return RsEvent(
        cross_type=cross_type,
        date=getattr(relative_strength, "rs_cross_date", "") or "",
        days_ago=getattr(relative_strength, "rs_cross_days_ago", 0) or 0,
        detail=f"Mansfield RS {relative_strength.mansfield_rs:+.1f} ({cross_type})",
    )
```

`run()` 내부 — criteria_verdict 계산 이후, return dict 직전:

```python
        snapshot = technical_data.snapshot
        momentum_events: MomentumEvents = build_momentum_events(
            df, vol_sma_20=snapshot.vol_sma_20, vol_sma_50=snapshot.vol_sma_50
        )
        if criteria_verdict is not None:
            momentum_events.rs_event = _rs_event_from_verdict(criteria_verdict.relative_strength)
```

return dict에 키 추가:

```python
            "momentum_events": momentum_events,
```

> 참고: 이 플랜에서는 veto/integrated/actionable 제거나 debate 배선을 하지 않는다(플랜 B 소관). deep_dive는 momentum_events 키만 추가한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/test_deep_dive_events.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/deep_dive.py tests/pipelines/test_deep_dive_events.py
git commit -m "feat(deep_dive): call events tool, add momentum_events to result"
```

---

## Task 9: 렌더 모듈 분리 — analyze_render.py 생성 (CLI)

main.py의 deep_dive 렌더 로직을 **그대로** `src/cli/analyze_render.py`로 옮긴다. 동작 변경 없음(순수 이동). 새 섹션 함수(Task 10-15)와 레이아웃 변경(Task 16)은 이동 후에 이 파일에서 한다.

**Files:**
- Create: `src/cli/analyze_render.py`
- Modify: `src/cli/main.py`
- Test: `tests/cli/test_analyze_render.py` (신규)

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_analyze_render.py
def test_render_module_exposes_format_deep_dive_output():
    from src.cli.analyze_render import format_deep_dive_output
    assert callable(format_deep_dive_output)


def test_main_reexports_format_deep_dive_output():
    # 기존 import 경로 호환 유지
    from src.cli.main import format_deep_dive_output
    assert callable(format_deep_dive_output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_analyze_render.py -v`
Expected: FAIL with "No module named 'src.cli.analyze_render'"

- [ ] **Step 3: Move render functions**

1. `src/cli/analyze_render.py`를 새로 만들고, main.py에서 다음 함수와 그 전용 헬퍼를 **잘라내어** 옮긴다:
   - `format_deep_dive_output`
   - `_format_factor_section`, `_format_scenario_section`, `_format_pattern_section`
   - `_format_structure_levels`, `_format_presented_structure`, `_format_execution_levels`, `_format_zone_bounds`, `_split_supply_zones_by_price`, `_to_payload_dict`
   - `_format_criteria_section`, `_format_raw_analysis_sections`
   - 이들이 쓰는 표시 헬퍼: `_format_metric_value`, `_format_disclosure_title`, `_format_growth_rate`, `_format_factor_label`, `_format_timing_label`, `_get_metric_display_name`
   - **제외(삭제)**: `_format_top_summary` — 옮기지 않고 main.py에서 삭제(판단요약 제거, R4)
   - ⚠️ **`_format_criteria_section` 이동 시 내부 수정 필요**: 게이트 체크리스트 블록(현 main.py:849-858)과 CAN SLIM 블록(현 main.py:860-878)을 **제거**한다 — 각각 Task 10 Summary 섹션, Task 11 CAN SLIM 섹션으로 역할 이동. 포지션 플랜(880-894)과 매도 판정(896-910)만 남기고 함수 헤더를 `## 📋 포지션 플랜 / 청산 판단`으로 변경. 이렇게 해야 Task 16의 `_format_criteria_section(criteria_verdict)` 호출이 증거 상세에서 이중 렌더를 일으키지 않는다.
2. analyze_render.py 상단에 필요한 import를 옮긴다 (`SectorMetrics` 등 이 함수들이 쓰던 것).
3. main.py 끝에 호환용 re-export 추가:

```python
# src/cli/main.py
from src.cli.analyze_render import format_deep_dive_output
```

4. main.py의 `analyze` 커맨드는 `format_deep_dive_output(result)` 호출을 그대로 둔다(이제 import된 것을 사용).

- [ ] **Step 4: Run tests (이동 회귀 확인)**

Run: `uv run pytest tests/cli/test_analyze_render.py tests/cli/test_analyze_output.py -v`
Expected: `test_analyze_render.py` PASS. `test_analyze_output.py`는 아직 옛 레이아웃을 단언하므로 통과(이동만 했고 동작 동일). 단, `_format_top_summary`를 직접 import하던 테스트가 있으면 이 단계에서 빨간불 → Task 18에서 일괄 정리.

- [ ] **Step 5: Commit**

```bash
git add src/cli/analyze_render.py src/cli/main.py tests/cli/test_analyze_render.py
git commit -m "refactor(cli): extract deep dive render into analyze_render.py"
```

---

## Task 10-15: 새 섹션 포맷 함수 (CLI — analyze_render.py)

각 task는 `src/cli/analyze_render.py`에 함수 추가 + `tests/cli/test_analyze_render.py`에 테스트. (Summary / CAN SLIM / Stage2 / 모멘텀 / Event / 구조레벨)

### Task 10: Summary 섹션

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_analyze_render.py (append)
from src.tools.criteria.models import CriteriaCheck, _GateEvaluation, RelativeStrengthResult


def _gate():
    return _GateEvaluation(
        passed=True,
        checklist=[
            CriteriaCheck(name="A", required=True, met=True, reason="시장환경=상승"),
            CriteriaCheck(name="B", required=True, met=True, reason="is_stage2=1.0 (7/7)"),
            CriteriaCheck(name="C", required=True, met=True, reason="RS=True, 업종강세=True"),
            CriteriaCheck(name="E", required=True, met=True, reason="breakout=True"),
        ],
        quality_grade="A", veto_reason=None,
    )


def test_format_summary_section():
    from src.cli.analyze_render import _format_summary_section

    rs = RelativeStrengthResult(mansfield_rs=2.1, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC")
    out = _format_summary_section(
        gate=_gate(), relative_strength=rs, high_52w=160.5, price=155.3,
        ud_volume_ratio=1.8, atr=3.2, perf_3m=18.0, perf_1y=45.0,
    )
    assert "Summary" in out
    assert "2.1" in out
    assert "-3.2%" in out or "-3.24%" in out
    assert "18" in out
```

- [ ] **Step 2: Run** `uv run pytest tests/cli/test_analyze_render.py::test_format_summary_section -v` → FAIL ("cannot import name '_format_summary_section'")

- [ ] **Step 3: Implement** (analyze_render.py에 추가)

```python
def _format_summary_section(*, gate, relative_strength, high_52w, price,
                            ud_volume_ratio, atr, perf_3m, perf_1y) -> str:
    """Summary: 게이트 pass/fail(부연) + 핵심 수치 + 퍼포먼스."""
    lines = ["## 📊 Summary", ""]
    if gate is not None:
        sym = {True: "✅", False: "❌", None: "—"}
        gate_parts = [f"{c.name}{sym[c.met]}" for c in checks if c.required]
        grade = f" · 등급 {quality_grade}" if quality_grade else ""
        lines.append(f"**게이트**: {' '.join(gate_parts)}{grade}")
        for c in checks:
            if c.required:
                lines.append(f"- {c.name}: {c.reason}")
        lines.append("")
    metrics = []
    if relative_strength is not None:
        metrics.append(f"Mansfield RS {relative_strength.mansfield_rs:+.1f}")
    if high_52w and high_52w > 0:
        metrics.append(f"52주 고점 대비 {(price - high_52w) / high_52w * 100:+.1f}%")
    if ud_volume_ratio is not None:
        metrics.append(f"U/D 거래량 {ud_volume_ratio:.1f}")
    if atr is not None:
        metrics.append(f"ATR {atr:.2f}")
    if metrics:
        lines.append("**핵심 수치**: " + " | ".join(metrics))
    perf = []
    if perf_3m is not None:
        perf.append(f"3M {perf_3m:+.1f}%")
    if perf_1y is not None:
        perf.append(f"1Y {perf_1y:+.1f}%")
    if perf:
        lines.append("**퍼포먼스**: " + " | ".join(perf))
    lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(cli): add Summary section formatter`

### Task 11: CAN SLIM 섹션

- [ ] **Step 1: Test**

```python
# tests/cli/test_analyze_render.py (append)
def test_format_canslim_section_shows_unmet():
    from src.cli.analyze_render import _format_canslim_section
    from src.tools.criteria.models import CanslimResult, ElementVerdict

    canslim = CanslimResult(
        c=ElementVerdict(met=True, detail="분기 EPS +42% (기준 25%)"),
        a=ElementVerdict(met=True, detail="연간 CAGR +28%"),
        n=ElementVerdict(met=True, detail="신제품"), s=ElementVerdict(met=True, detail="거래량 +180%"),
        l=ElementVerdict(met=True, detail="RS 강세"),
        i=ElementVerdict(met=False, detail="매집비율 0.38 (기준 0.50)"),
        m=ElementVerdict(met=True, detail="상승장"),
    )
    out = _format_canslim_section(canslim)
    assert "CAN SLIM" in out
    assert "6 / 7" in out
    assert "미충족" in out and "I" in out
    assert "0.38" in out and "+42%" in out
```

- [ ] **Step 2: Run** → FAIL  **Step 3: Implement**

```python
def _format_canslim_section(canslim) -> str:
    """CAN SLIM: 점수 + 미충족 한 줄 + 전 요소 수치."""
    if canslim is None:
        return ""
    order = [("C", canslim.c, "분기 EPS"), ("A", canslim.a, "연간 CAGR"), ("N", canslim.n, "신요소"),
             ("S", canslim.s, "수급"), ("L", canslim.l, "주도주(RS)"), ("I", canslim.i, "기관매집"),
             ("M", canslim.m, "시장")]
    graded = sum(1 for _, e, _ in order if e.met is not None)
    unmet = [(k, lbl) for k, e, lbl in order if e.met is False]
    lines = ["## CAN SLIM", ""]
    header = f"**{canslim.score} / {graded}**"
    if unmet:
        header += " · 미충족: " + ", ".join(f"{k}({lbl})" for k, lbl in unmet)
    lines += [header, ""]
    sym = {True: "✅", False: "❌", None: "—"}
    for k, e, lbl in order:
        lines.append(f"- {sym[e.met]} **{k} {lbl}**: {e.detail or '—'}")
    lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(cli): add CAN SLIM section formatter`

### Task 12: Stage2 섹션 (Supertrend gap%)

- [ ] **Step 1: Test**

```python
# tests/cli/test_analyze_render.py (append)
def test_format_stage2_section_with_supertrend():
    from src.cli.analyze_render import _format_stage2_section

    snap = {"price": 155.3, "sma_20": 148.2, "sma_50": 142.1, "sma_150": 135.6,
            "sma_200": 128.4, "high_52w": 160.5, "supertrend_direction": 1}
    out = _format_stage2_section(snapshot_dict=snap, gate_b_reason="is_stage2=1.0 (7/7)", supertrend_value=140.0)
    assert "Stage 2" in out and "148.2" in out
    assert "Supertrend" in out and "상승" in out
    assert "10.9%" in out or "+10.9" in out
```

- [ ] **Step 2: Run** → FAIL  **Step 3: Implement**

```python
def _format_stage2_section(*, snapshot_dict, gate_b_reason, supertrend_value) -> str:
    """Stage 2: SMA 값 + 정배열 + Supertrend(방향/라인/gap%)."""
    price = snapshot_dict.get("price")
    lines = ["## Stage 2", ""]
    if gate_b_reason:
        lines += [f"**판정**: {gate_b_reason}", ""]
    for length in (20, 50, 150, 200):
        val = snapshot_dict.get(f"sma_{length}")
        if val is not None:
            lines.append(f"- **SMA {length}**: ${val:.2f}")
    smas = [snapshot_dict.get(f"sma_{n}") for n in (20, 50, 150, 200)]
    if price is not None and all(s is not None for s in smas):
        aligned = price > smas[0] > smas[1] > smas[2] > smas[3]
        lines.append(f"- **배열**: {'정배열' if aligned else '비정배열'} (종가 ${price:.2f})")
    direction = snapshot_dict.get("supertrend_direction")
    if direction is not None:
        line = f"- **Supertrend**: {'상승' if direction == 1 else '하락'}"
        if supertrend_value is not None and price is not None:
            line += f" (라인 ${supertrend_value:.2f}, 현재가 대비 {(price - supertrend_value) / supertrend_value * 100:+.1f}%)"
        lines.append(line)
    high_52w = snapshot_dict.get("high_52w")
    if high_52w and price is not None and high_52w > 0:
        lines.append(f"- **52주 고점 대비**: {(price - high_52w) / high_52w * 100:+.1f}%")
    lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(cli): add Stage2 section with Supertrend`

### Task 13: 모멘텀 섹션

- [ ] **Step 1: Test**

```python
# tests/cli/test_analyze_render.py (append)
def test_format_momentum_section():
    from src.cli.analyze_render import _format_momentum_section
    from src.tools.technical.events_models import MacdCross, MomentumEvents

    events = MomentumEvents(
        macd_cross=MacdCross(cross_type="golden", date="2026-05-29", days_ago=10, macd=1.85, signal=1.42),
        ud_volume_ratio=1.6, volume_trend="증가",
    )
    snap = {"rsi": 68.2, "macd": 1.85, "macd_signal": 1.42, "macd_histogram": 0.43, "adx": 28.5}
    out = _format_momentum_section(snapshot_dict=snap, events=events)
    assert "모멘텀" in out and "68.2" in out
    assert "골든" in out and "2026-05-29" in out
    assert "1.6" in out and "28.5" in out
```

- [ ] **Step 2: Run** → FAIL  **Step 3: Implement**

```python
def _format_momentum_section(*, snapshot_dict, events) -> str:
    """모멘텀: RSI(다이버전스) + MACD(크로스) + 거래량(U/D·추세) + ADX."""
    lines = ["## 모멘텀", ""]
    rsi = snapshot_dict.get("rsi")
    if rsi is not None:
        state = "과매수" if rsi >= 70 else "과매도" if rsi <= 30 else "중립"
        lines.append(f"- **RSI (14)**: {rsi:.1f} ({state})")
    if events is not None and events.rsi_divergence is not None:
        d = events.rsi_divergence
        kind = "하락(Bearish)" if d.divergence_type == "bearish" else "상승(Bullish)"
        lines.append(f"  - 다이버전스: {kind} — {d.detail} ({d.date})")
    macd = snapshot_dict.get("macd")
    if macd is not None:
        parts = [f"{macd:+.2f}"]
        if snapshot_dict.get("macd_signal") is not None:
            parts.append(f"Signal {snapshot_dict['macd_signal']:+.2f}")
        if snapshot_dict.get("macd_histogram") is not None:
            parts.append(f"Hist {snapshot_dict['macd_histogram']:+.2f}")
        lines.append(f"- **MACD**: {' · '.join(parts)}")
    if events is not None and events.macd_cross is not None:
        c = events.macd_cross
        lines.append(f"  - {'골든크로스' if c.cross_type == 'golden' else '데드크로스'}: {c.date} ({c.days_ago}일 전)")
    if events is not None:
        if events.ud_volume_ratio is not None:
            lines.append(f"- **U/D Volume Ratio**: {events.ud_volume_ratio:.1f} (상승일/하락일 거래량, 50일)")
        if events.volume_trend is not None:
            lines.append(f"- **거래량 추세**: {events.volume_trend} (20일 vs 50일 평균)")
    adx = snapshot_dict.get("adx")
    if adx is not None:
        strength = "강함" if adx >= 25 else "약함" if adx < 20 else "보통"
        lines.append(f"- **ADX (추세 강도)**: {adx:.1f} ({strength})")
    lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(cli): add momentum section`

### Task 14: Event 섹션

- [ ] **Step 1: Test**

```python
# tests/cli/test_analyze_render.py (append)
def test_format_event_section():
    from src.cli.analyze_render import _format_event_section
    from src.tools.technical.events_models import MomentumEvents, PriceEvent, RsEvent

    events = MomentumEvents(
        price_events=[PriceEvent(code="NEW_HIGH_BREAKOUT", side="bull", headline="52주 신고가 돌파",
                                 detail="종가 155.3 > 152.5", date="2026-06-12", days_ago=0)],
        rs_event=RsEvent(cross_type="양전환", date="2026-06-01", days_ago=10, detail="Mansfield RS +2.1 (양전환)"),
    )
    patterns = {"vcp": {"pattern_name": "VCP", "detected": True, "confidence": 0.8,
                        "completed_date": "2026-06-10", "days_ago": 3, "description": "pivot 152.5"}}
    out = _format_event_section(events=events, chart_patterns=patterns)
    assert "Event" in out and "신고가 돌파" in out
    assert "양전환" in out and "VCP" in out and "2026-06-10" in out
```

- [ ] **Step 2: Run** → FAIL  **Step 3: Implement**

```python
def _format_event_section(*, events, chart_patterns) -> str:
    """Event: 가격 사건 + RS 전환 + 차트패턴(완성 날짜)."""
    lines = ["## Event", ""]
    has_any = False
    if events is not None:
        for pe in events.price_events:
            has_any = True
            when = f" ({pe.date})" if pe.date else ""
            lines.append(f"- **{pe.headline}**: {pe.detail}{when}")
        if events.rs_event is not None:
            has_any = True
            r = events.rs_event
            lines.append(f"- **RS {r.cross_type}**: {r.detail} ({r.date}, {r.days_ago}일 전)")
    if isinstance(chart_patterns, dict):
        for item in chart_patterns.values():
            payload = item if isinstance(item, dict) else item.model_dump()
            if not payload.get("detected"):
                continue
            has_any = True
            days_ago = payload.get("days_ago")
            timing = ("오늘 완성" if days_ago == 0 else f"{days_ago}일 전 완성"
                      if isinstance(days_ago, int) else "완성 시점 미확인")
            completed = payload.get("completed_date")
            when = f" ({completed})" if completed else ""
            lines.append(f"- **{payload.get('pattern_name', '패턴')}**: {timing}{when} | {payload.get('description', '')}")
    if not has_any:
        lines.append("- 감지된 사건 없음")
    lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(cli): add Event section`

### Task 15: 구조 레벨 섹션

- [ ] **Step 1: Test**

```python
# tests/cli/test_analyze_render.py (append)
def test_format_structure_section_with_pivots():
    from src.cli.analyze_render import _format_structure_section

    snap = {"pivot": 150.0, "support_s1": 145.0, "resistance_r1": 158.0, "price": 155.3}
    out = _format_structure_section(structure_levels=None, presented_structure=None, snapshot_dict=snap)
    assert "구조 레벨" in out
    assert "150.0" in out and "145.0" in out and "158.0" in out
```

- [ ] **Step 2: Run** → FAIL  **Step 3: Implement** (기존 `_format_presented_structure`/`_format_structure_levels` 재사용)

```python
def _format_structure_section(*, structure_levels, presented_structure, snapshot_dict) -> str:
    """구조 레벨: 수요/공급/밸런스 존 + Pivot/S1/R1."""
    parts = []
    if presented_structure:
        parts.append(_format_presented_structure(presented_structure))
    elif structure_levels:
        parts.append(_format_structure_levels(structure_levels, snapshot_dict.get("price", 0.0)))
    else:
        parts.append("## 구조 레벨\n")
    pivot, s1, r1 = snapshot_dict.get("pivot"), snapshot_dict.get("support_s1"), snapshot_dict.get("resistance_r1")
    if any(v is not None for v in (pivot, s1, r1)):
        pl = ["**피봇 레벨**:"]
        if pivot is not None:
            pl.append(f"- 피봇: ${pivot:.2f}")
        if s1 is not None:
            pl.append(f"- 지지 S1: ${s1:.2f}")
        if r1 is not None:
            pl.append(f"- 저항 R1: ${r1:.2f}")
        parts.append("\n".join(pl) + "\n")
    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(cli): add structure level section`

---

## Task 16: format_deep_dive_output 재구성 (CLI — 판단요약 없음)

**Files:**
- Modify: `src/cli/analyze_render.py`
- Test: `tests/cli/test_analyze_render.py`

- [ ] **Step 1: Write the failing test (통합 렌더)**

```python
# tests/cli/test_analyze_render.py (append)
def test_format_deep_dive_output_section_order_no_verdict():
    """플랜 A 출력: 판단요약·종합판정 없음. Summary→CANSLIM→Stage2→모멘텀→Event→구조→증거상세→원시."""
    from src.cli.analyze_render import format_deep_dive_output
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult
    from src.tools.technical.events_models import MomentumEvents
    from datetime import datetime

    snap = IndicatorSnapshot(price=155.3, change_pct=1.2, rsi=68.2, sma_20=148.2,
                             sma_50=142.1, sma_150=135.6, sma_200=128.4, high_52w=160.5)
    tech = TechnicalResult(ticker="TEST", timestamp=datetime(2026, 6, 15), snapshot=snap,
                           components={}, total_score=0)

    class _Sum:
        summary = "s"; recommendation = "보유"; confidence = 0.5; rationale = "r"; key_insights = []

    result = {
        "ticker": "TEST", "technical": tech, "technical_summary": _Sum(),
        "momentum_events": MomentumEvents(), "criteria_verdict": None,
        "chart_patterns": {}, "factor_assessments": [], "scenarios": [],
    }
    out = format_deep_dive_output(result)
    assert "## 📊 Summary" in out
    assert "## 모멘텀" in out
    assert "## Event" in out
    assert "판단 요약" not in out  # 삭제됨
    assert out.index("## 📊 Summary") < out.index("## 모멘텀") < out.index("## Event")
```

- [ ] **Step 2: Run** → FAIL (옛 format_deep_dive_output은 판단요약 포함)

- [ ] **Step 3: Rewrite format_deep_dive_output**

```python
def format_deep_dive_output(result: dict) -> str:
    """Format deep dive result as markdown (구조화 레이아웃, 결론 없음 — 플랜 A)."""
    ticker = result["ticker"]
    technical = result["technical"]
    snapshot = technical.indicators or technical.snapshot
    snapshot_dict = snapshot.model_dump()
    criteria_verdict = result.get("criteria_verdict")
    events = result.get("momentum_events")
    chart_patterns = result.get("chart_patterns")
    presented_structure = result.get("presented_structure")
    structure_levels = result.get("structure_levels")

    output = f"# Deep Dive Analysis: {ticker}\n\n"
    output += f"## 가격: ${snapshot.price:.2f} ({snapshot.change_pct:+.2f}%)\n\n"

    # [플랜 B가 여기에 종합 판정(debate) 섹션을 삽입한다 — 가격 줄과 Summary 사이]

    gate = criteria_verdict.gate if criteria_verdict else None
    rs = criteria_verdict.relative_strength if criteria_verdict else None
    output += _format_summary_section(
        gate=gate, relative_strength=rs, high_52w=snapshot.high_52w, price=snapshot.price,
        ud_volume_ratio=events.ud_volume_ratio if events else None,
        atr=snapshot.atr, perf_3m=snapshot.perf_3m, perf_1y=snapshot.perf_1y,
    )
    if criteria_verdict and criteria_verdict.canslim:
        output += _format_canslim_section(criteria_verdict.canslim)

    gate_b_reason = None
    if gate is not None:
        gb = next((c for c in checks if c.name == "B"), None)
        gate_b_reason = gb.reason if gb else None
    supertrend_value = None
    if technical.components and "supertrend" in technical.components:
        supertrend_value = technical.components["supertrend"]["metrics"].get("supertrend_value")
    output += _format_stage2_section(snapshot_dict=snapshot_dict, gate_b_reason=gate_b_reason,
                                     supertrend_value=supertrend_value)
    output += _format_momentum_section(snapshot_dict=snapshot_dict, events=events)
    output += _format_event_section(events=events, chart_patterns=chart_patterns)
    output += _format_structure_section(structure_levels=structure_levels,
                                        presented_structure=presented_structure, snapshot_dict=snapshot_dict)

    factor_assessments = result.get("factor_assessments", [])
    scenarios = result.get("scenarios", [])
    output += "## 📊 증거 상세\n\n"
    if criteria_verdict is not None:
        output += _format_criteria_section(criteria_verdict)
    if factor_assessments:
        output += _format_factor_section(factor_assessments) + "\n"
    if scenarios:
        output += _format_scenario_section(scenarios) + "\n"

    output += "\n"
    output += _format_raw_analysis_sections(result)
    return output
```

- [ ] **Step 4: Run** `uv run pytest tests/cli/test_analyze_render.py -v` → PASS (all)

- [ ] **Step 5: Commit** `feat(cli): restructure deep dive output, drop 판단요약`

---

## Task 17: main.py 정리 (판단요약·actionable 잔재)

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: Grep 잔재**

Run: `grep -n "_format_top_summary\|decision_summary" src/cli/main.py`
Expected: `analyze` 커맨드의 actionable 패널 분기(`if actionable_signal and not result.get("decision_summary")`)와 `_format_top_summary` 정의가 남아있다.

- [ ] **Step 2: Remove**

1. `_format_top_summary` 정의가 main.py에 아직 있으면 삭제(Task 9에서 이미 안 옮겼으면 정의 자체 삭제).
2. `analyze` 커맨드의 actionable 패널 출력 분기는 플랜 B에서 제거하지만, 이 플랜에서 출력 레이아웃상 혼동을 막기 위해 `decision_summary` 의존 조건만 단순화하지 않는다 — **건드리지 않고 플랜 B에 위임**(actionable 제거는 플랜 B Task 10).

> 이 플랜은 판단요약 렌더만 제거한다. actionable/integrated/veto 제거는 플랜 B 소관(중복 작업 방지).

- [ ] **Step 3: Verify**

Run: `grep -n "_format_top_summary" src/cli/main.py src/cli/analyze_render.py`
Expected: 빈 결과 (완전 삭제)

- [ ] **Step 4: Run** `uv run pytest tests/cli/ -v` → 통과(깨지는 것은 Task 18에서)

- [ ] **Step 5: Commit** `refactor(cli): drop 판단요약 from main`

---

## Task 18: 기존 출력 테스트 마이그레이션

리뷰 지적(C1): 옛 레이아웃을 단언하는 테스트를 새 레이아웃으로 갱신한다.

**Files:**
- Modify: `tests/cli/test_analyze_output.py`, `tests/cli/test_analyze_structure_golden.py`

- [ ] **Step 1: Identify breakages**

Run: `uv run pytest tests/cli/test_analyze_output.py tests/cli/test_analyze_structure_golden.py -v`
Expected: 옛 섹션(`## 판단 요약`, `## 패턴 분석`, `## 실행 레벨`, `presenter payload 누락`)을 단언하는 테스트가 FAIL.

- [ ] **Step 2: Update assertions**

각 실패 테스트를 새 레이아웃에 맞게 수정:
- `## 판단 요약` 단언 → 삭제(판단요약 제거됨). 대신 `## 📊 Summary` 존재 단언.
- `## 패턴 분석` 단언 → `## Event`에 패턴이 들어가므로 `## Event` + 패턴명 단언으로 변경.
- `## 실행 레벨` 단언 → `## 📊 증거 상세` 또는 구조 섹션으로 이동했으므로 해당 섹션 단언으로 변경.
- `presenter payload 누락` 단언 → `_format_structure_section`이 `## 구조 레벨` 헤더를 내므로 그것으로 변경.
- `from src.cli.main import _format_top_summary` 등 삭제 심볼 import → 제거.
- `format_deep_dive_output` import는 main.py re-export로 유지되므로 변경 불필요.

- [ ] **Step 3: Run** `uv run pytest tests/cli/ -v` → PASS (all)

- [ ] **Step 4: Commit** `test(cli): migrate output tests to structured layout`

---

## Task 19: 전체 회귀 + FEATURES.md

**Files:**
- Modify: `docs/FEATURES.md`

- [ ] **Step 1: Full suite**

Run: `uv run pytest tests/tools/technical/test_events.py tests/tools/criteria/test_relative_strength.py tests/pipelines/test_deep_dive_events.py tests/cli/ -v`
Expected: PASS (all)

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/tools/technical/events.py src/tools/technical/events_models.py src/cli/analyze_render.py src/cli/main.py src/tools/criteria/relative_strength.py src/pipelines/deep_dive.py`
Expected: no errors

- [ ] **Step 3: Update FEATURES.md** (analyze 섹션에 추가)

```markdown
- **구조화 분석 출력**: Summary(게이트+핵심수치+퍼포먼스 3M·1Y) / CAN SLIM(미충족 한 줄+전 요소 수치) / Stage2(SMA+Supertrend gap%) / 모멘텀(RSI 다이버전스·MACD 크로스·U/D Volume·ADX) / Event(신고가·스윙로우·RS 전환·차트패턴 완성일) / 구조레벨(존+Pivot/S1/R1) / 원시데이터. 렌더는 `src/cli/analyze_render.py`로 분리.
- **신규 사건 감지** (`src/tools/technical/events.py`): MACD 골든/데드 크로스, RSI 다이버전스, 신고가 돌파/실패, 스윙로우 이탈/유지 — 발생 날짜 포함. RS 음↔양 전환은 `relative_strength.py`.
- **U/D Volume Ratio**: 50일 상승일/하락일 거래량 압력 비율.
```

> 주의: SMA 기울기(%/주)는 구현하지 않으므로 FEATURES에 적지 않는다(spec §13).

- [ ] **Step 4: Commit** `docs: document structured analyze output (plan A)`

---

## Self-Review

**Spec coverage:** Summary(T10)·CAN SLIM(T11)·Stage2+Supertrend(T12)·모멘텀(T13)·Event(T14)·구조레벨(T15)·U/D(T2)·MACD크로스(T3)·신고가/스윙로우(T4)·RSI다이버전스(T5)·RS전환(T7) 전부 매핑.

**레이어 경계 (spec §3.0):** events·relative_strength = Tool(T1-7) / deep_dive 조율 = Pipeline(T8) / 렌더 = CLI analyze_render(T9-16). 판단요약·논쟁·가중치 없음(R4/R8). ✅

**리뷰 반영:** U/D 테스트 3.0(T2) / RS 진짜 전환 테스트(T7) / peak plateau `>=`(T5) / 기존 테스트 마이그레이션(T18) / 통합 렌더 테스트(T16) / 렌더 분리(T9). ✅

**플랜 B 연결:** format_deep_dive_output에 debate 삽입 지점(가격 줄과 Summary 사이)을 주석으로 표시 — 플랜 B는 Edit 한 줄 + `_format_debate_section`만 추가(재작성 안 함 → 충돌 없음).

**Type consistency:** `MomentumEvents`/`MacdCross`/`RsiDivergence`/`PriceEvent`/`RsEvent` 필드명이 T1 정의와 T8·T13·T14 사용처에서 일치.
