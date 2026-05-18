#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from src.pipelines.stock_report.tuning import (
    MessageSelector,
    run_prompt_tuning_round,
    with_model_override,
    write_prompt_tuning_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run stock report prompt tuning on real CSV samples."
    )
    parser.add_argument("date", nargs="?", default=None, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--provider", default="openai", help="LLM provider")
    parser.add_argument("--model", default="", help="Model override")
    parser.add_argument("--config-path", default="config.yaml", help="Config path")
    parser.add_argument(
        "--taxonomy-path",
        default="config/stock_report_vocabulary.yaml",
        help="Taxonomy vocabulary path",
    )
    parser.add_argument(
        "--prompt-path",
        default="",
        help="System prompt text file path (optional)",
    )
    parser.add_argument("--sample-size", type=int, default=24, help="Sample message count")
    parser.add_argument("--per-channel", type=int, default=2, help="Min samples per channel")
    parser.add_argument("--seed", type=int, default=7, help="Sampling random seed")
    parser.add_argument(
        "--pick",
        action="append",
        default=[],
        help="Always include message selector `channel_key:channel_message_id` (repeatable)",
    )
    parser.add_argument(
        "--pick-file",
        default="",
        help="File with one selector per line (`channel_key:channel_message_id`, # comment allowed)",
    )
    parser.add_argument(
        "--allow-missing-picks",
        action="store_true",
        help="Do not fail when selected messages are missing",
    )
    parser.add_argument(
        "--include-grouped-only",
        action="store_true",
        help="Include grouped_only rows in sampling candidates",
    )
    parser.add_argument(
        "--max-raw-chars",
        type=int,
        default=6000,
        help="Max raw text chars per sample (<=0 means full)",
    )
    parser.add_argument("--output-path", default="", help="Output markdown path")
    return parser.parse_args()


def _parse_selector(raw_value: str) -> MessageSelector:
    value = raw_value.strip()
    if not value:
        raise ValueError("빈 selector는 허용되지 않습니다.")
    channel_key, separator, channel_message_id = value.partition(":")
    if not separator or not channel_key.strip() or not channel_message_id.strip():
        raise ValueError(f"selector 형식 오류: `{raw_value}` (예시: hana_us_stock:9609)")
    return channel_key.strip(), channel_message_id.strip()


def _load_picked_messages(args: argparse.Namespace) -> set[MessageSelector]:
    picked: set[MessageSelector] = set()
    for selector in args.pick:
        picked.add(_parse_selector(selector))

    if args.pick_file:
        path = Path(args.pick_file)
        if not path.exists():
            raise FileNotFoundError(f"pick file을 찾을 수 없습니다: {path}")
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            picked.add(_parse_selector(line))
    return picked


def main() -> int:
    args = parse_args()
    date = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    output_path = args.output_path or f"reports/{date[:7]}/prompt_tuning_{date}.md"
    picked_messages = _load_picked_messages(args)

    with with_model_override(args.provider, args.model.strip() or None):
        result = run_prompt_tuning_round(
            date=date,
            data_dir=args.data_dir,
            provider=args.provider,
            config_path=args.config_path,
            taxonomy_path=args.taxonomy_path,
            sample_size=args.sample_size,
            per_channel=args.per_channel,
            seed=args.seed,
            include_grouped_only=args.include_grouped_only,
            picked_messages=picked_messages,
            strict_picks=not args.allow_missing_picks,
            system_prompt_path=args.prompt_path.strip() or None,
            max_raw_chars=args.max_raw_chars,
        )

    saved = write_prompt_tuning_report(result, Path(output_path))
    print("Stock Report V2 Prompt Tuning")
    print(f"- date: {result.date}")
    print(f"- provider/model: {result.provider} / {result.model or 'default'}")
    print(f"- prompt source: {result.system_prompt_source}")
    print(f"- picked messages: {len(picked_messages)}")
    print(f"- sampled rows: {result.sampled_rows} (candidate {result.candidate_rows})")
    print(f"- classified units: {result.classified_units}")
    print(f"- structure_type counts: {result.structure_type_counts}")
    print(f"- message_type counts: {result.message_type_counts}")
    print(f"- category counts: {result.category_counts}")
    print(f"Saved report: {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
