from pydantic import BaseModel, computed_field


class AccumulationResult(BaseModel):
    """오닐식 매집일/분산일 집계 (CAN SLIM I)."""

    accumulation_days: int
    distribution_days: int
    accumulation_ratio: float  # acc / (acc + dist); 분모 0이면 0.0
    window: int

    @computed_field
    @property
    def is_accumulating(self) -> bool:
        return self.accumulation_ratio > 0.5
