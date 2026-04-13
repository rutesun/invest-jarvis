# src/tools/disclosure.py
"""
공시 데이터 툴: SEC EDGAR (미국주식) 및 DART (한국주식).
"""
import json
import re
import time
import httpx
from datetime import datetime, timedelta, date
from pathlib import Path
from pydantic import BaseModel


class DisclosureItem(BaseModel):
    """공시 1건 (SEC 8-K/10-Q 또는 DART 보고서)."""

    form_type: str    # "8-K", "10-Q", "DART"
    date: str         # "YYYY-MM-DD"
    description: str  # 공시 제목 또는 1차 문서명
    url: str          # 원문 링크
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
            entry["ticker"].upper(): entry["cik_str"]
            for entry in data.values()
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

        for form, date_str, doc, accession in zip(forms, filing_dates, documents, accessions):
            if form not in ("10-Q", "8-K"):
                continue
            if date.fromisoformat(date_str) < cutoff:
                continue

            accession_clean = accession.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}"
                f"/{accession_clean}/{doc}"
            )
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
        self.CACHE_PATH.write_text(
            json.dumps(mapping, ensure_ascii=False), encoding="utf-8"
        )
