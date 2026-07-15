"""보유 종목 매도 신호 평가 (Plan 8).

5개 신호:
  1. CHARACTER_CHANGE  신고가 실패 또는 스윙로우 이탈 (weak)
  2. SMA_SHORT         종가 < SMA20 또는 종가 < SMA50 (medium)
  3. DISTRIBUTION      매집/분산 분석 결과 분산 우세 (medium)
  4. RS_WEAKENING      RS 음전환 (weak)
  5. SMA_LONG          종가 < SMA150 또는 종가 < SMA200 (strong)
                       단, 종가 > SMA150 이고 SMA150이 상승 중이면 weak로 강등
                       (와인스타인 Stage 기준선은 30주선(SMA150) — 150선 회복+상승은
                        Stage2 전환 시도 국면이라 SMA200 이탈만으로 청산하지 않음)

매핑:
  - 강(strong) 신호 1개 → 청산
  - 중(medium) 신호 2개 이상 → 청산
  - 중(medium) 신호 1개 → 비중축소
  - 나머지 → 경고+보유 (action="hold")

current_r: holding.stop_price 있을 때만 (close - avg) / (avg - stop_price).
trailing_stop: SMA50 마지막 값.
"""

from __future__ import annotations

import pandas as pd

from src.tools.playbook.models import ExitSignal, ExitVerdict


