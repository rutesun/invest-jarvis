"""Approved knowledge loader for daily report runtime."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ApprovedKnowledge(BaseModel):
    """Read-only approved knowledge bundle."""

    aliases: dict[str, list[str]] = Field(default_factory=dict)
    concepts: dict[str, dict[str, str]] = Field(default_factory=dict)
    relations: list[dict[str, str | float]] = Field(default_factory=list)
    message_types: dict[str, dict[str, list[str]]] = Field(default_factory=dict)


def _read_yaml(path: Path, empty: dict | list) -> dict | list:
    if not path.exists():
        return empty
    return yaml.safe_load(path.read_text(encoding="utf-8")) or empty


def load_approved_knowledge(base_dir: str | Path = "knowledge/daily_report") -> ApprovedKnowledge:
    base = Path(base_dir)
    return ApprovedKnowledge(
        aliases=_read_yaml(base / "aliases.yaml", {}),
        concepts=_read_yaml(base / "concepts.yaml", {}),
        relations=_read_yaml(base / "relations.yaml", []),
        message_types=_read_yaml(base / "message_types.yaml", {}),
    )
