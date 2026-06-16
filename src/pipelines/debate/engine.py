from __future__ import annotations

from src.llm.analyzer import run_debate_advocacy, run_debate_judge
from src.llm.models import DebateAdvocacyInput, DebateJudgeInput
from src.pipelines.debate.models import BullBearLedger, DebateBundle


async def run_debate(ledger: BullBearLedger, llm, *, ticker: str = "") -> DebateBundle:
    """① 변론 콜 → ② 독립 판사 콜 → DebateBundle."""
    advocacy = await run_debate_advocacy(
        DebateAdvocacyInput(
            ticker=ticker,
            mode=ledger.mode,
            bull_evidence=[{"headline": e.headline, "detail": e.detail} for e in ledger.bull],
            bear_evidence=[{"headline": e.headline, "detail": e.detail} for e in ledger.bear],
        ),
        llm,
    )
    verdict = await run_debate_judge(
        DebateJudgeInput(
            ticker=ticker,
            mode=ledger.mode,
            bull_case=advocacy.bull_case,
            bear_case=advocacy.bear_case,
            bull_weight=ledger.bull_weight,
            bear_weight=ledger.bear_weight,
            allowed_actions=ledger.action_space,
        ),
        llm,
    )
    return DebateBundle(
        ledger=ledger,
        bull_case=advocacy.bull_case,
        bear_case=advocacy.bear_case,
        verdict=verdict,
    )
