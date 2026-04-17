from pydantic import BaseModel


class KISToken(BaseModel):
    """KIS API access token."""

    access_token: str
    token_type: str
    expires_in: int


class KISQuote(BaseModel):
    """Korean stock quote."""

    ticker: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int


class KISPosition(BaseModel):
    """Portfolio position."""

    ticker: str
    name: str
    quantity: int
    avg_price: float
    current_price: float
    profit_loss: float
    profit_loss_pct: float


class KISBalance(BaseModel):
    """Portfolio balance."""

    total_assets: float
    cash: float
    stock_value: float
    positions: list[KISPosition]
