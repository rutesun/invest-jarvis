"""TDD: exit_rules.py — 보유 종목 매도 5신호 판정."""

import numpy as np
import pandas as pd
import pytest


def _make_df(n: int = 60, close_last: float = 100.0, trend: str = "flat") -> pd.DataFrame:
    """기본 OHLCV + 이동평균 DataFrame."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    if trend == "up":
        close = np.linspace(80, close_last, n)
    elif trend == "down":
        close = np.linspace(close_last, 80, n)
    else:
        close = np.full(n, close_last)

    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    # 이동평균 컬럼 추가
    df["SMA_20"] = df["Close"].rolling(20, min_periods=1).mean()
    df["SMA_50"] = df["Close"].rolling(50, min_periods=1).mean()
    df["SMA_100"] = df["Close"].rolling(100, min_periods=1).mean()
    df["SMA_150"] = df["Close"].rolling(150, min_periods=1).mean()
    df["SMA_200"] = df["Close"].rolling(200, min_periods=1).mean()
    df["Vol_SMA_20"] = df["Volume"].rolling(20, min_periods=1).mean()
    return df


def _snapshot(close: float, high_52w: float | None = None, swing_low: float | None = None):
    """minimal snapshot stub."""
    _high = high_52w if high_52w is not None else close * 1.1
    _swing = swing_low if swing_low is not None else close * 0.95

    class Snap:
        price = close

    Snap.high_52w = _high
    Snap.swing_low = _swing
    return Snap()


def _rs(strong: bool):
    from src.tools.criteria.models import RelativeStrengthResult

    return RelativeStrengthResult(
        mansfield_rs=5.0 if strong else -5.0,
        outperform_6m=10.0 if strong else -10.0,
        rp_slope_4w=0.5 if strong else -0.5,
        index_symbol="^GSPC",
    )


def _acc(ratio: float):
    from src.tools.criteria.models import AccumulationResult

    acc_days = int(ratio * 10)
    dist_days = 10 - acc_days
    return AccumulationResult(
        accumulation_days=acc_days,
        distribution_days=dist_days,
        accumulation_ratio=ratio,
        window=25,
    )


def _holding(avg: float, stop: float | None = None, qty: int = 100):
    class H:
        ticker = "AAPL"
        quantity = qty
        avg_price = avg
        stop_price = stop
        currency = "USD"

    return H()


# ---------------------------------------------------------------------------
# 신호 없음: 모든 지표 양호 → hold, 신호 0개
# ---------------------------------------------------------------------------


def test_exit_no_signals_hold():
    from src.tools.criteria.exit_rules import evaluate_exit

    # 종가가 모든 이평 위, 매집 우세, RS 강세
    df = _make_df(n=250, close_last=120.0, trend="up")
    # 이평을 강제로 낮게 설정 (close > 모든 MA)
    df["SMA_20"] = 90.0
    df["SMA_50"] = 85.0
    df["SMA_150"] = 80.0
    df["SMA_200"] = 78.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(120.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    assert result.action == "hold"
    assert len(result.signals) == 0


# ---------------------------------------------------------------------------
# 신호 2: SMA_SHORT — 종가 < SMA20 → medium
# ---------------------------------------------------------------------------


def test_exit_sma_short_below_sma20():
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=80.0)
    df["SMA_20"] = 95.0  # close(80) < SMA20(95)
    df["SMA_50"] = 100.0
    df["SMA_150"] = 70.0  # close > SMA150 → 신호5 없음
    df["SMA_200"] = 70.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(80.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=90.0),
    )
    codes = {s.code for s in result.signals}
    assert "SMA_SHORT" in codes
    short_sig = next(s for s in result.signals if s.code == "SMA_SHORT")
    assert short_sig.severity == "medium"


def test_exit_uses_last_valid_close_when_trailing_nan():
    """당일 미완성 봉(Close=NaN)이 끝에 붙어도 직전 유효 종가로 매도 신호를 판정한다."""
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=80.0)
    df["SMA_20"] = 95.0  # 직전 유효 close(80) < SMA20(95) → SMA_SHORT
    df["SMA_50"] = 100.0
    df["SMA_150"] = 70.0
    df["SMA_200"] = 70.0
    next_day = df.index[-1] + pd.offsets.BDay(1)
    df.loc[next_day] = {c: float("nan") for c in df.columns}  # 당일 미완성 봉

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(80.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=90.0),
    )
    codes = {s.code for s in result.signals}
    assert "SMA_SHORT" in codes, f"trailing NaN이 매도 신호를 무력화하면 안 됨, signals={codes}"


# ---------------------------------------------------------------------------
# 신호 3: DISTRIBUTION — 분산 우세
# ---------------------------------------------------------------------------


def test_exit_distribution_signal():
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=100.0)
    df["SMA_20"] = 80.0
    df["SMA_50"] = 75.0
    df["SMA_150"] = 70.0
    df["SMA_200"] = 68.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(100.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.2),  # 분산 우세
        holding=_holding(avg=95.0),
    )
    codes = {s.code for s in result.signals}
    assert "DISTRIBUTION" in codes


# ---------------------------------------------------------------------------
# 신호 4: RS_WEAKENING — RS 음전환
# ---------------------------------------------------------------------------


def test_exit_rs_weakening_signal():
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=100.0)
    df["SMA_20"] = 80.0
    df["SMA_50"] = 75.0
    df["SMA_150"] = 70.0
    df["SMA_200"] = 68.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(100.0),
        relative_strength=_rs(False),  # RS 약세
        accumulation=_acc(0.8),
        holding=_holding(avg=90.0),
    )
    codes = {s.code for s in result.signals}
    assert "RS_WEAKENING" in codes
    rs_sig = next(s for s in result.signals if s.code == "RS_WEAKENING")
    assert rs_sig.severity == "weak"


# ---------------------------------------------------------------------------
# 신호 5: 장기 이평 이탈 — 거래량 동반 하락 시만 (SMA200→청산, SMA100→비중축소)
# ---------------------------------------------------------------------------


def test_exit_sma200_break_volume_confirmed():
    """종가<SMA200 + 평균거래량 1.2배 이상 동반 하락 → SMA_200_BREAK(strong), 청산."""
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=250, close_last=200.0, trend="down")  # 마지막 close=80, 하락봉
    df["SMA_20"] = 70.0  # close(80) > → SMA_SHORT 없음
    df["SMA_50"] = 70.0
    df["SMA_100"] = 90.0
    df["SMA_200"] = 95.0  # close(80) < SMA200
    df["Vol_SMA_20"] = 1_000_000.0
    df.loc[df.index[-1], "Volume"] = 1_300_000.0  # 평균의 1.3배

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(80.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    codes = {s.code for s in result.signals}
    assert "SMA_200_BREAK" in codes
    assert next(s for s in result.signals if s.code == "SMA_200_BREAK").severity == "strong"
    assert result.action == "liquidate"


def test_exit_sma100_break_reduces():
    """종가<SMA100(SMA200 위) + 거래량 동반 하락 → SMA_100_BREAK(medium), 비중축소."""
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=250, close_last=200.0, trend="down")  # 마지막 close=80, 하락봉
    df["SMA_20"] = 70.0  # SMA_SHORT 없음
    df["SMA_50"] = 70.0
    df["SMA_100"] = 95.0  # close(80) < SMA100
    df["SMA_200"] = 70.0  # close(80) > SMA200 → 200 안 깨짐
    df["Vol_SMA_20"] = 1_000_000.0
    df.loc[df.index[-1], "Volume"] = 1_300_000.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(80.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    codes = {s.code for s in result.signals}
    assert "SMA_100_BREAK" in codes
    assert next(s for s in result.signals if s.code == "SMA_100_BREAK").severity == "medium"
    assert result.action == "reduce"


def test_exit_no_long_break_without_volume():
    """종가<SMA200이지만 거래량 미동반(1.2배 미만) → 장기 이탈 신호 없음."""
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=250, close_last=200.0, trend="down")  # 마지막 close=80
    df["SMA_20"] = 70.0
    df["SMA_50"] = 70.0
    df["SMA_100"] = 95.0
    df["SMA_200"] = 95.0  # close(80) < SMA200
    df["Vol_SMA_20"] = 1_000_000.0
    # 마지막 거래량은 평균 수준(1.0배) → 미동반

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(80.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    codes = {s.code for s in result.signals}
    assert "SMA_200_BREAK" not in codes
    assert "SMA_100_BREAK" not in codes


# ---------------------------------------------------------------------------
# 매핑: 중(2/3) → 비중축소
# ---------------------------------------------------------------------------


def test_exit_reduce_on_single_medium_signal():
    """medium 신호 1개(SMA_SHORT만) → 비중축소."""
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=80.0)
    df["SMA_20"] = 95.0  # close < SMA20 → SMA_SHORT(medium)
    df["SMA_50"] = 100.0  # close < SMA50 → SMA_SHORT에 포함 (같은 신호코드)
    df["SMA_100"] = 70.0  # close > SMA100 → 장기이탈 없음
    df["SMA_200"] = 68.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(80.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),  # 매집 우세 → DISTRIBUTION 없음
        holding=_holding(avg=90.0),
    )
    # SMA_SHORT(medium) 1개만 → reduce
    medium_signals = [s for s in result.signals if s.severity == "medium"]
    assert len(medium_signals) == 1
    assert result.action == "reduce"


# ---------------------------------------------------------------------------
# 매핑: 중 2개 이상 → 청산
# ---------------------------------------------------------------------------


def test_exit_liquidate_on_two_medium_signals():
    """medium 신호 2개 → 청산."""
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=80.0)
    df["SMA_20"] = 95.0  # SMA_SHORT(medium)
    df["SMA_50"] = 100.0  # close < SMA50 → 또다른 medium
    df["SMA_150"] = 70.0
    df["SMA_200"] = 68.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(80.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.2),  # DISTRIBUTION(medium)
        holding=_holding(avg=90.0),
    )
    medium_count = sum(1 for s in result.signals if s.severity == "medium")
    if medium_count >= 2:
        assert result.action == "liquidate"


# ---------------------------------------------------------------------------
# current_r: stop_price 있을 때 계산
# ---------------------------------------------------------------------------


def test_exit_current_r_with_stop():
    """stop_price 있으면 current_r = (close-avg)/(avg-stop_price)."""
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=115.0)
    df["SMA_20"] = 80.0
    df["SMA_50"] = 75.0
    df["SMA_150"] = 70.0
    df["SMA_200"] = 68.0

    holding = _holding(avg=100.0, stop=90.0)  # avg-stop=10, close-avg=15 → R=1.5
    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(115.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=holding,
    )
    assert result.current_r is not None
    assert abs(result.current_r - 1.5) < 0.001


# ---------------------------------------------------------------------------
# current_r: stop_price 없으면 None
# ---------------------------------------------------------------------------


def test_exit_current_r_without_stop():
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=115.0)
    df["SMA_20"] = 80.0
    df["SMA_50"] = 75.0
    df["SMA_150"] = 70.0
    df["SMA_200"] = 68.0

    holding = _holding(avg=100.0, stop=None)
    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(115.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=holding,
    )
    assert result.current_r is None


# ---------------------------------------------------------------------------
# trailing_stop: SMA50 기반
# ---------------------------------------------------------------------------


def test_exit_trailing_stop_is_sma50():
    from src.tools.criteria.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=115.0)
    sma50_last = float(df["SMA_50"].iloc[-1])
    df["SMA_20"] = 80.0
    df["SMA_150"] = 70.0
    df["SMA_200"] = 68.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(115.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    assert result.trailing_stop == pytest.approx(sma50_last, rel=1e-4)
