from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.stage_config import StageLLMConfig, resolve_stage_llm


def test_build_messages_plain_for_openai():
    config = StageLLMConfig(provider="openai", model="gpt-5.6-terra", temperature=0.0)
    messages = config.build_messages("sys", "user")
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert messages[0].additional_kwargs == {}


def test_build_messages_adds_cache_control_for_anthropic():
    config = StageLLMConfig(provider="anthropic", model="claude-x", temperature=0.0)
    messages = config.build_messages("sys", "user")
    assert messages[0].additional_kwargs == {"cache_control": {"type": "ephemeral"}}


def test_resolve_stage_llm_returns_config_backed_values():
    resolved = resolve_stage_llm("daily_v2", "synthesis")
    assert isinstance(resolved, StageLLMConfig)
    assert resolved.model == "gpt-5.6-sol"
    assert resolved.temperature == 0.1
