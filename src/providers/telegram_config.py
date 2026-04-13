# src/providers/telegram_config.py
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel


class ChannelConfig(BaseModel):
    """개별 채널의 수집 설정."""

    id: str
    include: list[str] = []
    exclude: list[str] = []

    def should_include(self, text: str) -> bool:
        """메시지가 include/exclude 필터를 통과하는지 확인한다."""
        if self.include:
            if not any(re.search(p, text) for p in self.include):
                return False
        if self.exclude:
            if any(re.search(p, text) for p in self.exclude):
                return False
        return True


class TelegramConfig(BaseModel):
    """config.yaml의 telegram 섹션을 파싱한 설정."""

    channels: list[ChannelConfig] = []
    output_dir: Path = Path("data")
    summarize_links_channels: list[str] = []

    @classmethod
    def from_yaml(cls, config_path: Path) -> TelegramConfig:
        if not config_path.exists():
            return cls()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        tg = raw.get("telegram", {})
        if not tg:
            return cls()

        channels: list[ChannelConfig] = []
        for ch in tg.get("channels", []):
            if isinstance(ch, str):
                channels.append(ChannelConfig(id=ch))
            elif isinstance(ch, dict):
                channels.append(ChannelConfig(
                    id=str(ch["id"]),
                    include=ch.get("include", []),
                    exclude=ch.get("exclude", []),
                ))

        output_dir = Path(tg.get("output_dir", "data"))
        link_proc = tg.get("link_processing", {})
        summarize = link_proc.get("summarize_links_channels", [])

        return cls(
            channels=channels,
            output_dir=output_dir,
            summarize_links_channels=summarize,
        )
