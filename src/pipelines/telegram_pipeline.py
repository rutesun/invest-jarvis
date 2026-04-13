# src/pipelines/telegram_pipeline.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.providers.telegram import (
    TelegramConfig,
    ChannelConfig,
    TelegramClientWrapper,
    TelegramCollector,
    TelegramMediaDownloader,
    TelegramStorage,
    TelegramState,
)


@dataclass
class TelegramPipeline:
    """텔레그램 메시지 수집 파이프라인."""

    config: TelegramConfig
    wrapper: TelegramClientWrapper
    collector: TelegramCollector
    storage: TelegramStorage
    state: TelegramState

    @classmethod
    async def create(cls, config_path: Path) -> "TelegramPipeline":
        """설정 파일로부터 파이프라인을 생성한다."""
        config = TelegramConfig.from_yaml(config_path)
        if not config.channels:
            raise ValueError("config.yaml에 telegram.channels가 설정되지 않았습니다.")

        wrapper = TelegramClientWrapper()
        await wrapper.start()

        media_downloader = TelegramMediaDownloader(
            client=wrapper.client, base_dir=config.output_dir,
        )
        collector = TelegramCollector(
            client=wrapper.client, media_downloader=media_downloader,
        )
        storage = TelegramStorage(output_dir=config.output_dir)
        state = TelegramState(config.output_dir / "monitor_state.json")

        return cls(
            config=config,
            wrapper=wrapper,
            collector=collector,
            storage=storage,
            state=state,
        )

    async def close(self) -> None:
        """클라이언트 연결을 종료한다."""
        await self.wrapper.stop()

    async def fetch(self, date_str: str) -> int:
        """특정 날짜의 메시지를 수집한다. 수집 건수 반환."""
        total = 0
        for ch_config in self.config.channels:
            messages = await self.collector.fetch_channel(ch_config, date_str)
            self.storage.save(ch_config.id, date_str, messages)
            for msg in messages:
                self.state.update(ch_config.id, msg["message_id"])
            total += len(messages)
        return total

    async def catch_up(self) -> int:
        """마지막 수집 이후 누락분을 보충한다. 수집 건수 반환."""
        total = 0
        for ch_config in self.config.channels:
            min_id = self.state.get_last_message_id(ch_config.id)
            by_date = await self.collector.fetch_since(ch_config, min_id)

            for date_str, date_msgs in by_date.items():
                self.storage.save(ch_config.id, date_str, date_msgs)
                for msg in date_msgs:
                    self.state.update(ch_config.id, msg["message_id"])
                total += len(date_msgs)
        return total
