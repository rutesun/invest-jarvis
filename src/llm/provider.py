"""LLM provider factory for creating langchain chat models."""

import os
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


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
            default_model = os.getenv("OPENAI_MODEL", "gpt-4o")
            return LLMProvider._create_openai(
                api_key=api_key,
                model=model or default_model,
                base_url=base_url,
                temperature=temperature,
            )
        elif provider == "anthropic":
            default_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
            use_bedrock = os.getenv("CLAUDE_CODE_USE_BEDROCK", "0") == "1"

            if use_bedrock:
                return LLMProvider._create_bedrock(
                    model=model or default_model,
                    temperature=temperature,
                )
            else:
                return LLMProvider._create_anthropic(
                    api_key=api_key,
                    model=model or default_model,
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

    @staticmethod
    def _create_bedrock(
        model: str,
        temperature: float,
    ) -> BaseChatModel:
        """Create Bedrock chat model with custom endpoint."""

        import boto3
        from botocore.config import Config
        from langchain_aws import ChatBedrockConverse

        # 환경 변수에서 Bedrock 설정 읽기
        region = os.getenv("AWS_REGION", "us-east-1")
        endpoint_url = os.getenv("ANTHROPIC_BEDROCK_BASE_URL")
        session_token = os.getenv("AWS_SESSION_TOKEN")
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "anything_is_fine")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "anything_is_fine")
        timeout_ms = int(os.getenv("API_TIMEOUT_MS", "600000"))

        # boto3 클라이언트 생성
        bedrock_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=60,
                read_timeout=timeout_ms // 1000,  # ms to seconds
            ),
        )

        return ChatBedrockConverse(
            model=model,
            client=bedrock_client,
            temperature=temperature,
        )
