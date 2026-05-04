from src.pipelines.daily_report.models import (
    DailyReport,
    MacroSnapshot,
    OpsKnowledgeReport,
    ResearchDump,
)
from src.pipelines.daily_report.renderers import (
    render_main_report,
    render_ops_knowledge_report,
    render_research_dump,
)


def test_renderers_return_three_markdown_outputs():
    report = DailyReport(
        date="2026-05-05",
        macro=MacroSnapshot(
            date="2026-05-05",
            us_markets={"S&P500": 1.2},
            kr_markets={"KOSPI": 0.5},
            vix=18.0,
            fear_greed=55,
            krw_usd=1380.0,
        ),
        key_insights=["메모리 업황 혼재"],
        news=[],
    )
    assert render_main_report(report).startswith("# Daily Market Report")
    assert render_research_dump(ResearchDump(date="2026-05-05", markdown="# dump")) == "# dump"
    assert (
        render_ops_knowledge_report(
            OpsKnowledgeReport(date="2026-05-05", candidates=[], markdown="# ops")
        )
        == "# ops"
    )
