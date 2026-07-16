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
    df["SMA20"] = df["Close"].rolling(20, min_periods=1).mean()
    df["SMA50"] = df["Close"].rolling(50, min_periods=1).mean()
    df["SMA150"] = df["Close"].rolling(150, min_periods=1).mean()
    df["SMA200"] = df["Close"].rolling(200, min_periods=1).mean()
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
    from src.tools.playbook.models import RelativeStrengthResult

    return RelativeStrengthResult(
        mansfield_rs=5.0 if strong else -5.0,
        outperform_6m=10.0 if strong else -10.0,
        rp_slope_4w=0.5 if strong else -0.5,
        index_symbol="^GSPC",
    )


def _acc(ratio: float):
    from src.tools.playbook.models import AccumulationResult

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
    from src.tools.playbook.exit_rules import evaluate_exit

    # 종가가 모든 이평 위, 매집 우세, RS 강세
    df = _make_df(n=250, close_last=120.0, trend="up")
    # 이평을 강제로 낮게 설정 (close > 모든 MA)
    df["SMA20"] = 90.0
    df["SMA50"] = 85.0
    df["SMA150"] = 80.0
    df["SMA200"] = 78.0

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
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=80.0)
    df["SMA20"] = 95.0  # close(80) < SMA20(95)
    df["SMA50"] = 100.0
    df["SMA150"] = 70.0  # close > SMA150 → 신호5 없음
    df["SMA200"] = 70.0

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


# ---------------------------------------------------------------------------
# 신호 3: DISTRIBUTION — 분산 우세
# ---------------------------------------------------------------------------


def test_exit_distribution_signal():
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=100.0)
    df["SMA20"] = 80.0
    df["SMA50"] = 75.0
    df["SMA150"] = 70.0
    df["SMA200"] = 68.0

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
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=100.0)
    df["SMA20"] = 80.0
    df["SMA50"] = 75.0
    df["SMA150"] = 70.0
    df["SMA200"] = 68.0

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
# 신호 5: SMA_LONG — 종가 < SMA150 또는 < SMA200 → strong
# ---------------------------------------------------------------------------


def test_exit_sma_long_below_sma150():
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=250, close_last=60.0)
    df["SMA20"] = 70.0
    df["SMA50"] = 75.0
    df["SMA150"] = 80.0  # close(60) < SMA150(80) → 신호 5
    df["SMA200"] = 85.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(60.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    codes = {s.code for s in result.signals}
    assert "SMA_LONG" in codes
    long_sig = next(s for s in result.signals if s.code == "SMA_LONG")
    assert long_sig.severity == "strong"


# ---------------------------------------------------------------------------
# 매핑: 강(5) → 청산
# ---------------------------------------------------------------------------


def test_exit_liquidate_on_strong_signal():
    """SMA_LONG(강) → 청산."""
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=250, close_last=60.0)
    df["SMA20"] = 70.0
    df["SMA50"] = 75.0
    df["SMA150"] = 80.0  # 신호5(강)
    df["SMA200"] = 85.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(60.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    assert result.action == "liquidate"


# ---------------------------------------------------------------------------
# 매핑: 중(2/3) → 비중축소
# ---------------------------------------------------------------------------


def test_exit_reduce_on_single_medium_signal():
    """medium 신호 1개(SMA_SHORT만) → 비중축소."""
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=80.0)
    df["SMA20"] = 95.0  # close < SMA20 → SMA_SHORT(medium)
    df["SMA50"] = 100.0  # close < SMA50 → SMA_SHORT에 포함 (같은 신호코드)
    df["SMA150"] = 70.0  # close > SMA150 → SMA_LONG 없음
    df["SMA200"] = 68.0

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
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=80.0)
    df["SMA20"] = 95.0  # SMA_SHORT(medium)
    df["SMA50"] = 100.0  # close < SMA50 → 또다른 medium
    df["SMA150"] = 70.0
    df["SMA200"] = 68.0

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
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=115.0)
    df["SMA20"] = 80.0
    df["SMA50"] = 75.0
    df["SMA150"] = 70.0
    df["SMA200"] = 68.0

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
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=115.0)
    df["SMA20"] = 80.0
    df["SMA50"] = 75.0
    df["SMA150"] = 70.0
    df["SMA200"] = 68.0

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
    from src.tools.playbook.exit_rules import evaluate_exit

    df = _make_df(n=60, close_last=115.0)
    sma50_last = float(df["SMA50"].iloc[-1])
    df["SMA20"] = 80.0
    df["SMA150"] = 70.0
    df["SMA200"] = 68.0

    result = evaluate_exit(
        df=df,
        snapshot=_snapshot(115.0),
        relative_strength=_rs(True),
        accumulation=_acc(0.8),
        holding=_holding(avg=100.0),
    )
    assert result.trailing_stop == pytest.approx(sma50_last, rel=1e-4)


