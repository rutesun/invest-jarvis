"""Global test configuration."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_entry_shadow_log(monkeypatch, tmp_path):
    """Keep synthetic strategy decisions out of the product research log."""
    monkeypatch.setenv("JARVIS_ENTRY_SHADOW_LOG_PATH", str(tmp_path / "entry-shadow.jsonl"))


@pytest.fixture(autouse=True)
def _no_chart_open():
    """Prevent tests from opening chart files in the system viewer."""
    with patch("subprocess.run"):
        yield
