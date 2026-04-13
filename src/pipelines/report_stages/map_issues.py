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
            logger.info("[Stage 2: Map] 메시지 없음, 스킵")
            return []

        chunks = [
            messages[i : i + self.chunk_size]
            for i in range(0, len(messages), self.chunk_size)
        ]

        logger.info("[Stage 2: Map] %d개 메시지를 %d개 청크로 분할 (청크 크기: %d)",
                    len(messages), len(chunks), self.chunk_size)
        logger.info("[Map] LLM 병렬 처리 시작 (%d개 청크)", len(chunks))

        tasks = [
            self._process_chunk(chunk, idx)
            for idx, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_issues: list[IssueExtract] = []
        successful_chunks = 0
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("[Map] 청크 %d/%d 실패: %s", idx + 1, len(chunks), result)
                continue
            all_issues.extend(result)
            successful_chunks += 1
            logger.debug("[Map] 청크 %d/%d 완료 - %d개 이슈 추출",
                        idx + 1, len(chunks), len(result))

        logger.info("[Stage 2: Map] 완료 - %d/%d 청크 성공, 총 %d개 이슈 추출",
                    successful_chunks, len(chunks), len(all_issues))
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
