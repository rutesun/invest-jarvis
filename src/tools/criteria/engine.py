"""CriteriaEngine — 기준 평가 오케스트레이터 (Plan 8).

데이터 흐름:
  1. index_provider.get_index_history(ticker) → (sym, index_df)
  2. 순수 부품 호출:
     - assess_market_regime(index_df, sym)
     - compute_relative_strength(stock_df, index_df, sym)
     - sector_strength: US → FmpSectorStrength / KR → KisSectorStrength
     - detect_vcp_breakout(stock_df)
     - analyze_accumulation(stock_df)
     - compute_canslim(...)
  3. is_stage2 = technical_result.components["minervini"]["metrics"].get("is_stage2", 0.0)
  4. 분기:
     - holding=None → evaluate_gate → (passed? plan_position)
     - holding 있음 → evaluate_exit

Plan 9 연결(deep_dive/CLI)은 이 엔진을 호출하는 상위 계층에서 담당.
KIS 동시 호출 금지: sector index는 순차 처리.
"""

from __future__ import annotations

import contextlib
import logging

import pandas as pd

from src.tools.criteria.accumulation import analyze_accumulation
from src.tools.criteria.canslim import compute_canslim
from src.tools.criteria.exit_rules import evaluate_exit
from src.tools.criteria.gate import evaluate_gate
from src.tools.criteria.market_regime import assess_market_regime
from src.tools.criteria.models import CriteriaVerdict
from src.tools.criteria.relative_strength import compute_relative_strength
from src.tools.criteria.sector_strength import (
    FmpSectorStrength,
    KisSectorStrength,
)
from src.tools.criteria.sizing import plan_position
from src.tools.criteria.vcp import detect_vcp_breakout
from src.tools.disclosure import is_korean_ticker
from src.tools.technical.components.minervini import STAGE2_CONDITION_LABELS
from src.tools.technical.df_guards import last_valid_close


logger = logging.getLogger(__name__)


