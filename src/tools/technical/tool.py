import logging
from typing import Final

from src.core.interfaces import BaseProvider, BaseTool
from src.core.models import ToolResult
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.staleness import StaleClose, drop_trailing_nan_close


logger = logging.getLogger(__name__)


CANONICAL_TECHNICAL_PERIOD: Final[str] = "3y"


class TechnicalAnalysisTool(BaseTool):
    """Technical analysis tool using component-based scoring."""

    name = "technical"
    description = "기술적 분석 도구 (추세, 모멘텀, 패턴)"

    def __init__(self, provider: BaseProvider, scorer: TechnicalScorer):
        self.provider = provider
        self.scorer = scorer
        self.calculator = IndicatorCalculator()

    async def execute(
        self,
        ticker: str,
        period: str = CANONICAL_TECHNICAL_PERIOD,
        **kwargs,
    ) -> ToolResult:
        """Execute technical analysis on ticker."""
        try:
            logger.debug("Fetching price history: %s (period=%s)", ticker, period)
            df = await self.provider.get_price_history(ticker, period)
            if df.empty:
                logger.debug("No price data returned for %s", ticker)
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"No data found for {ticker}",
                )

            # 최신 봉 종가가 비어 있으면(yfinance 미마감 봉 등) 걷어낸 뒤 계산한다.
            # 그대로 두면 스냅샷은 이전 유효 봉으로, market context는 close=0.0으로 갈려
            # 스테일 종가가 조용히 흘러나간다.
            df, stale = drop_trailing_nan_close(df)
            if df.empty:
                logger.warning("All close values are NaN for %s", ticker)
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"No valid close data for {ticker}",
                )

            logger.debug("Got %d rows for %s, calculating indicators", len(df), ticker)
            df = self.calculator.calculate(df)

            logger.debug("Scoring %s", ticker)
            technical_result = self.scorer.score(df, ticker=ticker)
            logger.debug("Score for %s: %s", ticker, technical_result.total_score)

            if stale.is_stale:
                warning = await self._build_stale_warning(ticker, stale, technical_result)
                technical_result.warnings = (technical_result.warnings or []) + [warning]

            return ToolResult(success=True, data=technical_result)

        except Exception as e:
            logger.debug("Technical analysis error for %s: %s", ticker, e)
            return ToolResult(success=False, data=None, error=str(e))

    async def _build_stale_warning(
        self,
        ticker: str,
        stale: StaleClose,
        technical_result,
    ) -> str:
        """스테일 종가 경고 문자열을 만들고 런타임에 즉시 표면화(logger.warning)한다.

        best-effort로 get_quote 실시간가를 병기한다 — 조회 실패해도 경고 자체는 남긴다.
        """
        stale_price = technical_result.snapshot.price
        dropped_bar = stale.dropped_dates[-1] if stale.dropped_dates else "최신 봉"

        live_price = None
        try:
            quote = await self.provider.get_quote(ticker)
            live_price = quote.get("price") if quote else None
        except Exception as exc:  # get_quote 실패는 분석을 막지 않는다
            logger.debug("get_quote failed for stale-close augmentation %s: %s", ticker, exc)

        message = (
            f"최신 봉({dropped_bar}) 종가가 비어 있어 마지막 유효 종가"
            f"({stale.last_valid_date}, ${stale_price:.2f})로 분석했습니다."
        )
        if live_price is not None:
            message += f" 실시간 가격은 약 ${live_price:.2f}입니다."
        else:
            message += " 실시간 가격 확인은 실패했습니다."
        message += " 표시 가격·변동률·점수가 실제와 다를 수 있습니다."

        logger.warning(
            "Stale close for %s: dropped %d trailing NaN-close bar(s) up to %s, "
            "analyzed with %s ($%.2f), live=%s",
            ticker,
            stale.dropped_rows,
            dropped_bar,
            stale.last_valid_date,
            stale_price,
            f"${live_price:.2f}" if live_price is not None else "n/a",
        )
        return message
