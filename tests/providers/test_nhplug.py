"""NH 공식 raw 예제의 golden tests + 합성 장애 사례. 실계좌 호출 없음."""

import copy
import importlib
import json
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from tests.harness.nhplug_contract import validate_nh_fixture


FIXTURES = Path(__file__).parents[1] / "fixtures" / "nhplug"


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def pacing_clock(monkeypatch):
    """Keep rate-limit waits deterministic and local to the NH module."""
    module = importlib.import_module("src.providers.nhplug.client")
    clock = FakeClock()
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(
            time=module.time.time,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        ),
    )
    return clock


@pytest.fixture
def official():
    def load(name):
        body = json.loads((FIXTURES / f"{name}.json").read_text(), parse_float=Decimal)
        validate_nh_fixture(name, body)
        return body

    return load


def response(body, **headers):
    return httpx.Response(
        200, content=json.dumps(body, default=str), headers={"cts_flag": "N", **headers}
    )


def provider():
    return importlib.import_module("src.providers.nhplug")


def make_client(tmp_path, handler):
    return provider().NHClient(
        "test-app-key",
        "test-app-secret",
        cache_dir=tmp_path / "tokens",
        transport=httpx.MockTransport(handler),
    )


def ordinary_handler(official, override=None):
    mapping = {
        "/oauth2/token": "token",
        "/n2/acctinfo": "accounts",
        "/krstock/inquiry/v1/balance": "kr_balance",
        "/gbstock/inquiry/v1/balance": "us_balance",
        "/krstock/inquiry/v1/dailyOrderExecution": "kr_executions",
        "/gbstock/inquiry/v1/dailyTransaction": "us_history",
    }

    def handle(request):
        assert str(request.url).startswith("https://api.nhplug.com:8443/")
        assert request.method == "POST"
        if override:
            special = override(request)
            if special is not None:
                return special
        if request.url.path != "/oauth2/token":
            assert request.headers["authorization"] == "Bearer TOKEN"
        return response(official(mapping[request.url.path]))

    return handle


def test_official_balances_preserve_cash_credit_unsettled_and_currencies(tmp_path, official):
    with make_client(tmp_path, ordinary_handler(official)) as client:
        account = client.accounts()[0]
        snapshot = client.balances(account)
    assert len(snapshot.holdings) == 7
    cash, credit = [h for h in snapshot.holdings if h.ticker == "005940"]
    assert (cash.quantity, cash.settled_quantity, cash.unsettled_quantity) == (
        Decimal("145"),
        Decimal("115"),
        Decimal("30"),
    )
    assert credit.credit_type == "유통융자" and credit.quantity == Decimal("4")
    assert credit.loan_date == date(2026, 6, 25)
    googl = next(h for h in snapshot.holdings if h.ticker == "GOOGL")
    assert (googl.currency, googl.avg_price, googl.current_price) == (
        "USD",
        Decimal("363.230000"),
        Decimal("358.150000"),
    )
    assert (googl.unrealized_pnl, googl.unrealized_pnl_krw) == (
        Decimal("-1016"),
        Decimal("-3782630"),
    )
    assert googl.market_value == Decimal("71630") and googl.market_value_krw == Decimal("106886286")
    assert googl.price_date is None and googl.price_basis == "NH foreign security closing price"
    assert snapshot.as_of.tzinfo is not None
    assert [(s.market, s.currency, s.total_assets) for s in snapshot.summaries] == [
        ("KR", "KRW", Decimal("1639431101")),
        ("US", "KRW", Decimal("1696832044")),
        ("US", "USD", Decimal("111959712.930")),
    ]


def test_official_accounts_hide_raw_and_identify_personal_only(tmp_path, official):
    with make_client(tmp_path, ordinary_handler(official)) as client:
        accounts = client.accounts()
        again = client.accounts()
    assert [a.is_personal for a in accounts] == [True, True, False]
    assert [a.account_id for a in accounts] == [a.account_id for a in again]
    assert len({a.account_id for a in accounts}) == 3
    assert all(
        a.raw_number not in repr(a)
        and a.raw_number not in a.account_id
        and a.raw_number not in a.masked_number
        for a in accounts
    )
    assert accounts[0].account_id.startswith("nh-")


