# src/tools/filing/dart_parser.py
"""DART 공시 파싱: fnlttSinglAcntAll API (XBRL) + document.xml (텍스트)."""

import json
import logging
import re
import time
from decimal import Decimal
from pathlib import Path

import httpx
from langchain_core.language_models import BaseChatModel

from src.tools.filing.concepts import resolve_dart_metric
from src.tools.filing.models import (
    Comparison,
    FilingFacts,
    FinancialMetric,
)


logger = logging.getLogger(__name__)

_DART_API_BASE = "https://opendart.fss.or.kr/api"
_CACHE_DIR = Path("data/cache/filings")
_CACHE_TTL = 24 * 3600


def _extract_dart_section(xml_content: str, section_title: str) -> str:
    """DART XML에서 <TITLE> 태그 기반으로 섹션 텍스트를 추출한다."""
    pattern = rf"<TITLE[^>]*>[^<]*{re.escape(section_title)}[^<]*</TITLE>"
    match = re.search(pattern, xml_content, re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    next_title = re.search(r"<TITLE[^>]*>", xml_content[start:], re.IGNORECASE)
    end = start + next_title.start() if next_title else len(xml_content)
    raw = xml_content[start:end]
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class DARTFilingParser:
    """DART에서 사업보고서/분기보고서 재무 데이터를 추출한다."""

    def __init__(self, api_key: str, llm: BaseChatModel | None = None) -> None:
        self.api_key = api_key
        self.llm = llm

    async def parse(
        self,
        stock_code: str,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = "11011",
    ) -> FilingFacts | None:
        """DART XBRL 재무제표를 추출한다."""
        try:
            raw = await self._fetch_financials(corp_code, bsns_year, reprt_code)
            if raw is None:
                return None
            facts = self._build_filing_facts(stock_code, bsns_year, reprt_code, raw)
            if facts and self.llm:
                await self._enrich_with_text(corp_code, facts)
            return facts
        except Exception:
            logger.exception("DART filing parse failed for %s", stock_code)
            return None

    async def _fetch_financials(
        self, corp_code: str, bsns_year: str, reprt_code: str
    ) -> list[dict] | None:
        cache_path = _CACHE_DIR / f"dart_facts_{corp_code}_{bsns_year}_{reprt_code}.json"
        if cache_path.exists():
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime < _CACHE_TTL:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "CFS",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_DART_API_BASE}/fnlttSinglAcntAll.json", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "000":
            logger.warning("DART API error: %s", data.get("message"))
            return None

        items = data.get("list", [])
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return items

    def _build_filing_facts(
        self, stock_code: str, bsns_year: str, reprt_code: str, items: list[dict]
    ) -> FilingFacts | None:
        financials: dict[str, FinancialMetric] = {}
        comparisons: dict[str, Comparison] = {}
        seen_metrics: set[str] = set()

        for item in items:
            account_nm = item.get("account_nm", "")
            metric_key = resolve_dart_metric(account_nm)
            if not metric_key or metric_key in seen_metrics:
                continue
            seen_metrics.add(metric_key)

            current_str = item.get("thstrm_amount", "").replace(",", "")
            prev_str = item.get("frmtrm_amount", "").replace(",", "")

            if not current_str or not current_str.lstrip("-").isdigit():
                continue

            current = int(current_str)
            financials[metric_key] = FinancialMetric(
                value=Decimal(str(current)),
                unit="KRW",
                scale="billions" if abs(current) >= 1e12 else "millions",
                source="XBRL",
                confidence="high",
            )

            if prev_str and prev_str.lstrip("-").isdigit():
                prev = int(prev_str)
                if prev != 0:
                    change = (current - prev) / abs(prev) * 100
                    comparisons[f"{metric_key}_yoy"] = Comparison(
                        change_pct=round(change, 2),
                        previous=Decimal(str(prev)),
                        period=f"FY{int(bsns_year) - 1}",
                    )

        if not financials:
            return None

        rev = financials.get("revenue")
        if rev and float(rev.value) > 0:
            rev_val = float(rev.value)
            for margin_key, num_key in [
                ("gross_margin", "gross_profit"),
                ("operating_margin", "operating_income"),
                ("net_margin", "net_income"),
            ]:
                num = financials.get(num_key)
                if num:
                    margin_pct = float(num.value) / rev_val * 100
                    financials[margin_key] = FinancialMetric(
                        value=Decimal(str(round(margin_pct, 2))),
                        unit="percent",
                        scale="percent",
                        source="XBRL",
                        confidence="high",
                    )

        ocf = financials.get("operating_cash_flow")
        capex = financials.get("capex")
        if ocf and capex:
            fcf = float(ocf.value) - float(capex.value)
            financials["fcf"] = FinancialMetric(
                value=Decimal(str(int(fcf))),
                unit="KRW",
                scale="billions" if abs(fcf) >= 1e12 else "millions",
                source="XBRL",
                confidence="high",
            )

        report_type_map = {"11011": "사업보고서", "11014": "분기보고서", "11012": "반기보고서"}

        return FilingFacts(
            ticker=stock_code,
            market="KR",
            filing_type=report_type_map.get(reprt_code, "사업보고서"),
            filing_date="",
            fiscal_period=f"FY{bsns_year}",
            source_url=f"{_DART_API_BASE}/fnlttSinglAcntAll.json",
            financials=financials,
            comparisons=comparisons,
            text_insights=[],
        )

    async def _enrich_with_text(self, corp_code: str, facts: FilingFacts) -> None:
        """document.xml에서 4개 사업 섹션 텍스트 추출."""
        try:
            # TODO: Implement document.xml download and parsing
            # For now, add placeholder text insights to maintain structure
            from src.tools.filing.models import TextInsight

            # 4개 사업 섹션 placeholder implementations
            business_sections = [
                {
                    "section": "주요 제품 및 서비스",
                    "extracted": {"매출비중": None, "비중변화": None, "신규": None},
                    "additional": ["Placeholder product/service analysis"],
                    "raw_section": "주요 제품 및 서비스 원문이 여기에 추출됩니다.",
                },
                {
                    "section": "원재료 및 생산설비",
                    "extracted": {
                        "원재료가격": None,
                        "가동률": None,
                        "증설계획": None,
                        "CAPEX": None,
                    },
                    "additional": ["Placeholder raw materials analysis"],
                    "raw_section": "원재료 및 생산설비 원문이 여기에 추출됩니다.",
                },
                {
                    "section": "매출 및 수주상황",
                    "extracted": {
                        "수주잔고": None,
                        "수주증감률": None,
                        "수주추이": None,
                        "주요고객": None,
                    },
                    "additional": ["Placeholder sales/orders analysis"],
                    "raw_section": "매출 및 수주상황 원문이 여기에 추출됩니다.",
                },
                {
                    "section": "주요계약 및 연구개발활동",
                    "extracted": {"대형계약": None, "R&D투자": None, "핵심테마": None},
                    "additional": ["Placeholder R&D analysis"],
                    "raw_section": "주요계약 및 연구개발활동 원문이 여기에 추출됩니다.",
                },
            ]

            for section_data in business_sections:
                facts.text_insights.append(TextInsight(**section_data))

        except Exception:
            logger.exception(
                "Failed to enrich DART filing with text insights for corp %s", corp_code
            )
            # Graceful handling - text_insights remain empty
