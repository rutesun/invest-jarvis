"""Ingest stage: 텔레그램 메시지 및 매크로 데이터 로드."""

import csv
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import fear_and_greed
import yfinance as yf
from dotenv import load_dotenv
from langsmith import traceable

from src.pipelines.daily_report.config import MACRO_MAX_RETRIES


# 환경변수 로드
load_dotenv()
from src.pipelines.daily_report.models import (
    IngestResult,
    MacroSnapshot,
    TelegramMessage,
)


logger = logging.getLogger(__name__)


@traceable(name="Ingest Stage")
def ingest(date: str, data_dir: str = "data") -> IngestResult:
    """
    주어진 날짜의 텔레그램 메시지와 매크로 데이터 로드.

    Args:
        date: 날짜 문자열 (YYYY-MM-DD)
        data_dir: 루트 데이터 디렉토리

    Returns:
        매크로 및 메시지가 포함된 IngestResult

    Raises:
        FileNotFoundError: 해당 날짜의 CSV 파일이 없을 때
    """
    macro = _fetch_macro(date)
    messages = _load_telegram_csvs(date, data_dir)

    if not messages:
        raise FileNotFoundError(
            f"{date}의 텔레그램 메시지를 찾을 수 없습니다. "
            f"실행: uv run jarvis telegram fetch {date}"
        )

    return IngestResult(date=date, macro=macro, messages=messages)


def _fetch_with_retry(
    fn: Callable[[], Any],
    label: str,
    max_retries: int = MACRO_MAX_RETRIES,
) -> Any | None:
    """매크로 데이터 수집 공통 리트라이 (exponential backoff). 모두 실패 시 None 반환."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            logger.warning(
                "%s fetch failed (attempt %d/%d): %s", label, attempt + 1, max_retries, e
            )
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
    return None


def _fetch_fear_greed() -> int | None:
    """CNN Fear & Greed Index 조회. 실패 시 None."""
    result = _fetch_with_retry(fear_and_greed.get, "Fear & Greed")
    if result is None:
        return None
    return round(result.value)


def _fetch_macro(date: str) -> MacroSnapshot:
    """주어진 날짜의 매크로 지표 수집."""

    def _get_pct_change(ticker: str) -> float:
        data = yf.Ticker(ticker).history(period="2d")
        if len(data) < 2:
            raise ValueError(f"{ticker}: insufficient data ({len(data)} rows)")
        return round(
            (data["Close"].iloc[-1] - data["Close"].iloc[-2]) / data["Close"].iloc[-2] * 100, 2
        )

    # 미국 시장
    us_tickers = {"S&P500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI"}
    us_markets = {}
    for name, symbol in us_tickers.items():
        result = _fetch_with_retry(lambda s=symbol: _get_pct_change(s), f"US:{name}")
        us_markets[name] = result if result is not None else 0.0

    # 한국 시장
    kr_tickers = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    kr_markets = {}
    for name, symbol in kr_tickers.items():
        result = _fetch_with_retry(lambda s=symbol: _get_pct_change(s), f"KR:{name}")
        kr_markets[name] = result if result is not None else 0.0

    # VIX
    def _get_vix() -> float:
        data = yf.Ticker("^VIX").history(period="1d")
        if len(data) == 0:
            raise ValueError("VIX: no data returned")
        return round(data["Close"].iloc[-1], 1)

    vix = _fetch_with_retry(_get_vix, "VIX")
    if vix is None:
        vix = 0.0

    # Fear & Greed (CNN)
    fg = _fetch_fear_greed()
    if fg is None:
        fg = 50

    # KRW/USD
    def _get_krw_usd() -> float:
        data = yf.Ticker("KRW=X").history(period="1d")
        if len(data) == 0:
            raise ValueError("KRW/USD: no data returned")
        return round(data["Close"].iloc[-1], 1)

    krw_usd = _fetch_with_retry(_get_krw_usd, "KRW/USD")
    if krw_usd is None:
        krw_usd = 0.0

    return MacroSnapshot(
        date=date,
        us_markets=us_markets,
        kr_markets=kr_markets,
        vix=vix,
        fear_greed=fg,
        krw_usd=krw_usd,
    )


def _load_telegram_csvs(date: str, data_dir: str) -> list[TelegramMessage]:
    """주어진 날짜의 모든 텔레그램 CSV 로드."""
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    year_month = date_obj.strftime("%Y-%m")
    csv_dir = Path(data_dir) / year_month

    if not csv_dir.exists():
        return []

    # 날짜 패턴과 일치하는 모든 CSV 찾기
    pattern = f"{date}-*.csv"
    csv_files = list(csv_dir.glob(pattern))

    messages = []
    for csv_file in csv_files:
        # 파일명에서 channel_id 추출 (예: "2026-04-14-shinhanresearch.csv")
        channel_id = csv_file.stem.split("-", 3)[-1]

        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # content가 비어있으면 스킵
                if not row.get("content"):
                    continue
                messages.append(
                    TelegramMessage(
                        channel_id=channel_id,
                        message_id=row["message_id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        text=row["content"],
                    )
                )

    return messages


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import json
    import sys

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"
    result = ingest(date)

    print(f"✓ {len(result.messages)}개 메시지 로드")
    print(f"✓ 매크로: VIX={result.macro.vix}, F&G={result.macro.fear_greed}")
    print(f"✓ 미국 시장: {result.macro.us_markets}")
    print(f"✓ 한국 시장: {result.macro.kr_markets}")

    # 다음 stage 테스트용으로 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/ingest_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
