from __future__ import annotations

from src.pipelines.stock_report.config import (
    get_report_synthesis_llm_config,
    get_semantic_extraction_llm_config,
)


def test_semantic_extraction_openai_model_defaults_to_mini(monkeypatch) -> None:
    monkeypatch.delenv("STOCK_REPORT_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = get_semantic_extraction_llm_config("openai")

    assert config.model == "gpt-5.4-mini"


def test_report_synthesis_openai_model_defaults_to_gpt_54(monkeypatch) -> None:
    monkeypatch.delenv("STOCK_REPORT_SYNTHESIS_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("STOCK_REPORT_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = get_report_synthesis_llm_config("openai")

    assert config.model == "gpt-5.4"


def test_report_synthesis_openai_model_uses_specific_override(monkeypatch) -> None:
    monkeypatch.setenv("STOCK_REPORT_SYNTHESIS_OPENAI_MODEL", "gpt-5.5")
    monkeypatch.setenv("STOCK_REPORT_OPENAI_MODEL", "gpt-5.4-mini")

    config = get_report_synthesis_llm_config("openai")

    assert config.model == "gpt-5.5"
