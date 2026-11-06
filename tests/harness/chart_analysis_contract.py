"""Offline chart baseline contracts; never update expectations while testing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import isfinite
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel

from src.tools.technical.models import TechnicalResult


def assert_chart_fixture_contract(raw: pd.DataFrame, manifest: dict) -> None:
    """Reject input drift before a consumer runs, including undeclared missing data."""
    assert isinstance(raw.index, pd.DatetimeIndex)
    assert raw.index.is_monotonic_increasing and raw.index.is_unique
    assert list(raw.columns) == manifest["columns"]
    assert len(raw) == manifest["rows"]
    assert raw.index[0].date().isoformat() == manifest["actual_start"]
    assert raw.index[-1].date().isoformat() == manifest["actual_end"]
    assert manifest["provenance"]["kind"] in {"synthetic", "existing_market_fixture"}
    assert manifest["adjustment_policy"]
    values = raw.to_numpy(dtype=float)
    assert np.isfinite(values).all(), "Fixture contains missing/non-finite OHLCV"
    assert (raw["Volume"] >= 0).all()
    assert (raw["High"] >= raw[["Open", "Close", "Low"]].max(axis=1)).all()
    assert (raw["Low"] <= raw[["Open", "Close", "High"]].min(axis=1)).all()


def _plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return _plain(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, pd.DataFrame):
        return {
            "index": _plain(value.index.tolist()),
            "columns": value.columns.tolist(),
            "data": _plain(value.to_numpy().tolist()),
        }
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_plain(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, float) and not isfinite(value):
        # Missing numeric values must not collapse into semantic nulls.
        return {"$float": "nan" if np.isnan(value) else str(value)}
    return value


def baseline_payload(result: object, *, consumer: str) -> dict:
    """Keep every pre-refactor field; omit only TechnicalResult's wall-clock time."""
    if isinstance(result, TechnicalResult):
        result = result.model_dump(mode="python", exclude={"timestamp"})
    return {"consumer": consumer, "payload": _plain(result)}


def seeded_consumer_payload(case: str, *, common_analysis: bool = False) -> dict:
    """Preserve existing set-iteration order under a declared process hash seed."""
    root = Path(__file__).resolve().parents[2]
    code = """
import json, pathlib, sys
import src
from tests.conftest import chart_fixture
from tests.strategies.test_common_chart_parity import capture_case
assert pathlib.Path(src.__file__).resolve().parent == pathlib.Path.cwd() / 'src'
json.dump(capture_case(sys.argv[1], chart_fixture.__wrapped__(),
                       common_analysis=sys.argv[2] == "1"), sys.stdout,
          ensure_ascii=False, allow_nan=False)
"""
    environment = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(root)}
    with subprocess.Popen(
        [sys.executable, "-c", code, case, str(int(common_analysis))],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
    assert process.returncode == 0, stderr
    return json.loads(stdout)
