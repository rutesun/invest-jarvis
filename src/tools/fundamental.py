# src/tools/fundamental.py
import asyncio
from functools import partial
from pydantic import BaseModel
import yfinance as yf
from src.core.interfaces import BaseTool
from src.core.models import ToolResult


class QuarterlyData(BaseModel):
    """Quarterly financial data with growth rates."""
    period: str
    revenue: float | None = None
    earnings: float | None = None
    revenue_yoy: float | None = None
    revenue_qoq: float | None = None
    earnings_yoy: float | None = None
    earnings_qoq: float | None = None


class FundamentalSnapshot(BaseModel):
    """Comprehensive fundamental data snapshot."""
    # Basic info
    market_cap: float | None = None
    sector: str | None = None
    industry: str | None = None

    # Valuation
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None

    # Profitability
    eps: float | None = None
    ebitda: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    profit_margin: float | None = None
    roe: float | None = None
    roa: float | None = None

    # Growth
    revenue_growth: float | None = None
    earnings_growth: float | None = None

    # Quarterly data with growth rates
    quarterly_data: list[QuarterlyData] | None = None

    # Financial health
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None

    # Cash flow
    free_cash_flow: float | None = None
    operating_cash_flow: float | None = None
    fcf_yield: float | None = None

    # Dividend
    dividend_yield: float | None = None
    payout_ratio: float | None = None

    # Shares
    shares_outstanding: float | None = None
    float_shares: float | None = None


class FundamentalTool(BaseTool):
    """Fundamental analysis tool using yfinance."""

    name = "fundamental"
    description = "펀더멘털 분석 (밸류에이션, 수익성, 성장성, 재무건전성)"

    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        try:
            loop = asyncio.get_running_loop()
            snapshot = await loop.run_in_executor(
                None, partial(self._fetch_fundamentals, ticker)
            )
            return ToolResult(success=True, data=snapshot)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _fetch_fundamentals(self, ticker: str) -> FundamentalSnapshot:
        t = yf.Ticker(ticker)
        info = t.info

        # FCF yield
        fcf = info.get("freeCashflow")
        mcap = info.get("marketCap")
        fcf_yield = (fcf / mcap) if fcf and mcap and mcap > 0 else None

        # Quarterly data with YoY/QoQ growth rates
        quarterly_data_list = None
        try:
            qf = t.quarterly_financials
            if qf is not None and not qf.empty:
                import math

                # Parse up to 8 quarters
                num_quarters = min(len(qf.columns), 8)
                quarters_raw = []

                for col in qf.columns[:num_quarters]:
                    period = f"{col.year}-Q{col.quarter}" if hasattr(col, "quarter") else str(col)
                    rev = qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else None
                    earn = qf.loc["Net Income", col] if "Net Income" in qf.index else None

                    # Handle pandas NaN
                    rev_value = None
                    if rev is not None:
                        try:
                            rev_float = float(rev)
                            if not math.isnan(rev_float):
                                rev_value = rev_float
                        except (ValueError, TypeError):
                            pass

                    earn_value = None
                    if earn is not None:
                        try:
                            earn_float = float(earn)
                            if not math.isnan(earn_float):
                                earn_value = earn_float
                        except (ValueError, TypeError):
                            pass

                    quarters_raw.append({
                        "period": period,
                        "revenue": rev_value,
                        "earnings": earn_value,
                    })

                # Calculate growth rates for most recent 4 quarters
                quarterly_data_list = []
                for i in range(min(4, len(quarters_raw))):
                    q = quarters_raw[i]

                    # YoY calculation (compare with 4 quarters ago)
                    revenue_yoy = None
                    earnings_yoy = None
                    if len(quarters_raw) >= i + 5:  # Need i+5 quarters for YoY
                        q_yoy = quarters_raw[i + 4]
                        if q["revenue"] is not None and q_yoy["revenue"] is not None and q_yoy["revenue"] > 0:
                            revenue_yoy = (q["revenue"] - q_yoy["revenue"]) / q_yoy["revenue"]
                        if q["earnings"] is not None and q_yoy["earnings"] is not None and q_yoy["earnings"] > 0:
                            earnings_yoy = (q["earnings"] - q_yoy["earnings"]) / q_yoy["earnings"]

                    # QoQ calculation (compare with 1 quarter ago)
                    revenue_qoq = None
                    earnings_qoq = None
                    if len(quarters_raw) >= i + 2:  # Need i+2 quarters for QoQ
                        q_qoq = quarters_raw[i + 1]
                        if q["revenue"] is not None and q_qoq["revenue"] is not None and q_qoq["revenue"] > 0:
                            revenue_qoq = (q["revenue"] - q_qoq["revenue"]) / q_qoq["revenue"]
                        if q["earnings"] is not None and q_qoq["earnings"] is not None and q_qoq["earnings"] > 0:
                            earnings_qoq = (q["earnings"] - q_qoq["earnings"]) / q_qoq["earnings"]

                    quarterly_data_list.append(QuarterlyData(
                        period=q["period"],
                        revenue=q["revenue"],
                        earnings=q["earnings"],
                        revenue_yoy=revenue_yoy,
                        revenue_qoq=revenue_qoq,
                        earnings_yoy=earnings_yoy,
                        earnings_qoq=earnings_qoq,
                    ))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to parse quarterly financials: %s", e)

        return FundamentalSnapshot(
            market_cap=info.get("marketCap"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            peg_ratio=info.get("pegRatio"),
            pb_ratio=info.get("priceToBook"),
            ps_ratio=info.get("priceToSalesTrailing12Months"),
            ev_ebitda=info.get("enterpriseToEbitda"),
            eps=info.get("trailingEps"),
            ebitda=info.get("ebitda"),
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            profit_margin=info.get("profitMargins"),
            roe=info.get("returnOnEquity"),
            roa=info.get("returnOnAssets"),
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=info.get("earningsGrowth"),
            quarterly_data=quarterly_data_list,
            debt_to_equity=info.get("debtToEquity"),
            current_ratio=info.get("currentRatio"),
            quick_ratio=info.get("quickRatio"),
            free_cash_flow=info.get("freeCashflow"),
            operating_cash_flow=info.get("operatingCashflow"),
            fcf_yield=fcf_yield,
            dividend_yield=info.get("dividendYield"),
            payout_ratio=info.get("payoutRatio"),
            shares_outstanding=info.get("sharesOutstanding"),
            float_shares=info.get("floatShares"),
        )
