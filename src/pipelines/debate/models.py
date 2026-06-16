from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.models import DebateCase, DebateVerdictOutput


class Evidence(BaseModel):
    side: str  # "bull" | "bear" | "neutral"
    key: str
    weight: float  # 0~5
    headline: str
    detail: str
    source: str  # "playbook" | "factor" | "flow" | "technical"
    kind: str = "signal"  # "signal" | "gate"


class BullBearLedger(BaseModel):
    mode: str  # "entry" | "holding"
    bull: list[Evidence] = Field(default_factory=list)
    bear: list[Evidence] = Field(default_factory=list)
    neutral: list[Evidence] = Field(default_factory=list)
    bull_weight: float = 0.0
    bear_weight: float = 0.0
    action_space: list[str] = Field(default_factory=list)


class DebateBundle(BaseModel):
    ledger: BullBearLedger
    bull_case: DebateCase
    bear_case: DebateCase
    verdict: DebateVerdictOutput
