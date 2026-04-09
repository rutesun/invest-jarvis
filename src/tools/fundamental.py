# src/tools/fundamental.py
import asyncio
from functools import partial
from pydantic import BaseModel
import yfinance as yf
from src.core.interfaces import BaseTool
from src.core.models import ToolResult


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

    # Quarterly results (last 4 quarters)
    quarterly_revenue: list[dict] | None = None
    quarterly_earnings: list[dict] | None = None

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
            loop = asyncio.get_event_loop()
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

        # Quarterly data
        quarterly_revenue = None
        quarterly_earnings = None
        try:
            qf = t.quarterly_financials
            if qf is not None and not qf.empty:
                quarterly_revenue = []
                quarterly_earnings = []
                for col in qf.columns[:4]:
                    period = col.strftime("%Y-Q%q") if hasattr(col, "strftime") else str(col)
                    rev = qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else None
                    earn = qf.loc["Net Income", col] if "Net Income" in qf.index else None
                    if rev is not None:
                        quarterly_revenue.append({"period": period, "revenue": float(rev)})
                    if earn is not None:
                        quarterly_earnings.append({"period": period, "earnings": float(earn)})
        except Exception:
            pass

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
            quarterly_revenue=quarterly_revenue,
            quarterly_earnings=quarterly_earnings,
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
