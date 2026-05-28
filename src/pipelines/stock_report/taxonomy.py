from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class ThemeNode:
    key: str
    aliases: list[str]


@dataclass(slots=True)
class CategoryNode:
    key: str
    aliases: list[str]
    themes: list[ThemeNode]


@dataclass(slots=True)
class TaxonomyRegistry:
    categories: list[CategoryNode]

    @property
    def category_keys(self) -> set[str]:
        return {category.key for category in self.categories}

    @property
    def theme_keys(self) -> set[str]:
        return {theme.key for category in self.categories for theme in category.themes}


def load_taxonomy_registry(path: str | Path) -> TaxonomyRegistry:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"taxonomy 파일을 찾을 수 없습니다: {file_path}")

    payload = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    categories: list[CategoryNode] = []

    for raw_category in payload.get("categories", []):
        themes = [
            ThemeNode(
                key=raw_theme["key"],
                aliases=list(raw_theme.get("aliases", [])),
            )
            for raw_theme in raw_category.get("themes", [])
        ]
        categories.append(
            CategoryNode(
                key=raw_category["key"],
                aliases=list(raw_category.get("aliases", [])),
                themes=themes,
            )
        )

    if not categories:
        raise ValueError(f"taxonomy category가 비어 있습니다: {file_path}")

    return TaxonomyRegistry(categories=categories)


def build_match_dictionary(
    registry: TaxonomyRegistry,
) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    category_map: dict[str, str] = {}
    theme_map: dict[str, tuple[str, str]] = {}

    for category in registry.categories:
        all_category_aliases = [category.key, *category.aliases]
        for alias in all_category_aliases:
            category_map[alias.lower()] = category.key

        for theme in category.themes:
            all_theme_aliases = [theme.key, *theme.aliases]
            for alias in all_theme_aliases:
                theme_map[alias.lower()] = (category.key, theme.key)

    return category_map, theme_map


def render_taxonomy_outline(registry: TaxonomyRegistry) -> str:
    lines: list[str] = []
    for category in registry.categories:
        theme_text = ", ".join(theme.key for theme in category.themes) or "-"
        lines.append(f"- {category.key}: {theme_text}")
    return "\n".join(lines)
