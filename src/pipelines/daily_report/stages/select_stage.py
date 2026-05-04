"""Select stage: rank clusters for brief/dump and surface contrarian signals."""

from pydantic import BaseModel

from src.pipelines.daily_report.models import (
    ClaimCluster,
    ContrarianSignal,
    MacroSnapshot,
    SelectedCluster,
)


class SelectResult(BaseModel):
    selected_clusters: list[SelectedCluster]
    contrarian_signals: list[ContrarianSignal]


def _score_cluster(cluster: ClaimCluster) -> tuple[float, list[str]]:
    score = min(len(set(cluster.source_ids)) * 0.2, 0.6)
    reasons = [f"independent_sources={len(set(cluster.source_ids))}"]

    if cluster.bull_claim_ids and cluster.bear_claim_ids:
        score += 0.2
        reasons.append("mixed_signal")

    if len(cluster.claim_ids) == 1 and "목표가" in cluster.title:
        score -= 0.15
        reasons.append("broker_only_penalty")

    return max(score, 0.0), reasons


def select_stage(clusters: list[ClaimCluster], macro: MacroSnapshot, date: str) -> SelectResult:
    del macro, date  # reserved for macro-aware scoring in the next step
    ranked: list[SelectedCluster] = []
    contrarian: list[ContrarianSignal] = []

    for cluster in clusters:
        score, reasons = _score_cluster(cluster)
        ranked.append(
            SelectedCluster(
                cluster_id=cluster.cluster_id,
                score=score,
                selected_for_brief=True,
                selected_for_dump=True,
                reasons=reasons,
            )
        )
        if cluster.bull_claim_ids and cluster.bear_claim_ids:
            contrarian.append(
                ContrarianSignal(
                    cluster_id=cluster.cluster_id,
                    summary=f"{cluster.title}: bull/bear 근거 공존",
                    supporting_claim_ids=cluster.claim_ids,
                )
            )

    return SelectResult(
        selected_clusters=sorted(ranked, key=lambda item: item.score, reverse=True),
        contrarian_signals=contrarian,
    )