class CriteriaEngine:
    """기준 평가 엔진. 미보유→기준체크+사이징 / 보유→매도 판정."""

    def __init__(
        self,
        index_provider,
        fmp_provider=None,
        kis_provider=None,
        usd_capital: float | None = None,
        usd_risk_pct: float = 0.01,
        krw_capital: float | None = None,
        krw_risk_pct: float = 0.01,
    ):
        self._index_provider = index_provider
        self._fmp_provider = fmp_provider
        self._kis_provider = kis_provider
        self._usd_capital = usd_capital
        self._usd_risk_pct = usd_risk_pct
        self._krw_capital = krw_capital
        self._krw_risk_pct = krw_risk_pct

    async def evaluate(
        self,
        ticker: str,
        technical_result,
        fundamental,
        flow,
        zone_set,
        holding,
    ) -> CriteriaVerdict:
        """CriteriaVerdict 생성. holding=None이면 미보유 분기."""
        stock_df: pd.DataFrame = technical_result.raw_dataframe

        # ── 1. 시장지수 fetch ─────────────────────────────────────────────────
        index_sym, index_df = await self._index_provider.get_index_history(ticker)

        # ── 2. 순수 부품 ──────────────────────────────────────────────────────
        market_regime = assess_market_regime(index_df, index_sym)

        relative_strength = compute_relative_strength(stock_df, index_df, index_sym)

        sector_strength = await self._fetch_sector_strength(
            ticker=ticker,
            technical_result=technical_result,
            fundamental=fundamental,
        )

        accumulation = analyze_accumulation(stock_df)

        # is_stage2 + 근접도(충족 개수·미충족 조건 라벨): minervini metrics
        is_stage2: float = 0.0
        stage2_met_count: float | None = None
        stage2_failed_labels: list[str] | None = None
        with contextlib.suppress(KeyError, TypeError, AttributeError):
            mv_metrics = technical_result.components["minervini"]["metrics"]
            is_stage2 = float(mv_metrics.get("is_stage2", 0.0))
            stage2_met_count = mv_metrics.get("conditions_met")
            stage2_failed_labels = [
                STAGE2_CONDITION_LABELS[name]
                for key, val in mv_metrics.items()
                if key.startswith("cond_")
                and val == 0.0
                and (name := key[len("cond_") :]) in STAGE2_CONDITION_LABELS
            ]

        vcp = detect_vcp_breakout(stock_df)

        canslim = compute_canslim(
            snapshot=getattr(technical_result, "snapshot", None),
            components=getattr(technical_result, "components", None),
            fundamental=fundamental,
            accumulation=accumulation,
            sector_strength=sector_strength,
            relative_strength=relative_strength,
            market_regime=market_regime,
        )

        # ── 3. 분기 ───────────────────────────────────────────────────────────
        is_holding = holding is not None

        if is_holding:
            # 보유 → 매도 판정
            exit_verdict = evaluate_exit(
                df=stock_df,
                snapshot=getattr(technical_result, "snapshot", None),
                relative_strength=relative_strength,
                accumulation=accumulation,
                holding=holding,
            )
            gate_result = None
            position_plan = None
            headline = _build_exit_headline(ticker, exit_verdict)

        else:
            # 미보유 → 게이트 + 사이징
            gate_result = evaluate_gate(
                market_regime=market_regime,
                is_stage2=is_stage2,
                relative_strength=relative_strength,
                sector_strength=sector_strength,
                vcp=vcp,
                canslim=canslim,
                flow=flow,
                stage2_met_count=stage2_met_count,
                stage2_failed_labels=stage2_failed_labels,
            )

            position_plan = None
            entry = last_valid_close(stock_df)  # 당일 미완성 봉(trailing NaN) 가드
            if gate_result.passed and entry is not None:
                atr_stop = _extract_atr_stop(stock_df, entry)
                invalidation_low = _extract_invalidation_low(zone_set, entry)

                capital, risk_pct = _resolve_account(ticker, self)
                position_plan = plan_position(
                    entry=entry,
                    atr_stop=atr_stop,
                    invalidation_low=invalidation_low,
                    capital=capital,
                    risk_pct=risk_pct,
                )
            elif gate_result.passed:
                logger.warning("Close all-NaN for %s; skip position plan", ticker)

            exit_verdict = None
            headline = _build_gate_headline(ticker, gate_result, position_plan)

        return CriteriaVerdict(
            ticker=ticker,
            holding=is_holding,
            market_regime=market_regime,
            relative_strength=relative_strength,
            sector_strength=sector_strength,
            canslim=canslim,
            checks=gate_result.checklist if gate_result else [],
            quality_grade=gate_result.quality_grade if gate_result else None,
            veto_reason=gate_result.veto_reason if gate_result else None,
            position_plan=position_plan,
            exit_verdict=exit_verdict,
            headline=headline,
        )

    async def _fetch_sector_strength(self, ticker: str, technical_result, fundamental):
        """미국 → FmpSectorStrength, 한국 → KisSectorStrength. sector None graceful."""
        if is_korean_ticker(ticker):
            return await self._fetch_kis_sector(ticker, technical_result)
        return await self._fetch_fmp_sector(ticker, fundamental)

    async def _fetch_fmp_sector(self, ticker: str, fundamental):
        """FMP 미국 업종 강도. fundamental.industry 없으면 None 반환."""
        if self._fmp_provider is None:
            return None

        industry: str | None = None
        if fundamental is not None:
            industry = getattr(fundamental, "industry", None)

        if not industry:
            return None

        try:
            from datetime import datetime

            today = datetime.now().strftime("%Y-%m-%d")
            snapshot_dict = await self._fmp_provider.industry_snapshot(today)
            historical = {}
            if industry in snapshot_dict:
                historical[industry] = await self._fmp_provider.historical_industry(industry)

            evaluator = FmpSectorStrength(snapshot=snapshot_dict, historical=historical)
            return evaluator.evaluate_industry(industry)
        except Exception as e:
            logger.warning("FMP sector fetch failed: %s", e)
            return None

    async def _fetch_kis_sector(self, ticker: str, technical_result):
        """KIS 한국 업종 강도. sector 매핑 실패 시 None 반환."""
        if self._kis_provider is None:
            return None

        try:
            # 업종명 추출: technical_result나 provider에서 가져옴
            bstp_kor_isnm: str | None = None
            snapshot = getattr(technical_result, "snapshot", None)
            if snapshot is not None:
                bstp_kor_isnm = getattr(snapshot, "bstp_kor_isnm", None)

            sector_code: str | None = None
            if bstp_kor_isnm:
                sector_code = KisSectorStrength.resolve_sector_code(bstp_kor_isnm)

            if not sector_code:
                # sector_code 없음 → graceful None
                return None

            # KIS 동시 호출 금지: 코스피 + 업종지수를 순차로
            kospi_df = await self._kis_provider.get_sector_index_history("0001", period="1y")
            sector_df = await self._kis_provider.get_sector_index_history(sector_code, period="1y")

            evaluator = KisSectorStrength()
            return evaluator.evaluate_sector_df(
                sector_code=sector_code,
                sector_df=sector_df,
                kospi_df=kospi_df,
            )
        except Exception as e:
            logger.warning("KIS sector fetch failed: %s", e)
            return None


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _extract_atr_stop(df: pd.DataFrame, entry: float) -> float | None:
    """2×ATR 손절가 계산. ATR 컬럼 없으면 None."""
    if "ATR" not in df.columns:
        return None
    atr = df["ATR"].iloc[-1]
    if pd.isna(atr) or float(atr) <= 0:
        return None
    return round(entry - 2.0 * float(atr), 4)


def _extract_invalidation_low(zone_set, entry: float) -> float | None:
    """zone_set에서 가장 가까운 지지 zone 하단 반환."""
    if zone_set is None:
        return None
    support_zones = getattr(zone_set, "support_zones", None)
    if not support_zones:
        return None
    # entry 아래 support zone 중 가장 가까운 것
    below = [z for z in support_zones if z.upper_bound < entry]
    if not below:
        return None
    closest = max(below, key=lambda z: z.upper_bound)
    return closest.lower_bound


def _resolve_account(ticker: str, engine: CriteriaEngine) -> tuple[float | None, float]:
    """티커 통화에 맞는 (capital, risk_pct) 반환."""
    if is_korean_ticker(ticker):
        return engine._krw_capital, engine._krw_risk_pct
    return engine._usd_capital, engine._usd_risk_pct


def _build_gate_headline(ticker: str, gate_result, position_plan) -> str:
    """매수 게이트 헤드라인."""
    if gate_result.passed:
        grade = gate_result.quality_grade or "?"
        if position_plan and position_plan.shares is not None:
            return f"{ticker}: 매수 적격 (grade={grade}) — {position_plan.shares}주 @ {position_plan.entry:.2f}, stop={position_plan.stop:.2f}"
        return f"{ticker}: 매수 적격 (grade={grade}) — 비율 모드"
    return f"{ticker}: 매수 거부 — {gate_result.veto_reason}"


def _build_exit_headline(ticker: str, exit_verdict) -> str:
    """보유 종목 매도 헤드라인."""
    action_label = {"liquidate": "청산", "reduce": "비중축소", "hold": "보유유지"}.get(
        exit_verdict.action, exit_verdict.action
    )
    r_str = f" (R={exit_verdict.current_r:.2f})" if exit_verdict.current_r is not None else ""
    return f"{ticker}: {action_label}{r_str} — {exit_verdict.detail}"
