"""NH 계좌 사실 모델. 원문 계좌번호는 통신 경계에서만 사용한다."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal


Market = Literal["KR", "US"]
Side = Literal["buy", "sell"]


def _identifier(prefix: str, *parts: str) -> str:
    return prefix + sha256("\x00".join(parts).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class NHAccount:
    raw_number: str = field(repr=False)
    account_type: str

    @property
    def account_id(self) -> str:
        return _identifier("nh-", self.account_type, self.raw_number)

    @property
    def masked_number(self) -> str:
        # Short/non-numeric official placeholders must not expose their raw value either.
        suffix = (
            self.raw_number[-4:] if self.raw_number.isdigit() and len(self.raw_number) > 8 else ""
        )
        return "****-****" + ("-" + suffix if suffix else "")

    @property
    def is_personal(self) -> bool:
        return self.account_type == "01"


@dataclass(frozen=True)
class NHHolding:
    account_id: str
    market: Market
    currency: str
    ticker: str
    name: str
    quantity: Decimal
    avg_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    credit_type: str
    loan_date: date | None = None
    expiry_date: date | None = None
    settled_quantity: Decimal | None = None
    unsettled_quantity: Decimal | None = None
    avg_price_krw: Decimal | None = None
    current_price_krw: Decimal | None = None
    market_value_krw: Decimal | None = None
    unrealized_pnl_krw: Decimal | None = None
    price_basis: str = "NH all-session current price (UNT)"
    price_date: date | None = None


@dataclass(frozen=True)
class NHBalanceSummary:
    market: Market
    currency: str
    total_assets: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    cash: Decimal
    source: str
    # Domestic/foreign totals can overlap; consumers must not add these totals.
    assets_scope: str = "NH source-specific; overlap with other summaries unverified"


@dataclass(frozen=True)
class NHBalanceSnapshot:
    account_id: str
    as_of: datetime
    holdings: tuple[NHHolding, ...]
    summaries: tuple[NHBalanceSummary, ...]


@dataclass(frozen=True)
class NHTrade:
    account_id: str
    market: Market
    currency: str
    ticker: str
    name: str
    side: Side
    quantity: Decimal
    price: Decimal
    amount: Decimal
    trade_date: date | None
    query_date: date
    source_id: str
    source: str
    credit_type: str = "unspecified"
    loan_date: date | None = None
    date_precision: str = "date"
    trade_date_basis: str = "actual_date"
    amount_krw: Decimal | None = None
    # Raw field names preserve source semantics; no undocumented currency summation.
    fee_fields: dict[str, Decimal] = field(default_factory=dict)
    tax_fields: dict[str, Decimal] = field(default_factory=dict)
    balance_before: Decimal | None = None
    balance_after: Decimal | None = None

    @property
    def trade_id(self) -> str:
        # Query date scopes daily source identifiers. Cumulative quantities are not identity.
        return _identifier(
            "nh-trade-",
            self.account_id,
            self.market,
            self.source,
            self.query_date.isoformat(),
            self.source_id,
        )
