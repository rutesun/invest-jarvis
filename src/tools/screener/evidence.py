import asyncio
import contextlib

import pandas as pd

from src.providers.kis import KISProvider
from src.providers.yfinance_provider import YFinanceProvider
from src.tools.screener.models import ScreenerEvidence, UniverseStock
from src.tools.screener.scoring import (
    score_accumulation,
    score_momentum,
    score_source_diversity,
    score_up_days,
    score_volume_burst,
)
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.turnaround import TurnaroundSignal, score_turnaround


class EvidenceCollector:
    """Collect evidence and score stocks."""

    def __init__(
        self,
        kis_provider: KISProvider | None,
        yf_provider: YFinanceProvider,
        concurrency: int = 10,
    ):
        self.kis = kis_provider
        self.yf = yf_provider
        self.concurrency = concurrency
        self.calculator = IndicatorCalculator()

    async def collect_and_score(self, universe: list[UniverseStock]) -> list[ScreenerEvidence]:
        """Collect evidence and score all stocks in universe.

        Args:
            universe: List of UniverseStock objects to score

        Returns:
            Ranked list of ScreenerEvidence objects sorted by momentum and total score
        """
        semaphore = asyncio.Semaphore(self.concurrency)

        async def bounded_collect(stock: UniverseStock) -> ScreenerEvidence | None:
            async with semaphore:
                try:
                    return await self._collect_one(stock)
                except Exception:
                    return None

        tasks = [bounded_collect(stock) for stock in universe]
        results = await asyncio.gather(*tasks)

        scored = [r for r in results if r is not None]
        scored.sort(key=lambda x: (x.momentum_total, x.total_score), reverse=True)
        for i, item in enumerate(scored):
            item.rank = i + 1

        return scored

    async def score_tickers(self, tickers: list[str]) -> list[ScreenerEvidence]:
        """Score arbitrary tickers without universe building.

        This is a reusable interface to score any list of tickers directly.

        Args:
            tickers: List of ticker symbols to score

        Returns:
            Ranked list of ScreenerEvidence objects
        """
        universe = [
            UniverseStock(
                ticker=ticker,
                name=ticker,
                market=self._detect_market(ticker),
                sources=["direct"],
            )
            for ticker in tickers
        ]
        return await self.collect_and_score(universe)

    async def _collect_one(self, stock: UniverseStock) -> ScreenerEvidence:
        """Collect evidence for a single stock.

        Args:
            stock: UniverseStock object to collect evidence for

        Returns:
            ScreenerEvidence with calculated scores
        """
        is_kr = stock.market in ("KOSPI", "KOSDAQ")

        # 1. OHLCV (140+ days)
        if stock.market == "KOSPI":
            ticker_for_yf = f"{stock.ticker}.KS"
        elif stock.market == "KOSDAQ":
            ticker_for_yf = f"{stock.ticker}.KQ"
        else:
            ticker_for_yf = stock.ticker

        df = await self.yf.get_price_history(ticker_for_yf, period="6mo")

        # 2. Calculate indicators (for momentum signals)
        if not df.empty:
            df = self.calculator.calculate(df)

        # 3. Investor trend (KR only)
        investor_trends = []
        program_trades = []
        if is_kr and self.kis:
            with contextlib.suppress(Exception):
                investor_trends = await self.kis.get_investor_trend(stock.ticker, days=10)

            try:
                program_trades = await self.kis.get_program_trade(stock.ticker, days=10)
            except Exception as e:
                # Log but continue - program trade may not be available for all stocks
                import logging

                logging.debug(f"Program trade data not available for {stock.ticker}: {e}")

        # 4. Score
        acc_score = score_accumulation(investor_trends)
        up_days = score_up_days(df, window=10) if not df.empty else 0

        # Calculate daily (most recent day)
        daily_foreign = investor_trends[0].get("foreign_net", 0) if investor_trends else 0
        daily_institution = investor_trends[0].get("institution_net", 0) if investor_trends else 0
        daily_program = program_trades[0].get("program_net", 0) if program_trades else 0

        # Calculate 10-day aggregates
        foreign_net_total = sum(t.get("foreign_net", 0) for t in investor_trends)
        institution_net_total = sum(t.get("institution_net", 0) for t in investor_trends)
        program_net_total = sum(t.get("program_net", 0) for t in program_trades)

        # Calculate buy days count (how many days had net buying)
        foreign_days_count = sum(1 for t in investor_trends if t.get("foreign_net", 0) > 0)
        institution_days_count = sum(1 for t in investor_trends if t.get("institution_net", 0) > 0)
        program_days_count = sum(1 for t in program_trades if t.get("program_net", 0) > 0)

        vol_ratio = 0.0
        if not df.empty and "Vol_SMA_20" in df.columns:
            latest_vol = df.iloc[-1].get("Volume", 0)
            vol_sma = df.iloc[-1].get("Vol_SMA_20", 0)
            if not pd.isna(vol_sma) and float(vol_sma) > 0:
                vol_ratio = float(latest_vol) / float(vol_sma)

        vol_score = score_volume_burst(vol_ratio)
        diversity = score_source_diversity(stock.sources)
        momentum = score_momentum(df)

        turnaround = score_turnaround(df) if not df.empty else TurnaroundSignal()

        # Flow score from accumulation
        momentum["flow"] = acc_score * 5.0
        momentum["momentum_total"] += momentum["flow"]

        total = acc_score + vol_score + diversity

        return ScreenerEvidence(
            stock=stock,
            accumulation_score=acc_score,
            daily_foreign=daily_foreign,
            daily_institution=daily_institution,
            daily_program=daily_program,
            foreign_net=foreign_net_total,
            institution_net=institution_net_total,
            program_net=program_net_total,
            foreign_days_count=foreign_days_count,
            institution_days_count=institution_days_count,
            program_days_count=program_days_count,
            up_days=up_days,
            volume_burst_score=vol_score,
            source_diversity_bonus=diversity,
            momentum_total=momentum["momentum_total"],
            total_score=total,
            vol_ratio=round(vol_ratio, 2),
            turnaround_score=turnaround.score,
            turnaround_markers=turnaround.marker_labels,
            turnaround_candidate=turnaround.is_candidate,
            turnaround_confirmed=turnaround.confirmed,
        )

    def _detect_market(self, ticker: str) -> str:
        """Detect market from ticker format.

        Args:
            ticker: Ticker symbol

        Returns:
            Market code: "KOSPI", "KOSDAQ", or "US"
        """
        if ticker.endswith(".KS"):
            return "KOSPI"
        elif ticker.endswith(".KQ"):
            return "KOSDAQ"
        elif ticker.isdigit() and len(ticker) == 6:
            return "KOSPI"
        return "US"
