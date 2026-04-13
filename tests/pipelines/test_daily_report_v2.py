# tests/pipelines/test_daily_report_v2.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from src.pipelines.daily_report_v2 import DailyReportV2Pipeline, STAGE_NAMES


def test_stage_names_order():
    assert STAGE_NAMES == ["ingest", "map", "shuffle", "catalyst", "synthesize"]


def test_stages_from_returns_correct_slice():
    pipeline = DailyReportV2Pipeline.__new__(DailyReportV2Pipeline)
    stages = pipeline._stages_from("shuffle")
    assert stages == ["shuffle", "catalyst", "synthesize"]


def test_stages_from_invalid_raises():
    pipeline = DailyReportV2Pipeline.__new__(DailyReportV2Pipeline)
    with pytest.raises(ValueError, match="Unknown stage"):
        pipeline._stages_from("invalid")


@pytest.mark.asyncio
async def test_run_single_stage_saves_cache(tmp_path):
    mock_ingest = AsyncMock()
    mock_ingest.run.return_value = MagicMock(
        model_dump=MagicMock(return_value={
            "telegram_messages": [], "macro_snapshot": {},
            "market_news": [], "kr_flow": [], "momentum": [],
        }),
    )

    pipeline = DailyReportV2Pipeline(
        ingest_stage=mock_ingest,
        map_stage=AsyncMock(),
        shuffle_stage=AsyncMock(),
        catalyst_stage=AsyncMock(),
        synthesize_stage=AsyncMock(),
        cache_base=tmp_path / ".cache" / "report",
    )

    await pipeline.run(stage="ingest")
    cache_files = list((tmp_path / ".cache" / "report").rglob("*.json"))
    assert any("1_ingest" in f.name for f in cache_files)
