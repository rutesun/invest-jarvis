"""Daily report 파이프라인 설정."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.provider import LLMProvider


@dataclass(frozen=True)
class StageLLMConfig:
    """스테이지별 LLM 설정."""

    provider: str
    model: str
    temperature: float

    def create_llm(self) -> BaseChatModel:
        return LLMProvider.create(
            provider=self.provider,
            model=self.model,
            temperature=self.temperature,
        )

    def build_messages(self, system_prompt: str, user_prompt: str) -> list:
        """LLM 메시지 리스트 생성. Anthropic이면 system prompt 캐싱 적용."""
        kwargs = {}
        if self.provider == "anthropic":
            kwargs["cache_control"] = {"type": "ephemeral"}
        return [
            SystemMessage(content=system_prompt, additional_kwargs=kwargs),
            HumanMessage(content=user_prompt),
        ]


# 스테이지별 LLM 설정
MAP_LLM = StageLLMConfig(
    provider="anthropic",
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    temperature=0.2,
)

SHUFFLE_LLM = StageLLMConfig(
    provider="anthropic",
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    temperature=0.1,
)

REDUCE_LLM = StageLLMConfig(
    provider="anthropic",
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    temperature=0.3,
)

WRAPUP_LLM = StageLLMConfig(
    provider="anthropic",
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    temperature=0.4,
)

# Map stage 청크 설정
MAP_MAX_TOKENS_PER_CHUNK = 80_000

# LLM 호출 재시도/타임아웃
LLM_TIMEOUT_SECONDS = 60.0
LLM_MAX_RETRIES = 3
