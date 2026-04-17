from src.providers.kis_models import (
    KISBalance,
    KISPosition,
    KISQuote,
    KISToken,
)


def test_kis_token():
    token = KISToken(
        access_token="test_token_xyz",
        token_type="Bearer",
        expires_in=86400,
    )
    assert token.access_token == "test_token_xyz"
    assert token.token_type == "Bearer"


def test_kis_quote():
    quote = KISQuote(
        ticker="005930",
        name="삼성전자",
        price=70000,
        change=1000,
        change_pct=1.45,
        volume=10000000,
    )
    assert quote.ticker == "005930"
    assert quote.name == "삼성전자"
    assert quote.price == 70000


def test_kis_position():
    position = KISPosition(
        ticker="005930",
        name="삼성전자",
        quantity=100,
        avg_price=68000,
        current_price=70000,
        profit_loss=200000,
        profit_loss_pct=2.94,
    )
    assert position.ticker == "005930"
    assert position.quantity == 100


def test_kis_balance():
    positions = [
        KISPosition(
            ticker="005930",
            name="삼성전자",
            quantity=100,
            avg_price=68000,
            current_price=70000,
            profit_loss=200000,
            profit_loss_pct=2.94,
        )
    ]
    balance = KISBalance(
        total_assets=10000000,
        cash=3000000,
        stock_value=7000000,
        positions=positions,
    )
    assert balance.total_assets == 10000000
    assert len(balance.positions) == 1
