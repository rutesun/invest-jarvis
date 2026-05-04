"""Artifact persistence helpers for replayable stage outputs."""

import json
from pathlib import Path


class StageArtifactStore:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: dict | list) -> Path:
        path = self.base_dir / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_markdown(self, name: str, markdown: str) -> Path:
        path = self.base_dir / f"{name}.md"
        path.write_text(markdown, encoding="utf-8")
        return path
