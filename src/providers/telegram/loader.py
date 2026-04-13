# src/providers/telegram/loader.py
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path


class TelegramLoader:
    """날짜별 CSV에서 텔레그램 메시지를 로드한다.

    Daily Report V2의 IngestStage에서 사용.
    인터페이스: load(date) -> list[dict] (동기, asyncio.to_thread로 호출됨)
    반환 형식: [{"id": int, "channel": str, "text": str, "timestamp": str}, ...]
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def load(self, date_str: str | None = None) -> list[dict]:
        """지정 날짜의 모든 채널 메시지를 로드한다.

        Args:
            date_str: YYYY-MM-DD 형식. None이면 전날.
        """
        if date_str is None:
            date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        month_dir = self._data_dir / date_str[:7]
        if not month_dir.exists():
            return []

        messages: list[dict] = []
        for csv_file in month_dir.glob(f"{date_str}-*.csv"):
            with open(csv_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    messages.append({
                        "id": int(row["message_id"]),
                        "channel": row["channel_name"],
                        "text": row["content"],
                        "timestamp": row["timestamp"],
                    })

        messages.sort(key=lambda m: m["timestamp"])
        return messages
