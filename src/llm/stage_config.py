"""파이프라인 스테이지 공용 LLM 설정 — config.yaml llm 섹션이 단일 소스."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.core.config import get_app_config
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

    def build_messages(self, system_prompt: str, user_prompt: str) -> list[BaseMessage]:
        """LLM 메시지 리스트 생성. Anthropic이면 system prompt 캐싱 적용."""
        kwargs = {}
        if self.provider == "anthropic":
            kwargs["cache_control"] = {"type": "ephemeral"}
        return [
            SystemMessage(content=system_prompt, additional_kwargs=kwargs),
            HumanMessage(content=user_prompt),
        ]


def resolve_stage_llm(pipeline: str, stage: str | None = None) -> StageLLMConfig:
    """config.yaml llm 섹션에서 defaults 병합된 스테이지 설정을 얻는다."""
    entry = get_app_config().llm.resolve(pipeline, stage)
    return StageLLMConfig(
        provider=entry.provider,
        model=entry.model,
        temperature=entry.temperature,
    )
