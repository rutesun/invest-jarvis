# src/tools/disclosure.py
"""
공시 데이터 툴: SEC EDGAR (미국주식) 및 DART (한국주식).
"""

import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import BaseModel

from src.core.models import ToolResult


class DisclosureItem(BaseModel):
    """공시 1건 (SEC 8-K/10-Q 또는 DART 보고서)."""

    form_type: str  # "8-K", "10-Q", "DART"
    date: str  # "YYYY-MM-DD"
    description: str  # 공시 제목 또는 1차 문서명
    url: str  # 원문 링크
    score: float = 1.0  # 관련도 점수 (DART 키워드 스코어링)


def is_korean_ticker(ticker: str) -> bool:
    """한국주식 여부 판별 (.KS/.KQ 접미사 또는 6자리 숫자)."""
    if re.search(r"\.(KS|KQ)$", ticker, re.IGNORECASE):
        return True
    return bool(re.match(r"^\d{6}$", ticker))


def extract_kr_code(ticker: str) -> str:
    """한국 티커 문자열에서 6자리 KRX 종목코드 추출."""
    cleaned = re.sub(r"\.(KS|KQ)$", "", ticker, flags=re.IGNORECASE)
    return cleaned.zfill(6)


_SEC_USER_AGENT = "invest-jarvis research@example.com"


class SECDisclosureFetcher:
    """미국주식 SEC EDGAR에서 10-Q, 8-K 공시를 조회한다."""

    CIK_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSION_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
    CACHE_PATH = Path("data/cache/sec_cik_cache.json")
    CACHE_TTL = 6 * 3600  # 6시간

    async def fetch(self, ticker: str) -> list[DisclosureItem]:
        """미국 티커에 대한 최근 10-Q/8-K 최대 5건을 반환한다."""
        cik = await self._get_cik(ticker.upper())
        if cik is None:
            return []
        return await self._get_filings(cik)

    async def _get_cik(self, ticker: str) -> int | None:
        cache = self._load_cache()
        if ticker in cache:
            return cache[ticker]

        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(self.CIK_URL)
            resp.raise_for_status()
            data = resp.json()

        mapping: dict[str, int] = {
            entry["ticker"].upper(): entry["cik_str"] for entry in data.values()
        }
        self._save_cache(mapping)
        return mapping.get(ticker)

    async def _get_filings(self, cik: int) -> list[DisclosureItem]:
        url = self.SUBMISSION_URL.format(cik=cik)
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        documents = recent.get("primaryDocument", [])
        accessions = recent.get("accessionNumber", [])

        cutoff = (datetime.now() - timedelta(days=90)).date()
        results: list[DisclosureItem] = []

        for form, date_str, doc, accession in zip(
            forms, filing_dates, documents, accessions, strict=False
        ):
            if form not in ("10-Q", "8-K"):
                continue
            if date.fromisoformat(date_str) < cutoff:
                continue

            accession_clean = accession.replace("-", "")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{doc}"
            results.append(
                DisclosureItem(
                    form_type=form,
                    date=date_str,
                    description=doc,
                    url=filing_url,
                )
            )
            if len(results) >= 5:
                break

        return results

    def _load_cache(self) -> dict[str, int]:
        if not self.CACHE_PATH.exists():
            return {}
        try:
            mtime = self.CACHE_PATH.stat().st_mtime
            if time.time() - mtime > self.CACHE_TTL:
                return {}
            return json.loads(self.CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self, mapping: dict[str, int]) -> None:
        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.CACHE_PATH.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")


_DART_API_BASE = "https://opendart.fss.or.kr/api"

# DART 보고서명 키워드 가중치 테이블
_DART_KEYWORD_WEIGHTS: dict[str, float] = {
    # 고신호 이벤트: 각 키워드 +1.0
    "계약": 1.0,
    "수주": 1.0,
    "실적": 1.0,
    "매출": 1.0,
    "영업이익": 1.0,
    "투자": 1.0,
    "유상증자": 1.0,
    "자기주식": 1.0,
    "소송": 1.0,
    "내부자매도": 1.0,
    # 정기 보고서 (저신호): -1.0
    "사업보고서": -1.0,
    "분기보고서": -1.0,
    "반기보고서": -1.0,
    # 금액 단위 포함 시 소폭 가산
    "조": 0.5,
    "억원": 0.5,
}

