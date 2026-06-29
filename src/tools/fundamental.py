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
    eps: float | None = None
    eps_yoy: float | None = None


class AnnualData(BaseModel):
    """Annual financial data (CAN SLIM A — annual EPS time series)."""

    year: str
    eps: float | None = None
    revenue: float | None = None
    earnings: float | None = None


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

    # Annual time series (CAN SLIM A)
    annual_data: list[AnnualData] | None = None

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

    @classmethod
    def _build_yf_quarterly_eps(cls, quarterly_income_stmt) -> list[QuarterlyData]:
        """quarterly_income_stmt의 'Diluted EPS' 행으로 분기 EPS + YoY 계산.

        YoY는 4개 분기 전 대비. EPS가 NaN이면 None으로 처리.
        """
        if quarterly_income_stmt is None or quarterly_income_stmt.empty:
            return []

        eps_row_name = "Diluted EPS"
        if eps_row_name not in quarterly_income_stmt.index:
            return []

        eps_series = quarterly_income_stmt.loc[eps_row_name]
        columns = list(eps_series.index)  # newest first

        raw: list[tuple[str, float | None]] = []
        for col in columns:
            # Use YYYY-QN format to match quarterly_financials period keys
            if hasattr(col, "quarter"):
                period_str = f"{col.year}-Q{col.quarter}"
            elif hasattr(col, "date"):
                period_str = str(col.date())
            else:
                period_str = str(col)
            val = eps_series[col]
            try:
                f = float(val)
                eps_val = None if math.isnan(f) else f
            except (TypeError, ValueError):
                eps_val = None
            raw.append((period_str, eps_val))

        result: list[QuarterlyData] = []
        for i in range(min(4, len(raw))):
            period, eps_val = raw[i]
            eps_yoy = None
            if len(raw) >= i + 5:
                _, prev_eps = raw[i + 4]
                if eps_val is not None and prev_eps not in (None, 0):
                    eps_yoy = (eps_val - prev_eps) / abs(prev_eps)
            result.append(QuarterlyData(period=period, eps=eps_val, eps_yoy=eps_yoy))
        return result

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

        # Merge EPS from quarterly_income_stmt into quarterly_data_list
        try:
            qis = t.quarterly_income_stmt
            eps_quarters = self._build_yf_quarterly_eps(qis)
            if eps_quarters and quarterly_data_list:
                eps_by_period = {eq.period: eq for eq in eps_quarters}
                merged: list[QuarterlyData] = []
                for bq in quarterly_data_list:
                    eq = eps_by_period.get(bq.period)
                    merged.append(
                        QuarterlyData(
                            period=bq.period,
                            revenue=bq.revenue,
                            earnings=bq.earnings,
                            revenue_yoy=bq.revenue_yoy,
                            revenue_qoq=bq.revenue_qoq,
                            earnings_yoy=bq.earnings_yoy,
                            earnings_qoq=bq.earnings_qoq,
                            eps=eq.eps if eq else None,
                            eps_yoy=eq.eps_yoy if eq else None,
                        )
                    )
                quarterly_data_list = merged
            elif eps_quarters and not quarterly_data_list:
                quarterly_data_list = eps_quarters
        except Exception as e:
            logger.warning("Failed to merge yfinance EPS: %s", e)

        # Build annual_data from income_stmt Diluted EPS
        annual_data: list[AnnualData] | None = None
        try:
            ann = t.income_stmt
            if ann is not None and not ann.empty and "Diluted EPS" in ann.index:
                ann_eps_series = ann.loc["Diluted EPS"]
                ann_rows = []
                for col in ann_eps_series.index:
                    year_str = str(col.year) if hasattr(col, "year") else str(col)[:4]
                    val = ann_eps_series[col]
                    try:
                        f = float(val)
                        eps_val = None if math.isnan(f) else f
                    except (TypeError, ValueError):
                        eps_val = None
                    if eps_val is not None:
                        ann_rows.append(AnnualData(year=year_str, eps=eps_val))
                if ann_rows:
                    annual_data = ann_rows[:5]
        except Exception as e:
            logger.warning("Failed to parse yfinance annual EPS: %s", e)

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
            annual_data=annual_data,
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
    def _kis_cumulative_to_standalone(
        cls, rows: list[dict], value_key: str
    ) -> dict[str, float | None]:
        """KIS 분기 누적 수치를 순수 분기(standalone) 수치로 변환.

        KIS balance-sheet·profit-ratio 분기 API는 당해 회계연도 누적으로 반환한다
        (Q2=Q1+Q2 합계, Q3=Q1+Q2+Q3 합계). 순수 분기 = 누적 - 직전 분기 누적.
        Q1(월=03)은 누적=순수이므로 그대로 사용.

        Returns:
            {"YYYY-MM": standalone_value} 형태의 dict
        """
        month_order = {"03": 0, "06": 1, "09": 2, "12": 3}

        by_year: dict[str, dict[str, float | None]] = {}
        for row in rows:
            ym = (row.get("stac_yymm") or "").strip()
            if len(ym) != 6:
                continue
            year, month = ym[:4], ym[4:]
            if month not in month_order:
                continue
            by_year.setdefault(year, {})[month] = cls._to_float(row.get(value_key))

        result: dict[str, float | None] = {}
        for year, months_map in by_year.items():
            sorted_months = sorted(months_map.keys(), key=lambda m: month_order[m])
            prev_cum: float | None = None
            for month in sorted_months:
                cum = months_map[month]
                if prev_cum is None:
                    standalone = cum
                else:
                    standalone = (
                        (cum - prev_cum) if (cum is not None and prev_cum is not None) else None
                    )
                result[f"{year}-{month}"] = standalone
                prev_cum = cum

        return result

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

    @classmethod
    def _build_quarterly_eps(cls, financial_ratio_q_rows: list[dict]) -> list[QuarterlyData]:
        """financial-ratio div=1 분기 행으로 순수 분기 EPS + YoY 계산.

        KIS는 당해 연도 누적 EPS를 반환하므로 _kis_cumulative_to_standalone으로 변환 후
        같은 분기월 1년 전(YYYY-1) 순수 분기 EPS와 YoY 비교.
        """
        # 누적 → 순수 분기 EPS 변환
        standalone_eps = cls._kis_cumulative_to_standalone(financial_ratio_q_rows, "eps")

        # YYYYMM 키 순서 유지를 위해 원본 rows 순서 기준으로 4개 선택
        seen: list[str] = []
        for row in financial_ratio_q_rows:
            ym = (row.get("stac_yymm") or "").strip()
            period_key = f"{ym[:4]}-{ym[4:]}" if len(ym) == 6 else None
            if period_key and period_key in standalone_eps and period_key not in seen:
                seen.append(period_key)
            if len(seen) == 4:
                break

        result: list[QuarterlyData] = []
        for period_key in seen:
            eps = standalone_eps.get(period_key)
            if eps is None:
                continue
            year, mm = period_key[:4], period_key[5:]
            prev_key = f"{int(year) - 1}-{mm}"
            prev_eps = standalone_eps.get(prev_key)
            eps_yoy = (eps - prev_eps) / abs(prev_eps) if prev_eps not in (None, 0) else None
            result.append(QuarterlyData(period=period_key, eps=eps, eps_yoy=eps_yoy))
        return result

    def _normalize_kis_snapshot(
        self,
        *,
        ticker: str,
        quote_data: dict,
        profit_ratio: list[dict],
        financial_ratio: list[dict],
        profit_ratio_q: list[dict],
        profit_ratio_a: list[dict],
        other_major_ratios: list[dict],
        income_statement: list[dict],
        balance_sheet: list[dict],
        balance_sheet_q: list[dict],
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
        # KIS balance_sheet은 최신 분기행(예: 202603)과 연간행(XX12)이 혼재한다.
        # 분기행 vs 연간행을 비교하면 의미 없는 성장률이 나오므로 연간행끼리만 비교한다.
        annual_balance_rows = [
            r for r in valid_balance_sheet
            if (r.get("stac_yymm") or "").strip().endswith("12")
        ]
        if len(annual_balance_rows) >= 2:
            current_row = annual_balance_rows[0]
            previous_row = annual_balance_rows[1]
            current_revenue = self._to_float(current_row.get("sale_account"))
            previous_revenue = self._to_float(previous_row.get("sale_account"))
            current_earnings = self._to_float(current_row.get("thtr_ntin"))
            previous_earnings = self._to_float(previous_row.get("thtr_ntin"))
            if current_revenue is not None and previous_revenue not in (None, 0):
                revenue_growth = (current_revenue - previous_revenue) / previous_revenue
            if current_earnings is not None and previous_earnings not in (None, 0):
                earnings_growth = (current_earnings - previous_earnings) / previous_earnings

        # Build quarterly data: profit-ratio 분기 EPS series를 기준으로 구성.
        # balance-sheet 매출/순이익은 같은 period만 병합. 연간 행은 quarterly에 넣지 않음.
        # EPS series가 없으면 balance-sheet 기준으로 fallback.
        eps_quarters = self._build_quarterly_eps(profit_ratio_q)
        # 분기 balance sheet(div=1)에서 순수 분기(standalone) period-keyed map 구성.
        # KIS는 누적값을 반환하므로 _kis_cumulative_to_standalone으로 변환한다.
        valid_balance_sheet_q = self._filter_valid_rows(
            balance_sheet_q, ["sale_account", "op_prfi", "thtr_ntin"]
        )
        standalone_rev = self._kis_cumulative_to_standalone(valid_balance_sheet_q, "sale_account")
        standalone_earn = self._kis_cumulative_to_standalone(valid_balance_sheet_q, "thtr_ntin")
        all_periods = set(standalone_rev) | set(standalone_earn)
        balance_by_period: dict[str, tuple[float | None, float | None]] = {
            p: (standalone_rev.get(p), standalone_earn.get(p)) for p in all_periods
        }
        if eps_quarters:
            # EPS series 기준: balance-sheet는 period 매칭 시만 병합, 연간 행 제외
            merged_quarters: list[QuarterlyData] = []
            for eq in eps_quarters:
                rev, earn = balance_by_period.get(eq.period, (None, None))
                merged_quarters.append(
                    QuarterlyData(
                        period=eq.period,
                        revenue=rev,
                        earnings=earn,
                        eps=eq.eps,
                        eps_yoy=eq.eps_yoy,
                    )
                )
            quarterly_data_final = merged_quarters if merged_quarters else None
        else:
            # EPS 없음: 분기 balance-sheet 기준 fallback
            balance_quarters = self._build_kis_quarterly_data(valid_balance_sheet_q) or []
            quarterly_data_final = balance_quarters if balance_quarters else None

        # Build annual_data from profit-ratio div=0
        # KIS는 div=0(연간) API에서도 최신 분기행(XX03/06/09)을 먼저 반환한다.
        # 연간 데이터는 결산월(stac_yymm이 XX12로 끝나는) 행만 사용한다.
        annual_data: list[AnnualData] | None = None
        annual_rows = [
            AnnualData(
                year=(r.get("stac_yymm") or "")[:4],
                eps=self._to_float(r.get("eps")),
            )
            for r in profit_ratio_a
            if self._to_float(r.get("eps")) is not None
            and (r.get("stac_yymm") or "").strip().endswith("12")
        ][:5]
        if annual_rows:
            annual_data = annual_rows

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
            quarterly_data=quarterly_data_final,
            annual_data=annual_data,
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
            "balance_sheet_q": self._run_with_retry(
                "balance_sheet_q",
                lambda: self.kis_provider.get_balance_sheet(ticker, div_cls_code="1"),
            ),
            "profit_ratio": self._run_with_retry(
                "profit_ratio", lambda: self.kis_provider.get_profit_ratio(ticker)
            ),
            "profit_ratio_q": self._run_with_retry(
                "profit_ratio_q",
                lambda: self.kis_provider.get_profit_ratio(ticker, div_cls_code="1"),
            ),
            "profit_ratio_a": self._run_with_retry(
                "profit_ratio_a",
                lambda: self.kis_provider.get_profit_ratio(ticker, div_cls_code="0"),
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
        balance_sheet_q = merged["balance_sheet_q"][0] or []
        profit_ratio = merged["profit_ratio"][0] or []
        profit_ratio_q = merged["profit_ratio_q"][0] or []
        profit_ratio_a = merged["profit_ratio_a"][0] or []
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
            profit_ratio_q=profit_ratio_q,
            profit_ratio_a=profit_ratio_a,
            other_major_ratios=other_major,
            income_statement=income_statement,
            balance_sheet=balance_sheet,
            balance_sheet_q=balance_sheet_q,
        )
