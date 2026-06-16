from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.models import DebateAdvocacyOutput, DebateCase, DebateVerdictOutput
from src.pipelines.debate.models import BullBearLedger, Evidence


def _make_adv():
    return DebateAdvocacyOutput(
        bull_case=DebateCase(stance="bull", thesis="강세", points=["게이트 A 통과"]),
        bear_case=DebateCase(stance="bear", thesis="약세", points=["VCP 미돌파"]),
    )


def _make_ver():
    return DebateVerdictOutput(
        action="매수", confidence=0.7, swing_factor="시장환경", reconciliation="bull 우세"
    )


@pytest.mark.asyncio
async def test_run_debate_bundle():
    from src.pipelines.debate.engine import run_debate

    ledger = BullBearLedger(
        mode="entry",
        bull=[
            Evidence(
                side="bull",
                key="gate_A",
                weight=4.0,
                headline="게이트 A",
                detail="상승장",
                source="playbook",
            )
        ],
        bear=[
            Evidence(
                side="bear",
                key="gate_E",
                weight=3.0,
                headline="게이트 E",
                detail="미돌파",
                source="playbook",
            )
        ],
        neutral=[],
        bull_weight=4.0,
        bear_weight=3.0,
        action_space=["매수", "관망"],
    )

    adv = _make_adv()
    ver = _make_ver()

    with (
        patch(
            "src.pipelines.debate.engine.run_debate_advocacy",
            new_callable=AsyncMock,
            return_value=adv,
        ),
        patch(
            "src.pipelines.debate.engine.run_debate_judge",
            new_callable=AsyncMock,
            return_value=ver,
        ),
    ):
        bundle = await run_debate(ledger, MagicMock(), ticker="TEST")

    assert bundle.verdict.action in ledger.action_space
    assert bundle.bull_case.thesis == "강세"
    assert bundle.ledger is ledger
