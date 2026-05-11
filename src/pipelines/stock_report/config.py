from __future__ import annotations

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


def get_semantic_extraction_llm_config(provider: str) -> SemanticExtractionLLMConfig:
    return SemanticExtractionLLMConfig(provider=provider, temperature=0.1)


SEMANTIC_EXTRACTION_MAX_CONCURRENCY = 8
SEMANTIC_EXTRACTION_TIMEOUT_SECONDS = 180.0
SEMANTIC_EXTRACTION_MAX_RETRIES = 3
