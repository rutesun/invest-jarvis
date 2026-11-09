"""실제 보유와 로컬 투자 설정의 책임 경계."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.pipelines.broker_account import merge_broker_holdings, position_for_holding, select_account
from src.providers.nhplug import NHAccount, NHBalanceSnapshot, NHBalanceSummary, NHHolding
from src.tools.brief.broker import render_broker_header, render_broker_holding
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig, WatchEntry


def row(ticker="005930", quantity="3", avg="100", credit="현금", market="KR"):
    return NHHolding(
        account_id="nh-test",
        market=market,
        currency="KRW" if market == "KR" else "USD",
        ticker=ticker,
        name=ticker,
        quantity=Decimal(quantity),
        avg_price=Decimal(avg),
        current_price=Decimal("120"),
        market_value=Decimal("360"),
        unrealized_pnl=Decimal("60"),
        credit_type=credit,
    )


def snapshot(*rows):
    return NHBalanceSnapshot("nh-test", datetime(2026, 11, 6, tzinfo=UTC), rows, ())


def config():
    return HoldingsConfig(
        100000,
        0.01,
        None,
        None,
        holdings=[
            HoldingEntry("005930.KS", 99, 200, 90, "KRW"),
            HoldingEntry("MSFT", 10, 200, None, "USD"),
        ],
        watchlist=[
            WatchEntry("005930.KS", "기존 관심", "KRW"),
            WatchEntry("NVDA", "관심 유지", "USD"),
        ],
    )


def test_real_holdings_replace_yaml_but_keep_settings_without_mutating_source():
    local = config()
    observed = snapshot(row())
    merged = merge_broker_holdings(local, observed)
    assert [(h.ticker, h.quantity, h.avg_price, h.stop_price) for h in merged.holdings] == [
        ("005930", 3, 100.0, 90)
    ]
    assert [(w.ticker, w.note) for w in merged.watchlist] == [("NVDA", "관심 유지")]
    assert merged.krw_capital == 100000 and merged.krw_risk_pct == 0.01
    assert merged.broker_snapshot is observed
    assert local.holdings[0].quantity == 99 and len(local.holdings) == 2
    assert len(local.watchlist) == 2


def test_cash_credit_rows_are_preserved_and_weighted_for_ticker_analysis():
    observed = snapshot(row(quantity="3", avg="100"), row(quantity="1", avg="200", credit="신용"))
    merged = merge_broker_holdings(config(), observed)
    assert len(merged.holdings) == 1
    assert merged.holdings[0].quantity == 4 and merged.holdings[0].avg_price == 125
    lines = "\n".join(render_broker_holding(merged.broker_snapshot.holdings))
    assert "현금" in lines and "신용" in lines and "125" not in lines


def test_fractional_quantity_is_preserved_and_never_passed_as_integer_position():
    merged = merge_broker_holdings(
        config(), snapshot(row("AAPL", "0.004552", "151.3322", market="US"))
    )
    holding = merged.holdings[0]
    assert holding.quantity == Decimal("0.004552")
    position, warning = position_for_holding(holding)
    assert position is None and "소수점" in warning
    whole, warning = position_for_holding(HoldingEntry("AAPL", Decimal("5"), 1.0, None, "USD"))
    assert whole.quantity == 5 and isinstance(whole.quantity, int) and warning is None


def test_empty_live_account_does_not_keep_stale_yaml_holdings():
    merged = merge_broker_holdings(config(), snapshot())
    assert merged.holdings == [] and len(merged.watchlist) == 2


def test_non_stock_kr_assets_keep_balance_facts_without_entering_stock_analysis():
    observed = snapshot(row("RKRW221", "2000", "0"), row("0167A0", "3", "100"))
    merged = merge_broker_holdings(HoldingsConfig(None, None, None, None), observed)
    assert [holding.ticker for holding in merged.holdings] == ["0167A0"]
    assert merged.broker_snapshot is observed
    assert len(merged.broker_snapshot.holdings) == 2
    header = "\n".join(render_broker_header(observed))
    assert "주식 분석 제외 자산" in header and "RKRW221" in header
    assert "수량 단위는 NH 제공 기준" in header
    assert "2,000주" not in header


@pytest.mark.asyncio
async def test_non_stock_only_account_renders_facts_without_requesting_stock_analysis():
    from unittest.mock import AsyncMock, MagicMock

    from tests.pipelines.test_brief import _pipeline

    observed = snapshot(row("RUSD200", "11.4", "0"))
    merged = merge_broker_holdings(HoldingsConfig(None, None, None, None), observed)
    engine = MagicMock()
    engine.evaluate = AsyncMock()
    pipeline = _pipeline(engine)
    result = await pipeline.run(merged)
    assert result["items"] == []
    engine.evaluate.assert_not_awaited()
    assert "RUSD200" in pipeline.format_output(result)


def test_explicit_yaml_watch_survives_when_live_position_has_been_sold(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    path = tmp_path / "playbook.yaml"
    path.write_text(
        "holdings:\n  - ticker: AAPL\n    quantity: 2\n    avg_price: 100\n"
        'watchlist:\n  - ticker: AAPL\n    note: "재진입 관찰"\n'
    )
    assert load_holdings(path).watchlist == []
    local = load_holdings(path, preserve_held_watches=True)
    merged = merge_broker_holdings(local, snapshot())
    assert merged.holdings == []
    assert [(watch.ticker, watch.note) for watch in merged.watchlist] == [("AAPL", "재진입 관찰")]


def test_multiple_personal_accounts_require_explicit_public_id_and_never_echo_raw():
    one, two = NHAccount("12345678901", "01"), NHAccount("98765432109", "01")
    assert select_account([one, NHAccount("11111111111", "03")]) == one
    assert select_account([one, two], two.account_id) == two
    with pytest.raises(ValueError, match="계좌") as error:
        select_account([one, two])
    assert one.raw_number not in str(error.value)
    with pytest.raises(ValueError):
        select_account([NHAccount("11111111111", "03")])
    with pytest.raises(ValueError):
        select_account([one], "12345678901")


def test_market_summaries_are_separate_and_collection_time_is_not_a_price_date():
    summary = (
        NHBalanceSummary(
            "KR", "KRW", Decimal(1000), Decimal(900), Decimal(100), Decimal(100), "kr"
        ),
        NHBalanceSummary(
            "US", "KRW", Decimal(1000), Decimal(900), Decimal(100), Decimal(100), "us"
        ),
        NHBalanceSummary("US", "USD", Decimal(10), Decimal(9), Decimal(1), Decimal(1), "us"),
    )
    observed = NHBalanceSnapshot("nh-test", datetime(2026, 11, 6, tzinfo=UTC), (), summary)
    text = "\n".join(render_broker_header(observed))
    assert "KRW" in text and "USD" in text and "2,000" not in text
    assert "조회" in text and "합산" in text
    holding_text = "\n".join(render_broker_holding([row("AAPL", market="US")]))
    assert "가격 거래일 미제공" in holding_text and "평가" in holding_text


def test_mixed_accounts_are_rejected_instead_of_silently_added():
    from dataclasses import replace

    with pytest.raises(ValueError):
        merge_broker_holdings(config(), snapshot(replace(row(), account_id="other")))


@pytest.mark.asyncio
async def test_fractional_live_brief_keeps_facts_with_analysis_and_a_quantity_warning():
    from unittest.mock import AsyncMock, MagicMock

    from tests.pipelines.test_brief import _pipeline, _verdict_holding

    observed = snapshot(row("AAPL", "0.004552", "151.3322", market="US"))
    merged = merge_broker_holdings(HoldingsConfig(None, None, None, None), observed)
    engine = MagicMock()
    engine.evaluate = AsyncMock(return_value=_verdict_holding("AAPL", "hold"))
    pipeline = _pipeline(engine)
    result = await pipeline.run(merged)
    assert result["items"][0].action == "hold"
    assert any("소수점" in warning for warning in result["items"][0].warnings)
    text = pipeline.format_output(result)
    assert "0.004552주" in text and "151.3322 USD" in text
    assert text.index("### AAPL") < text.index("NH 보유")
