# src/pipelines/report_stages/map_issues.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import IssueExtract
from src.llm.daily_report_analyzer import map_chunk

logger = logging.getLogger(__name__)


def _format_messages_for_prompt(messages: list[dict]) -> str:
    """메시지 목록을 프롬프트용 텍스트로 변환한다."""
    lines = []
    for msg in messages:
        msg_id = msg.get("id", "?")
        channel = msg.get("channel", "?")
        text = msg.get("text", "")
        lines.append(f"[{msg_id}] ({channel}) {text}")
    return "\n".join(lines)


@dataclass
class MapStage:
    llm: BaseChatModel
    known_themes: str
    chunk_size: int = 50

    async def run(self, messages: list[dict]) -> list[IssueExtract]:
        if not messages:
            return []

        chunks = [
            messages[i : i + self.chunk_size]
            for i in range(0, len(messages), self.chunk_size)
        ]

        tasks = [
            self._process_chunk(chunk, idx)
            for idx, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_issues: list[IssueExtract] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("Map 청크 %d 실패: %s", idx, result)
                continue
            all_issues.extend(result)
        return all_issues

    async def _process_chunk(
        self, chunk: list[dict], chunk_index: int
    ) -> list[IssueExtract]:
        messages_text = _format_messages_for_prompt(chunk)
        return await map_chunk(
            llm=self.llm,
            known_themes=self.known_themes,
            messages_text=messages_text,
            run_name=f"map_chunk_{chunk_index}",
            metadata={"stage": "map", "chunk_index": chunk_index, "chunk_size": len(chunk)},
        )
