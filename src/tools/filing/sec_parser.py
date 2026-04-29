# src/tools/filing/sec_parser.py
"""SEC EDGAR 공시 파싱: companyfacts API (XBRL) + edgartools (텍스트)."""

import json
import logging
import re
import time
from decimal import Decimal
from pathlib import Path

import httpx
from langchain_core.language_models import BaseChatModel

from src.tools.filing.concepts import SEC_CONCEPT_CHAINS
from src.tools.filing.models import (
    Comparison,
    FilingFacts,
    FinancialMetric,
)


logger = logging.getLogger(__name__)

_SEC_USER_AGENT = "invest-jarvis research@example.com"
_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_CIK_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
_CACHE_DIR = Path("data/cache/filings")
_CACHE_TTL = 24 * 3600  # 24시간


def _extract_section(markdown: str, item_pattern: str) -> str:
    """마크다운에서 ## Item X. 으로 시작하는 섹션 텍스트를 추출한다."""
    pattern = rf"^##\s*{item_pattern}.*$"
    match = re.search(pattern, markdown, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^## ", markdown[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(markdown)
    return markdown[start:end].strip()


class SECFilingParser:
    """SEC EDGAR에서 10-K/10-Q XBRL 재무 데이터를 추출한다."""

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.llm = llm

    async def parse(self, ticker: str) -> FilingFacts | None:
        """ticker에 대한 최신 10-K/10-Q 재무 데이터를 추출한다."""
        try:
            cik = await self._resolve_cik(ticker.upper())
            if cik is None:
                logger.warning("CIK not found for %s", ticker)
                return None

            raw = await self._fetch_companyfacts(cik)
            if raw is None:
                return None

            facts = self._build_filing_facts(ticker.upper(), raw)
            if facts and self.llm:
                await self._enrich_with_text(ticker.upper(), facts)
            return facts
        except Exception:
            logger.exception("SEC filing parse failed for %s", ticker)
            return None

    async def _resolve_cik(self, ticker: str) -> int | None:
        """ticker → CIK 변환."""
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(_CIK_LOOKUP_URL)
            resp.raise_for_status()
            data = resp.json()
        for entry in data.values():
            if entry["ticker"].upper() == ticker:
                return entry["cik_str"]
        return None

    async def _fetch_companyfacts(self, cik: int) -> dict | None:
        """companyfacts API 호출. 캐시 있으면 사용."""
        cache_path = _CACHE_DIR / f"sec_facts_{cik}.json"
        if cache_path.exists():
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime < _CACHE_TTL:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        url = _COMPANYFACTS_URL.format(cik=cik)
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def _build_filing_facts(self, ticker: str, raw: dict) -> FilingFacts | None:
        """companyfacts 응답에서 FilingFacts를 구성한다."""
        us_gaap = raw.get("facts", {}).get("us-gaap", {})

        latest_values: dict[str, float] = {}
        prev_values: dict[str, float] = {}
        filing_date = ""
        fiscal_period = ""

        for metric, chain in SEC_CONCEPT_CHAINS.items():
            for tag in chain:
                if tag not in us_gaap:
                    continue
                unit_key = "shares" if "Shares" in tag or "shares" in tag.lower() else "USD"
                entries = us_gaap[tag].get("units", {}).get(unit_key, [])
                annual = [e for e in entries if e.get("form") == "10-K" and e.get("fp") == "FY"]
                if not annual:
                    continue
                annual.sort(key=lambda e: e.get("filed", ""))
                latest = annual[-1]
                latest_values[metric] = float(latest["val"])
                if not filing_date or latest.get("filed", "") > filing_date:
                    filing_date = latest.get("filed", "")
                    fiscal_period = f"FY{latest.get('fy', '')}"
                if len(annual) >= 2:
                    prev_values[metric] = float(annual[-2]["val"])
                break

        if not latest_values:
            return None

        financials: dict[str, FinancialMetric] = {}
        for metric, val in latest_values.items():
            unit = "shares" if metric == "shares_outstanding" else "USD"
            financials[metric] = FinancialMetric(
                value=Decimal(str(val)),
                unit=unit,
                scale="billions" if abs(val) >= 1e9 else "millions",
                source="XBRL",
                confidence="high",
            )

        rev = latest_values.get("revenue")
        if rev and rev > 0:
            for margin_key, numerator_key in [
                ("gross_margin", "gross_profit"),
                ("operating_margin", "operating_income"),
                ("net_margin", "net_income"),
            ]:
                num = latest_values.get(numerator_key)
                if num is not None:
                    margin_pct = num / rev * 100
                    financials[margin_key] = FinancialMetric(
                        value=Decimal(str(round(margin_pct, 2))),
                        unit="percent",
                        scale="percent",
                        source="XBRL",
                        confidence="high",
                    )

        ocf = latest_values.get("operating_cash_flow")
        capex = latest_values.get("capex")
        if ocf is not None and capex is not None:
            fcf = ocf - capex
            financials["fcf"] = FinancialMetric(
                value=Decimal(str(fcf)),
                unit="USD",
                scale="billions" if abs(fcf) >= 1e9 else "millions",
                source="XBRL",
                confidence="high",
            )

        comparisons: dict[str, Comparison] = {}
        for metric, current in latest_values.items():
            prev = prev_values.get(metric)
            if prev and prev != 0:
                change = (current - prev) / abs(prev) * 100
                comparisons[f"{metric}_yoy"] = Comparison(
                    change_pct=round(change, 2),
                    previous=Decimal(str(prev)),
                    period=f"FY{int(fiscal_period[2:]) - 1}"
                    if fiscal_period.startswith("FY")
                    else "",
                )

        return FilingFacts(
            ticker=ticker,
            market="US",
            filing_type="10-K",
            filing_date=filing_date,
            fiscal_period=fiscal_period,
            source_url=_COMPANYFACTS_URL.format(cik=0),
            financials=financials,
            comparisons=comparisons,
            text_insights=[],
        )

    async def _enrich_with_text(self, ticker: str, facts: FilingFacts) -> None:
        """edgartools로 10-K 텍스트 추출 후 Guidance/Risk LLM 추출."""
        try:
            # TODO: Implement edgartools integration for 10-K markdown extraction
            # For now, add placeholder text insights to maintain structure
            from src.tools.filing.models import TextInsight

            # Placeholder implementation - would extract Item 7 and Item 1A in full version
            mock_item7_text = (
                "Revenue guidance and forward-looking statements would be extracted here."
            )
            mock_item1a_text = "Risk factors and uncertainties would be extracted here."

            facts.text_insights.extend(
                [
                    TextInsight(
                        section="Item 7 - Management Discussion",
                        extracted={"guidance_direction": None, "revenue_outlook": None},
                        additional=["Placeholder guidance extraction"],
                        raw_section=mock_item7_text,
                    ),
                    TextInsight(
                        section="Item 1A - Risk Factors",
                        extracted={"supply_chain_risk": None, "regulatory_risk": None},
                        additional=["Placeholder risk extraction"],
                        raw_section=mock_item1a_text,
                    ),
                ]
            )

        except Exception:
            logger.exception("Failed to enrich SEC filing with text insights for %s", ticker)
            # Graceful handling - text_insights remain empty
