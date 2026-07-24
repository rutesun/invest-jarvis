from pathlib import Path

import pytest

from src.core.config import AppConfig, LLMConfig, get_app_config, load_config


# ---------------------------------------------------------------------------
# Fix 1: extra="forbid" — unknown field 거부
# ---------------------------------------------------------------------------


def test_llm_unknown_field_key_fails_validation():
    with pytest.raises(ValueError):
        LLMConfig.model_validate({"defaults": {"modle": "oops"}})


def test_llm_unknown_pipeline_key_fails_validation():
    with pytest.raises(ValueError):
        LLMConfig.model_validate({"analyz": {}})


def test_llm_invalid_provider_fails_validation():
    with pytest.raises(ValueError):
        LLMConfig.model_validate({"defaults": {"provider": "gemini"}})


# ---------------------------------------------------------------------------
# Fix 2: empty model string 거부
# ---------------------------------------------------------------------------


def test_llm_empty_model_fails_at_resolve():
    llm = LLMConfig.model_validate({"defaults": {"model": ""}})
    with pytest.raises(ValueError):
        llm.resolve("analyze")


def test_load_config_from_yaml(tmp_path):
    config_content = """
technical:
  strategies:
    - trend
    - oscillator
cache:
  quote_ttl: 60
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    config = load_config(config_file)

    assert config.technical.strategies == ["trend", "oscillator"]
    assert config.cache.quote_ttl == 60


def test_load_config_default():
    config = load_config(None)
    assert isinstance(config, AppConfig)
    assert config.cache.quote_ttl == 60


def test_llm_defaults_when_section_absent():
    config = AppConfig()
    resolved = config.llm.resolve("analyze")
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-5.6-terra"
    assert resolved.temperature == 0.0


def test_llm_daily_stage_code_defaults():
    llm = LLMConfig()
    assert llm.resolve("daily", "map").model == "gpt-5.6-luna"
    assert llm.resolve("daily", "map").temperature == 0.2
    assert llm.resolve("daily", "shuffle").model == "gpt-5.6-luna"
    assert llm.resolve("daily", "shuffle").temperature == 0.1
    assert llm.resolve("daily", "reduce").model == "gpt-5.6-terra"
    assert llm.resolve("daily", "reduce").temperature == 0.3
    assert llm.resolve("daily", "wrapup").temperature == 0.4


def test_llm_daily_v2_stage_code_defaults():
    llm = LLMConfig()
    extraction = llm.resolve("daily_v2", "extraction")
    synthesis = llm.resolve("daily_v2", "synthesis")
    assert extraction.model == "gpt-5.6-luna"
    assert extraction.temperature == 0.1
    assert synthesis.model == "gpt-5.6-sol"
    assert synthesis.temperature == 0.1


def test_llm_stage_entry_inherits_unset_fields_from_defaults():
    llm = LLMConfig.model_validate(
        {
            "defaults": {"provider": "openai", "model": "gpt-5.6-terra", "temperature": 0.0},
            "daily": {"reduce": {"temperature": 0.9}},
        }
    )
    resolved = llm.resolve("daily", "reduce")
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-5.6-terra"  # defaults 상속
    assert resolved.temperature == 0.9  # 명시 필드만 오버라이드


def test_llm_partial_stage_section_keeps_sibling_code_defaults():
    llm = LLMConfig.model_validate({"daily": {"reduce": {"temperature": 0.9}}})
    assert llm.resolve("daily", "map").model == "gpt-5.6-luna"
    assert llm.resolve("daily", "map").temperature == 0.2
    assert llm.resolve("daily", "reduce").temperature == 0.9


def test_llm_resolve_unknown_pipeline_raises():
    with pytest.raises(KeyError):
        LLMConfig().resolve("quick_check")


def test_llm_resolve_unknown_stage_raises():
    with pytest.raises(KeyError):
        LLMConfig().resolve("daily", "nonexistent")


def test_llm_resolve_staged_pipeline_requires_stage():
    with pytest.raises(KeyError):
        LLMConfig().resolve("daily")


def test_llm_unknown_stage_key_in_yaml_fails_validation():
    with pytest.raises(ValueError):
        LLMConfig.model_validate({"daily": {"tpyo": {"temperature": 0.5}}})


def test_get_app_config_is_cached():
    get_app_config.cache_clear()
    assert get_app_config() is get_app_config()
    get_app_config.cache_clear()


def test_repo_config_yaml_llm_section_matches_code_defaults():
    repo_config = Path(__file__).resolve().parents[2] / "config.yaml"
    config = load_config(repo_config)
    assert config.llm.model_dump() == LLMConfig().model_dump()
