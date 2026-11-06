"""Exercise baseline-process cleanup with a real child, not a process double."""

import os
import signal
import subprocess
import sys

import pytest

from tests.harness.chart_analysis_contract import seeded_consumer_payload


def test_timeout_kills_and_reaps_the_consumer_before_reraising(monkeypatch, tmp_path):
    """A timed-out child must not finish its work or survive as an unreaped child."""
    finished = tmp_path / "consumer-finished"
    real_popen = subprocess.Popen
    children = []

    def start_slow_consumer(command, **kwargs):
        process = real_popen(
            [
                sys.executable,
                "-c",
                f"import time; time.sleep(0.4); open({str(finished)!r}, 'w').close()",
            ],
            **kwargs,
        )
        children.append(process)
        real_communicate = process.communicate

        def communicate(input=None, timeout=None):
            return real_communicate(input=input, timeout=0.01 if timeout is not None else None)

        monkeypatch.setattr(process, "communicate", communicate)
        return process

    monkeypatch.setattr(subprocess, "Popen", start_slow_consumer)
    with pytest.raises(subprocess.TimeoutExpired):
        seeded_consumer_payload("timeout-regression")

    child = children[0]
    assert child.returncode == -signal.SIGKILL
    assert not finished.exists()
    with pytest.raises(ChildProcessError):
        os.waitpid(child.pid, os.WNOHANG)
