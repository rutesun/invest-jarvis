"""Telemetry container for stage-level self-review and ops reporting."""

from pydantic import BaseModel, Field


class StageTelemetry(BaseModel):
    unknown_entities: list[str] = Field(default_factory=list)
    low_confidence_edges: list[dict[str, str | float]] = Field(default_factory=list)
    counters: dict[str, int] = Field(default_factory=dict)

    def increment(self, key: str, value: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + value

    def record_unknown_entity(self, entity: str) -> None:
        self.unknown_entities.append(entity)
        self.increment("unknown_entity_count")

    def record_low_confidence_edge(
        self, left_claim_id: str, right_claim_id: str, score: float
    ) -> None:
        self.low_confidence_edges.append(
            {"left_claim_id": left_claim_id, "right_claim_id": right_claim_id, "score": score}
        )
        self.increment("low_confidence_edge_count")
