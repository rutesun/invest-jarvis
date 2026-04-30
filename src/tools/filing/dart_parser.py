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
        """DART XBRL 재무제표를 다중 소스에서 추출하여 최적 데이터 선택."""
        try:
            # 1. 다중 소스에서 데이터 수집
            all_datasets = await self._collect_multi_source_data(corp_code, bsns_year, reprt_code)

            if not all_datasets:
                logger.warning(f"No DART data found for {stock_code} ({corp_code})")
                return None

            # 2. 최적 데이터셋 선택
            best_dataset = self._select_best_dataset(all_datasets)

            if not best_dataset:
                logger.warning(f"No valid dataset found for {stock_code}")
                return None

            # 3. FilingFacts 구성
            facts = self._build_filing_facts_enhanced(stock_code, best_dataset)

            # 4. 텍스트 인사이트 추가 (선택)
            if facts and self.llm:
                await self._enrich_with_text(corp_code, facts)

            return facts

        except Exception:
            logger.exception("DART filing parse failed for %s", stock_code)
            return None

    async def _fetch_financials(
        self, corp_code: str, bsns_year: str, reprt_code: str
    ) -> list[dict] | None:
        """Legacy method for backward compatibility - uses CFS by default."""
        return await self._fetch_dart_data(corp_code, bsns_year, reprt_code, "CFS")

    async def _collect_multi_source_data(
        self, corp_code: str, bsns_year: str, reprt_code: str
    ) -> list[dict]:
        """다중 소스에서 DART 데이터 수집 및 검증."""

        data_sources = []

        # 수집할 데이터 소스들 (우선순위 순)
        collection_targets = [
            # 기본 요청 (연결/별도)
            {"fs_div": "CFS", "priority": 1, "desc": f"FY{bsns_year} 연결"},
            {"fs_div": "OFS", "priority": 2, "desc": f"FY{bsns_year} 별도"},
        ]

        # 연간 보고서인 경우 분기 데이터도 시도
        if reprt_code == "11011":  # 사업보고서
            collection_targets.extend(
                [
                    {"fs_div": "CFS", "priority": 3, "desc": f"FY{int(bsns_year) - 1} 연결 (전년)"},
                    {"fs_div": "OFS", "priority": 4, "desc": f"FY{int(bsns_year) - 1} 별도 (전년)"},
                ]
            )

        for target in collection_targets:
            try:
                raw_data = await self._fetch_dart_data(
                    corp_code=corp_code,
                    bsns_year=bsns_year if target["priority"] <= 2 else str(int(bsns_year) - 1),
                    reprt_code=reprt_code,
                    fs_div=target["fs_div"],
                )

                if raw_data:
                    # 메타데이터 추가
                    dataset = {
                        "data": raw_data,
                        "metadata": {
                            "year": bsns_year
                            if target["priority"] <= 2
                            else str(int(bsns_year) - 1),
                            "report_type": reprt_code,
                            "fs_type": target["fs_div"],
                            "priority": target["priority"],
                            "description": target["desc"],
                        },
                    }

                    # 기본 유효성 검사
                    if self._validate_dataset(dataset):
                        data_sources.append(dataset)
                        logger.info(f"✅ Collected: {target['desc']} ({len(raw_data)} items)")
                    else:
                        logger.warning(f"❌ Invalid: {target['desc']}")

            except Exception as e:
                logger.warning(f"Failed to collect {target['desc']}: {e}")

        logger.info(f"Total datasets collected: {len(data_sources)}")
        return data_sources

    async def _fetch_dart_data(
        self, corp_code: str, bsns_year: str, reprt_code: str, fs_div: str
    ) -> list[dict] | None:
        """DART API 호출 (개선된 캐시 지원)."""

        cache_key = f"dart_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}"
        cache_path = _CACHE_DIR / f"{cache_key}.json"

        # 캐시 확인
        if cache_path.exists():
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime < _CACHE_TTL:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        # API 호출
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_DART_API_BASE}/fnlttSinglAcntAll.json", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "000":
            return None

        items = data.get("list", [])

        # 캐시 저장
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

        return items

    def _validate_dataset(self, dataset: dict) -> bool:
        """데이터셋 기본 유효성 검증."""

        data = dataset["data"]
        if not data or len(data) < 5:  # 최소 5개 항목 필요
            return False

        # 매출액 확인 (영업수익 포함)
        revenue_items = [
            item
            for item in data
            if any(keyword in item.get("account_nm", "") for keyword in ["매출", "영업수익"])
        ]
        if not revenue_items:
            return False

        # 숫자 데이터 확인
        valid_numbers = 0
        for item in data[:20]:  # 처음 20개만 체크
            amount = item.get("thstrm_amount", "").replace(",", "")
            if amount and amount.lstrip("-").isdigit():
                valid_numbers += 1

        return valid_numbers >= 5  # 최소 5개 유효한 숫자 필요

    def _select_best_dataset(self, all_datasets: list[dict]) -> dict | None:
        """최적 데이터셋 선택 로직."""

        if not all_datasets:
            return None

        # 각 데이터셋 점수 계산
        scored_datasets = []

        for dataset in all_datasets:
            score = self._calculate_dataset_score(dataset)
            scored_datasets.append((score, dataset))

        # 점수 순으로 정렬
        scored_datasets.sort(key=lambda x: x[0], reverse=True)

        # 최고 점수 데이터셋 선택
        best_score, best_dataset = scored_datasets[0]

        logger.info(
            f"Selected dataset: {best_dataset['metadata']['description']} (score: {best_score:.2f})"
        )

        return best_dataset

    def _calculate_dataset_score(self, dataset: dict) -> float:
        """데이터셋 품질 점수 계산."""

        score = 0.0
        data = dataset["data"]
        metadata = dataset["metadata"]

        # 1. 우선순위 점수 (40점)
        priority_score = max(0, 5 - metadata["priority"]) * 8
        score += priority_score

        # 2. 데이터 완성도 (30점)
        key_accounts = ["매출액", "영업수익", "영업이익", "당기순이익", "자산총계"]
        found_accounts = sum(
            1 for acc in key_accounts if any(acc in item.get("account_nm", "") for item in data)
        )
        completeness_score = (found_accounts / len(key_accounts)) * 30
        score += completeness_score

        # 3. 매출액 합리성 (20점)
        revenue_score = self._evaluate_revenue_reasonableness(data)
        score += revenue_score

        # 4. 데이터 신선도 (10점) - 더 보수적
        year = int(metadata["year"])
        freshness_score = max(0, min((year - 2020) * 2, 10))
        score += freshness_score

        return score

    def _evaluate_revenue_reasonableness(self, data: list[dict]) -> float:
        """매출액 합리성 평가."""

        # 매출액 또는 영업수익 검색
        revenue_items = [item for item in data if item.get("account_nm") in ["매출액", "영업수익"]]

        if not revenue_items:
            return 0.0

        for item in revenue_items:
            amount_str = item.get("thstrm_amount", "").replace(",", "")
            if amount_str and amount_str.lstrip("-").isdigit():
                amount = int(amount_str)
                amount_billions = amount / 100_000_000  # 억원 단위

                # 매출액 합리성 체크 (대략적 범위)
                if 100 <= amount_billions <= 5_000_000:  # 100억~500조 범위 (더 넓게)
                    return 20.0

        return 5.0  # 부분 점수

    def _build_filing_facts_enhanced(
        self, stock_code: str, best_dataset: dict
    ) -> FilingFacts | None:
        """향상된 FilingFacts 구성."""

        data = best_dataset["data"]
        metadata = best_dataset["metadata"]

        financials: dict[str, FinancialMetric] = {}
        comparisons: dict[str, Comparison] = {}
        seen_metrics: set[str] = set()

        for item in data:
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

            # Confidence 조정 (데이터 품질 기반)
            confidence = "high" if metadata["priority"] <= 2 else "medium"

            financials[metric_key] = FinancialMetric(
                value=Decimal(str(current)),
                unit="KRW",
                scale="billions" if abs(current) >= 1e12 else "millions",
                source="XBRL",
                confidence=confidence,
            )

            # YoY 비교
            if prev_str and prev_str.lstrip("-").isdigit():
                prev = int(prev_str)
                if prev != 0:
                    change = (current - prev) / abs(prev) * 100
                    comparisons[f"{metric_key}_yoy"] = Comparison(
                        change_pct=round(change, 2),
                        previous=Decimal(str(prev)),
                        period=f"FY{int(metadata['year']) - 1}",
                    )

        if not financials:
            return None

        # 마진 계산
        self._calculate_margins(financials)

        # FCF 계산
        self._calculate_fcf(financials)

        # Report type 결정
        report_type_map = {"11011": "사업보고서", "11014": "3분기보고서", "11012": "반기보고서"}

        return FilingFacts(
            ticker=stock_code,
            market="KR",
            filing_type=report_type_map.get(metadata["report_type"], "사업보고서"),
            filing_date="",
            fiscal_period=f"FY{metadata['year']}",
            source_url=f"{_DART_API_BASE}/fnlttSinglAcntAll.json",
            financials=financials,
            comparisons=comparisons,
            text_insights=[],
        )

    def _calculate_margins(self, financials: dict[str, FinancialMetric]) -> None:
        """마진 계산."""

        rev = financials.get("revenue")
        if not rev or float(rev.value) <= 0:
            return

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

    def _calculate_fcf(self, financials: dict[str, FinancialMetric]) -> None:
        """FCF 계산."""

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
