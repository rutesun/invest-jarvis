from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel

from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry


class _Output(BaseModel):
    value: str


class _NeverRespondingChain:
    async def ainvoke(self, messages, config=None):  # type: ignore[no-untyped-def]
        import asyncio

        await asyncio.sleep(10)


class _NeverRespondingLLM:
    def with_structured_output(self, output_model):  # type: ignore[no-untyped-def]
        return _NeverRespondingChain()


@pytest.mark.asyncio
async def test_invoke_llm_with_retry_logs_stage_and_metadata_on_timeout(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="src.pipelines.daily_report.llm_utils")

    with pytest.raises(TimeoutError):
        await invoke_llm_with_retry(
            _NeverRespondingLLM(),
            _Output,
            messages=[],
            config={
                "run_name": "StockReport Local Evidence Synthesis - 2026-05-26",
                "metadata": {
                    "stage": "local_evidence_synthesis",
                    "model": "gpt-5.4-mini",
                    "report_date": "2026-05-26",
                    "chunk_count": 110,
                },
            },
            max_retries=1,
            timeout_seconds=0.01,
        )

    log_text = caplog.text
    assert "stage=local_evidence_synthesis" in log_text
    assert "model=gpt-5.4-mini" in log_text
    assert "report_date=2026-05-26" in log_text
    assert "chunk_count=110" in log_text
