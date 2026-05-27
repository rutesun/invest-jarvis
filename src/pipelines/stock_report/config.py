from __future__ import annotations

import os
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.llm.provider import LLMProvider


@dataclass(frozen=True)
class SemanticExtractionLLMConfig:
    provider: str
    model: str | None = None
    temperature: float = 0.1

    def create_llm(self) -> BaseChatModel:
        return LLMProvider.create(
            provider=self.provider,
            model=self.model,
            temperature=self.temperature,
        )

    def build_messages(self, system_prompt: str, user_prompt: str) -> list[BaseMessage]:
        kwargs = {}
        if self.provider == "anthropic":
            kwargs["cache_control"] = {"type": "ephemeral"}
        return [
            SystemMessage(content=system_prompt, additional_kwargs=kwargs),
            HumanMessage(content=user_prompt),
        ]


StockReportLLMConfig = SemanticExtractionLLMConfig


def get_semantic_extraction_llm_config(provider: str) -> SemanticExtractionLLMConfig:
    model: str | None = None
    if provider == "openai":
        model = (
            os.getenv("STOCK_REPORT_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.4-mini"
        )
    elif provider == "anthropic":
        model = os.getenv("STOCK_REPORT_ANTHROPIC_MODEL") or os.getenv("ANTHROPIC_MODEL")
    return SemanticExtractionLLMConfig(provider=provider, model=model, temperature=0.1)


def get_report_synthesis_llm_config(provider: str) -> StockReportLLMConfig:
    model: str | None = None
    if provider == "openai":
        model = (
            os.getenv("STOCK_REPORT_SYNTHESIS_OPENAI_MODEL")
            or os.getenv("STOCK_REPORT_OPENAI_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "gpt-5.4"
        )
    elif provider == "anthropic":
        model = (
            os.getenv("STOCK_REPORT_SYNTHESIS_ANTHROPIC_MODEL")
            or os.getenv("STOCK_REPORT_ANTHROPIC_MODEL")
            or os.getenv("ANTHROPIC_MODEL")
        )
    return StockReportLLMConfig(provider=provider, model=model, temperature=0.1)


SEMANTIC_EXTRACTION_MAX_CONCURRENCY = 8
SEMANTIC_EXTRACTION_TIMEOUT_SECONDS = 180.0
SEMANTIC_EXTRACTION_MAX_RETRIES = 3
