import pytest
from src.tools.screener.models import UniverseStock, ScreenerEvidence


def test_universe_stock():
    stock = UniverseStock(
        ticker="005930",
        name="삼성전자",
        market="KOSPI",
        sources=["theme", "volume_rank"],
        theme="AI/반도체",
        theme_change_rate=3.2,
        price=70000,
        change_pct=2.5,
    )
    assert stock.ticker == "005930"
    assert len(stock.sources) == 2
    assert stock.theme == "AI/반도체"


def test_universe_stock_minimal():
    stock = UniverseStock(
        ticker="AAPL",
        name="Apple Inc.",
        market="NAS",
        sources=["rise_rank"],
    )
    assert stock.theme is None
    assert stock.price is None


def test_screener_evidence():
    stock = UniverseStock(
        ticker="005930", name="삼성전자", market="KOSPI", sources=["theme"],
    )
    evidence = ScreenerEvidence(
        stock=stock,
        accumulation_score=12.0,
        up_days=7,
        volume_burst_score=5.0,
        source_diversity_bonus=4.0,
        momentum_total=47.0,
        total_score=21.0,
        vol_ratio=3.5,
        rank=1,
    )
    assert evidence.rank == 1
    assert evidence.momentum_total == 47.0
    assert evidence.up_days == 7  # collected but not in total_score
    assert evidence.total_score == 21.0  # accumulation + volume_burst + diversity