def evaluate_exit(
    *,
    df: pd.DataFrame,
    snapshot,
    relative_strength,
    accumulation,
    holding,
) -> ExitVerdict:
    """보유 종목 매도 판정. 순수 함수 — I/O 없음."""
    signals: list[ExitSignal] = []
    last = df.iloc[-1]
    close = float(last["Close"])

    # ── 신호 1: CHARACTER_CHANGE (성격변화) ───────────────────────────────────
    # 신고가 실패: 종가가 52주 고점의 -15% 미만이면서 이전 swing_high 돌파 실패
    # 스윙로우 이탈: snapshot.swing_low 있으면 close < swing_low
    if snapshot is not None:
        swing_low = getattr(snapshot, "swing_low", None)
        high_52w = getattr(snapshot, "high_52w", None)
        cc_triggered = False
        cc_detail_parts = []

        if swing_low is not None and close < swing_low:
            cc_triggered = True
            cc_detail_parts.append(f"스윙로우 이탈: close={close:.2f} < swing_low={swing_low:.2f}")

        if high_52w is not None and high_52w > 0:
            pct_from_high = (close - high_52w) / high_52w
            if pct_from_high < -0.15:  # 신고가에서 15% 이상 하락
                cc_triggered = True
                cc_detail_parts.append(f"신고가 실패: 52주고점 대비 {pct_from_high:.1%}")

        if cc_triggered:
            signals.append(
                ExitSignal(
                    code="CHARACTER_CHANGE",
                    severity="weak",
                    detail=" / ".join(cc_detail_parts),
                )
            )

    # ── 신호 2: SMA_SHORT (단기이평) ─────────────────────────────────────────
    sma20 = _get_ma(df, "SMA20", last)
    sma50 = _get_ma(df, "SMA50", last)
    short_parts = []
    if sma20 is not None and close < sma20:
        short_parts.append(f"종가<SMA20({sma20:.2f})")
    if sma50 is not None and close < sma50:
        short_parts.append(f"종가<SMA50({sma50:.2f})")
    if short_parts:
        signals.append(
            ExitSignal(
                code="SMA_SHORT",
                severity="medium",
                detail=" | ".join(short_parts),
            )
        )

    # ── 신호 3: DISTRIBUTION (분산 우세) ─────────────────────────────────────
    if accumulation is not None:
        acc_ratio = accumulation.accumulation_ratio
        # 매집비율 < 0.4 → 분산 우세
        if acc_ratio < 0.4:
            signals.append(
                ExitSignal(
                    code="DISTRIBUTION",
                    severity="medium",
                    detail=f"매집비율={acc_ratio:.2f} (분산 우세)",
                )
            )

    # ── 신호 4: RS_WEAKENING (RS 음전환) ─────────────────────────────────────
    if relative_strength is not None and not relative_strength.is_strong:
        signals.append(
            ExitSignal(
                code="RS_WEAKENING",
                severity="weak",
                detail=f"mansfield_rs={relative_strength.mansfield_rs:.2f}, slope={relative_strength.rp_slope_4w:.4f}",
            )
        )

    # ── 신호 5: SMA_LONG (장기이평) ──────────────────────────────────────────
    sma150 = _get_ma(df, "SMA150", last)
    sma200 = _get_ma(df, "SMA200", last)
    long_parts = []
    if sma150 is not None and close < sma150:
        long_parts.append(f"종가<SMA150({sma150:.2f})")
    if sma200 is not None and close < sma200:
        long_parts.append(f"종가<SMA200({sma200:.2f})")
    if long_parts:
        # 전환 시도 국면 강등: 와인스타인 Stage 기준선은 30주선(SMA150).
        # 종가가 SMA150 위에 있고 SMA150이 상승 중이면 Stage2 전환 시도 국면 —
        # SMA200 이탈만으로는 "추세 붕괴"가 아니므로 weak로 강등한다.
        severity = "strong"
        if sma150 is not None and close >= sma150 and _is_ma_rising(df, "SMA150"):
            severity = "weak"
            long_parts.append(f"단, 종가>SMA150({sma150:.2f})·SMA150 상승 — 전환 시도 국면")
        signals.append(
            ExitSignal(
                code="SMA_LONG",
                severity=severity,
                detail=" | ".join(long_parts),
            )
        )

    # ── current_r 계산 ────────────────────────────────────────────────────────
    current_r: float | None = None
    stop_price = getattr(holding, "stop_price", None)
    avg_price = getattr(holding, "avg_price", None)
    if stop_price is not None and avg_price is not None:
        risk = avg_price - stop_price
        if risk > 0:
            current_r = round((close - avg_price) / risk, 4)

    # ── trailing_stop: SMA50 마지막 값 ───────────────────────────────────────
    trailing_stop: float | None = sma50

    # ── action 결정 ───────────────────────────────────────────────────────────
    strong_count = sum(1 for s in signals if s.severity == "strong")
    medium_count = sum(1 for s in signals if s.severity == "medium")

    if strong_count >= 1 or medium_count >= 2:
        action = "liquidate"
        detail = f"청산: 강{strong_count} 중{medium_count} 약{sum(1 for s in signals if s.severity == 'weak')}"
    elif medium_count == 1:
        action = "reduce"
        detail = f"비중축소: 중신호 {medium_count}개"
    else:
        action = "hold"
        weak_count = sum(1 for s in signals if s.severity == "weak")
        detail = f"보유 유지 (약신호 {weak_count}개)" if signals else "이상 없음"

    return ExitVerdict(
        action=action,
        signals=signals,
        current_r=current_r,
        trailing_stop=trailing_stop,
        detail=detail,
    )


def _get_ma(df: pd.DataFrame, col: str, last) -> float | None:
    """DataFrame 마지막 행에서 이동평균 값 추출.

    'SMA50'(레거시 픽스처)·'SMA_50'(IndicatorCalculator 실제 출력) 양식 모두 허용.
    """
    for name in (col, col.replace("SMA", "SMA_", 1)):
        if name in df.columns:
            val = last.get(name)
            if val is not None and not pd.isna(val):
                return float(val)
    return None


_MA_SLOPE_LOOKBACK = 21  # 거래일 — market_regime의 SMA200 상승 판정과 동일 창


def _is_ma_rising(df: pd.DataFrame, col: str, lookback: int = _MA_SLOPE_LOOKBACK) -> bool:
    """이동평균이 lookback 거래일 전보다 상승했는지. 데이터 부족·결측이면 False (보수적)."""
    for name in (col, col.replace("SMA", "SMA_", 1)):
        if name in df.columns:
            series = df[name].dropna()
            if len(series) <= lookback:
                return False
            return float(series.iloc[-1]) > float(series.iloc[-1 - lookback])
    return False
