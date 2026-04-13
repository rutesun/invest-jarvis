# tests/providers/test_telegram_config.py
import pytest
from pathlib import Path
from src.providers.telegram_config import TelegramConfig, ChannelConfig


def test_load_simple_channel(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        '    - "12345"\n'
        "  output_dir: data\n",
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    assert len(config.channels) == 1
    assert config.channels[0].id == "12345"
    assert config.channels[0].include == []
    assert config.channels[0].exclude == []
    assert config.output_dir == Path("data")


def test_load_channel_with_filters(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        "    - id: chan1\n"
        "      include:\n"
        '        - "Breaking|Urgent"\n'
        "      exclude:\n"
        '        - "(?i)ad"\n',
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    ch = config.channels[0]
    assert ch.id == "chan1"
    assert ch.include == ["Breaking|Urgent"]
    assert ch.exclude == ["(?i)ad"]


def test_load_mixed_channels(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        '    - "simple_id"\n'
        "    - id: filtered_id\n"
        "      include:\n"
        '        - "pattern"\n',
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    assert len(config.channels) == 2
    assert config.channels[0].id == "simple_id"
    assert config.channels[1].id == "filtered_id"
    assert config.channels[1].include == ["pattern"]


def test_missing_telegram_section(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("technical:\n  strategies: [trend]\n", encoding="utf-8")
    config = TelegramConfig.from_yaml(config_file)
    assert config.channels == []
    assert config.output_dir == Path("data")


def test_missing_file_returns_defaults():
    config = TelegramConfig.from_yaml(Path("/nonexistent/config.yaml"))
    assert config.channels == []


def test_channel_config_should_include():
    ch = ChannelConfig(id="test", include=["Breaking|Urgent"], exclude=["(?i)ad"])
    assert ch.should_include("Breaking news today") is True
    assert ch.should_include("일반 메시지") is False
    assert ch.should_include("Breaking Ad campaign") is False


def test_channel_config_no_filters_includes_all():
    ch = ChannelConfig(id="test")
    assert ch.should_include("아무 메시지") is True
    assert ch.should_include("") is True


def test_channel_config_exclude_only():
    ch = ChannelConfig(id="test", exclude=["(?i)spam"])
    assert ch.should_include("좋은 정보") is True
    assert ch.should_include("이건 SPAM 입니다") is False


def test_summarize_links_channels(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        '    - "ch1"\n'
        "  link_processing:\n"
        "    summarize_links_channels:\n"
        "      - kiwoom_semibat\n",
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    assert "kiwoom_semibat" in config.summarize_links_channels
