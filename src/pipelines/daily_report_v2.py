# src/pipelines/daily_report_v2.py
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from src.llm.daily_report_models import (
    DailyReport,
    IngestResult,
    ShuffleResult,
    StockCatalyst,
    IssueExtract,
)
from src.pipelines.report_stages import StageCache
from src.pipelines.report_stages.ingest import IngestStage
from src.pipelines.report_stages.map_issues import MapStage
from src.pipelines.report_stages.shuffle_filter import ShuffleStage
from src.pipelines.report_stages.catalyst import CatalystStage
from src.pipelines.report_stages.synthesize import SynthesizeStage

logger = logging.getLogger(__name__)

STAGE_NAMES = ["ingest", "map", "shuffle", "catalyst", "synthesize"]

STAGE_CACHE_KEYS = {
    "ingest": "1_ingest",
    "map": "2_map",
    "shuffle": "3_shuffle",
    "catalyst": "4_catalyst",
    "synthesize": "5_synthesize",
}


@dataclass
class DailyReportV2Pipeline:
    ingest_stage: IngestStage
    map_stage: MapStage
    shuffle_stage: ShuffleStage
    catalyst_stage: CatalystStage
    synthesize_stage: SynthesizeStage
    cache_base: Path = Path(".cache/report")

    async def run(
        self,
        stage: str | None = None,
        from_stage: str | None = None,
    ) -> DailyReport | None:
        today = datetime.now().strftime("%Y-%m-%d")
        cache = StageCache(StageCache.cache_dir_for_date(self.cache_base, today))

        if stage:
            return await self._run_single_stage(stage, cache)

        stages_to_run = self._stages_from(from_stage) if from_stage else STAGE_NAMES
        return await self._run_stages(stages_to_run, cache)

    async def _run_stages(
        self, stages: list[str], cache: StageCache
    ) -> DailyReport | None:
        ingest_result = None
        map_result = None
        shuffle_result = None
        catalyst_result = None
        report = None

        for stage_name in stages:
            if stage_name == "ingest":
                ingest_result = await self.ingest_stage.run()
                cache.save(STAGE_CACHE_KEYS["ingest"], ingest_result.model_dump())

            elif stage_name == "map":
                if ingest_result is None:
                    ingest_result = IngestResult(**cache.load(STAGE_CACHE_KEYS["ingest"]))
                map_result = await self.map_stage.run(ingest_result.telegram_messages)
                cache.save(STAGE_CACHE_KEYS["map"], [i.model_dump() for i in map_result])

            elif stage_name == "shuffle":
                if ingest_result is None:
                    ingest_result = IngestResult(**cache.load(STAGE_CACHE_KEYS["ingest"]))
                if map_result is None:
                    map_result = [IssueExtract(**i) for i in cache.load(STAGE_CACHE_KEYS["map"])]
                shuffle_result = await self.shuffle_stage.run(
                    map_result, ingest_result.kr_flow, ingest_result.momentum,
                )
                cache.save(STAGE_CACHE_KEYS["shuffle"], shuffle_result.model_dump())

            elif stage_name == "catalyst":
                if shuffle_result is None:
                    shuffle_result = ShuffleResult(**cache.load(STAGE_CACHE_KEYS["shuffle"]))
                catalyst_result = await self.catalyst_stage.run(shuffle_result)
                cache.save(STAGE_CACHE_KEYS["catalyst"], [c.model_dump() for c in catalyst_result])

            elif stage_name == "synthesize":
                if ingest_result is None:
                    ingest_result = IngestResult(**cache.load(STAGE_CACHE_KEYS["ingest"]))
                if shuffle_result is None:
                    shuffle_result = ShuffleResult(**cache.load(STAGE_CACHE_KEYS["shuffle"]))
                if catalyst_result is None:
                    catalyst_result = [StockCatalyst(**c) for c in cache.load(STAGE_CACHE_KEYS["catalyst"])]
                report = await self.synthesize_stage.run(
                    ingest_result, shuffle_result, catalyst_result,
                )
                cache.save(STAGE_CACHE_KEYS["synthesize"], report.model_dump())

        return report

    async def _run_single_stage(self, stage: str, cache: StageCache) -> DailyReport | None:
        return await self._run_stages([stage], cache)

    def _stages_from(self, start: str) -> list[str]:
        if start not in STAGE_NAMES:
            raise ValueError(f"Unknown stage: {start}. 사용 가능: {STAGE_NAMES}")
        idx = STAGE_NAMES.index(start)
        return STAGE_NAMES[idx:]
