import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.storage.canonical import canonical_bytes, canonical_hash, strategy_input_hash


def test_canonical_numbers_and_datetimes_have_one_representation():
    assert canonical_bytes({"n": 1}) == b'{"n":1}'
    assert canonical_bytes({"n": 1.0}) == canonical_bytes({"n": Decimal("1.00")})
    assert canonical_bytes({"n": -0.0}) == canonical_bytes({"n": 0})
    assert canonical_bytes({"n": Decimal("1E+3")}) == b'{"n":1000}'
    assert canonical_bytes({"n": Decimal("123456789012345678901234567890.12300")}) == (
        b'{"n":123456789012345678901234567890.123}'
    )
    assert (
        canonical_bytes({"at": datetime(2026, 10, 2, 9, tzinfo=timezone(timedelta(hours=9)))})
        == b'{"at":"2026-10-02T00:00:00Z"}'
    )
    assert (
        canonical_bytes({"day": date(2026, 10, 2), "empty": None})
        == b'{"day":"2026-10-02","empty":null}'
    )
    for value in (float("nan"), float("inf"), float("-inf"), Decimal("NaN")):
        with pytest.raises(ValueError):
            canonical_bytes({"n": value})
    with pytest.raises(ValueError):
        canonical_bytes({"at": datetime(2026, 10, 2, 9)})


def test_canonical_hash_uses_domain_nul_and_sorted_utf8_payload():
    payload = '{"a":"한글","z":1}'.encode()
    expected = hashlib.sha256(b"jarvis:test:v1\0" + payload).hexdigest()
    assert canonical_bytes({"z": 1.0, "a": "한글"}) == payload
    assert canonical_hash("jarvis:test:v1", {"z": 1, "a": "한글"}) == expected
    assert canonical_hash("jarvis:other:v1", {"z": 1, "a": "한글"}) != expected


def test_strategy_input_hash_uses_only_bundle_hash_and_strategy_identity():
    class Bundle:
        bundle_hash = "bundle-123"

    expected = canonical_hash(
        "jarvis:strategy-input:v1",
        {"chart_bundle_hash": "bundle-123", "strategy_id": "SWING_W150", "strategy_version": "v1"},
    )
    assert (
        strategy_input_hash(Bundle(), strategy_id="SWING_W150", strategy_version="v1") == expected
    )
    assert (
        strategy_input_hash(Bundle(), strategy_id="SWING_W150", strategy_version="v2") != expected
    )


def test_strategy_input_hash_changes_with_parameter_fingerprint():
    class Bundle:
        bundle_hash = "bundle-123"

    first = strategy_input_hash(
        Bundle(),
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_fingerprint="aaa",
    )
    second = strategy_input_hash(
        Bundle(),
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_fingerprint="bbb",
    )
    assert first != second