def test_official_trades_exclude_zero_execution_and_preserve_fractional_history(tmp_path, official):
    with make_client(tmp_path, ordinary_handler(official)) as client:
        account = client.accounts()[0]
        trades = client.trades(account, date(2025, 4, 21), date(2025, 4, 21))
    assert len(trades) == 5
    kr = trades[0]
    assert (kr.quantity, kr.price, kr.amount, kr.source_id) == (
        Decimal("10"),
        Decimal("34000"),
        Decimal("340000"),
        "29",
    )
    assert kr.source == "kr_order_cumulative" and kr.trade_date_basis == "order_date"
    assert kr.credit_type == "유통융자" and kr.date_precision == "date"
    assert kr.balance_before is None and kr.balance_after is None
    us = trades[1]
    assert (us.ticker, us.quantity, us.price, us.amount) == (
        "GOOGL",
        Decimal("0.004552"),
        Decimal("151.332200"),
        Decimal("0.69"),
    )
    assert us.trade_date == us.query_date == date(2025, 4, 21)
    assert us.balance_before == Decimal("0.158601")
    assert us.balance_after == Decimal("0.163153")
    assert us.source == "us_settled_transaction" and us.source_id == "1"
    assert account.raw_number not in repr(trades)
    assert all(t.trade_id.startswith("nh-trade-") for t in trades)


def test_token_reuse_and_private_disk_cache_across_clients(tmp_path, official):
    issued = []

    def override(request):
        if request.url.path == "/oauth2/token":
            issued.append(request.content)

    handler = ordinary_handler(official, override)
    with make_client(tmp_path, handler) as client:
        client.accounts()
        client.accounts()
    with make_client(tmp_path, handler) as client:
        client.accounts()
    assert len(issued) == 1
    assert (
        b"grant_type=client_credentials" in issued[0]
        and b"appsecretkey=test-app-secret" in issued[0]
    )
    files = list((tmp_path / "tokens").glob("*.json"))
    assert len(files) == 1
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(files[0].parent.stat().st_mode) == 0o700
    assert "test-app-key" not in files[0].name


def test_parallel_clients_do_not_issue_duplicate_token(tmp_path, official):
    issued = []
    gate = threading.Barrier(4)

    def override(request):
        if request.url.path == "/oauth2/token":
            issued.append(1)

    handler = ordinary_handler(official, override)

    def run():
        gate.wait(timeout=5)
        with make_client(tmp_path, handler) as client:
            return len(client.accounts())

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(lambda _: run(), range(4))) == [3] * 4
    assert len(issued) == 1


def test_all_pages_are_collected_and_final_summary_is_used(tmp_path, official):
    calls = []

    def override(request):
        if request.url.path == "/krstock/inquiry/v1/balance":
            calls.append(dict(request.headers))
            body = official("kr_balance")
            if len(calls) == 1:
                body["Output_1"] = body["Output_1"][:1]
                body["Output_0"]["tot_aet_amt"] = 0
                return response(body, cts_flag="Y", cts="NEXT")
            assert request.headers["cts"] == "NEXT" and request.headers["cts_flag"] == "Y"
            body["Output_1"] = body["Output_1"][1:]
            return response(body)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        snapshot = client.balances(client.accounts()[0])
    assert len(calls) == 2 and len(snapshot.holdings) == 7
    assert snapshot.summaries[0].total_assets == Decimal("1639431101")


@pytest.mark.parametrize(
    "headers",
    [{"cts_flag": "Y"}, {"cts_flag": "BAD"}, {"cts": "NEXT"}, {"cts": "NEXT", "cts_flag": ""}],
)
def test_missing_or_invalid_paging_fails_instead_of_empty_success(tmp_path, official, headers):
    def override(request):
        if request.url.path == "/n2/acctinfo":
            return httpx.Response(200, json=official("accounts"), headers=headers)

    with (
        make_client(tmp_path, ordinary_handler(official, override)) as client,
        pytest.raises(provider().NHError),
    ):
        client.accounts()


