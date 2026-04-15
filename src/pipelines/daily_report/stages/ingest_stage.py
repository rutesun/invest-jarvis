"""Ingest stage: 텔레그램 메시지 및 매크로 데이터 로드."""
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import List
from dotenv import load_dotenv
import yfinance as yf

# 환경변수 로드
load_dotenv()
from src.pipelines.daily_report.models import (
    IngestResult,
    MacroSnapshot,
    TelegramMessage,
)
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


def _fetch_macro(date: str) -> MacroSnapshot:
    """주어진 날짜의 매크로 지표 수집."""
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    prev_date = date_obj - timedelta(days=1)

    # 미국 시장 (전날 종가)
    us_tickers = {"S&P500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI"}
    us_markets = {}
    for name, ticker in us_tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                pct_change = (
                    (data["Close"].iloc[-1] - data["Close"].iloc[-2])
                    / data["Close"].iloc[-2]
                    * 100
                )
                us_markets[name] = round(pct_change, 2)
            else:
                us_markets[name] = 0.0
        except Exception:
            us_markets[name] = 0.0

    # 한국 시장 (당일 종가)
    kr_tickers = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    kr_markets = {}
    for name, ticker in kr_tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                pct_change = (
                    (data["Close"].iloc[-1] - data["Close"].iloc[-2])
                    / data["Close"].iloc[-2]
                    * 100
                )
                kr_markets[name] = round(pct_change, 2)
            else:
                kr_markets[name] = 0.0
        except Exception:
            kr_markets[name] = 0.0

    # VIX
    try:
        vix_data = yf.Ticker("^VIX").history(period="1d")
        vix = round(vix_data["Close"].iloc[-1], 1) if len(vix_data) > 0 else 0.0
    except Exception:
        vix = 0.0

    # Fear & Greed (간단한 계산: VIX 기반 추정)
    # VIX < 15: Greed, VIX 15-25: Neutral, VIX > 25: Fear
    try:
        if vix < 15:
            fear_greed = 70  # Greed
        elif vix < 25:
            fear_greed = 50  # Neutral
        else:
            fear_greed = 30  # Fear
    except Exception:
        fear_greed = 50

    # KRW/USD (yfinance KRW=X 사용)
    try:
        krw_data = yf.Ticker("KRW=X").history(period="1d")
        krw_usd = round(krw_data["Close"].iloc[-1], 1) if len(krw_data) > 0 else 1320.0
    except Exception:
        krw_usd = 1320.0

    return MacroSnapshot(
        date=date,
        us_markets=us_markets,
        kr_markets=kr_markets,
        vix=vix,
        fear_greed=fear_greed,
        krw_usd=krw_usd,
    )


def _load_telegram_csvs(date: str, data_dir: str) -> List[TelegramMessage]:
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

        with open(csv_file, "r", encoding="utf-8") as f:
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
    import sys
    import json

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
