# src/tools/disclosure.py
"""
공시 데이터 툴: SEC EDGAR (미국주식) 및 DART (한국주식).
"""
import re
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
