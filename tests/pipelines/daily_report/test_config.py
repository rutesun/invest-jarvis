"""StageLLMConfig 테스트."""

from langchain_core.messages import HumanMessage, SystemMessage

from src.pipelines.daily_report.config import StageLLMConfig


def test_build_messages_anthropic_has_cache_control():
    """Anthropic provider일 때 system message에 cache_control 추가."""
    cfg = StageLLMConfig(provider="anthropic", model="test-model", temperature=0.2)
    messages = cfg.build_messages("system prompt", "user prompt")

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == "system prompt"
    assert messages[0].additional_kwargs["cache_control"] == {"type": "ephemeral"}
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "user prompt"


def test_build_messages_openai_no_cache_control():
    """OpenAI provider일 때 cache_control 없음."""
    cfg = StageLLMConfig(provider="openai", model="test-model", temperature=0.2)
    messages = cfg.build_messages("system prompt", "user prompt")

    assert len(messages) == 2
    assert messages[0].additional_kwargs == {}
