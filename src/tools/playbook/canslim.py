"""CAN SLIM aggregation (Plan 7).

compute_canslim is a pure function — no fetching. All inputs are pre-computed
component results injected from outside. Missing data yields met=None.

CAN SLIM mapping:
  C = Current quarterly EPS YoY >= 25% (+ acceleration check)
  A = Annual EPS growth >= 25% AND ROE >= 15%
  N = Near 52-week high (price >= 75% of 52w high) — reference
  S = Volume score > 0 — reference
  L = Sector strong AND RS strong — reference
  I = Accumulation dominant OR Pocket Pivot — reference
  M = Market regime allows new buy — reference
"""

from src.tools.playbook.models import CanslimResult, ElementVerdict


_MIN_GROWTH = 0.25
_MIN_ROE = 0.15
_HIGH_52W_THRESHOLD = 0.75


def _v(met: bool | None, detail: str = "") -> ElementVerdict:
    return ElementVerdict(met=met, detail=detail)


def compute_canslim(
    *,
    snapshot,
    components,
    fundamental,
    accumulation,
    sector_strength,
    relative_strength,
    market_regime,
) -> CanslimResult:
    """Aggregate pre-computed component results into CAN SLIM 7-element verdict.

    Args:
        snapshot: Object with price, high_52w attributes (technical snapshot).
        components: Dict of component results; expects components["volume"].
        fundamental: FundamentalSnapshot with quarterly_data, annual_data, roe.
        accumulation: AccumulationResult.
        sector_strength: SectorStrengthResult.
        relative_strength: RelativeStrengthResult.
        market_regime: MarketRegimeResult.

    Returns:
        CanslimResult with score and summary computed fields.
    """
    return CanslimResult(
        c=_judge_c(fundamental),
        a=_judge_a(fundamental),
        n=_judge_n(snapshot),
        s=_judge_s(components),
        l=_judge_l(sector_strength, relative_strength),
        i=_judge_i(accumulation, components),
        m=_judge_m(market_regime),
    )


def _judge_c(fundamental) -> ElementVerdict:
    """C: Current quarterly EPS YoY >= 25% (+ acceleration bonus in detail)."""
    if fundamental is None:
        return _v(None, "fundamental 없음")
    quarters = fundamental.quarterly_data or []
    if not quarters or quarters[0].eps_yoy is None:
        return _v(None, "분기 EPS 없음")
    latest_yoy = quarters[0].eps_yoy
    accel = (
        len(quarters) > 1 and quarters[1].eps_yoy is not None and latest_yoy > quarters[1].eps_yoy
    )
    met = latest_yoy >= _MIN_GROWTH
    detail = f"분기EPS YoY {latest_yoy:.1%}{' 가속' if accel else ''}"
    return _v(met, detail)


def _judge_a(fundamental) -> ElementVerdict:
    """A: Annual EPS growth >= 25% AND ROE >= 15%."""
    if fundamental is None:
        return _v(None, "fundamental 없음")
    annual = fundamental.annual_data or []
    if len(annual) < 2 or annual[0].eps is None or annual[1].eps is None:
        return _v(None, "연간 EPS 부족")
    prior_eps = annual[1].eps
    if prior_eps == 0:
        return _v(None, "전년 EPS=0")
    growth = (annual[0].eps - prior_eps) / abs(prior_eps)
    roe = fundamental.roe or 0.0
    roe_ok = roe >= _MIN_ROE
    met = growth >= _MIN_GROWTH and roe_ok
    return _v(met, f"연EPS {growth:.1%}, ROE {roe:.1%}")


def _judge_n(snapshot) -> ElementVerdict:
    """N: Price within 25% of 52-week high (reference — snapshot)."""
    if snapshot is None:
        return _v(None, "snapshot 없음")
    high_52w = getattr(snapshot, "high_52w", None)
    price = getattr(snapshot, "price", None)
    if high_52w is None or price is None or high_52w == 0:
        return _v(None, "52주 데이터 없음")
    ratio = price / high_52w
    near = ratio >= _HIGH_52W_THRESHOLD
    return _v(near, f"52주고점 대비 {(ratio - 1) * 100:.1f}%")


