from src.pipelines.daily_report.models import ClaimCluster, MacroSnapshot
from src.pipelines.daily_report.stages.select_stage import select_stage


def test_select_stage_penalizes_broker_only_cluster():
    clusters = [
        ClaimCluster(
            cluster_id="broker-only",
            category="반도체",
            claim_ids=["c1"],
            source_ids=["kwusa-1"],
            bull_claim_ids=["c1"],
            bear_claim_ids=[],
            title="목표가 상향",
        ),
        ClaimCluster(
            cluster_id="mixed-memory",
            category="반도체",
            claim_ids=["c2", "c3"],
            source_ids=["growth-1", "kwusa-2"],
            bull_claim_ids=["c2"],
            bear_claim_ids=["c3"],
            title="메모리 업황 혼재",
        ),
    ]
    macro = MacroSnapshot(
        date="2026-04-29",
        us_markets={"S&P500": 1.0},
        kr_markets={"KOSPI": 0.2},
        vix=18.0,
        fear_greed=55,
        krw_usd=1473.0,
    )

    result = select_stage(clusters, macro, date="2026-04-29")

    assert result.selected_clusters[0].cluster_id == "mixed-memory"
    assert result.contrarian_signals[0].cluster_id == "mixed-memory"
