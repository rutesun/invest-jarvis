"""LLM provider factory for creating langchain chat models."""
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel


class LLMProvider:
    """Factory for creating LLM instances."""

    @staticmethod
    def create(
        provider: Literal["openai", "anthropic"] = "openai",
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0,
    ) -> BaseChatModel:
        """Create LLM instance based on provider."""
        if provider == "openai":
            return LLMProvider._create_openai(
                api_key=api_key,
                model=model or "gpt-4o",
                base_url=base_url,
                temperature=temperature,
            )
        elif provider == "anthropic":
            return LLMProvider._create_anthropic(
                api_key=api_key,
                model=model or "claude-3-5-sonnet-20241022",
                base_url=base_url,
                temperature=temperature,
            )
        raise ValueError(f"Unsupported provider: {provider}")

    @staticmethod
    def _create_openai(
        api_key: str | None,
        model: str,
        base_url: str | None,
        temperature: float,
    ) -> ChatOpenAI:
        """Create OpenAI chat model."""
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            seed=42,
        )

    @staticmethod
    def _create_anthropic(
        api_key: str | None,
        model: str,
        base_url: str | None,
        temperature: float,
    ) -> ChatAnthropic:
        """Create Anthropic chat model."""
        return ChatAnthropic(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
        )
