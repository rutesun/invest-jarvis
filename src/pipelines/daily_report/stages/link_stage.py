"""Link stage: score claim edges and build deterministic clusters."""

from collections import defaultdict

from pydantic import BaseModel

from src.pipelines.daily_report.knowledge import ApprovedKnowledge
from src.pipelines.daily_report.models import Claim, ClaimCluster, ClaimEdge
from src.pipelines.daily_report.telemetry import StageTelemetry


class LinkResult(BaseModel):
    edges: list[ClaimEdge]
    clusters: list[ClaimCluster]


def _edge_score(
    left: Claim, right: Claim, knowledge: ApprovedKnowledge
) -> tuple[float, list[str], bool]:
    score = 0.0
    reasons: list[str] = []
    contradiction = left.target_scope == right.target_scope and left.polarity != right.polarity

    if left.category == right.category:
        score += 0.10
        reasons.append("same_category")

    if set(left.canonical_entities) & set(right.canonical_entities):
        score += 0.25
        reasons.append("shared_entity")

    left_concepts = {
        knowledge.concepts.get(entity, {}).get("concept") for entity in left.canonical_entities
    }
    right_concepts = {
        knowledge.concepts.get(entity, {}).get("concept") for entity in right.canonical_entities
    }

    left_concepts.discard(None)
    right_concepts.discard(None)

    if left_concepts & right_concepts:
        score += 0.30
        reasons.append("shared_concept")

    for relation in knowledge.relations:
        if (
            relation["from"] in left_concepts
            and relation["to"] in right_concepts
            or relation["from"] in right_concepts
            and relation["to"] in left_concepts
        ):
            score += float(relation["weight"])
            reasons.append("approved_relation")

    return min(score, 1.0), reasons, contradiction


def link_stage(
    claims: list[Claim],
    knowledge: ApprovedKnowledge,
    date: str,
    telemetry: StageTelemetry | None = None,
) -> LinkResult:
    edges: list[ClaimEdge] = []
    parents = {claim.claim_id: claim.claim_id for claim in claims}

    if telemetry is not None:
        for claim in claims:
            for entity in claim.canonical_entities:
                if entity not in knowledge.concepts:
                    telemetry.record_unknown_entity(entity)

    def find(claim_id: str) -> str:
        while parents[claim_id] != claim_id:
            parents[claim_id] = parents[parents[claim_id]]
            claim_id = parents[claim_id]
        return claim_id

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root != right_root:
            parents[right_root] = left_root

    for index, left in enumerate(claims):
        for right in claims[index + 1 :]:
            score, reasons, contradiction = _edge_score(left, right, knowledge)
            if score <= 0:
                continue
            if telemetry is not None and 0.35 <= score < 0.65:
                telemetry.record_low_confidence_edge(left.claim_id, right.claim_id, score)
            edges.append(
                ClaimEdge(
                    left_claim_id=left.claim_id,
                    right_claim_id=right.claim_id,
                    score=score,
                    reasons=reasons,
                    contradiction=contradiction,
                )
            )
            if score >= 0.65:
                union(left.claim_id, right.claim_id)

    grouped: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        grouped[find(claim.claim_id)].append(claim)

    clusters: list[ClaimCluster] = []
    for idx, grouped_claims in enumerate(grouped.values(), start=1):
        clusters.append(
            ClaimCluster(
                cluster_id=f"{date}-cluster-{idx}",
                category=grouped_claims[0].category,
                claim_ids=[claim.claim_id for claim in grouped_claims],
                source_ids=[
                    source_id for claim in grouped_claims for source_id in claim.source_ids
                ],
                bull_claim_ids=[
                    claim.claim_id for claim in grouped_claims if claim.polarity == "bull"
                ],
                bear_claim_ids=[
                    claim.claim_id for claim in grouped_claims if claim.polarity == "bear"
                ],
                title=grouped_claims[0].target_scope,
            )
        )

    return LinkResult(edges=edges, clusters=clusters)
