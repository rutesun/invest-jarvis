"""playbook.yaml 보유 종목·워치리스트 및 계좌 설정 로더 (Plan 8 + brief)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.tools.disclosure import is_korean_ticker

logger = logging.getLogger(__name__)


@dataclass
class HoldingEntry:
    """보유 종목 단일 항목."""

    ticker: str
    quantity: int
    avg_price: float
    stop_price: float | None
    currency: str  # "KRW" | "USD"


@dataclass
class WatchEntry:
    """워치리스트 단일 항목 (관심 = 티커만 필수)."""

    ticker: str
    note: str | None
    currency: str  # "KRW" | "USD"


@dataclass
class HoldingsConfig:
    """playbook.yaml 전체 설정."""

    krw_capital: float | None
    krw_risk_pct: float | None
    usd_capital: float | None
    usd_risk_pct: float | None
    holdings: list[HoldingEntry] = field(default_factory=list)
    watchlist: list[WatchEntry] = field(default_factory=list)

    def find(self, ticker: str) -> HoldingEntry | None:
        """대소문자 무시 티커 검색. 없으면 None."""
        upper = ticker.upper()
        return next((h for h in self.holdings if h.ticker.upper() == upper), None)

    def get_account_for(self, ticker: str) -> tuple[float | None, float | None]:
        """티커 통화에 맞는 (capital, risk_pct) 반환. 설정 없으면 (None, None)."""
        if is_korean_ticker(ticker):
            return self.krw_capital, self.krw_risk_pct
        return self.usd_capital, self.usd_risk_pct


def load_holdings(path: str | Path = "playbook.yaml") -> HoldingsConfig:
    """playbook.yaml 로드. 파일 없으면 빈 설정 반환. 스키마 오류는 항목 인덱스와 함께 즉시 예외."""
    p = Path(path)
    if not p.exists():
        return HoldingsConfig(
            krw_capital=None,
            krw_risk_pct=None,
            usd_capital=None,
            usd_risk_pct=None,
        )

    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    account = data.get("account") or {}
    krw = account.get("krw") or {}
    usd = account.get("usd") or {}

    holdings = _parse_holdings(data.get("holdings") or [])
    watchlist = _parse_watchlist(data.get("watchlist") or [], holdings)

    return HoldingsConfig(
        krw_capital=float(krw["capital"]) if krw.get("capital") is not None else None,
        krw_risk_pct=float(krw["risk_per_trade_pct"])
        if krw.get("risk_per_trade_pct") is not None
        else None,
        usd_capital=float(usd["capital"]) if usd.get("capital") is not None else None,
        usd_risk_pct=float(usd["risk_per_trade_pct"])
        if usd.get("risk_per_trade_pct") is not None
        else None,
        holdings=holdings,
        watchlist=watchlist,
    )


def _parse_holdings(raw: list) -> list[HoldingEntry]:
    holdings: list[HoldingEntry] = []
    for i, item in enumerate(raw):
        try:
            ticker = str(item["ticker"])
            currency = "KRW" if is_korean_ticker(ticker) else "USD"
            holdings.append(
                HoldingEntry(
                    ticker=ticker,
                    quantity=int(item["quantity"]),
                    avg_price=float(item["avg_price"]),
                    stop_price=float(item["stop_price"])
                    if item.get("stop_price") is not None
                    else None,
                    currency=currency,
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"playbook.yaml holdings[{i}] 파싱 실패: {e!r}") from e
    return holdings


def _parse_watchlist(raw: list, holdings: list[HoldingEntry]) -> list[WatchEntry]:
    holding_tickers = {h.ticker.upper() for h in holdings}
    watchlist: list[WatchEntry] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or "ticker" not in item:
            raise ValueError(f"playbook.yaml watchlist[{i}]: 'ticker' 필드가 필요합니다")
        ticker = str(item["ticker"])
        upper = ticker.upper()
        if upper in holding_tickers:
            logger.warning(
                "watchlist 티커 %s는 holdings에 이미 존재 — 보유 우선, 워치에서 무시", ticker
            )
            continue
        if upper in seen:
            logger.warning("watchlist 티커 %s 중복 — 첫 항목만 사용", ticker)
            continue
        seen.add(upper)
        note = item.get("note")
        watchlist.append(
            WatchEntry(
                ticker=ticker,
                note=str(note) if note is not None else None,
                currency="KRW" if is_korean_ticker(ticker) else "USD",
            )
        )
    return watchlist