_DART_SCORE_THRESHOLD = 1.0
_DART_MAX_RESULTS = 5


def _score_dart_report(report_nm: str) -> float:
    """DART 보고서명으로 관련도 점수 계산."""
    score = 0.0
    for keyword, weight in _DART_KEYWORD_WEIGHTS.items():
        if keyword in report_nm:
            score += weight
    return score


def _fmt_dart_date(rcept_dt: str) -> str:
    """DART 날짜 형식 YYYYMMDD → YYYY-MM-DD 변환."""
    if len(rcept_dt) == 8:
        return f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}"
    return rcept_dt


class DARTDisclosureFetcher:
    """OpenDART API로 한국주식 공시를 키워드 필터링하여 조회한다.

    corp_code 조회 결과는 파일 캐시(6시간 TTL)에 저장해
    같은 종목을 반복 분석할 때 불필요한 API 호출을 방지한다.
    """

    CACHE_PATH = Path("data/cache/dart_corp_code_cache.json")
    CACHE_TTL = 6 * 3600  # 6시간

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def fetch(self, stock_code: str) -> list[DisclosureItem]:
        """6자리 KRX 종목코드로 최근 3개월 스코어링된 공시 최대 5건을 반환한다."""
        corp_code = await self._get_corp_code(stock_code)
        if corp_code is None:
            return []

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bgn_de": start_date,
            "end_de": end_date,
            "page_count": 20,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_DART_API_BASE}/list.json", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "000":
            return []

        scored: list[tuple[float, DisclosureItem]] = []
        for item in data.get("list", []):
            report_nm = item.get("report_nm", "")
            score = _score_dart_report(report_nm)
            if score < _DART_SCORE_THRESHOLD:
                continue
            rcp_no = item.get("rcp_no", "")
            disclosure = DisclosureItem(
                form_type="DART",
                date=_fmt_dart_date(item.get("rcept_dt", "")),
                description=report_nm,
                url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}",
                score=score,
            )
            scored.append((score, disclosure))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:_DART_MAX_RESULTS]]

    async def _get_corp_code(self, stock_code: str) -> str | None:
        """KRX 종목코드로 DART 내부 corp_code를 조회한다. 결과를 파일 캐시에 저장한다."""
        # 캐시 확인
        cache = self._load_cache()
        if stock_code in cache:
            return cache[stock_code]

        params = {"crtfc_key": self.api_key, "stock_code": stock_code}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_DART_API_BASE}/company.json", params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("status") != "000":
                return None
            corp_code = data.get("corp_code")

        if corp_code:
            cache[stock_code] = corp_code
            self._save_cache(cache)

        return corp_code

    def _load_cache(self) -> dict[str, str]:
        if not self.CACHE_PATH.exists():
            return {}
        try:
            mtime = self.CACHE_PATH.stat().st_mtime
            if time.time() - mtime > self.CACHE_TTL:
                return {}
            return json.loads(self.CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self, mapping: dict[str, str]) -> None:
        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.CACHE_PATH.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")


class DisclosureTool:
    """티커 형식에 따라 SEC(미국) 또는 DART(한국)로 공시 조회를 라우팅한다."""

    def __init__(
        self,
        sec_fetcher: SECDisclosureFetcher,
        dart_fetcher: DARTDisclosureFetcher | None = None,
    ) -> None:
        self.sec_fetcher = sec_fetcher
        self.dart_fetcher = dart_fetcher

    async def execute(self, ticker: str) -> ToolResult:
        """주어진 티커의 공시를 조회한다. ToolResult[list[DisclosureItem]] 반환."""
        try:
            if is_korean_ticker(ticker):
                if self.dart_fetcher is None:
                    return ToolResult(
                        success=False,
                        data=None,
                        error="DART 페처 미설정 — OPENDART_API_KEY를 환경변수에 추가하세요",
                    )
                code = extract_kr_code(ticker)
                items = await self.dart_fetcher.fetch(code)
            else:
                items = await self.sec_fetcher.fetch(ticker)
            return ToolResult(success=True, data=items)
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))
