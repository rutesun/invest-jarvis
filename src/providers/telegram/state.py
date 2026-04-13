# src/providers/telegram/state.py
from __future__ import annotations

import json
from pathlib import Path


class TelegramState:
    """채널별 마지막 수집 메시지 ID를 추적한다.

    data/monitor_state.json에 {channel_id: max_msg_id} 형태로 저장.
    단조 증가(monotonic): 더 큰 ID만 업데이트한다.
    """

    def __init__(self, state_path: Path) -> None:
        self._path = state_path
        self._data: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        if self._path.exists():
            return json.loads(self._path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2),
            encoding="utf-8",
        )

    def get_last_message_id(self, channel_id: str) -> int:
        return self._data.get(channel_id, 0)

    def update(self, channel_id: str, message_id: int) -> None:
        current = self._data.get(channel_id, 0)
        if message_id > current:
            self._data[channel_id] = message_id
            self._save()
