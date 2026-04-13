# src/tools/telegram_loader.py
from __future__ import annotations

import csv
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TelegramMessageLoader:
    """저장된 Telegram CSV 파일에서 메시지를 로드한다."""

    def __init__(self, data_dir: Path = Path("data")) -> None:
        self.data_dir = data_dir

    def load(self, date: str | None = None, days_back: int = 1) -> list[dict]:
        """지정된 날짜의 Telegram 메시지를 로드한다.

        Args:
            date: YYYY-MM-DD 형식 날짜. None이면 어제 날짜.
            days_back: date가 None일 때, 며칠 전 데이터를 로드할지 (기본값: 1일 전)

        Returns:
            메시지 dict 리스트. 각 dict는 id, channel, text, timestamp 포함.
        """
        if date is None:
            target_date = datetime.now() - timedelta(days=days_back)
            date = target_date.strftime("%Y-%m-%d")

        logger.info("[TelegramLoader] 날짜 %s의 메시지 로드 시작", date)

        year_month = date[:7]  # YYYY-MM
        date_dir = self.data_dir / year_month

        if not date_dir.exists():
            logger.warning("[TelegramLoader] 디렉토리 없음: %s", date_dir)
            return []

        messages = []
        csv_files = list(date_dir.glob(f"{date}-*.csv"))

        if not csv_files:
            logger.warning("[TelegramLoader] %s에 해당하는 CSV 파일 없음", date)
            return []

        logger.info("[TelegramLoader] %d개 CSV 파일 발견", len(csv_files))

        for csv_file in csv_files:
            try:
                channel_name = csv_file.stem.split("-", 3)[-1]  # 2026-04-01-channel_name
                file_messages = self._read_csv(csv_file, channel_name)
                messages.extend(file_messages)
                logger.debug("[TelegramLoader] %s: %d개 메시지 로드",
                            csv_file.name, len(file_messages))
            except Exception as e:
                logger.warning("[TelegramLoader] %s 읽기 실패: %s", csv_file.name, e)

        logger.info("[TelegramLoader] 총 %d개 메시지 로드 완료", len(messages))
        return messages

    def _read_csv(self, csv_path: Path, channel_name: str) -> list[dict]:
        """단일 CSV 파일을 읽어 메시지 리스트로 변환한다."""
        messages = []

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # CSV 컬럼: message_id, timestamp, channel_name, author, content, media_info, forward_from
                try:
                    message = {
                        "id": int(row["message_id"]),
                        "channel": channel_name,
                        "text": row["content"].strip(),
                        "timestamp": row["timestamp"],
                    }
                    # 빈 메시지 제외
                    if message["text"]:
                        messages.append(message)
                except (KeyError, ValueError) as e:
                    logger.debug("메시지 파싱 실패: %s", e)
                    continue

        return messages
