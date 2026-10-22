"""Preserve the existing technical action as a chart-only strategy opinion."""

from datetime import date

import pandas as pd

from src.strategies.models import (
    ChartBundle,
    EntryIntent,
    EntryVerdict,
    ExitIntent,
    ExitVerdict,
    StrategyVerdict,
)
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.models import TechnicalVerdict
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance
from src.tools.technical.scorer import TechnicalScorer


_INTENTS = {
    "buy": (EntryIntent.ALLOW, ExitIntent.HOLD),
    "add": (EntryIntent.ALLOW, ExitIntent.HOLD),
    "hold": (EntryIntent.WATCH, ExitIntent.HOLD),
    "watch": (EntryIntent.WATCH, ExitIntent.HOLD),
    "accumulate": (EntryIntent.WATCH, ExitIntent.HOLD),
    "reduce": (EntryIntent.BLOCK, ExitIntent.REDUCE),
    "avoid": (EntryIntent.BLOCK, ExitIntent.NOT_EVALUATED),
}


class LegacyTechnicalStrategy:
    strategy_id = "TECHNICAL_LEGACY"
    strategy_version = "TECHNICAL_LEGACY_V1"

    def evaluate(self, bundle: ChartBundle) -> StrategyVerdict:
        bars = bundle.instrument.bars
        frame = pd.DataFrame(
            {
                "Open": [float(bar.open) for bar in bars],
                "High": [float(bar.high) for bar in bars],
                "Low": [float(bar.low) for bar in bars],
                "Close": [float(bar.close) for bar in bars],
                "Volume": [float(bar.volume) for bar in bars],
            },
            index=pd.DatetimeIndex([bar.session_date for bar in bars]),
        )
        calculated = IndicatorCalculator().calculate(frame)
        legacy = (
            TechnicalScorer()
            .score(calculated, ticker=bundle.ticker, include_history=False)
            .technical_verdict
        )
        if legacy is None:
            raise ValueError("Legacy technical scorer returned no verdict")
        return self.from_legacy(legacy, ticker=bundle.ticker, as_of=bundle.as_of)

    def from_legacy(
        self, verdict: TechnicalVerdict, *, ticker: str = "", as_of: date = date.min
    ) -> StrategyVerdict:
        entry_intent, exit_intent = _INTENTS[verdict.action]
        reasons = [
            Evidence(
                code="legacy_reason",
                message=message,
                observed_value=None,
                reference_value=None,
                importance=Importance.MEDIUM,
                source=self.strategy_id,
            )
            for message in verdict.reasons
        ]
        cautions = [
            Evidence(
                code="legacy_caution",
                message=message,
                observed_value=None,
                reference_value=None,
                importance=Importance.HIGH,
                source=self.strategy_id,
            )
            for message in verdict.cautions
        ]
        evidence = reasons + cautions
        return StrategyVerdict(
            verdict_schema_version="1",
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            ticker=ticker,
            as_of=as_of,
            entry=EntryVerdict(
                intent=entry_intent,
                opportunity=None,
                data_status=DataStatus.COMPLETE,
                reasons=evidence,
            ),
            exit=ExitVerdict(
                intent=exit_intent,
                data_status=DataStatus.COMPLETE,
                reasons=evidence,
            ),
            events=[],
            strategy_state=None,
        )
