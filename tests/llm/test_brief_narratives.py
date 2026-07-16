"""generate_brief_narratives — LLM 목으로 프롬프트 조립·구조화 출력 검증."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.analyzer import generate_brief_narratives
from src.llm.models import BriefNarrativesOutput, TickerNarrative


@pytest.mark.asyncio
async def test_generate_brief_narratives_returns_structured_output():
    expected = BriefNarrativesOutput(
        narratives=[
            TickerNarrative(
                ticker="NVDA",
                technical_note="Stage2 7/7 충족, VCP 돌파 확인.",
                flow_note=None,
                news_note="신규 수주 발표가 돌파를 뒷받침.",
                next_check="진입 후 stop 152.0 관리.",
            )
        ]
    )
    # 기존 analyzer 테스트 패턴: prompt | chain 은 실제 ChatPromptTemplate.__or__를
    # 타므로, ChatPromptTemplate를 patch해 __or__가 목 체인을 반환하게 한다.
    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_prompt_class:
        mock_prompt = MagicMock()
        mock_prompt_class.from_messages.return_value = mock_prompt

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=expected)
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        mock_llm = MagicMock()

        result = await generate_brief_narratives('{"items": []}', llm=mock_llm)

    assert isinstance(result, BriefNarrativesOutput)
    assert result.narratives[0].ticker == "NVDA"
    mock_llm.with_structured_output.assert_called_once()
    mock_chain.ainvoke.assert_awaited_once()
