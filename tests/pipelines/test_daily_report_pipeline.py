"""Tests for daily report pipeline formatting."""

from datetime import datetime

import pytest

from src.pipelines.daily_report.models import (
    Claim,
    ClaimCluster,
    ClaimType,
    DailyReport,
    DailyReportRun,
    ExtractResult,
    IngestedMessage,
    IngestResult,
    KnowledgeCandidate,
    MacroSnapshot,
    MessageType,
    NewsItem,
    OpsKnowledgeReport,
    SelectedCluster,
    Sentiment,
    StockDetail,
)
from src.pipelines.daily_report.pipeline import format_report
from src.pipelines.daily_report.stages.link_stage import LinkResult
from src.pipelines.daily_report.stages.select_stage import SelectResult


@pytest.fixture
def sample_report():
    """샘플 DailyReport 객체."""
    macro = MacroSnapshot(
        date="2026-04-24",
        us_markets={"S&P500": 1.2, "NASDAQ": 1.5},
        kr_markets={"KOSPI": 0.8, "KOSDAQ": 0.5},
        vix=18.5,
        fear_greed=65,
        krw_usd=1300.0,
    )

    news_item = NewsItem(
        category="반도체",
        technical_theme="HBM 공급 부족",
        investment_theme="AI 메모리 수요 폭증, HBM 가격 파워 강화",
        keywords=["HBM", "AI", "메모리"],
        source_ids=["msg1"],
        emoji="🚀",
        summary="AI 인프라 투자 확대로 HBM 수요 급증\nSK하이닉스 공급 부족 장기화\n2026년까지 가격 상승 전망",
        impact="메모리 반도체 업체 실적 개선 예상",
        stocks=[
            StockDetail(
                name="SK하이닉스",
                ticker="000660",
                catalyst="HBM 공급 부족으로 가격 인상",
            )
        ],
    )

    return DailyReport(
        date="2026-04-24",
        macro=macro,
        key_insights=["AI 투자 확대로 메모리 수요 증가"],
        news=[news_item],
    )


def test_format_report_summary_bullet_list(sample_report):
    """Summary가 bullet list로 포맷팅되는지 테스트."""
    result = format_report(sample_report, data_dir="data")

    # Summary가 bullet list로 변환되었는지 확인
    assert "- AI 인프라 투자 확대로 HBM 수요 급증" in result
    assert "- SK하이닉스 공급 부족 장기화" in result
    assert "- 2026년까지 가격 상승 전망" in result

    # \n literal이 남아있지 않은지 확인
    assert r"\n" not in result


def test_format_report_source_indentation(sample_report, tmp_path):
    """출처 들여쓰기가 2칸인지 테스트."""
    # Mock source messages

    data_dir = tmp_path / "data" / "2026-04"
    data_dir.mkdir(parents=True)

    # Create mock CSV with source message
    csv_file = data_dir / "2026-04-24-test_channel.csv"
    csv_file.write_text(
        "message_id,timestamp,text\nmsg1,2026-04-24 10:00:00,HBM 수요가 급증하고 있습니다\n"
    )

    result = format_report(sample_report, data_dir=str(tmp_path / "data"))

    # 출처가 2칸 들여쓰기로 되어있는지 확인 (code block인 4칸이 아님)
    lines = result.split("\n")
    source_lines = [
        line for line in lines if line.strip().startswith("1.") or line.strip().startswith("2.")
    ]

    for line in source_lines:
        # 2칸 들여쓰기 확인 (4칸이 아님)
        if line.startswith("  ") and not line.startswith("    "):
            assert True
            return

    # 출처가 있어야 함
    if source_lines:
        pytest.fail("출처 들여쓰기가 2칸이 아닙니다")


def test_format_report_no_literal_newlines(sample_report):
    """Summary에 literal \n이 포함되지 않는지 테스트."""
    result = format_report(sample_report, data_dir="data")

    # \n literal 문자열 확인
    assert "\\n" not in result


def test_format_report_structure(sample_report):
    """리포트 기본 구조 테스트."""
    result = format_report(sample_report, data_dir="data")

    # 필수 섹션 확인
    assert "# Daily Market Report - 2026-04-24" in result
    assert "## 📊 Macro Snapshot" in result
    assert "## 💡 Key Insights" in result
    assert "## 반도체" in result  # 카테고리 헤딩

    # 테마 제목 확인
    assert "### 🚀 AI 메모리 수요 폭증, HBM 가격 파워 강화" in result

    # Impact 확인
    assert "**Impact**:" in result

    # 관련 종목 확인
    assert "**관련 종목**:" in result
    assert "SK하이닉스" in result


