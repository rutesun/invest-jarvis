# src/providers/telegram/storage.py
from __future__ import annotations

import csv
from pathlib import Path

CSV_COLUMNS = [
    "message_id",
    "timestamp",
    "channel_name",
    "author",
    "content",
    "media_info",
    "forward_from",
]


class TelegramStorage:
    """텔레그램 메시지를 날짜별 CSV로 저장한다.

    파일 경로: {output_dir}/YYYY-MM/YYYY-MM-DD-{channel_name}.csv
    저장 전 기존 message_id를 스캔하여 중복을 방지한다.
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def csv_path(self, channel_name: str, date_str: str) -> Path:
        """YYYY-MM-DD 형식의 날짜와 채널명으로 CSV 경로를 생성한다."""
        month_dir = date_str[:7]  # YYYY-MM
        return self._output_dir / month_dir / f"{date_str}-{channel_name}.csv"

    def get_existing_ids(self, channel_name: str, date_str: str) -> set[int]:
        """해당 CSV에 이미 저장된 message_id 집합을 반환한다."""
        path = self.csv_path(channel_name, date_str)
        if not path.exists():
            return set()
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return {int(row["message_id"]) for row in reader}

    def save(self, channel_name: str, date_str: str, messages: list[dict]) -> None:
        """메시지 목록을 CSV에 저장한다. 중복은 스킵."""
        if not messages:
            return

        path = self.csv_path(channel_name, date_str)
        existing_ids = self.get_existing_ids(channel_name, date_str)
        new_messages = [m for m in messages if int(m["message_id"]) not in existing_ids]

        if not new_messages:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()

        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if not file_exists:
                writer.writeheader()
            for msg in new_messages:
                writer.writerow({col: msg.get(col, "") for col in CSV_COLUMNS})
