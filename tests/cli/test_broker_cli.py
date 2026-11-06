"""CLI uses public fixture responses; no real accounts or network calls."""

import asyncio
import copy
import importlib
import itertools
import json
import threading
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.providers.nhplug import NHAccount, NHClient
from tests.harness.nhplug_contract import validate_nh_fixture


runner = CliRunner()
FIXTURES = Path(__file__).parents[1] / "fixtures" / "nhplug"


@pytest.fixture
def nh_cli(monkeypatch, tmp_path):
    """Replace only the transport; token, validation, pages and models stay real."""
    bodies = {}
    for name in ("token", "accounts", "kr_balance", "us_balance", "kr_executions", "us_history"):
        bodies[name] = json.loads((FIXTURES / f"{name}.json").read_text(), parse_float=Decimal)
        validate_nh_fixture(name, bodies[name])
    paths = {
        "/oauth2/token": "token",
        "/n2/acctinfo": "accounts",
        "/krstock/inquiry/v1/balance": "kr_balance",
        "/gbstock/inquiry/v1/balance": "us_balance",
        "/krstock/inquiry/v1/dailyOrderExecution": "kr_executions",
        "/gbstock/inquiry/v1/dailyTransaction": "us_history",
    }
    state = SimpleNamespace(bodies=bodies, fail=None, clients=[], threads=[])

    def handle(request):
        state.threads.append(threading.get_ident())
        if paths[request.url.path] == state.fail:
            return httpx.Response(500, text="ACCOUNT NUMBER 1 secret-token")
        return httpx.Response(
            200,
            content=json.dumps(copy.deepcopy(bodies[paths[request.url.path]]), default=str),
            headers={"cts_flag": "N"},
        )

    def create(cls):
        client = cls(
            "fixture-key",
            "fixture-secret",
            cache_dir=tmp_path / "token",
            transport=httpx.MockTransport(handle),
        )
        state.clients.append(client)
        return client

    monkeypatch.setattr(NHClient, "from_env", classmethod(create))
    module = importlib.import_module("src.providers.nhplug.client")
    ticks = itertools.count()
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(time=module.time.time, monotonic=lambda: next(ticks), sleep=lambda _: None),
    )
    state.account = NHAccount("ACCOUNT NUMBER 1", "01")
    return state


def test_accounts_show_only_masked_number_public_selector_and_type(nh_cli):
    result = runner.invoke(app, ["broker", "accounts"])
    assert result.exit_code == 0, result.output
    assert nh_cli.account.account_id in result.output
    assert nh_cli.account.masked_number in result.output
    assert "01" in result.output and "03" in result.output
    assert "ACCOUNT NUMBER 1" not in result.output
    assert nh_cli.clients[-1]._http.is_closed


def test_holdings_preserve_market_rows_and_source_summaries(nh_cli):
    result = runner.invoke(app, ["broker", "holdings", "--account", nh_cli.account.account_id])
    assert result.exit_code == 0, result.output
    assert "005940" in result.output and "GOOGL" in result.output
    assert "유통융자" in result.output and "현금" in result.output
    assert "1639431101" in result.output and "1696832044" in result.output
    assert "111959712.930" in result.output
    assert "KRW" in result.output and "USD" in result.output
    assert "NH foreign security closing price" in result.output
    assert "ACCOUNT NUMBER 1" not in result.output


def test_multiple_personal_accounts_require_public_selector(nh_cli):
    result = runner.invoke(app, ["broker", "holdings"])
    assert result.exit_code == 1
    assert "--account" in result.output
    assert "ACCOUNT NUMBER" not in result.output


def test_provider_failure_is_sanitized_and_nonzero(nh_cli):
    nh_cli.fail = "us_balance"
    result = runner.invoke(app, ["broker", "holdings", "--account", nh_cli.account.account_id])
    assert result.exit_code == 1
    assert "조회" in result.output
    assert "ACCOUNT NUMBER" not in result.output and "secret-token" not in result.output
    assert "005940" not in result.output


