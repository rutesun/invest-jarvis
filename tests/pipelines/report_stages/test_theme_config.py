# tests/pipelines/report_stages/test_theme_config.py
import pytest
from pathlib import Path
from src.pipelines.report_stages.theme_config import ThemeConfig


@pytest.fixture
def theme_file(tmp_path):
    path = tmp_path / "themes.yaml"
    path.write_text(
        "themes:\n  - CPO/광통신\n  - AI 반도체\n  - 방산\n",
        encoding="utf-8",
    )
    return path


def test_load_known_themes(theme_file):
    config = ThemeConfig(theme_file)
    themes = config.load()
    assert "CPO/광통신" in themes
    assert "AI 반도체" in themes
    assert len(themes) == 3


def test_add_new_themes(theme_file):
    config = ThemeConfig(theme_file)
    config.add_themes(["로봇/자동화", "양자컴퓨팅"])
    themes = config.load()
    assert "로봇/자동화" in themes
    assert "양자컴퓨팅" in themes
    assert len(themes) == 5


def test_add_duplicate_themes_ignored(theme_file):
    config = ThemeConfig(theme_file)
    config.add_themes(["CPO/광통신", "새테마"])
    themes = config.load()
    assert themes.count("CPO/광통신") == 1
    assert len(themes) == 4


def test_as_prompt_string(theme_file):
    config = ThemeConfig(theme_file)
    prompt_str = config.as_prompt_string()
    assert "- CPO/광통신" in prompt_str
    assert "- AI 반도체" in prompt_str


def test_missing_file_returns_empty():
    config = ThemeConfig(Path("/nonexistent/themes.yaml"))
    themes = config.load()
    assert themes == []
