"""Chart-only adapter for the existing Playbook gate and exit rules."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.strategies.models import (
    ChartBundle,
    EntryIntent,
    EntryVerdict,
    ExitIntent,
    ExitVerdict,
    StrategyVerdict,
)
from src.tools.playbook.accumulation import analyze_accumulation
from src.tools.playbook.exit_rules import evaluate_exit
from src.tools.playbook.gate import evaluate_gate
from src.tools.playbook.market_regime import assess_market_regime
from src.tools.playbook.relative_strength import _SLOPE_DAYS, compute_relative_strength
from src.tools.playbook.vcp import detect_vcp_breakout
from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


def _frame(series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [float(bar.open) for bar in series.bars],
            "High": [float(bar.high) for bar in series.bars],
            "Low": [float(bar.low) for bar in series.bars],
            "Close": [float(bar.close) for bar in series.bars],
            "Volume": [float(bar.volume) for bar in series.bars],
        },
        index=pd.DatetimeIndex([bar.session_date for bar in series.bars]),
    )


def _reason(code: str, message: str) -> Evidence:
    return Evidence(
        code=code,
        message=message,
        observed_value=None,
        reference_value=None,
        importance=Importance.MEDIUM,
        source="PLAYBOOK_V1",
    )


class PlaybookStrategy:
    strategy_id = "PLAYBOOK_V1"
    strategy_version = "PLAYBOOK_V1_V1"

    def evaluate(self, bundle: ChartBundle) -> StrategyVerdict:
        instrument = bundle.instrument
        stock_ready = (
            instrument.coverage.complete
            and instrument.coverage.truncation_reason is None
            and len(instrument.bars) >= 221
        )
        if not stock_ready:
            reason = [_reason("insufficient_chart", "Complete 221-bar instrument chart required")]
            return self._verdict(
                bundle,
                EntryIntent.NOT_EVALUATED,
                ExitIntent.NOT_EVALUATED,
                DataStatus.INSUFFICIENT_DATA,
                DataStatus.INSUFFICIENT_DATA,
                reason,
                reason,
            )

        stock = IndicatorCalculator().calculate(_frame(instrument))
        last = stock.iloc[-1]
        swing_lows = stock["Swing_Low"].dropna()
        snapshot = SimpleNamespace(
            high_52w=float(last["High_52w"]),
            swing_low=float(swing_lows.iloc[-1]) if not swing_lows.empty else None,
        )
        accumulation = analyze_accumulation(stock)
        market_ready = (
            bundle.market is not None
            and bundle.market_ticker is not None
            and bundle.market.coverage.complete
            and bundle.market.coverage.truncation_reason is None
            and len(bundle.market.bars) >= 221
            and bundle.market.bars[-1].session_date == bundle.as_of
        )
        common_sessions = (
            len(
                {bar.session_date for bar in instrument.bars}
                & {bar.session_date for bar in bundle.market.bars}
            )
            if market_ready
            else 0
        )
        rs_ready = market_ready and common_sessions >= _SLOPE_DAYS + 1
        relative_strength = None
        if rs_ready:
            market = _frame(bundle.market)
            regime = assess_market_regime(market, bundle.market_ticker)
            relative_strength = compute_relative_strength(stock, market, bundle.market_ticker)
            stage2 = analyze_minervini(stock).metrics
            gate = evaluate_gate(
                market_regime=regime,
                is_stage2=stage2.get("is_stage2"),
                relative_strength=relative_strength,
                sector_strength=None,
                vcp=detect_vcp_breakout(stock),
                canslim=None,
                flow=None,
                chart_only=True,
            )
            entry = EntryIntent.ALLOW if gate.passed else EntryIntent.BLOCK
            entry_status = DataStatus.COMPLETE
            entry_reasons = [_reason("gate", gate.veto_reason or "Chart gate passed")]
        else:
            entry = EntryIntent.NOT_EVALUATED
            entry_status = DataStatus.INSUFFICIENT_DATA
            entry_reasons = [
                _reason(
                    "insufficient_rs_chart" if market_ready else "missing_market_chart",
                    "At least 21 common stock/market sessions required"
                    if market_ready
                    else "Complete market chart required",
                )
            ]

        exit_result = evaluate_exit(
            df=stock,
            snapshot=snapshot,
            relative_strength=relative_strength,
            accumulation=accumulation,
        )
        exit_intent = {
            "hold": ExitIntent.HOLD,
            "reduce": ExitIntent.REDUCE,
            "liquidate": ExitIntent.EXIT,
        }[exit_result.action]
        exit_status = DataStatus.COMPLETE if rs_ready else DataStatus.PARTIAL
        exit_reasons = [_reason(signal.code, signal.detail) for signal in exit_result.signals]
        if not rs_ready:
            exit_reasons.extend(entry_reasons)
        return self._verdict(
            bundle, entry, exit_intent, entry_status, exit_status, entry_reasons, exit_reasons
        )

    def _verdict(
        self, bundle, entry, exit_, entry_status, exit_status, entry_reasons, exit_reasons
    ) -> StrategyVerdict:
        return StrategyVerdict(
            verdict_schema_version="1",
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            ticker=bundle.ticker,
            as_of=bundle.as_of,
            entry=EntryVerdict(
                intent=entry, opportunity=None, data_status=entry_status, reasons=entry_reasons
            ),
            exit=ExitVerdict(intent=exit_, data_status=exit_status, reasons=exit_reasons),
            events=[],
            strategy_state=None,
        )
