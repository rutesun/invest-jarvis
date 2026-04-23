from unittest.mock import AsyncMock

import pytest

from src.llm.retry import invoke_llm_with_retry


@pytest.mark.asyncio
async def test_invoke_llm_with_retry_success():
    """Test successful LLM invocation without retries."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke.return_value = "Success"

    result = await invoke_llm_with_retry(
        chain=mock_chain, input_data={"test": "data"}, max_retries=3, backoff_factor=0.1
    )

    assert result == "Success"
    assert mock_chain.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_invoke_llm_with_retry_transient_error():
    """Test retry on transient errors."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke.side_effect = [
        Exception("Transient error"),
        Exception("Another transient error"),
        "Success",
    ]

    result = await invoke_llm_with_retry(
        chain=mock_chain, input_data={"test": "data"}, max_retries=3, backoff_factor=0.01
    )

    assert result == "Success"
    assert mock_chain.ainvoke.call_count == 3


@pytest.mark.asyncio
async def test_invoke_llm_with_retry_max_retries_exceeded():
    """Test failure after exceeding max retries."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke.side_effect = Exception("Persistent error")

    with pytest.raises(Exception, match="Persistent error"):
        await invoke_llm_with_retry(
            chain=mock_chain, input_data={"test": "data"}, max_retries=2, backoff_factor=0.01
        )

    assert mock_chain.ainvoke.call_count == 2  # max_retries attempts
