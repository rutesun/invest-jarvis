import asyncio
import logging
import math
from functools import partial

import httpx
import yfinance as yf
from pydantic import BaseModel

from src.core.interfaces import BaseTool
from src.core.models import ToolResult
from src.providers.kis import KISProvider
from src.tools.disclosure import is_korean_ticker


logger = logging.getLogger(__name__)


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
    """Fundamental analysis tool using KIS for Korean stocks and yfinance elsewhere."""

    name = "fundamental"
    description = "펀더멘털 분석 (밸류에이션, 수익성, 성장성, 재무건전성)"

    def __init__(self, kis_provider: KISProvider | None = None):
        self.kis_provider = kis_provider

    @staticmethod
    def _is_retryable_error(error: Exception) -> bool:
        if isinstance(error, (httpx.TimeoutException, httpx.NetworkError, httpx.RequestError)):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in {429, 500, 502, 503, 504}
        return False

    async def _run_with_retry(self, name: str, coro_factory, retries: int = 2):
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return await coro_factory(), None
            except Exception as error:
                last_error = error
                if attempt >= retries or not self._is_retryable_error(error):
                    break
                backoff = 0.4 * (2**attempt)
                logger.warning(
                    "KIS %s call failed (attempt=%s/%s): %s",
                    name,
                    attempt + 1,
                    retries + 1,
                    error,
                )
                await asyncio.sleep(backoff)
        return None, last_error

    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        try:
            if is_korean_ticker(ticker) and self.kis_provider is not None:
                snapshot = await self._fetch_kis_fundamentals(ticker)
            else:
                loop = asyncio.get_running_loop()
                snapshot = await loop.run_in_executor(
                    None, partial(self._fetch_yfinance_fundamentals, ticker)
                )
            return ToolResult(success=True, data=snapshot)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _fetch_yfinance_fundamentals(self, ticker: str) -> FundamentalSnapshot:
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

                    quarters_raw.append(
                        {
                            "period": period,
                            "revenue": rev_value,
                            "earnings": earn_value,
                        }
                    )

                # Calculate growth rates for most recent 4 quarters
                quarterly_data_list = []
                for i in range(min(4, len(quarters_raw))):
                    q = quarters_raw[i]

                    # YoY calculation (compare with 4 quarters ago)
                    revenue_yoy = None
                    earnings_yoy = None
                    if len(quarters_raw) >= i + 5:  # Need i+5 quarters for YoY
                        q_yoy = quarters_raw[i + 4]
                        if (
                            q["revenue"] is not None
                            and q_yoy["revenue"] is not None
                            and q_yoy["revenue"] > 0
                        ):
                            revenue_yoy = (q["revenue"] - q_yoy["revenue"]) / q_yoy["revenue"]
                        if (
                            q["earnings"] is not None
                            and q_yoy["earnings"] is not None
                            and q_yoy["earnings"] > 0
                        ):
                            earnings_yoy = (q["earnings"] - q_yoy["earnings"]) / q_yoy["earnings"]

                    # QoQ calculation (compare with 1 quarter ago)
                    revenue_qoq = None
                    earnings_qoq = None
                    if len(quarters_raw) >= i + 2:  # Need i+2 quarters for QoQ
                        q_qoq = quarters_raw[i + 1]
                        if (
                            q["revenue"] is not None
                            and q_qoq["revenue"] is not None
                            and q_qoq["revenue"] > 0
                        ):
                            revenue_qoq = (q["revenue"] - q_qoq["revenue"]) / q_qoq["revenue"]
                        if (
                            q["earnings"] is not None
                            and q_qoq["earnings"] is not None
                            and q_qoq["earnings"] > 0
                        ):
                            earnings_qoq = (q["earnings"] - q_qoq["earnings"]) / q_qoq["earnings"]

                    quarterly_data_list.append(
                        QuarterlyData(
                            period=q["period"],
                            revenue=q["revenue"],
                            earnings=q["earnings"],
                            revenue_yoy=revenue_yoy,
                            revenue_qoq=revenue_qoq,
                            earnings_yoy=earnings_yoy,
                            earnings_qoq=earnings_qoq,
                        )
                    )
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

    @staticmethod
    def _to_float(value) -> float | None:
        if value in (None, "", "-", "N/A"):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            return None
        if parsed == 99.99:
            return None
        return parsed

    @classmethod
    def _filter_valid_rows(cls, rows: list[dict], signal_keys: list[str]) -> list[dict]:
        valid_rows: list[dict] = []
        for row in rows:
            values = [cls._to_float(row.get(key)) for key in signal_keys]
            if any(value is not None and value != 0 for value in values):
                valid_rows.append(row)
        return valid_rows

    @classmethod
    def _build_kis_quarterly_data(cls, rows: list[dict]) -> list[QuarterlyData] | None:
        valid_rows = cls._filter_valid_rows(rows, ["sale_account", "op_prfi", "thtr_ntin"])
        if not valid_rows:
            return None

        quarterly_data: list[QuarterlyData] = []
        for index, row in enumerate(valid_rows[:4]):
            revenue = cls._to_float(row.get("sale_account"))
            earnings = cls._to_float(row.get("thtr_ntin"))
            revenue_qoq = None
            earnings_qoq = None

            if index + 1 < len(valid_rows):
                previous = valid_rows[index + 1]
                previous_revenue = cls._to_float(previous.get("sale_account"))
                previous_earnings = cls._to_float(previous.get("thtr_ntin"))
                if revenue is not None and previous_revenue not in (None, 0):
                    revenue_qoq = (revenue - previous_revenue) / previous_revenue
                if earnings is not None and previous_earnings not in (None, 0):
                    earnings_qoq = (earnings - previous_earnings) / previous_earnings

            quarterly_data.append(
                QuarterlyData(
                    period=f"{row.get('stac_yymm', '')[:4]}-{row.get('stac_yymm', '')[4:]}",
                    revenue=revenue,
                    earnings=earnings,
                    revenue_qoq=revenue_qoq,
                    earnings_qoq=earnings_qoq,
                )
            )

        return quarterly_data

    def _normalize_kis_snapshot(
        self,
        *,
        ticker: str,
        quote_data: dict,
        profit_ratio: list[dict],
        financial_ratio: list[dict],
        other_major_ratios: list[dict],
        income_statement: list[dict],
        balance_sheet: list[dict],
    ) -> FundamentalSnapshot:
        valid_profit_ratio = self._filter_valid_rows(profit_ratio, ["roe_val", "eps", "bps", "sps"])
        valid_financial_ratio = self._filter_valid_rows(
            financial_ratio,
            ["cras", "flow_lblt", "total_lblt", "total_cptl"],
        )
        valid_other_major = self._filter_valid_rows(
            other_major_ratios,
            ["ebitda", "ev_ebitda", "payout_rate"],
        )
        valid_income_statement = self._filter_valid_rows(
            income_statement,
            ["cptl_ntin_rate", "self_cptl_ntin_inrt", "sale_ntin_rate", "sale_totl_rate"],
        )
        valid_balance_sheet = self._filter_valid_rows(
            balance_sheet,
            ["sale_account", "sale_totl_prfi", "op_prfi", "thtr_ntin"],
        )

        profit_row = valid_profit_ratio[0] if valid_profit_ratio else {}
        financial_row = valid_financial_ratio[0] if valid_financial_ratio else {}
        other_major_row = valid_other_major[0] if valid_other_major else {}
        income_row = valid_income_statement[0] if valid_income_statement else {}
        balance_row = valid_balance_sheet[0] if valid_balance_sheet else {}

        price = self._to_float(quote_data.get("price"))
        eps = self._to_float(profit_row.get("eps"))
        bps = self._to_float(profit_row.get("bps"))
        sps = self._to_float(profit_row.get("sps"))
        ebitda = self._to_float(other_major_row.get("ebitda"))

        sale_account = self._to_float(balance_row.get("sale_account"))
        sale_totl_prfi = self._to_float(balance_row.get("sale_totl_prfi"))
        op_prfi = self._to_float(balance_row.get("op_prfi"))
        thtr_ntin = self._to_float(balance_row.get("thtr_ntin"))

        cras = self._to_float(financial_row.get("cras"))
        flow_lblt = self._to_float(financial_row.get("flow_lblt"))
        total_lblt = self._to_float(financial_row.get("total_lblt"))
        total_cptl = self._to_float(financial_row.get("total_cptl"))

        revenue_growth = None
        earnings_growth = None
        if len(valid_balance_sheet) >= 2:
            current_row = valid_balance_sheet[0]
            previous_row = valid_balance_sheet[1]
            current_revenue = self._to_float(current_row.get("sale_account"))
            previous_revenue = self._to_float(previous_row.get("sale_account"))
            current_earnings = self._to_float(current_row.get("thtr_ntin"))
            previous_earnings = self._to_float(previous_row.get("thtr_ntin"))
            if current_revenue is not None and previous_revenue not in (None, 0):
                revenue_growth = (current_revenue - previous_revenue) / previous_revenue
            if current_earnings is not None and previous_earnings not in (None, 0):
                earnings_growth = (current_earnings - previous_earnings) / previous_earnings

        return FundamentalSnapshot(
            market_cap=None,
            sector=None,
            industry=None,
            pe_ratio=(price / eps) if price is not None and eps not in (None, 0) else None,
            forward_pe=None,
            peg_ratio=None,
            pb_ratio=(price / bps) if price is not None and bps not in (None, 0) else None,
            ps_ratio=(price / sps) if price is not None and sps not in (None, 0) else None,
            ev_ebitda=self._to_float(other_major_row.get("ev_ebitda")),
            eps=eps,
            ebitda=ebitda,
            gross_margin=(
                self._to_float(income_row.get("sale_totl_rate")) / 100
                if self._to_float(income_row.get("sale_totl_rate")) is not None
                else (
                    sale_totl_prfi / sale_account
                    if sale_totl_prfi is not None and sale_account not in (None, 0)
                    else None
                )
            ),
            operating_margin=(
                op_prfi / sale_account
                if op_prfi is not None and sale_account not in (None, 0)
                else None
            ),
            profit_margin=(
                self._to_float(income_row.get("sale_ntin_rate")) / 100
                if self._to_float(income_row.get("sale_ntin_rate")) is not None
                else (
                    thtr_ntin / sale_account
                    if thtr_ntin is not None and sale_account not in (None, 0)
                    else None
                )
            ),
            roe=(
                self._to_float(profit_row.get("roe_val")) / 100
                if self._to_float(profit_row.get("roe_val")) is not None
                else (
                    self._to_float(income_row.get("self_cptl_ntin_inrt")) / 100
                    if self._to_float(income_row.get("self_cptl_ntin_inrt")) is not None
                    else None
                )
            ),
            roa=(
                self._to_float(income_row.get("cptl_ntin_rate")) / 100
                if self._to_float(income_row.get("cptl_ntin_rate")) is not None
                else None
            ),
            revenue_growth=revenue_growth,
            earnings_growth=earnings_growth,
            quarterly_data=self._build_kis_quarterly_data(valid_balance_sheet),
            debt_to_equity=(
                total_lblt / total_cptl
                if total_lblt is not None and total_cptl not in (None, 0)
                else None
            ),
            current_ratio=(
                cras / flow_lblt if cras is not None and flow_lblt not in (None, 0) else None
            ),
            quick_ratio=None,
            free_cash_flow=None,
            operating_cash_flow=None,
            fcf_yield=None,
            dividend_yield=None,
            payout_ratio=(
                self._to_float(other_major_row.get("payout_rate")) / 100
                if self._to_float(other_major_row.get("payout_rate")) is not None
                else None
            ),
            shares_outstanding=None,
            float_shares=None,
        )

    async def _fetch_kis_fundamentals(self, ticker: str) -> FundamentalSnapshot:
        if self.kis_provider is None:
            raise ValueError("KIS provider is required for Korean stock fundamentals")

        kr_code = ticker.replace(".KS", "").replace(".KQ", "")
        tasks = {
            "quote": self._run_with_retry("quote", lambda: self.kis_provider.get_quote(kr_code)),
            "financial_ratio": self._run_with_retry(
                "financial_ratio", lambda: self.kis_provider.get_financial_ratio(ticker)
            ),
            "balance_sheet": self._run_with_retry(
                "balance_sheet", lambda: self.kis_provider.get_balance_sheet(ticker)
            ),
            "profit_ratio": self._run_with_retry(
                "profit_ratio", lambda: self.kis_provider.get_profit_ratio(ticker)
            ),
            "income_statement": self._run_with_retry(
                "income_statement", lambda: self.kis_provider.get_income_statement(ticker)
            ),
            "other_major_ratios": self._run_with_retry(
                "other_major_ratios", lambda: self.kis_provider.get_other_major_ratios(ticker)
            ),
        }
        results = await asyncio.gather(*tasks.values())
        merged = dict(zip(tasks.keys(), results, strict=True))

        errors = {name: error for name, (_, error) in merged.items() if error is not None}
        for name, error in errors.items():
            logger.warning("KIS %s failed after retries: %s", name, error)

        quote_data = merged["quote"][0] or {}
        financial_ratio = merged["financial_ratio"][0] or []
        balance_sheet = merged["balance_sheet"][0] or []
        profit_ratio = merged["profit_ratio"][0] or []
        income_statement = merged["income_statement"][0] or []
        other_major = merged["other_major_ratios"][0] or []

        if not quote_data and not any(
            [financial_ratio, balance_sheet, profit_ratio, income_statement, other_major]
        ):
            raise RuntimeError(
                "KIS 재무 조회 실패: 모든 재무 엔드포인트 응답이 비어 있습니다."
            ) from errors.get("quote")

        return self._normalize_kis_snapshot(
            ticker=ticker,
            quote_data=quote_data,
            profit_ratio=profit_ratio,
            financial_ratio=financial_ratio,
            other_major_ratios=other_major,
            income_statement=income_statement,
            balance_sheet=balance_sheet,
        )