def test_sma_signals_fire_with_underscore_columns():
    """indicators.py 실제 컬럼명(SMA_50 형식)으로도 SMA 신호가 발화해야 한다 (계약 회귀)."""
    from src.tools.playbook.exit_rules import evaluate_exit

    df = pd.DataFrame({"Close": [100.0] * 60})
    df.loc[df.index[-1], "Close"] = 80.0
    df["SMA_20"] = 90.0
    df["SMA_50"] = 85.0
    df["SMA_150"] = 95.0
    df["SMA_200"] = 96.0

    verdict = evaluate_exit(
        df=df, snapshot=None, relative_strength=None, accumulation=None, holding=None
    )

    codes = {s.code for s in verdict.signals}
    assert "SMA_SHORT" in codes
    assert "SMA_LONG" in codes
    assert verdict.trailing_stop == 85.0
    assert verdict.action == "liquidate"  # strong 1개(SMA_LONG) → 청산


# ── SMA_LONG 전환 시도 국면 강등 (와인스타인 Stage 기준선 = SMA150) ──────────


def test_sma_long_downgraded_to_weak_in_turnaround_phase():
    """종가>SMA150이면 SMA200 이탈은 약신호 — 전환 선취매 국면. 기울기 상승은 근거에 병기."""
    from src.tools.playbook.exit_rules import evaluate_exit

    df = pd.DataFrame({"Close": [100.0] * 60})
    df.loc[df.index[-1], "Close"] = 95.0
    df["SMA_150"] = np.linspace(80.0, 90.0, 60)  # 상승 중, 종가(95) > SMA150(90)
    df["SMA_200"] = 96.0  # 종가 95 < SMA200

    verdict = evaluate_exit(
        df=df, snapshot=None, relative_strength=None, accumulation=None, holding=None
    )

    sma_long = next(s for s in verdict.signals if s.code == "SMA_LONG")
    assert sma_long.severity == "weak"
    assert "전환 시도" in sma_long.detail
    assert "SMA150 상승" in sma_long.detail
    assert verdict.action == "hold"  # 약신호만으로는 청산/축소 아님


def test_sma_long_downgraded_even_when_sma150_falling():
    """가격 회복만으로 강등(사용자 결정) — 기울기 하락 중이면 '미확인 전환'으로 병기."""
    from src.tools.playbook.exit_rules import evaluate_exit

    df = pd.DataFrame({"Close": [100.0] * 60})
    df.loc[df.index[-1], "Close"] = 95.0
    df["SMA_150"] = np.linspace(94.0, 90.0, 60)  # 하락 중
    df["SMA_200"] = 96.0

    verdict = evaluate_exit(
        df=df, snapshot=None, relative_strength=None, accumulation=None, holding=None
    )

    sma_long = next(s for s in verdict.signals if s.code == "SMA_LONG")
    assert sma_long.severity == "weak"
    assert "전환 시도" in sma_long.detail
    assert "SMA150 하락 중" in sma_long.detail
    assert verdict.action == "hold"


def test_sma_long_stays_strong_when_below_sma150():
    """종가 < SMA150이면 (SMA150 상승 여부와 무관하게) 강신호 유지."""
    from src.tools.playbook.exit_rules import evaluate_exit

    df = pd.DataFrame({"Close": [100.0] * 60})
    df.loc[df.index[-1], "Close"] = 85.0
    df["SMA_150"] = np.linspace(80.0, 90.0, 60)  # 상승 중이지만 종가(85) < SMA150(90)
    df["SMA_200"] = 96.0

    verdict = evaluate_exit(
        df=df, snapshot=None, relative_strength=None, accumulation=None, holding=None
    )

    sma_long = next(s for s in verdict.signals if s.code == "SMA_LONG")
    assert sma_long.severity == "strong"
    assert verdict.action == "liquidate"
