from __future__ import annotations

from src.llm.stage_config import StageLLMConfig
from src.pipelines.stock_report.config import (
    get_report_synthesis_llm_config,
    get_semantic_extraction_llm_config,
)


def test_semantic_extraction_config_from_yaml_defaults() -> None:
    config = get_semantic_extraction_llm_config()
    assert isinstance(config, StageLLMConfig)
    assert config.provider == "openai"
    assert config.model == "gpt-5.6-luna"
    assert config.temperature == 0.1


def test_report_synthesis_config_from_yaml_defaults() -> None:
    config = get_report_synthesis_llm_config()
    assert config.provider == "openai"
    assert config.model == "gpt-5.6-sol"
    assert config.temperature == 0.1
