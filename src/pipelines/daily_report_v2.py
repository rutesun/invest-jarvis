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
            logger.info("=== Daily Report V2: 단일 Stage 실행 '%s' ===", stage)
            return await self._run_single_stage(stage, cache)

        stages_to_run = self._stages_from(from_stage) if from_stage else STAGE_NAMES
        logger.info(
            "=== Daily Report V2: %d개 Stage 실행 (%s) ===",
            len(stages_to_run),
            " → ".join(stages_to_run),
        )
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
                logger.info(">>> Stage 1/5: Ingest 실행 중...")
                ingest_result = await self.ingest_stage.run()
                cache_path = cache.save(
                    STAGE_CACHE_KEYS["ingest"], ingest_result.model_dump()
                )
                logger.info(">>> Stage 1/5: Ingest 완료, 캐시 저장: %s", cache_path)

            elif stage_name == "map":
                logger.info(">>> Stage 2/5: Map 실행 중...")
                if ingest_result is None:
                    logger.debug("캐시에서 Ingest 결과 로드")
                    ingest_result = IngestResult(
                        **cache.load(STAGE_CACHE_KEYS["ingest"])
                    )
                map_result = await self.map_stage.run(ingest_result.telegram_messages)
                cache_path = cache.save(
                    STAGE_CACHE_KEYS["map"], [i.model_dump() for i in map_result]
                )
                logger.info(">>> Stage 2/5: Map 완료, 캐시 저장: %s", cache_path)

            elif stage_name == "shuffle":
                logger.info(">>> Stage 3/5: Shuffle 실행 중...")
                if ingest_result is None:
                    logger.debug("캐시에서 Ingest 결과 로드")
                    ingest_result = IngestResult(
                        **cache.load(STAGE_CACHE_KEYS["ingest"])
                    )
                if map_result is None:
                    logger.debug("캐시에서 Map 결과 로드")
                    map_result = [
                        IssueExtract(**i) for i in cache.load(STAGE_CACHE_KEYS["map"])
                    ]
                shuffle_result = await self.shuffle_stage.run(
                    map_result,
                    ingest_result.kr_flow,
                    ingest_result.momentum,
                )
                cache_path = cache.save(
                    STAGE_CACHE_KEYS["shuffle"], shuffle_result.model_dump()
                )
                logger.info(">>> Stage 3/5: Shuffle 완료, 캐시 저장: %s", cache_path)

            elif stage_name == "catalyst":
                logger.info(">>> Stage 4/5: Catalyst 실행 중...")
                if shuffle_result is None:
                    logger.debug("캐시에서 Shuffle 결과 로드")
                    shuffle_result = ShuffleResult(
                        **cache.load(STAGE_CACHE_KEYS["shuffle"])
                    )
                catalyst_result = await self.catalyst_stage.run(shuffle_result)
                cache_path = cache.save(
                    STAGE_CACHE_KEYS["catalyst"],
                    [c.model_dump() for c in catalyst_result],
                )
                logger.info(">>> Stage 4/5: Catalyst 완료, 캐시 저장: %s", cache_path)

            elif stage_name == "synthesize":
                logger.info(">>> Stage 5/5: Synthesize 실행 중...")
                if ingest_result is None:
                    logger.debug("캐시에서 Ingest 결과 로드")
                    ingest_result = IngestResult(
                        **cache.load(STAGE_CACHE_KEYS["ingest"])
                    )
                if shuffle_result is None:
                    logger.debug("캐시에서 Shuffle 결과 로드")
                    shuffle_result = ShuffleResult(
                        **cache.load(STAGE_CACHE_KEYS["shuffle"])
                    )
                if catalyst_result is None:
                    logger.debug("캐시에서 Catalyst 결과 로드")
                    catalyst_result = [
                        StockCatalyst(**c)
                        for c in cache.load(STAGE_CACHE_KEYS["catalyst"])
                    ]
                report = await self.synthesize_stage.run(
                    ingest_result,
                    shuffle_result,
                    catalyst_result,
                )
                cache_path = cache.save(
                    STAGE_CACHE_KEYS["synthesize"], report.model_dump()
                )
                logger.info(">>> Stage 5/5: Synthesize 완료, 캐시 저장: %s", cache_path)

        if report:
            logger.info("=== Daily Report V2: 전체 파이프라인 완료 ===")
        else:
            logger.info("=== Daily Report V2: 부분 실행 완료 ===")

        return report

    async def _run_single_stage(
        self, stage: str, cache: StageCache
    ) -> DailyReport | None:
        return await self._run_stages([stage], cache)

    def _stages_from(self, start: str) -> list[str]:
        if start not in STAGE_NAMES:
            raise ValueError(f"Unknown stage: {start}. 사용 가능: {STAGE_NAMES}")
        idx = STAGE_NAMES.index(start)
        return STAGE_NAMES[idx:]
