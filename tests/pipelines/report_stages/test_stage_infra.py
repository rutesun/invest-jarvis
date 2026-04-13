# tests/pipelines/report_stages/test_stage_infra.py
import json
import pytest
from pathlib import Path
from src.pipelines.report_stages import StageCache


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / ".cache" / "report" / "2026-04-13"


def test_save_and_load_stage_result(cache_dir):
    cache = StageCache(cache_dir)
    data = {"themes": [{"name": "AI", "stocks": ["NVDA"]}]}
    cache.save("3_shuffle", data)

    loaded = cache.load("3_shuffle")
    assert loaded["themes"][0]["name"] == "AI"


def test_load_missing_stage_raises(cache_dir):
    cache = StageCache(cache_dir)
    with pytest.raises(FileNotFoundError):
        cache.load("2_map")


def test_has_stage(cache_dir):
    cache = StageCache(cache_dir)
    assert not cache.has("1_ingest")
    cache.save("1_ingest", {"data": True})
    assert cache.has("1_ingest")


def test_cache_dir_auto_created(tmp_path):
    cache_dir = tmp_path / "deep" / "nested" / "dir"
    cache = StageCache(cache_dir)
    cache.save("test", {"ok": True})
    assert cache.load("test") == {"ok": True}


def test_get_cache_dir_for_date():
    base = Path(".cache/report")
    result = StageCache.cache_dir_for_date(base, "2026-04-13")
    assert result == base / "2026-04-13"
