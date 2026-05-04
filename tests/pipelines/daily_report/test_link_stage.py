from src.pipelines.daily_report.knowledge import ApprovedKnowledge
from src.pipelines.daily_report.models import Claim, ClaimType
from src.pipelines.daily_report.stages.link_stage import link_stage


def test_link_stage_clusters_memory_and_packaging_but_splits_fx():
    claims = [
        Claim(
            claim_id="c1",
            category="반도체",
            claim_type=ClaimType.FACT,
            text="HBM4 베이스다이 확대",
            canonical_entities=["HBM4"],
            target_scope="memory_cycle",
            polarity="bull",
            source_ids=["growth-1"],
            fact_ids=[],
            confidence=0.9,
        ),
        Claim(
            claim_id="c2",
            category="반도체",
            claim_type=ClaimType.FACT,
            text="CoWoS 패키징 ramp",
            canonical_entities=["CoWoS"],
            target_scope="packaging",
            polarity="bull",
            source_ids=["kwusa-2"],
            fact_ids=[],
            confidence=0.9,
        ),
        Claim(
            claim_id="c3",
            category="매크로",
            claim_type=ClaimType.MARKET_DATA,
            text="달러원 1473원",
            canonical_entities=["KRWUSD"],
            target_scope="fx",
            polarity="bear",
            source_ids=["brain-3"],
            fact_ids=[],
            confidence=0.9,
        ),
    ]
    knowledge = ApprovedKnowledge(
        aliases={},
        concepts={
            "HBM4": {"concept": "memory"},
            "CoWoS": {"concept": "advanced_packaging"},
            "KRWUSD": {"concept": "fx"},
        },
        relations=[{"from": "memory", "to": "advanced_packaging", "weight": 0.7}],
        message_types={},
    )

    result = link_stage(claims, knowledge, date="2026-04-29")

    assert len(result.clusters) == 2
    assert sorted(len(cluster.claim_ids) for cluster in result.clusters) == [1, 2]
