#!/usr/bin/env python3
"""Daily Report V2 파이프라인 디버그 스크립트

IDE 디버거에서 브레이크포인트를 걸어 각 Stage 결과를 확인하세요.

IDE 디버깅:
    1. 아래 DEBUG_CONFIG에서 실행할 Stage 설정
    2. 브레이크포인트 설정 (run_XXX_stage 함수 내부)
    3. IDE에서 이 파일을 디버그 모드로 실행
    4. 변수 inspector로 중간 결과 확인

CLI 사용:
    uv run python scripts/debug_report_v2.py ingest
    uv run python scripts/debug_report_v2.py --from shuffle
    uv run python scripts/debug_report_v2.py --all
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.cli.main import create_daily_report_pipeline

# ============================================================
# IDE 디버깅 설정 (CLI 인자 없이 실행 시 사용됨)
# ============================================================
DEBUG_CONFIG = {
    "stage": None,  # None | "ingest" | "map" | "shuffle" | "catalyst" | "synthesize"
    "from_stage": "ingest",  # None | "ingest" | "map" | "shuffle" | "catalyst" | "synthesize"
    "run_all": False,  # True이면 전체 파이프라인 실행
    "provider": "openai",  # "openai" | "anthropic"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# LLM 관련 모듈만 DEBUG 레벨
logging.getLogger("langchain").setLevel(logging.DEBUG)
logging.getLogger("langchain_core").setLevel(logging.DEBUG)
logging.getLogger("langchain_openai").setLevel(logging.DEBUG)
logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("anthropic").setLevel(logging.DEBUG)
logging.getLogger("src.llm").setLevel(logging.DEBUG)
logging.getLogger("src.providers.llm_ticker_agent").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


# ============================================================
# Stage별 실행 함수 (브레이크포인트를 여기에 걸어서 디버깅)
# ============================================================


async def run_ingest_stage(pipeline):
    """Stage 1: 데이터 수집"""
    logger.info("=== [Stage 1] Ingest 시작 ===")
    result = await pipeline.ingest_stage.run()
    logger.info(f"Ingest 완료 - Telegram: {len(result.telegram_messages)}개 메시지")
    return result  # ← 브레이크포인트: result 확인


async def run_map_stage(pipeline, ingest_result):
    """Stage 2: 이슈 추출"""
    logger.info("=== [Stage 2] Map 시작 ===")
    map_result = await pipeline.map_stage.run(ingest_result.telegram_messages)
    logger.info(f"Map 완료 - {len(map_result)}개 이슈 추출")
    return map_result  # ← 브레이크포인트: map_result 확인


async def run_shuffle_stage(pipeline, map_result, ingest_result):
    """Stage 3: 테마 병합 & 종목 스코어링"""
    logger.info("=== [Stage 3] Shuffle 시작 ===")
    shuffle_result = await pipeline.shuffle_stage.run(
        map_result,
        ingest_result.kr_flow,
        ingest_result.momentum,
    )
    logger.info(f"Shuffle 완료 - {len(shuffle_result.themes)}개 테마")
    return shuffle_result  # ← 브레이크포인트: shuffle_result 확인


async def run_catalyst_stage(pipeline, shuffle_result):
    """Stage 4: 촉매 뉴스 매칭"""
    logger.info("=== [Stage 4] Catalyst 시작 ===")
    catalyst_result = await pipeline.catalyst_stage.run(shuffle_result)
    logger.info(f"Catalyst 완료 - {len(catalyst_result)}개 종목 분석")
    return catalyst_result  # ← 브레이크포인트: catalyst_result 확인


async def run_synthesize_stage(
    pipeline, ingest_result, shuffle_result, catalyst_result
):
    """Stage 5: 최종 리포트 합성"""
    logger.info("=== [Stage 5] Synthesize 시작 ===")
    report = await pipeline.synthesize_stage.run(
        ingest_result,
        shuffle_result,
        catalyst_result,
    )
    logger.info("Synthesize 완료 - 리포트 생성")
    return report  # ← 브레이크포인트: report 확인


async def run_full_pipeline(pipeline):
    """전체 파이프라인 실행 (각 Stage 결과를 변수에 저장)"""
    logger.info("=== 전체 파이프라인 실행 ===")

    ingest_result = await run_ingest_stage(pipeline)
    map_result = await run_map_stage(pipeline, ingest_result)
    shuffle_result = await run_shuffle_stage(pipeline, map_result, ingest_result)
    catalyst_result = await run_catalyst_stage(pipeline, shuffle_result)
    report = await run_synthesize_stage(
        pipeline, ingest_result, shuffle_result, catalyst_result
    )

    logger.info("=== 전체 파이프라인 완료 ===")
    return report


# ============================================================
# 캐시 체크 헬퍼
# ============================================================


def check_cache_and_warn(stage: str) -> tuple[bool, list[str]]:
    """필요한 캐시가 있는지 확인하고 없으면 경고 메시지 반환

    Returns:
        (has_all_cache, missing_caches)
    """
    from datetime import datetime
    from src.pipelines.report_stages import StageCache
    from src.pipelines.daily_report_v2 import STAGE_CACHE_KEYS

    date_str = datetime.now().strftime("%Y-%m-%d")
    cache = StageCache(StageCache.cache_dir_for_date(Path(".cache/report"), date_str))

    required_caches = []
    if stage in ["map", "shuffle", "catalyst", "synthesize"]:
        required_caches.append(STAGE_CACHE_KEYS["ingest"])
    if stage in ["shuffle", "catalyst", "synthesize"]:
        required_caches.append(STAGE_CACHE_KEYS["map"])
    if stage in ["catalyst", "synthesize"]:
        required_caches.append(STAGE_CACHE_KEYS["shuffle"])
    if stage == "synthesize":
        required_caches.append(STAGE_CACHE_KEYS["catalyst"])

    missing = [c for c in required_caches if not cache.has(c)]
    return (len(missing) == 0, missing)


# ============================================================
# Main 함수
# ============================================================


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Daily Report V2 디버그 실행")
    parser.add_argument(
        "stage", nargs="?", help="실행할 Stage (ingest/map/shuffle/catalyst/synthesize)"
    )
    parser.add_argument("--from", dest="from_stage", help="시작 Stage부터 끝까지 실행")
    parser.add_argument("--all", action="store_true", help="전체 파이프라인 실행")
    parser.add_argument(
        "--provider", default="openai", help="LLM Provider (openai/anthropic)"
    )

    # CLI 인자가 없으면 DEBUG_CONFIG 사용
    if len(sys.argv) == 1:
        logger.info("CLI 인자 없음 → DEBUG_CONFIG 사용")
        config = DEBUG_CONFIG
    else:
        args = parser.parse_args()
        config = {
            "stage": args.stage,
            "from_stage": args.from_stage,
            "run_all": args.all,
            "provider": args.provider,
        }

    provider = config["provider"]
    pipeline = create_daily_report_pipeline(provider)

    print(f"\n{'='*60}")
    print(f"Daily Report V2 디버그 실행")
    print(f"Provider: {provider}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    result = None

    # 전체 파이프라인
    if config["run_all"]:
        result = await run_full_pipeline(pipeline)

    # 특정 Stage부터 끝까지
    elif config["from_stage"]:
        from_stage = config["from_stage"]
        logger.info(f"[실행] {from_stage} 부터 끝까지")

        has_cache, missing = check_cache_and_warn(from_stage)
        if not has_cache:
            logger.warning(
                f"필요한 캐시가 없습니다: {missing}\n"
                f"→ 처음부터 실행합니다 (run_full_pipeline)"
            )
            result = await run_full_pipeline(pipeline)
        else:
            logger.info("캐시 발견 → 캐시 사용")
            result = await pipeline.run(from_stage=from_stage)

    # 단일 Stage
    elif config["stage"]:
        stage = config["stage"]
        logger.info(f"[실행] {stage} stage만")

        has_cache, missing = check_cache_and_warn(stage)
        if not has_cache:
            logger.warning(
                f"필요한 캐시가 없습니다: {missing}\n"
                f"→ 처음부터 실행합니다 (run_full_pipeline)"
            )
            result = await run_full_pipeline(pipeline)
        else:
            logger.info("캐시 발견 → 캐시 사용")
            result = await pipeline.run(stage=stage)

    else:
        parser.print_help()
        return

    print(f"\n{'='*60}")
    print("실행 완료")
    print(f"{'='*60}\n")

    if result and hasattr(result, "model_dump"):
        print("결과 미리보기:")
        print(
            json.dumps(result.model_dump(), indent=2, ensure_ascii=False)[:1000] + "..."
        )


if __name__ == "__main__":
    asyncio.run(main())
