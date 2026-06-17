"""TDD: holdings.py — playbook.yaml 로더."""

import textwrap


# ---------------------------------------------------------------------------
# 파일 없을 때: 빈 설정 반환
# ---------------------------------------------------------------------------


def test_load_holdings_no_file_returns_empty(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    config = load_holdings(tmp_path / "nonexistent.yaml")
    assert config.krw_capital is None
    assert config.usd_capital is None
    assert config.holdings == []


# ---------------------------------------------------------------------------
# 정상 YAML: account + holdings 로드
# ---------------------------------------------------------------------------

SAMPLE_YAML = textwrap.dedent("""
    account:
      krw:
        capital: 10000000
        risk_per_trade_pct: 1.0
      usd:
        capital: 5000
        risk_per_trade_pct: 0.5
    holdings:
      - ticker: "005930.KS"
        quantity: 100
        avg_price: 70000
        stop_price: 64000
      - ticker: "AAPL"
        quantity: 10
        avg_price: 180.0
""")


def test_load_holdings_full_yaml(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    assert config.krw_capital == 10_000_000.0
    assert config.krw_risk_pct == 1.0
    assert config.usd_capital == 5_000.0
    assert config.usd_risk_pct == 0.5
    assert len(config.holdings) == 2


# ---------------------------------------------------------------------------
# 통화 판별: is_korean_ticker 재사용
# ---------------------------------------------------------------------------


def test_holding_currency_korean(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    ks_holding = next(h for h in config.holdings if h.ticker == "005930.KS")
    assert ks_holding.currency == "KRW"


def test_holding_currency_us(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    aapl_holding = next(h for h in config.holdings if h.ticker == "AAPL")
    assert aapl_holding.currency == "USD"


# ---------------------------------------------------------------------------
# stop_price 선택적
# ---------------------------------------------------------------------------


def test_holding_stop_price_optional(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    aapl = next(h for h in config.holdings if h.ticker == "AAPL")
    assert aapl.stop_price is None


def test_holding_stop_price_present(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    ks = next(h for h in config.holdings if h.ticker == "005930.KS")
    assert ks.stop_price == 64000.0


# ---------------------------------------------------------------------------
# find(ticker): 보유 찾기
# ---------------------------------------------------------------------------


def test_find_existing_ticker(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    h = config.find("AAPL")
    assert h is not None
    assert h.quantity == 10


def test_find_missing_ticker(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    assert config.find("TSLA") is None


def test_find_case_insensitive(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    assert config.find("aapl") is not None
    assert config.find("AAPL") is not None


# ---------------------------------------------------------------------------
# account 없는 YAML: capital=None
# ---------------------------------------------------------------------------

MINIMAL_YAML = textwrap.dedent("""
    holdings:
      - ticker: "MSFT"
        quantity: 5
        avg_price: 420.0
""")


def test_load_minimal_yaml_no_account(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(MINIMAL_YAML)
    config = load_holdings(p)

    assert config.krw_capital is None
    assert config.usd_capital is None
    assert len(config.holdings) == 1
    assert config.holdings[0].ticker == "MSFT"


# ---------------------------------------------------------------------------
# get_account_for(ticker): 통화에 맞는 capital/risk_pct 반환
# ---------------------------------------------------------------------------


def test_get_account_for_us_ticker(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    capital, risk_pct = config.get_account_for("AAPL")
    assert capital == 5_000.0
    assert risk_pct == 0.5


def test_get_account_for_kr_ticker(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(SAMPLE_YAML)
    config = load_holdings(p)

    capital, risk_pct = config.get_account_for("005930.KS")
    assert capital == 10_000_000.0
    assert risk_pct == 1.0


def test_get_account_for_no_account_returns_none(tmp_path):
    from src.tools.playbook.holdings import load_holdings

    p = tmp_path / "playbook.yaml"
    p.write_text(MINIMAL_YAML)
    config = load_holdings(p)

    capital, risk_pct = config.get_account_for("MSFT")
    assert capital is None
