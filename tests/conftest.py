"""Global test configuration."""

from unittest.mock import patch

import pytest


@pytest.fixture(scope="session")
def chart_fixture():
    """Load fixed local input only after checking its bytes and shape contract."""
    import hashlib
    import json
    from pathlib import Path

    import pandas as pd

    from tests.harness.chart_analysis_contract import assert_chart_fixture_contract

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "tests/fixtures/chart_analysis/manifest.json").read_text())

    def load(name):
        entry = manifest["inputs"][name]
        path = root / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], name
        raw = pd.read_csv(path, index_col="Date", parse_dates=True)
        assert_chart_fixture_contract(raw, entry)
        return raw

    return load


@pytest.fixture(autouse=True)
def _isolate_entry_shadow_log(monkeypatch, tmp_path):
    """Keep synthetic strategy decisions out of the product research log."""
    monkeypatch.setenv("JARVIS_ENTRY_SHADOW_LOG_PATH", str(tmp_path / "entry-shadow.jsonl"))


@pytest.fixture(autouse=True)
def _no_chart_open():
    """Prevent tests from opening chart files in the system viewer."""
    with patch("subprocess.run"):
        yield
