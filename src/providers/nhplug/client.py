"""Read-only NH PLUG boundary with private, shared 24-hour token caching."""

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from hashlib import sha256
from pathlib import Path
from threading import Lock

import httpx

from src.providers.nhplug.models import (
    NHAccount,
    NHBalanceSnapshot,
    NHBalanceSummary,
    NHHolding,
    NHTrade,
)


BASE_URL = "https://api.nhplug.com:8443"
ACCOUNT_PATH = "/n2/acctinfo"
KR_BALANCE_PATH = "/krstock/inquiry/v1/balance"
US_BALANCE_PATH = "/gbstock/inquiry/v1/balance"
KR_TRADE_PATH = "/krstock/inquiry/v1/dailyOrderExecution"
US_TRADE_PATH = "/gbstock/inquiry/v1/dailyTransaction"


class NHError(RuntimeError):
    """Sanitized provider failure: never contains request, response, token or account."""


def _schema_boundary(method):
    @wraps(method)
    def checked(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
            raise NHError("NH response schema failure") from None

    return checked


def _text(row: dict, key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError
    return value.strip()


def _number(row: dict, key: str, *, nonnegative: bool = False) -> Decimal:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError
    result = Decimal(value)
    if not result.is_finite() or (nonnegative and result < 0):
        raise ValueError
    return result


def _source_id(row: dict, key: str) -> str:
    value = _number(row, key, nonnegative=True)
    if value != value.to_integral_value() or value <= 0:
        raise ValueError
    return str(int(value))


def _day(value: str | None) -> date | None:
    if value in (None, "", "00000000"):
        return None
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise ValueError
    return datetime.strptime(value, "%Y%m%d").date()


def _rows(body: dict, key: str) -> list[dict]:
    rows = body[key]
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError
    return rows


def _credit(row: dict) -> str:
    # Official raw example and field table disagree on the suffix.
    values = [row[key] for key in ("cfd_lon_cd", "cfd_lon_cd_nm") if key in row]
    if not values or len(set(values)) != 1 or not isinstance(values[0], str) or not values[0]:
        raise ValueError
    return values[0]


class NHClient:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        cache_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        if not app_key or not app_secret:
            raise NHError("NH credentials are not configured") from None
        self._app_key = app_key
        self._app_secret = app_secret
        self._cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path.home() / ".cache" / "invest-jarvis" / "nhplug"
        )
        identity = sha256((BASE_URL + "\x00" + app_key).encode()).hexdigest()
        self._cache_path = self._cache_dir / f"{identity}.json"
        self._lock_path = self._cache_dir / f"{identity}.lock"
        self._request_lock = Lock()
        self._request_started: float | None = None
        self._token_started: float | None = None
        self._http = httpx.Client(
            transport=transport, timeout=20, follow_redirects=False, trust_env=False
        )

    @classmethod
    def from_env(cls, **kwargs):
        # The CLI owns dotenv loading; never inspect a local .env here.
        return cls(os.getenv("NS_APP_KEY", ""), os.getenv("NS_APP_SECRET", ""), **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._http.close()

    def _post(
        self,
        path: str,
        *,
        headers: dict | None = None,
        body: dict | None = None,
        form: dict | None = None,
    ) -> httpx.Response:
        try:
            # Pace all NH paths together at 4/s, below the documented 5/s.
            # Token issuance additionally retains its documented 1/s limit.
            # Separate clients/processes do not share this pacing budget.
            with self._request_lock:
                now = time.monotonic()
                remaining = (
                    0.25 - (now - self._request_started)
                    if self._request_started is not None
                    else 0.0
                )
                if path == "/oauth2/token" and self._token_started is not None:
                    remaining = max(remaining, 1.0 - (now - self._token_started))
                if remaining > 0:
                    time.sleep(remaining)
                self._request_started = time.monotonic()
                if path == "/oauth2/token":
                    self._token_started = self._request_started
                response = self._http.post(BASE_URL + path, headers=headers, json=body, data=form)
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            raise NHError("NH transport failure") from None

    @staticmethod
    def _body(response: httpx.Response) -> dict:
        try:
            body = json.loads(response.content, parse_float=Decimal)
            if not isinstance(body, dict):
                raise ValueError
            return body
        except (ValueError, TypeError):
            raise NHError("NH response schema failure") from None

    @contextmanager
    def _cache_lock(self):
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self._cache_dir.is_symlink():
                raise OSError
            self._cache_dir.chmod(0o700)
            flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
            fd = os.open(self._lock_path, flags, 0o600)
            with os.fdopen(fd, "a+") as lock:
                os.fchmod(lock.fileno(), 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError:
            raise NHError("NH private token cache failure") from None

    def _read_token(self) -> str | None:
        if not self._cache_path.exists() and not self._cache_path.is_symlink():
            return None
        try:
            fd = os.open(self._cache_path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as cached:
                if os.fstat(cached.fileno()).st_mode & 0o077:
                    raise ValueError
                body = json.load(cached)
            issued = body["issued_at"]
            expires = body["expires_at"]
            token = body["access_token"]
            if (
                not isinstance(token, str)
                or not token
                or isinstance(issued, bool)
                or isinstance(expires, bool)
                or not isinstance(issued, (float, int))
                or not isinstance(expires, (float, int))
                or not 0 < expires - issued <= 86400
                or issued > time.time()
            ):
                raise ValueError
            return token if time.time() < expires else None
        except (OSError, ValueError, KeyError, TypeError):
            # A damaged cache must not silently cause premature token reissuance.
            raise NHError("NH private token cache failure") from None

    def _token(self) -> str:
        with self._cache_lock():
            token = self._read_token()
            if token is not None:
                return token
            body = self._body(
                self._post(
                    "/oauth2/token",
                    form={
                        "appkey": self._app_key,
                        "appsecretkey": self._app_secret,
                        "grant_type": "client_credentials",
                        "scope": "oob",
                    },
                )
            )
            try:
                token = _text(body, "access_token")
                seconds = body["expires_in"]
                if (
                    body["token_type"] != "Bearer"
                    or body["scope"] != "oob"
                    or isinstance(seconds, bool)
                    or not isinstance(seconds, int)
                    or not 0 < seconds <= 86400
                ):
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                raise NHError("NH token response failure") from None
            # Start the local 24h window after receipt, avoiding premature reissue
            # caused by request latency; an expired bearer is never auto-refreshed.
            issued_at = time.time()
            temporary = None
            try:
                fd, temporary = tempfile.mkstemp(prefix=".token-", dir=self._cache_dir)
                with os.fdopen(fd, "w") as target:
                    os.fchmod(target.fileno(), 0o600)
                    json.dump(
                        {
                            "access_token": token,
                            "issued_at": issued_at,
                            "expires_at": issued_at + seconds,
                        },
                        target,
                    )
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, self._cache_path)
            except OSError:
                raise NHError("NH private token cache failure") from None
            finally:
                if temporary is not None and os.path.exists(temporary):
                    os.unlink(temporary)
            return token

    def _pages(self, path: str, inputs: dict | None = None):
        token = self._token()
        cursor = ""
        seen = set()
        for _ in range(1000):
            response = self._post(
                path,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json;charset=utf-8",
                    "cts": cursor,
                    "cts_flag": "Y" if cursor else "N",
                },
                body={"Input_0": inputs} if inputs is not None else {},
            )
            body = self._body(response)
            expected = "00000" if path == ACCOUNT_PATH else "00166"
            flag = response.headers.get("cts_flag")
            next_cursor = response.headers.get("cts", "")
            # Both response headers are optional in the official contract.
            # Their joint absence/emptiness denotes a terminal page only.
            if flag in (None, "") and not next_cursor:
                flag = "N"
            # A no-history response is valid only on trade queries, with an
            # explicit empty row list and terminal paging. Other failures stay errors.
            empty_history = (
                path in (KR_TRADE_PATH, US_TRADE_PATH)
                and body.get("rsp_cd") == "11512"
                and body.get("Output_0") == []
                and flag == "N"
            )
            if body.get("rsp_cd") != expected and not empty_history:
                raise NHError("NH business response failure") from None
            if flag not in ("Y", "N") or (flag == "Y" and (not next_cursor or next_cursor in seen)):
                raise NHError("NH pagination failure") from None
            yield body
            if flag == "N":
                return
            seen.add(next_cursor)
            cursor = next_cursor
        raise NHError("NH pagination limit exceeded") from None

    @_schema_boundary
    def accounts(self) -> list[NHAccount]:
        accounts = {}
        for body in self._pages(ACCOUNT_PATH):
            for row in _rows(body, "Output_0"):
                account_type = _text(row, "acct_type")
                if account_type not in ("01", "02", "03"):
                    raise ValueError
                account = NHAccount(_text(row, "acct_no"), account_type)
                accounts[account.account_id] = account
        return list(accounts.values())

    @staticmethod
    def _personal(account: NHAccount):
        if not isinstance(account, NHAccount) or not account.is_personal:
            raise NHError("NH personal production account required") from None

    @_schema_boundary
    def balances(self, account: NHAccount) -> NHBalanceSnapshot:
        self._personal(account)
        holdings = []
        summary = None
        for body in self._pages(
            KR_BALANCE_PATH,
            {
                "act_no": account.raw_number,
                "bnc_bse_cd": "1",
                "ltg_aot_dit_cd": "9",
                "aet_bse": "2",
                "qut_dit_cd": "UNT",
                "aly_qut_cd": "2",
            },
        ):
            for row in _rows(body, "Output_1"):
                quantity = _number(row, "rsdl_qty", nonnegative=True)
                holding = NHHolding(
                    account_id=account.account_id,
                    market="KR",
                    currency="KRW",
                    ticker=_text(row, "iem_cd").removeprefix("A"),
                    name=_text(row, "iem_nm"),
                    quantity=quantity,
                    avg_price=_number(row, "phs_pr", nonnegative=True),
                    current_price=_number(row, "now_pr", nonnegative=True),
                    market_value=_number(row, "eal_amt"),
                    unrealized_pnl=_number(row, "eal_pls_amt"),
                    credit_type=_text(row, "tp_cd_nm"),
                    loan_date=_day(row.get("lon_byn_dt")),
                    expiry_date=_day(row.get("xrn_dt")),
                    settled_quantity=_number(row, "itg_bnc_qty", nonnegative=True),
                    unsettled_quantity=_number(row, "ny_stl_qty"),
                )
                if quantity:
                    holdings.append(holding)
            summary = body["Output_0"]
        summaries = [
            NHBalanceSummary(
                "KR",
                "KRW",
                _number(summary, "tot_aet_amt"),
                _number(summary, "tot_eal_amt"),
                _number(summary, "tot_eal_pls"),
                _number(summary, "dca"),
                KR_BALANCE_PATH,
            )
        ]
        for body in self._pages(
            US_BALANCE_PATH,
            {
                "act_no": account.raw_number,
                "qut_iqr_dit_cd": "9",
                "fc_sec_trd_nat_cd": "200",
                "cur_cd": "USD",
                "xns_dit_cd": "0",
            },
        ):
            for row in _rows(body, "Output_1"):
                if _text(row, "fc_sec_trd_nat_cd") != "200" or _text(row, "cur_cd") != "USD":
                    raise ValueError
                quantity = _number(row, "cns_bse_bnc_qty", nonnegative=True)
                holding = NHHolding(
                    account_id=account.account_id,
                    market="US",
                    currency="USD",
                    ticker=_text(row, "iem_cd"),
                    name=_text(row, "iem_nm"),
                    quantity=quantity,
                    avg_price=_number(row, "fc_phs_uit_pr", nonnegative=True),
                    current_price=_number(row, "fc_sec_end_pr", nonnegative=True),
                    market_value=_number(row, "fc_eal_amt"),
                    unrealized_pnl=_number(row, "fc_eal_pls_amt"),
                    credit_type=_text(row, "cfd_lon_cd_nm"),
                    loan_date=_day(row.get("lon_dt")),
                    expiry_date=_day(row.get("xrn_dt")),
                    avg_price_krw=_number(row, "phs_uit_pr"),
                    current_price_krw=_number(row, "end_pr"),
                    market_value_krw=_number(row, "krw_eal_amt"),
                    unrealized_pnl_krw=_number(row, "krw_eal_pls_amt"),
                    price_basis="NH foreign security closing price",
                )
                if quantity:
                    holdings.append(holding)
            summary = body["Output_0"]
        summaries.extend(
            [
                NHBalanceSummary(
                    "US",
                    "KRW",
                    _number(summary, "tot_aet_amt"),
                    _number(summary, "eal_amt_sum"),
                    _number(summary, "eal_pls_sum_amt"),
                    _number(summary, "krw_dca"),
                    US_BALANCE_PATH,
                ),
                NHBalanceSummary(
                    "US",
                    "USD",
                    _number(summary, "fc_aet_amt"),
                    _number(summary, "fc_eal_amt"),
                    _number(summary, "fc_eal_pls_amt"),
                    _number(summary, "fc_dca"),
                    US_BALANCE_PATH,
                ),
            ]
        )
        return NHBalanceSnapshot(
            account.account_id, datetime.now(UTC), tuple(holdings), tuple(summaries)
        )

    @_schema_boundary
    def trades(self, account: NHAccount, start: date, end: date) -> list[NHTrade]:
        self._personal(account)
        if not isinstance(start, date) or not isinstance(end, date) or end < start:
            raise NHError("NH invalid trade date range") from None
        trades = []
        queried = start
        while queried <= end:
            for body in self._pages(
                KR_TRADE_PATH,
                {
                    "act_no": account.raw_number,
                    "orr_dt": queried.strftime("%Y%m%d"),
                    "orr_mkt_cd": "00",
                    "ost_cns_dit": "0",
                },
            ):
                for row in _rows(body, "Output_0"):
                    quantity = _number(row, "tot_cns_qty", nonnegative=True)
                    if not quantity:
                        continue
                    side_name = _text(row, "sby_dit_cd_nm")
                    if side_name not in ("현금매수", "현금매도", "신용매수", "신용매도"):
                        raise ValueError
                    trades.append(
                        NHTrade(
                            account_id=account.account_id,
                            market="KR",
                            currency="KRW",
                            ticker=_text(row, "iem_cd").removeprefix("A"),
                            name=_text(row, "iem_nm"),
                            side="buy" if side_name.endswith("매수") else "sell",
                            quantity=quantity,
                            price=_number(row, "cns_avg_uit_pr", nonnegative=True),
                            amount=_number(row, "cns_amt", nonnegative=True),
                            trade_date=queried,
                            query_date=queried,
                            source_id=_source_id(row, "itg_orr_no"),
                            source="kr_order_cumulative",
                            credit_type=_credit(row),
                            loan_date=_day(row.get("lon_dt")),
                            trade_date_basis="order_date",
                        )
                    )
            queried += timedelta(days=1)
        for body in self._pages(
            US_TRADE_PATH,
            {
                "act_no": account.raw_number,
                "iqr_sta_dt": start.strftime("%Y%m%d"),
                "iqr_end_dt": end.strftime("%Y%m%d"),
                "act_trd_cfc_cd": "00",
                "iem_mlf_cd": "00001",
            },
        ):
            for row in _rows(body, "Output_0"):
                side_name = _text(row, "act_trd_tp_nm")
                if side_name not in ("매수", "매도"):
                    continue
                symbol = _text(row, "iem_cd")
                currency = _text(row, "cur_cd_nm")
                # This API covers foreign equities, so explicitly select US facts.
                if currency != "USD" or not symbol.endswith(" US"):
                    continue
                quantity = _number(row, "trd_qty", nonnegative=True)
                if not quantity:
                    continue
                query_date = _day(_text(row, "trd_dt"))
                if query_date is None:
                    raise ValueError
                trade_date = _day(row.get("ral_trd_dt"))
                trades.append(
                    NHTrade(
                        account_id=account.account_id,
                        market="US",
                        currency=currency,
                        ticker=symbol.removesuffix(" US"),
                        name=_text(row, "iem_nm"),
                        side="buy" if side_name == "매수" else "sell",
                        quantity=quantity,
                        price=_number(row, "trd_uit_pr", nonnegative=True),
                        amount=_number(row, "fc_trd_amt", nonnegative=True),
                        amount_krw=_number(row, "krw_trd_amt"),
                        trade_date=trade_date,
                        query_date=query_date,
                        source_id=_source_id(row, "trd_sno"),
                        balance_before=_number(row, "trd_bf_bnc_qty")
                        if "trd_bf_bnc_qty" in row
                        else None,
                        balance_after=_number(row, "trd_af_bnc_qty")
                        if "trd_af_bnc_qty" in row
                        else None,
                        source="us_settled_transaction",
                        trade_date_basis="actual_date" if trade_date else "unknown",
                        fee_fields={
                            key: _number(row, key)
                            for key in ("ose_fee", "dmt_fee", "abd_sdr_xps_fc_amt")
                            if key in row
                        },
                        tax_fields={
                            key: _number(row, key)
                            for key in (
                                "fc_tax_sum",
                                "tax_sum",
                                "oss_stm_tax",
                                "icm_tax",
                                "rsd_tax",
                            )
                            if key in row
                        },
                    )
                )
        return trades
