"""증권사 보유 사실을 기존 분석 입력에 연결하는 경계."""

from dataclasses import replace
from decimal import Decimal

from src.position.models import PositionSnapshot
from src.providers.nhplug import NHAccount, NHBalanceSnapshot
from src.tools.brief.broker import supports_stock_analysis
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig, WatchEntry


def canonical_ticker(ticker: str) -> str:
    return ticker.upper().removesuffix(".KS").removesuffix(".KQ")


def select_account(accounts: list[NHAccount], selector: str | None = None) -> NHAccount:
    """자동 선택은 유일한 개인 실계좌에 한정한다."""
    personal = [account for account in accounts if account.is_personal]
    if selector is not None:
        matches = [account for account in personal if account.account_id == selector]
        if len(matches) == 1:
            return matches[0]
        raise ValueError("개인 실계좌 식별자를 확인하세요: jarvis broker accounts")
    if len(personal) != 1:
        raise ValueError("연결 계좌를 선택하세요: jarvis broker accounts 후 --account 지정")
    return personal[0]


def merge_broker_holdings(local: HoldingsConfig, observed: NHBalanceSnapshot) -> HoldingsConfig:
    """원본 YAML을 변경하지 않고 실제 수량과 사용자 설정을 결합한다."""
    grouped = {}
    for row in observed.holdings:
        if row.account_id != observed.account_id or row.quantity < 0:
            raise ValueError("NH 잔고 계좌 또는 수량 계약 오류")
        if row.quantity == 0 or not supports_stock_analysis(row):
            continue
        key = (row.market, row.currency, canonical_ticker(row.ticker))
        grouped.setdefault(key, []).append(row)
    configured = {canonical_ticker(h.ticker): h for h in local.holdings}
    holdings = []
    for (_, currency, ticker), rows in sorted(grouped.items()):
        quantity = sum((row.quantity for row in rows), Decimal(0))
        avg_price = sum((row.avg_price * row.quantity for row in rows), Decimal(0)) / quantity
        original = configured.get(ticker)
        holdings.append(
            HoldingEntry(
                ticker=ticker,
                quantity=int(quantity) if quantity == quantity.to_integral_value() else quantity,
                avg_price=float(avg_price),
                stop_price=original.stop_price if original is not None else None,
                currency=currency,
            )
        )
    held = {h.ticker for h in holdings}
    watches = []
    seen = set()
    for watch in local.watchlist:
        ticker = canonical_ticker(watch.ticker)
        if ticker not in held and ticker not in seen:
            watches.append(WatchEntry(ticker, watch.note, watch.currency))
            seen.add(ticker)
    return replace(local, holdings=holdings, watchlist=watches, broker_snapshot=observed)


def position_for_holding(
    holding: HoldingEntry | None,
) -> tuple[PositionSnapshot | None, str | None]:
    quantity = Decimal(str(holding.quantity)) if holding is not None else Decimal(0)
    if quantity != quantity.to_integral_value():
        return None, "소수점 보유 수량은 그대로 표시하며 정수 기준 대응 수량은 계산하지 않습니다."
    return PositionSnapshot(int(quantity)), None
