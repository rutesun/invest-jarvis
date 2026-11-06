"""Chart integration uses only the current technical frame and local rendering."""

from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from PIL import Image

from src.core.models import ToolResult
from src.pipelines.quick_check import QuickCheckPipeline
from src.tools.technical.charting import ChartResult, _right_value_labels
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


@pytest.fixture
def _no_chart_open():
    """이 renderer는 viewer를 열지 않는다. 실제 font 조회 subprocess는 허용한다."""
    yield


def technical():
    n = 230
    df = pd.DataFrame(
        {
            "Open": [100.0] * n,
            "High": [105.0] * n,
            "Low": [95.0] * n,
            "Close": [102.0] * n,
            "Volume": [1000000] * n,
            "SMA_20": [100.5] * n,
            "SMA_150": [99.0] * n,
        },
        index=pd.bdate_range("2025-01-01", periods=n),
    )
    return TechnicalResult(
        ticker="TEST",
        snapshot=IndicatorSnapshot(price=102, change_pct=2),
        total_score=0,
        timestamp=datetime(2026, 11, 4),
        components={},
        raw_dataframe=df,
    )


def test_render_reuses_current_frame_snapshot_and_200_bar_renderer(monkeypatch):
    import src.pipelines.check_chart as module

    tech = technical()
    before = tech.raw_dataframe.copy(deep=True)
    seen = {}

    def renderer(**kwargs):
        seen.update(kwargs)
        assert kwargs["indicators"] == tech.snapshot.model_dump()
        assert kwargs["window_days"] == 200
        assert "support_levels" in kwargs["price_levels"]
        pd.testing.assert_frame_equal(kwargs["df"], before)
        # Mutation in local pattern/chart processing must not escape to the result.
        kwargs["df"].iloc[0, 0] = 1
        target = Path(kwargs["out_dir"]) / "chart.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        return ChartResult(ticker=kwargs["ticker"], path=str(target), success=True)

    monkeypatch.setattr(module, "render_technical_chart", renderer)
    png, warning = module.render_check_chart("../../ALAB", tech)
    assert png.startswith(b"\x89PNG") and warning is None
    assert not Path(seen["out_dir"]).exists()
    assert "/" not in seen["ticker"] and ".." not in seen["ticker"]
    pd.testing.assert_frame_equal(tech.raw_dataframe, before)


def test_real_chart_is_valid_png_and_missing_raw_is_nonfatal():
    from src.pipelines.check_chart import render_check_chart

    tech = technical()
    png, warning = render_check_chart("161890.KS", tech)
    assert warning is None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(png)) as image:
        assert image.width > 500 and image.height > 300
        image.verify()
    tech.raw_dataframe = None
    assert render_check_chart("TEST", tech)[0] is None
    assert render_check_chart("TEST", tech)[1]


@pytest.mark.parametrize(
    ("ticker", "expected"), [("ALAB", "MA20: $100.5"), ("161890.KS", "MA20: ₩100")]
)
def test_moving_average_labels_follow_market_currency(ticker, expected):
    from unittest.mock import MagicMock

    ax = MagicMock()
    _right_value_labels(None, ax, technical().raw_dataframe, ticker=ticker)
    assert expected in ax.text.call_args.args[2]


def test_chart_render_failure_returns_warning(monkeypatch):
    import src.pipelines.check_chart as module

    monkeypatch.setattr(
        module,
        "render_technical_chart",
        lambda **kw: ChartResult(kw["ticker"], "", False, "renderer failed"),
    )
    png, warning = module.render_check_chart("TEST", technical())
    assert png is None and "renderer failed" in warning


@pytest.mark.asyncio
async def test_quick_check_chart_is_opt_in_and_failure_keeps_text(monkeypatch):
    import src.pipelines.check_chart as module

    tool = AsyncMock()
    tool.execute.return_value = ToolResult(success=True, data=technical())
    calls = []

    def chart(ticker, tech):
        calls.append(ticker)
        return None, "차트 실패"

    monkeypatch.setattr(module, "render_check_chart", chart)
    pipeline = QuickCheckPipeline(tool)
    default = await pipeline.run("TEST")
    assert not calls and "chart_png" not in default
    result = await pipeline.run("TEST", include_chart=True)
    assert result["success"] and result["price"] == 102
    assert result["chart_warning"] == "차트 실패" and result["chart_png"] is None


def test_partial_technical_without_raw_attribute_returns_warning():
    from types import SimpleNamespace

    from src.pipelines.check_chart import render_check_chart

    png, warning = render_check_chart("PARTIAL", SimpleNamespace())
    assert png is None and "raw" in warning


@pytest.mark.asyncio
async def test_brief_metadata_is_opt_in_and_helper_failure_preserves_all_existing_output(
    monkeypatch,
):
    import src.pipelines.check_chart as chart_module
    import src.tools.technical.chart_brief as brief_module

    tool = AsyncMock()
    tool.execute.return_value = ToolResult(success=True, data=technical())
    monkeypatch.setattr(chart_module, "render_check_chart", lambda *args: (b"png", None))
    pipeline = QuickCheckPipeline(tool)
    default = await pipeline.run("TEST")
    text = pipeline.format_output(default)
    assert "chart_brief" not in default and "chart_brief_warning" not in default
    html_result = await pipeline.run("TEST", include_chart=True)
    assert html_result["chart_brief"]["as_of"] == "2025-11-18"
    assert pipeline.format_output(html_result) == text
    for key in default:
        assert html_result[key] == default[key]

    def fail(*args, **kwargs):
        raise ValueError("bad <input>")

    monkeypatch.setattr(brief_module, "build_chart_brief", fail)
    failed = await pipeline.run("TEST", include_chart=True)
    assert failed["chart_png"] == b"png" and failed["chart_brief"] is None
    assert "브리핑 미산출" in failed["chart_brief_warning"]
    assert pipeline.format_output(failed) == text


@pytest.mark.asyncio
async def test_html_brief_reads_same_day_strategy_manifest_without_serialization_change(
    monkeypatch,
):
    from dataclasses import replace

    import src.pipelines.quick_check as module
    from tests.pipelines.test_observation_story import alab
    from tests.tools.technical.test_chart_brief import technical as brief_technical

    tech = brief_technical(finality="UNKNOWN")
    analysis = alab()
    known = replace(
        tech.common_analyses[0],
        manifest=replace(tech.common_analyses[0].manifest, finality="FINAL"),
    )
    analysis.strategy_run.common_analyses = {known.analysis_id: known}
    before = analysis.strategy_run.model_dump()
    monkeypatch.setattr(module, "evaluate_optional", AsyncMock(return_value=(analysis, None)))
    monkeypatch.setattr(
        "src.pipelines.check_chart.render_check_chart", lambda *args: (b"png", None)
    )
    tool = AsyncMock()
    tool.execute.return_value = ToolResult(success=True, data=tech)
    result = await QuickCheckPipeline(tool).run("TEST", include_chart=True)
    assert result["chart_brief"]["finality"] == "FINAL"
    assert analysis.strategy_run.model_dump() == before
    assert tech.common_analyses[0].manifest.finality == "UNKNOWN"