def test_repeated_cursor_and_middle_business_failure_abort(tmp_path, official):
    for failure in ("repeated", "business"):
        count = []

        def override(request, count=count, failure=failure):
            if request.url.path == "/n2/acctinfo":
                count.append(1)
                if len(count) == 2 and failure == "business":
                    return response(
                        {"rsp_cd": "99999", "rsp_msg": "ACCOUNT NUMBER 1 test-app-secret TOKEN"}
                    )
                return response(official("accounts"), cts_flag="Y", cts="REPEAT")

        with (
            make_client(tmp_path, ordinary_handler(official, override)) as client,
            pytest.raises(provider().NHError) as caught,
        ):
            client.accounts()
        assert len(count) == 2
        assert "ACCOUNT NUMBER" not in str(caught.value) and "TOKEN" not in str(caught.value)


@pytest.mark.parametrize("failure", ["http", "schema", "numeric", "business"])
def test_errors_are_sanitized_without_retry_or_partial_result(tmp_path, official, failure):
    def override(request):
        if request.url.path == "/gbstock/inquiry/v1/balance":
            body = official("us_balance")
            if failure == "http":
                return httpx.Response(403, text="test-app-secret ACCOUNT NUMBER 1 TOKEN")
            if failure == "schema":
                body["Output_1"] = {"account": "ACCOUNT NUMBER 1"}
            elif failure == "numeric":
                body["Output_1"][0]["fc_phs_uit_pr"] = "NaN"
            else:
                body["rsp_cd"] = "99999"
                body["rsp_msg"] = "test-app-secret ACCOUNT NUMBER 1 TOKEN"
            return response(body)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        account = client.accounts()[0]
        with pytest.raises(provider().NHError) as caught:
            client.balances(account)
    assert all(
        secret not in str(caught.value) for secret in ("test-app-secret", "ACCOUNT NUMBER", "TOKEN")
    )
    assert caught.value.__suppress_context__


def test_fractional_balances_and_source_trade_dates_are_preserved(tmp_path, official):
    def override(request):
        if request.url.path == "/gbstock/inquiry/v1/balance":
            body = official("us_balance")
            body["Output_1"][0]["cns_bse_bnc_qty"] = "0.000123"
            return response(body)
        if request.url.path == "/gbstock/inquiry/v1/dailyTransaction":
            body = official("us_history")
            body["Output_0"][0]["ral_trd_dt"] = "20250418"
            non_trade = copy.deepcopy(body["Output_0"][0])
            non_trade["act_trd_tp_nm"] = "입고"
            body["Output_0"].append(non_trade)
            return response(body)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        account = client.accounts()[0]
        assert next(
            h for h in client.balances(account).holdings if h.ticker == "GOOGL"
        ).quantity == Decimal("0.000123")
        trades = client.trades(account, date(2025, 4, 21), date(2025, 4, 21))
    assert len(trades) == 5
    assert trades[1].trade_date == date(2025, 4, 18) and trades[1].query_date == date(2025, 4, 21)


def test_cumulative_order_identity_stays_stable_when_quantity_grows(tmp_path, official):
    quantities = iter(["2", "5"])

    def override(request):
        if request.url.path == "/krstock/inquiry/v1/dailyOrderExecution":
            body = official("kr_executions")
            body["Output_0"][0]["tot_cns_qty"] = next(quantities)
            return response(body)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        account = client.accounts()[0]
        first = client.trades(account, date(2025, 4, 21), date(2025, 4, 21))[0]
        second = client.trades(account, date(2025, 4, 21), date(2025, 4, 21))[0]
    assert first.trade_id == second.trade_id and (first.quantity, second.quantity) == (
        Decimal("2"),
        Decimal("5"),
    )


def test_env_configuration_uses_ns_names_and_never_loads_dotenv(tmp_path, official, monkeypatch):
    monkeypatch.setenv("NS_APP_KEY", "test-app-key")
    monkeypatch.setenv("NS_APP_SECRET", "test-app-secret")
    with provider().NHClient.from_env(
        cache_dir=tmp_path / "tokens", transport=httpx.MockTransport(ordinary_handler(official))
    ) as client:
        assert len(client.accounts()) == 3
    monkeypatch.delenv("NS_APP_SECRET")
    with pytest.raises(provider().NHError):
        provider().NHClient.from_env()


