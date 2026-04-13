# src/pipelines/report_stages/theme_config.py
from __future__ import annotations

from pathlib import Path

import yaml


class ThemeConfig:
    """themes.yaml에서 알려진 테마 목록을 로드/업데이트한다."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[str]:
        if not self._path.exists():
            return []
        data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        return data.get("themes", []) if data else []

    def add_themes(self, new_themes: list[str]) -> None:
        existing = self.load()
        existing_set = set(existing)
        for theme in new_themes:
            if theme not in existing_set:
                existing.append(theme)
                existing_set.add(theme)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            yaml.dump({"themes": existing}, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def as_prompt_string(self) -> str:
        themes = self.load()
        return "\n".join(f"- {t}" for t in themes)
