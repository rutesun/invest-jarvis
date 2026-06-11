"""playbook.yaml 보유 종목 및 계좌 설정 로더 (Plan 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.tools.disclosure import is_korean_ticker


@dataclass
class HoldingEntry:
    """보유 종목 단일 항목."""

    ticker: str
    quantity: int
    avg_price: float
    stop_price: float | None
    currency: str  # "KRW" | "USD"


@dataclass
class HoldingsConfig:
    """playbook.yaml 전체 설정."""

    krw_capital: float | None
    krw_risk_pct: float | None
    usd_capital: float | None
    usd_risk_pct: float | None
    holdings: list[HoldingEntry] = field(default_factory=list)

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
    """playbook.yaml 로드. 파일 없으면 빈 설정 반환."""
    p = Path(path)
    if not p.exists():
        return HoldingsConfig(
            krw_capital=None,
            krw_risk_pct=None,
            usd_capital=None,
            usd_risk_pct=None,
            holdings=[],
        )

    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    account = data.get("account") or {}
    krw = account.get("krw") or {}
    usd = account.get("usd") or {}

    raw_holdings = data.get("holdings") or []
    holdings: list[HoldingEntry] = []
    for item in raw_holdings:
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
    )