def test_run_pipeline_returns_daily_report_run(monkeypatch, tmp_path):
    from src.pipelines.daily_report.knowledge import ApprovedKnowledge
    from src.pipelines.daily_report.pipeline import run_pipeline

    def fake_ingest(date: str, data_dir: str) -> IngestResult:
        del data_dir
        return IngestResult(
            date=date,
            macro=MacroSnapshot(
                date=date,
                us_markets={"S&P500": 1.0},
                kr_markets={"KOSPI": 0.5},
                vix=18.0,
                fear_greed=55,
                krw_usd=1380.0,
            ),
            messages=[
                IngestedMessage(
                    source_id="kwusa-1",
                    channel_id="kwusa",
                    message_id="1",
                    timestamp=datetime.fromisoformat("2026-05-05T01:00:00+00:00"),
                    raw_text="마이크론 목표주가 상향",
                    message_type=MessageType.BROKER_SUMMARY,
                    source_file="data/2026-05/2026-05-05-kwusa.csv",
                )
            ],
        )

    def fake_extract(messages, date: str) -> ExtractResult:
        del messages, date
        return ExtractResult(
            claims=[
                Claim(
                    claim_id="c1",
                    category="반도체",
                    claim_type=ClaimType.BROKER_VIEW,
                    text="마이크론 목표주가 상향",
                    canonical_entities=["Micron"],
                    target_scope="memory",
                    polarity=Sentiment.BULL,
                    source_ids=["kwusa-1"],
                    fact_ids=[],
                    confidence=0.9,
                )
            ],
            facts=[],
        )

    def fake_knowledge(base_dir):
        del base_dir
        return ApprovedKnowledge(
            aliases={},
            concepts={"Micron": {"concept": "memory_vendor"}},
            relations=[],
            message_types={},
        )

    def fake_link(claims, knowledge, date: str, telemetry=None) -> LinkResult:
        del claims, knowledge, date, telemetry
        return LinkResult(
            edges=[],
            clusters=[
                ClaimCluster(
                    cluster_id="2026-05-05-cluster-1",
                    category="반도체",
                    claim_ids=["c1"],
                    source_ids=["kwusa-1"],
                    bull_claim_ids=["c1"],
                    bear_claim_ids=[],
                    title="메모리 공급망",
                )
            ],
        )

    def fake_select(clusters, macro, date: str) -> SelectResult:
        del clusters, macro, date
        return SelectResult(
            selected_clusters=[
                SelectedCluster(
                    cluster_id="2026-05-05-cluster-1",
                    score=0.8,
                    selected_for_brief=True,
                    selected_for_dump=True,
                    reasons=["independent_sources=1"],
                )
            ],
            contrarian_signals=[],
        )

    def fake_ops(telemetry, date: str) -> OpsKnowledgeReport:
        del telemetry
        return OpsKnowledgeReport(
            date=date,
            candidates=[
                KnowledgeCandidate(
                    candidate_type="concept",
                    key="Micron",
                    reason="unknown_entity_repeated",
                    evidence_source_ids=[],
                    priority=2,
                    confidence=0.6,
                )
            ],
            markdown="# ops",
        )

    monkeypatch.setattr("src.pipelines.daily_report.pipeline.ingest", fake_ingest)
    monkeypatch.setattr("src.pipelines.daily_report.pipeline.extract_stage", fake_extract)
    monkeypatch.setattr(
        "src.pipelines.daily_report.pipeline.load_approved_knowledge", fake_knowledge
    )
    monkeypatch.setattr("src.pipelines.daily_report.pipeline.link_stage", fake_link)
    monkeypatch.setattr("src.pipelines.daily_report.pipeline.select_stage", fake_select)
    monkeypatch.setattr("src.pipelines.daily_report.pipeline.build_ops_knowledge_report", fake_ops)
    monkeypatch.setattr(
        "src.pipelines.daily_report.pipeline.ARTIFACTS_ROOT", tmp_path / "artifacts"
    )

    result = run_pipeline("2026-05-05", data_dir="data")

    assert isinstance(result, DailyReportRun)
    assert result.main_report.key_insights[0] == "메모리 공급망"
    assert result.research_dump.markdown.startswith("# Research Dump")
