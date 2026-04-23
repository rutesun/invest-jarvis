"""Generic LLM retry utility for structured output chains."""

import asyncio
import logging
from typing import Any


logger = logging.getLogger(__name__)


async def invoke_llm_with_retry(
    chain: Any,
    input_data: dict[str, Any],
    max_retries: int = 3,
    backoff_factor: float = 1.0,
) -> Any:
    """
    Invoke LLM chain with exponential backoff retry.

    Args:
        chain: LangChain runnable (e.g., prompt | llm.with_structured_output())
        input_data: Input dictionary for chain.ainvoke()
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Backoff multiplier for exponential delay (default: 1.0)

    Returns:
        Structured output from the chain

    Raises:
        Last exception encountered if all retries fail
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            response = await chain.ainvoke(input_data)
            return response
        except Exception as e:
            last_exception = e
            logger.warning(
                "LLM call failed (attempt %d/%d): %s",
                attempt + 1,
                max_retries,
                e,
            )

            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2**attempt)
                await asyncio.sleep(wait_time)

    raise last_exception
