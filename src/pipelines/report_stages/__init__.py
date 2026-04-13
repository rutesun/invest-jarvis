# src/pipelines/report_stages/__init__.py
from __future__ import annotations

import json
from pathlib import Path


class StageCache:
    """파이프라인 스테이지 중간 결과를 JSON으로 관리하는 캐시."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir

    @staticmethod
    def cache_dir_for_date(base: Path, date_str: str) -> Path:
        return base / date_str

    def save(self, stage_name: str, data: dict) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{stage_name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, stage_name: str) -> dict:
        path = self._dir / f"{stage_name}.json"
        if not path.exists():
            raise FileNotFoundError(f"스테이지 캐시를 찾을 수 없습니다: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def has(self, stage_name: str) -> bool:
        return (self._dir / f"{stage_name}.json").exists()
