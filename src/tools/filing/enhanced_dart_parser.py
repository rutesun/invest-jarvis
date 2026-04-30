# src/tools/filing/enhanced_dart_parser.py
"""Enhanced DART 파서 - 정확도 개선 및 다중 소스 지원"""

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel

from src.tools.filing.concepts import resolve_dart_metric
from src.tools.filing.models import (
    Comparison,
    FilingFacts,
    FinancialMetric,
    TextInsight,
)


logger = logging.getLogger(__name__)

_DART_API_BASE = "https://opendart.fss.or.kr/api"
_CACHE_DIR = Path("data/cache/filings")
_CACHE_TTL = 24 * 3600


class EnhancedDARTParser:
    """Enhanced DART 파서 - 정확도 및 신뢰성 향상"""

    def __init__(self, api_key: str, llm: BaseChatModel | None = None) -> None:
        self.api_key = api_key
        self.llm = llm

    async def parse(self, stock_code: str, corp_code: str) -> FilingFacts | None:
        """Enhanced DART 파싱 - 다중 소스 및 검증 로직"""
        try:
            # 1. 다중 소스에서 데이터 수집
            all_data = await self._collect_multi_source_data(corp_code)

            if not all_data:
                logger.warning(f"No DART data found for {stock_code} ({corp_code})")
                return None

            # 2. 최적 데이터셋 선택 및 검증
            best_data = self._select_best_dataset(all_data)

            if not best_data:
                logger.warning(f"No valid dataset found for {stock_code}")
                return None

            # 3. FilingFacts 구성
            facts = self._build_enhanced_filing_facts(stock_code, best_data)

            # 4. 텍스트 인사이트 추가 (선택)
            if facts and self.llm:
                await self._enrich_with_text(corp_code, facts)

            return facts

        except Exception:
            logger.exception(f"Enhanced DART parsing failed for {stock_code}")
            return None

    async def _collect_multi_source_data(self, corp_code: str) -> list[dict[str, Any]]:
        """다중 소스에서 DART 데이터 수집"""

        data_sources = []

        # 수집할 데이터 소스들 (우선순위 순)
        collection_targets = [
            # 연간 데이터
            {
                "year": "2024",
                "reprt": "11011",
                "fs": "OFS",
                "priority": 1,
                "desc": "2024 별도 연간",
            },
            {
                "year": "2024",
                "reprt": "11011",
                "fs": "CFS",
                "priority": 2,
                "desc": "2024 연결 연간",
            },
            {
                "year": "2023",
                "reprt": "11011",
                "fs": "OFS",
                "priority": 3,
                "desc": "2023 별도 연간",
            },
            {
                "year": "2023",
                "reprt": "11011",
                "fs": "CFS",
                "priority": 4,
                "desc": "2023 연결 연간",
            },
            # 분기 데이터 (최신)
            {"year": "2025", "reprt": "11014", "fs": "OFS", "priority": 5, "desc": "2025Q3 별도"},
            {"year": "2025", "reprt": "11014", "fs": "CFS", "priority": 6, "desc": "2025Q3 연결"},
            {"year": "2024", "reprt": "11014", "fs": "OFS", "priority": 7, "desc": "2024Q3 별도"},
        ]

        for target in collection_targets:
            try:
                raw_data = await self._fetch_dart_data(
                    corp_code=corp_code,
                    bsns_year=target["year"],
                    reprt_code=target["reprt"],
                    fs_div=target["fs"],
                )

                if raw_data:
                    # 메타데이터 추가
                    dataset = {
                        "data": raw_data,
                        "metadata": {
                            "year": target["year"],
                            "report_type": target["reprt"],
                            "fs_type": target["fs"],
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
        """DART API 호출 (캐시 지원)"""

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

    def _validate_dataset(self, dataset: dict[str, Any]) -> bool:
        """데이터셋 기본 유효성 검증"""

        data = dataset["data"]
        if not data or len(data) < 5:  # 최소 5개 항목 필요
            return False

        # 매출액 확인
        revenue_items = [item for item in data if "매출" in item.get("account_nm", "")]
        if not revenue_items:
            return False

        # 숫자 데이터 확인
        valid_numbers = 0
        for item in data[:20]:  # 처음 20개만 체크
            amount = item.get("thstrm_amount", "").replace(",", "")
            if amount and amount.lstrip("-").isdigit():
                valid_numbers += 1

        return valid_numbers >= 5  # 최소 5개 유효한 숫자 필요

    def _select_best_dataset(self, all_datasets: list[dict[str, Any]]) -> dict[str, Any] | None:
        """최적 데이터셋 선택 로직"""

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

    def _calculate_dataset_score(self, dataset: dict[str, Any]) -> float:
        """데이터셋 품질 점수 계산"""

        score = 0.0
        data = dataset["data"]
        metadata = dataset["metadata"]

        # 1. 우선순위 점수 (40점)
        priority_score = max(0, 10 - metadata["priority"]) * 4
        score += priority_score

        # 2. 데이터 완성도 (30점)
        key_accounts = ["매출액", "영업이익", "당기순이익", "자산총계"]
        found_accounts = sum(
            1 for acc in key_accounts if any(acc in item.get("account_nm", "") for item in data)
        )
        completeness_score = (found_accounts / len(key_accounts)) * 30
        score += completeness_score

        # 3. 매출액 합리성 (20점)
        revenue_score = self._evaluate_revenue_reasonableness(data)
        score += revenue_score

        # 4. 데이터 신선도 (10점)
        year = int(metadata["year"])
        freshness_score = max(0, (year - 2020) * 2)  # 2021년부터 2점씩
        score += min(freshness_score, 10)

        return score

    def _evaluate_revenue_reasonableness(self, data: list[dict]) -> float:
        """매출액 합리성 평가"""

        revenue_items = [item for item in data if item.get("account_nm") == "매출액"]

        if not revenue_items:
            return 0.0

        for item in revenue_items:
            amount_str = item.get("thstrm_amount", "").replace(",", "")
            if amount_str and amount_str.lstrip("-").isdigit():
                amount = int(amount_str)
                amount_billions = amount / 100_000_000  # 억원 단위

                # 매출액 합리성 체크 (대략적 범위)
                if 10_000 <= amount_billions <= 2_000_000:  # 100억~2천조 범위
                    return 20.0

        return 5.0  # 부분 점수

    def _build_enhanced_filing_facts(
        self, stock_code: str, best_dataset: dict[str, Any]
    ) -> FilingFacts | None:
        """향상된 FilingFacts 구성"""

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
        """마진 계산"""

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
        """FCF 계산"""

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

    async def _enrich_with_text(self, corp_code: str, facts: FilingFacts) -> None:
        """텍스트 인사이트 추가 (placeholder)"""

        # Placeholder - 실제로는 document.xml 파싱 필요
        placeholder_insights = [
            TextInsight(
                section="주요 제품 및 서비스",
                extracted={"매출비중": None},
                additional=["Enhanced parsing - placeholder"],
                raw_section="Enhanced text extraction placeholder",
            )
        ]

        facts.text_insights.extend(placeholder_insights)
