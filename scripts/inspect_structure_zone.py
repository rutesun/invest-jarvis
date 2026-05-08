from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.providers.kis import KISProvider
from src.providers.kis_wrapper import KISProviderWrapper
from src.providers.ticker_resolver import TickerResolver
from src.providers.yfinance_provider import YFinanceProvider
from src.tools.technical.components.chart_patterns import detect_chart_patterns
from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.price_levels import get_fibonacci_base_points, identify_key_levels
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.structure_presentation import build_structure_presentation
from src.tools.technical.structure_zone_inspector import (
    build_indicator_snapshot_from_ohlcv,
    build_structure_zone_inspect_payload,
    compare_structure_zone_inspect_payloads,
    format_structure_zone_inspect_comparison,
    format_structure_zone_inspection,
)
from src.tools.technical.structure_zones import StructureZoneConfig, StructureZoneDetector
from src.tools.technical.tool import TechnicalAnalysisTool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect structure zone candidates and selection.")
    parser.add_argument(
        "query", nargs="?", help="Ticker or company name. Optional with --fixture-csv."
    )
    parser.add_argument(
        "--fixture-csv",
        type=Path,
        help="CSV fixture path. If set, inspect from local OHLCV instead of live fetch.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON payload instead of text output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write inspect payload JSON to file.",
    )
    parser.add_argument(
        "--compare-json",
        type=Path,
        help="Compare current inspect result against a saved inspect JSON payload.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=5,
        help="Maximum number of candidates to show in text output.",
    )
    return parser.parse_args()


def _is_korean_ticker(ticker: str) -> bool:
    return ticker.endswith((".KS", ".KQ"))


async def _resolve_ticker(query: str) -> str:
    resolver = TickerResolver()
    resolution = await resolver.resolve(query)
    return resolution.resolved_ticker


def _load_fixture_dataframe(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, index_col="Date")
    df.index = pd.to_datetime(df.index, utc=True)
    return df


async def _build_live_payload(query: str) -> dict:
    ticker = await _resolve_ticker(query)

    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    if _is_korean_ticker(ticker) and kis_key and kis_secret:
        provider = KISProviderWrapper(KISProvider(app_key=kis_key, app_secret=kis_secret))
    else:
        provider = YFinanceProvider()

    technical_tool = TechnicalAnalysisTool(provider=provider, scorer=TechnicalScorer())
    technical_result = await technical_tool.execute(ticker, period="3y")
    if not technical_result.success:
        raise RuntimeError(f"Technical analysis failed: {technical_result.error}")

    technical_data = technical_result.data
    df = technical_data.raw_dataframe
    if df is None or df.empty:
        raise RuntimeError(f"No raw dataframe available for {ticker}")

    config = StructureZoneConfig()
    detector = StructureZoneDetector(config)
    zone_set = detector.detect(df, technical_data.snapshot)
    chart_patterns = detect_chart_patterns(df, technical_data.snapshot)
    lookback_high, lookback_low = get_fibonacci_base_points(df, technical_data.snapshot)
    price_levels = identify_key_levels(
        snapshot=technical_data.snapshot,
        pattern_results=chart_patterns,
        lookback_high=lookback_high,
        lookback_low=lookback_low,
    )
    level_payload = compose_level_payload(
        zone_set,
        price_levels,
        atr=technical_data.snapshot.atr,
    )
    presented_structure = build_structure_presentation(
        level_payload.structure_levels,
        level_payload.execution_levels,
    )

    return build_structure_zone_inspect_payload(
        symbol=ticker,
        snapshot=technical_data.snapshot,
        zone_set=zone_set,
        level_payload=level_payload,
        presented_structure=presented_structure,
        config=config,
        source="live",
    )


def _build_fixture_payload(symbol: str, csv_path: Path) -> dict:
    df = _load_fixture_dataframe(csv_path)
    snapshot = build_indicator_snapshot_from_ohlcv(df)

    config = StructureZoneConfig()
    detector = StructureZoneDetector(config)
    zone_set = detector.detect(df, snapshot)
    chart_patterns = detect_chart_patterns(df, snapshot)
    lookback_high, lookback_low = get_fibonacci_base_points(df, snapshot)
    price_levels = identify_key_levels(
        snapshot=snapshot,
        pattern_results=chart_patterns,
        lookback_high=lookback_high,
        lookback_low=lookback_low,
    )
    level_payload = compose_level_payload(
        zone_set,
        price_levels,
        atr=snapshot.atr,
    )
    presented_structure = build_structure_presentation(
        level_payload.structure_levels,
        level_payload.execution_levels,
    )

    return build_structure_zone_inspect_payload(
        symbol=symbol,
        snapshot=snapshot,
        zone_set=zone_set,
        level_payload=level_payload,
        presented_structure=presented_structure,
        config=config,
        csv_path=str(csv_path),
        source="fixture",
    )


def _write_output_file(output_path: Path, payload: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_json_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def main() -> None:
    load_dotenv()
    args = parse_args()

    if not args.query and not args.fixture_csv:
        raise SystemExit("query 또는 --fixture-csv 중 하나는 필요합니다.")

    if args.fixture_csv:
        symbol = args.query or args.fixture_csv.stem
        payload = _build_fixture_payload(symbol=symbol, csv_path=args.fixture_csv)
    else:
        payload = await _build_live_payload(args.query)

    if args.output:
        _write_output_file(args.output, payload)

    if args.compare_json:
        baseline_payload = _load_json_payload(args.compare_json)
        diff_payload = compare_structure_zone_inspect_payloads(baseline_payload, payload)
        if args.json:
            print(json.dumps(diff_payload, ensure_ascii=False, indent=2))
            return

        print(format_structure_zone_inspect_comparison(diff_payload))
        return

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(format_structure_zone_inspection(payload, max_candidates=args.max_candidates))


if __name__ == "__main__":
    asyncio.run(main())
