"""LLM client wrapper that combines provider and analyzer."""
from typing import Literal
from langchain_core.language_models import BaseChatModel
from src.llm.provider import LLMProvider
from src.llm import analyzer
from src.llm.models import (
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


class LLMClient:
    """
    High-level LLM client for financial analysis.

    Combines LLMProvider (model creation) and analyzer functions.
    Allows switching LLM models flexibly.
    """

    def __init__(
        self,
        provider: Literal["openai", "anthropic"] = "openai",
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0,
    ):
        """Initialize LLM client with a default LLM instance."""
        self.default_llm = LLMProvider.create(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
        )

    async def analyze_news(
        self,
        input_data: NewsAnalysisInput,
        llm: BaseChatModel | None = None,
    ) -> NewsAnalysisOutput:
        """
        Analyze news sentiment and impact.

        Args:
            input_data: News analysis input
            llm: Optional custom LLM to use. If None, uses default LLM.

        Returns:
            News analysis output
        """
        model = llm or self.default_llm
        return await analyzer.analyze_news(input_data, model)

    async def generate_technical_summary(
        self,
        input_data: TechnicalSummaryInput,
        llm: BaseChatModel | None = None,
    ) -> TechnicalSummaryOutput:
        """
        Generate technical analysis summary.

        Args:
            input_data: Technical analysis input
            llm: Optional custom LLM to use. If None, uses default LLM.

        Returns:
            Technical summary output
        """
        model = llm or self.default_llm
        return await analyzer.generate_technical_summary(input_data, model)
