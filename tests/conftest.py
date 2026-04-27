"""Global test configuration."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_chart_open():
    """Prevent tests from opening chart files in the system viewer."""
    with patch("subprocess.run"):
        yield