def _judge_s(components) -> ElementVerdict:
    """S: Volume score > 0 (reference — components)."""
    if components is None:
        return _v(None, "components 없음")
    vol = components.get("volume", {}) if isinstance(components, dict) else {}
    score = vol.get("score", 0)
    metrics = vol.get("metrics", {}) if isinstance(vol, dict) else {}
    vol_ratio = metrics.get("vol_ratio")
    signals = vol.get("signals", []) if isinstance(vol, dict) else []
    parts = []
    if vol_ratio is not None:
        parts.append(f"거래량 {vol_ratio:.2f}x(20일평균 대비)")
    parts.append(f"score {score}")
    if signals:
        parts.append("/".join(signals))
    return _v(bool(score and score > 0), ", ".join(parts))


def _judge_l(sector_strength, relative_strength) -> ElementVerdict:  # noqa: E741
    """L: Sector strong AND RS strong (reference)."""
    if sector_strength is None and relative_strength is None:
        return _v(None, "업종+RS 데이터 없음")
    sector_ok = bool(getattr(sector_strength, "is_strong", None))
    rs_ok = bool(getattr(relative_strength, "is_strong", None))

    if sector_strength is None:
        sec_detail = "업종강세=None(데이터없음)"
    else:
        sec_detail = f"업종강세={sector_ok}"
        industry = getattr(sector_strength, "industry", None)
        rank_pct = getattr(sector_strength, "rank_pct", None)
        sec_extras = []
        if industry:
            sec_extras.append(industry)
        if rank_pct is not None:
            sec_extras.append(f"상위{rank_pct:.0%}")
        if sec_extras:
            sec_detail += f"({', '.join(sec_extras)})"

    rs_detail = f"RS강세={rs_ok}"
    mansfield = getattr(relative_strength, "mansfield_rs", None)
    outperform = getattr(relative_strength, "outperform_6m", None)
    slope = getattr(relative_strength, "rp_slope_4w", None)
    rs_extras = []
    if mansfield is not None:
        rs_extras.append(f"Mansfield {mansfield:.1f}")
    if outperform is not None:
        rs_extras.append(f"6M초과 {outperform:+.1f}%p")
    if slope is not None:
        rs_extras.append(f"4주기울기 {slope:+.2f}")
    if rs_extras:
        rs_detail += f"({', '.join(rs_extras)})"

    return _v(sector_ok and rs_ok, f"{sec_detail}, {rs_detail}")


def _judge_i(accumulation, components) -> ElementVerdict:  # noqa: E741
    """I: Accumulation dominant OR Pocket Pivot (reference)."""
    if accumulation is None and components is None:
        return _v(None, "매집 데이터 없음")
    acc_ok = getattr(accumulation, "is_accumulating", False) is True
    vol = (
        (components.get("volume", {}) if isinstance(components, dict) else {}) if components else {}
    )
    pp = any("Pocket Pivot" in sig for sig in vol.get("signals", []))
    met = acc_ok or pp
    acc_ratio = getattr(accumulation, "accumulation_ratio", None)
    return _v(met, f"매집비율 {acc_ratio}, PP={pp}")


def _judge_m(market_regime) -> ElementVerdict:
    """M: Market regime allows new buy (reference)."""
    if market_regime is None:
        return _v(None, "시장환경 데이터 없음")
    allow = getattr(market_regime, "allow_new_buy", None)
    regime = getattr(market_regime, "regime", "")
    index_symbol = getattr(market_regime, "index_symbol", "")
    basis = getattr(market_regime, "detail", "")
    text = regime
    if index_symbol:
        text += f" [{index_symbol}]"
    if basis:
        text += f" ({basis})"
    return _v(allow, text)