def test_secret_rotation_for_same_appkey_reuses_still_valid_token(tmp_path, official):
    issued = []

    def override(request):
        if request.url.path == "/oauth2/token":
            issued.append(1)

    handler = ordinary_handler(official, override)
    with make_client(tmp_path, handler) as client:
        client.accounts()
    with provider().NHClient(
        "test-app-key",
        "rotated-secret",
        cache_dir=tmp_path / "tokens",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.accounts()
    assert len(issued) == 1


def test_response_latency_cannot_cause_reissue_before_24_hours(tmp_path, official, monkeypatch):
    clock = [1000.0]
    issued = []
    monkeypatch.setattr("src.providers.nhplug.client.time.time", lambda: clock[0])

    def override(request):
        if request.url.path == "/oauth2/token":
            issued.append(1)
            clock[0] += 5  # Token exists somewhere within this request interval.

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        client.accounts()
        clock[0] = 87401.0  # 24h after request start; <24h after response receipt.
        client.accounts()
        assert len(issued) == 1
        clock[0] = 87406.0
        client.accounts()
        assert len(issued) == 2


def test_token_business_or_http_error_is_not_retried(tmp_path, official):
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(401, text="TOKEN test-app-secret ACCOUNT NUMBER 1")

    with make_client(tmp_path, handler) as client, pytest.raises(provider().NHError) as caught:
        client.accounts()
    assert requests == ["/oauth2/token"]
    assert all(
        value not in str(caught.value) for value in ("TOKEN", "test-app-secret", "ACCOUNT NUMBER")
    )


def test_corrupted_token_cache_fails_without_premature_reissuance(tmp_path, official):
    with make_client(tmp_path, ordinary_handler(official)) as client:
        client.accounts()
    cache = next((tmp_path / "tokens").glob("*.json"))
    cache.write_text('{"access_token":"TOKEN"}')
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return response(official("token"))

    with make_client(tmp_path, handler) as client, pytest.raises(provider().NHError):
        client.accounts()
    assert requests == []


@pytest.mark.parametrize("kind", ["02", "03"])
def test_non_personal_or_simulated_account_is_rejected_before_network(tmp_path, kind):
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(500)

    account = provider().NHAccount("000000000123", kind)
    with make_client(tmp_path, handler) as client:
        with pytest.raises(provider().NHError):
            client.balances(account)
        with pytest.raises(provider().NHError):
            client.trades(account, date(2026, 1, 1), date(2026, 1, 1))
    assert requests == []


def test_unknown_actual_trade_date_is_not_replaced_with_query_date(tmp_path, official):
    def override(request):
        if request.url.path == "/gbstock/inquiry/v1/dailyTransaction":
            body = official("us_history")
            body["Output_0"][0]["ral_trd_dt"] = ""
            return response(body)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        account = client.accounts()[0]
        trade = client.trades(account, date(2025, 4, 21), date(2025, 4, 21))[1]
    assert trade.trade_date is None and trade.trade_date_basis == "unknown"
    assert trade.query_date == date(2025, 4, 21)


def test_trade_paging_and_market_failure_do_not_return_partial_facts(tmp_path, official):
    seen = []

    def override(request):
        if request.url.path == "/gbstock/inquiry/v1/dailyTransaction":
            seen.append(1)
            if len(seen) == 1:
                return response(official("us_history"), cts_flag="Y", cts="NEXT")
            assert request.headers["cts"] == "NEXT"
            return response({"rsp_cd": "99999", "rsp_msg": "ACCOUNT NUMBER 1"})

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        account = client.accounts()[0]
        with pytest.raises(provider().NHError):
            client.trades(account, date(2025, 4, 21), date(2025, 4, 21))
    assert len(seen) == 2


def test_paging_requests_obey_global_250ms_interval(tmp_path, official, pacing_clock):
    starts = []

    def override(request):
        if request.url.path == "/krstock/inquiry/v1/balance":
            starts.append(pacing_clock.monotonic())
            if len(starts) == 1:
                return response(official("kr_balance"), cts_flag="Y", cts="NEXT")
            return response(official("kr_balance"))

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        client.balances(client.accounts()[0])
    assert starts == pytest.approx([0.5, 0.75])
    assert pacing_clock.sleeps == pytest.approx([0.25] * 4)


def test_trade_date_loop_and_endpoint_switch_obey_global_interval(tmp_path, official, pacing_clock):
    starts = {}

    def override(request):
        starts.setdefault(request.url.path, []).append(pacing_clock.monotonic())

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        client.trades(client.accounts()[0], date(2025, 4, 21), date(2025, 4, 23))
    assert starts["/krstock/inquiry/v1/dailyOrderExecution"] == pytest.approx([0.5, 0.75, 1.0])
    assert starts["/gbstock/inquiry/v1/dailyTransaction"] == pytest.approx([1.25])
    assert starts["/n2/acctinfo"] == [0.25]
    assert pacing_clock.sleeps == pytest.approx([0.25] * 5)


def test_endpoint_pacing_only_waits_for_remaining_interval(tmp_path, official, pacing_clock):
    starts = []

    def override(request):
        if request.url.path == "/n2/acctinfo":
            starts.append(pacing_clock.monotonic())

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        client.accounts()
        pacing_clock.now += 0.25
        client.accounts()
        pacing_clock.now += 0.05
        client.accounts()
    assert starts == pytest.approx([0.25, 0.5, 0.75])
    assert pacing_clock.sleeps == pytest.approx([0.25, 0.2])


def test_failed_token_endpoint_respects_documented_one_request_per_second(tmp_path, pacing_clock):
    starts = []

    def handler(request):
        starts.append(pacing_clock.monotonic())
        return httpx.Response(401)

    with make_client(tmp_path, handler) as client:
        for _ in range(2):
            with pytest.raises(provider().NHError):
                client.accounts()
    assert starts == pytest.approx([0.0, 1.0])
    assert pacing_clock.sleeps == pytest.approx([1.0])


@pytest.mark.parametrize(
    "headers", [{}, {"cts_flag": ""}, {"cts": ""}, {"cts": "", "cts_flag": ""}]
)
def test_optional_paging_headers_without_cursor_allow_complete_response(
    tmp_path, official, headers
):
    def override(request):
        mapping = {
            "/n2/acctinfo": "accounts",
            "/krstock/inquiry/v1/balance": "kr_balance",
            "/gbstock/inquiry/v1/balance": "us_balance",
            "/krstock/inquiry/v1/dailyOrderExecution": "kr_executions",
            "/gbstock/inquiry/v1/dailyTransaction": "us_history",
        }
        if request.url.path in mapping:
            body = official(mapping[request.url.path])
            return httpx.Response(200, content=json.dumps(body, default=str), headers=headers)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        accounts = client.accounts()
        snapshot = client.balances(accounts[0])
        trades = client.trades(accounts[0], date(2025, 4, 21), date(2025, 4, 21))
    assert len(accounts) == 3 and len(snapshot.holdings) == 7 and len(trades) == 5


def test_last_page_can_omit_both_optional_paging_headers(tmp_path, official):
    calls = []

    def override(request):
        if request.url.path == "/n2/acctinfo":
            calls.append(request.headers.get("cts"))
            body = official("accounts")
            if len(calls) == 1:
                body["Output_0"] = body["Output_0"][:1]
                return response(body, cts_flag="Y", cts="NEXT")
            body["Output_0"] = body["Output_0"][1:]
            return httpx.Response(200, json=body)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        accounts = client.accounts()
    assert len(accounts) == 3 and calls == ["", "NEXT"]


@pytest.mark.parametrize(
    "headers",
    [{"cts": "OTHER"}, {"cts": "OTHER", "cts_flag": ""}, {"cts_flag": "Y"}, {"cts_flag": "BAD"}],
)
def test_middle_page_inconsistent_paging_still_fails_closed(tmp_path, official, headers):
    calls = []

    def override(request):
        if request.url.path == "/n2/acctinfo":
            calls.append(1)
            if len(calls) == 1:
                return response(official("accounts"), cts_flag="Y", cts="NEXT")
            return httpx.Response(200, json=official("accounts"), headers=headers)

    with (
        make_client(tmp_path, ordinary_handler(official, override)) as client,
        pytest.raises(provider().NHError),
    ):
        client.accounts()
    assert len(calls) == 2


# Privacy-safe root observation: a holiday KR execution query returned HTTP200,
# rsp_cd=11512, Output_0=[] and cts_flag=N. No personal response is reproduced;
# cursor strings below are invented test values, never the observed opaque key.
@pytest.mark.parametrize(
    "path,expected_count",
    [
        ("/krstock/inquiry/v1/dailyOrderExecution", 4),
        ("/gbstock/inquiry/v1/dailyTransaction", 1),
    ],
)
@pytest.mark.parametrize(
    "headers", [{"cts_flag": "N", "cts": "SYNTHETIC-END"}, {"cts_flag": "N"}, {}]
)
def test_trade_no_data_code_is_empty_only_with_empty_rows_and_terminal_headers(
    tmp_path, official, path, expected_count, headers
):
    def override(request):
        if request.url.path == path:
            return httpx.Response(
                200,
                json={"rsp_cd": "11512", "rsp_msg": "데이터가 존재하지 않습니다.", "Output_0": []},
                headers=headers,
            )

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        trades = client.trades(client.accounts()[0], date(2025, 4, 21), date(2025, 4, 21))
    assert len(trades) == expected_count


@pytest.mark.parametrize(
    "code,rows,headers",
    [
        ("99999", [], {"cts_flag": "N"}),
        ("11512", [{}], {"cts_flag": "N"}),
        ("11512", None, {"cts_flag": "N"}),
        ("11512", {}, {"cts_flag": "N"}),
        ("11512", "", {"cts_flag": "N"}),
        ("11512", [], {"cts_flag": "Y", "cts": "SYNTHETIC-NEXT"}),
        ("11512", [], {"cts": "SYNTHETIC-NEXT"}),
        ("11512", [], {"cts_flag": "BAD"}),
    ],
)
@pytest.mark.parametrize(
    "path", ["/krstock/inquiry/v1/dailyOrderExecution", "/gbstock/inquiry/v1/dailyTransaction"]
)
def test_trade_no_data_code_rejects_malformed_or_continuing_responses(
    tmp_path, official, code, rows, headers, path
):
    def override(request):
        if request.url.path == path:
            return httpx.Response(200, json={"rsp_cd": code, "Output_0": rows}, headers=headers)

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        account = client.accounts()[0]
        with pytest.raises(provider().NHError):
            client.trades(account, date(2025, 4, 21), date(2025, 4, 21))


def test_trade_date_loop_continues_after_holiday_no_data(tmp_path, official):
    queried = []

    def override(request):
        if request.url.path == "/krstock/inquiry/v1/dailyOrderExecution":
            queried.append(json.loads(request.content)["Input_0"]["orr_dt"])
            if len(queried) == 1:
                return response({"rsp_cd": "11512", "Output_0": []}, cts="SYNTHETIC-END")

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        trades = client.trades(client.accounts()[0], date(2025, 4, 20), date(2025, 4, 21))
    assert queried == ["20250420", "20250421"] and len(trades) == 5


@pytest.mark.parametrize(
    "path", ["/n2/acctinfo", "/krstock/inquiry/v1/balance", "/gbstock/inquiry/v1/balance"]
)
def test_no_data_code_is_not_general_success_for_accounts_or_balances(tmp_path, official, path):
    def override(request):
        if request.url.path == path:
            return response({"rsp_cd": "11512", "Output_0": []}, cts="SYNTHETIC-END")

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        if path == "/n2/acctinfo":
            with pytest.raises(provider().NHError):
                client.accounts()
        else:
            account = client.accounts()[0]
            with pytest.raises(provider().NHError):
                client.balances(account)


def test_accounts_trades_and_account_switches_share_one_global_pacing_budget(
    tmp_path, official, pacing_clock
):
    starts = []
    paths = []

    def override(request):
        paths.append(request.url.path)
        starts.append(pacing_clock.monotonic())

    with make_client(tmp_path, ordinary_handler(official, override)) as client:
        primary, secondary = client.accounts()[:2]
        client.trades(primary, date(2025, 4, 21), date(2025, 4, 21))
        client.accounts()
        client.trades(secondary, date(2025, 4, 21), date(2025, 4, 21))
    assert paths == [
        "/oauth2/token",
        "/n2/acctinfo",
        "/krstock/inquiry/v1/dailyOrderExecution",
        "/gbstock/inquiry/v1/dailyTransaction",
        "/n2/acctinfo",
        "/krstock/inquiry/v1/dailyOrderExecution",
        "/gbstock/inquiry/v1/dailyTransaction",
    ]
    assert starts == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5])
    assert pacing_clock.sleeps == pytest.approx([0.25] * 6)
