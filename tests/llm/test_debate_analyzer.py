from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.models import (
    DebateAdvocacyInput,
    DebateAdvocacyOutput,
    DebateCase,
    DebateJudgeInput,
    DebateVerdictOutput,
)


def _make_mock_llm(output):
    """ChatPromptTemplate 패치 없이 LLM 체인을 직접 mock."""
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=output)

    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=mock_chain)

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock()

    return mock_prompt, mock_llm, mock_chain


@pytest.mark.asyncio
async def test_run_debate_advocacy():
    from src.llm.analyzer import run_debate_advocacy

    adv = DebateAdvocacyOutput(
        bull_case=DebateCase(stance="bull", thesis="강세", points=["p"]),
        bear_case=DebateCase(stance="bear", thesis="약세", points=["q"]),
    )
    mock_prompt, mock_llm, _ = _make_mock_llm(adv)

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_cls:
        mock_cls.from_messages.return_value = mock_prompt
        out = await run_debate_advocacy(
            DebateAdvocacyInput(
                ticker="T",
                mode="entry",
                bull_evidence=[{"headline": "게이트 A", "detail": "상승장"}],
                bear_evidence=[],
            ),
            mock_llm,
        )
    assert out.bull_case.thesis == "강세"


@pytest.mark.asyncio
async def test_run_debate_judge():
    from src.llm.analyzer import run_debate_judge

    ver = DebateVerdictOutput(
        action="매수", confidence=0.72, swing_factor="VCP", reconciliation="bull 우세"
    )
    mock_prompt, mock_llm, _ = _make_mock_llm(ver)

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_cls:
        mock_cls.from_messages.return_value = mock_prompt
        out = await run_debate_judge(
            DebateJudgeInput(
                ticker="T",
                mode="entry",
                bull_case=DebateCase(stance="bull", thesis="t", points=["p"]),
                bear_case=DebateCase(stance="bear", thesis="t", points=["q"]),
                bull_weight=12.0,
                bear_weight=4.0,
                allowed_actions=["매수", "관망"],
            ),
            mock_llm,
        )
    assert out.action in ["매수", "관망"]
