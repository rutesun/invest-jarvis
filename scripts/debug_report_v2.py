#!/usr/bin/env python3
"""Daily Report V2 파이프라인 디버그 스크립트

각 Stage를 독립적으로 실행하고 결과를 확인할 수 있습니다.

Usage:
    uv run python scripts/debug_report_v2.py ingest
    uv run python scripts/debug_report_v2.py map
    uv run python scripts/debug_report_v2.py shuffle
    uv run python scripts/debug_report_v2.py catalyst
    uv run python scripts/debug_report_v2.py synthesize
    uv run python scripts/debug_report_v2.py --from shuffle  # shuffle부터 끝까지
    uv run python scripts/debug_report_v2.py --all           # 전체 파이프라인
"""
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.cli.main import create_daily_report_pipeline


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily Report V2 디버그 실행")
    parser.add_argument("stage", nargs="?", help="실행할 Stage (ingest/map/shuffle/catalyst/synthesize)")
    parser.add_argument("--from", dest="from_stage", help="시작 Stage부터 끝까지 실행")
    parser.add_argument("--all", action="store_true", help="전체 파이프라인 실행")
    parser.add_argument("--provider", default="openai", help="LLM Provider (openai/anthropic)")
    args = parser.parse_args()

    pipeline = create_daily_report_pipeline(args.provider)

    print(f"\n{'='*60}")
    print(f"Daily Report V2 디버그 실행")
    print(f"Provider: {args.provider}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    if args.all:
        print("[실행] 전체 파이프라인 (5 stages)\n")
        result = await pipeline.run()
    elif args.from_stage:
        print(f"[실행] {args.from_stage} 부터 끝까지\n")
        result = await pipeline.run(from_stage=args.from_stage)
    elif args.stage:
        print(f"[실행] {args.stage} stage만\n")
        result = await pipeline.run(stage=args.stage)
    else:
        parser.print_help()
        return

    print(f"\n{'='*60}")
    print("실행 완료")
    print(f"{'='*60}\n")

    if result:
        print("결과:")
        print(f"  - Type: {type(result).__name__}")
        if hasattr(result, "model_dump"):
            import json
            print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False)[:1000] + "...")


if __name__ == "__main__":
    asyncio.run(main())