def _brief_pipeline(monkeypatch):
    module = importlib.import_module("src.cli.main")
    observed = []

    class Pipeline:
        def __init__(self, **kwargs):
            pass

        async def run(self, config):
            observed.append(config)
            return {"ok": True}

        def format_output(self, result, **kwargs):
            return "브리핑 결과"

        def save_report(self, result):
            return Path("reports/fixture.md")

    monkeypatch.setattr(module, "BriefPipeline", Pipeline)
    for key in ("KIS_APP_KEY", "KIS_APP_SECRET", "FMP_API_KEY", "OPENDART_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    return module, observed


def test_nh_brief_without_yaml_fetches_in_thread_and_closes(nh_cli, monkeypatch, tmp_path):
    module, observed = _brief_pipeline(monkeypatch)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["brief", "--broker", "nh", "--account", nh_cli.account.account_id, "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert "리포트 저장" in result.output
    assert observed[0].broker_snapshot.account_id == nh_cli.account.account_id
    assert any(h.ticker == "GOOGL" for h in observed[0].holdings)
    assert all(thread != threading.get_ident() for thread in nh_cli.threads)
    assert nh_cli.clients[-1]._http.is_closed
    assert not (tmp_path / "playbook.yaml").exists()


def test_default_brief_keeps_local_yaml(nh_cli, monkeypatch, tmp_path):
    module, observed = _brief_pipeline(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "playbook.yaml").write_text(
        "holdings:\n- ticker: AAPL\n  quantity: 3\n  avg_price: 100\n"
    )
    result = asyncio.run(module.run_brief(use_llm=False))
    assert result["ok"]
    assert [(h.ticker, h.quantity) for h in observed[0].holdings] == [("AAPL", 3)]
    assert observed[0].broker_snapshot is None
    assert not nh_cli.clients


def test_nh_brief_failure_never_uses_yaml(nh_cli, monkeypatch, tmp_path):
    _, observed = _brief_pipeline(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "playbook.yaml").write_text("watchlist:\n- ticker: AAPL\n")
    nh_cli.fail = "us_balance"
    result = runner.invoke(
        app, ["brief", "--broker", "nh", "--account", nh_cli.account.account_id, "--no-llm"]
    )
    assert result.exit_code == 1
    assert not observed
    assert nh_cli.clients[-1]._http.is_closed
    assert "secret-token" not in result.output


@pytest.mark.parametrize("args", [["--broker", "other"], ["--account", "nh-invalid"]])
def test_brief_rejects_invalid_broker_or_account_with_local(args, nh_cli):
    result = runner.invoke(app, ["brief", "--no-llm", *args])
    assert result.exit_code == 1
    assert not nh_cli.clients


def test_successful_empty_nh_account_still_reaches_brief_pipeline(nh_cli, monkeypatch, tmp_path):
    _, observed = _brief_pipeline(monkeypatch)
    monkeypatch.chdir(tmp_path)
    nh_cli.bodies["kr_balance"]["Output_1"] = []
    nh_cli.bodies["us_balance"]["Output_1"] = []
    result = runner.invoke(
        app, ["brief", "--broker", "nh", "--account", nh_cli.account.account_id, "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert observed[0].broker_snapshot.account_id == nh_cli.account.account_id
    assert observed[0].holdings == [] and observed[0].watchlist == []
    assert len(observed[0].broker_snapshot.summaries) == 3


def test_empty_default_yaml_still_rejects_missing_analysis_targets(monkeypatch, tmp_path):
    module, observed = _brief_pipeline(monkeypatch)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(module.run_brief(use_llm=False))
    assert not observed


def test_nh_brief_retains_explicit_watch_after_yaml_holding_is_sold(nh_cli, monkeypatch, tmp_path):
    _, observed = _brief_pipeline(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "playbook.yaml").write_text(
        'holdings:\n- ticker: AAPL\n  quantity: 3\n  avg_price: 100\n'
        'watchlist:\n- ticker: AAPL\n  note: "재진입 관찰"\n'
    )
    nh_cli.bodies["kr_balance"]["Output_1"] = []
    nh_cli.bodies["us_balance"]["Output_1"] = []
    result = runner.invoke(
        app, ["brief", "--broker", "nh", "--account", nh_cli.account.account_id, "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert observed[0].holdings == []
    assert [(watch.ticker, watch.note) for watch in observed[0].watchlist] == [
        ("AAPL", "재진입 관찰")
    ]
