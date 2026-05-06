import json
from pathlib import Path

import pandas as pd

from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.models import IndicatorSnapshot, ZoneTestArtifact
from src.tools.technical.price_levels import identify_key_levels
from src.tools.technical.structure_zones import StructureZoneDetector


FIXTURE_DIR = Path("tests/fixtures/technical/structure_zones")


def _load_fixture(symbol: str) -> pd.DataFrame:
    csv_path = FIXTURE_DIR / f"{symbol}.csv"
    return pd.read_csv(csv_path, index_col="Date", parse_dates=["Date"])


def _build_snapshot(df: pd.DataFrame) -> IndicatorSnapshot:
    close = df["Close"]
    atr_series = (df["High"] - df["Low"]).rolling(window=14, min_periods=1).mean()
    sma_50 = close.rolling(window=50, min_periods=1).mean().iloc[-1]
    sma_150 = close.rolling(window=150, min_periods=1).mean().iloc[-1]
    previous_close = close.iloc[-2]
    current_close = close.iloc[-1]
    change_pct = ((current_close - previous_close) / previous_close) * 100

    return IndicatorSnapshot(
        price=float(current_close),
        change_pct=float(change_pct),
        atr=float(atr_series.iloc[-1]),
        sma_50=float(sma_50),
        sma_150=float(sma_150),
    )


def _build_payload(symbol: str) -> tuple[Path, dict]:
    csv_path = FIXTURE_DIR / f"{symbol}.csv"
    df = _load_fixture(symbol)
    snapshot = _build_snapshot(df)
    zone_set = StructureZoneDetector().detect(df, snapshot)
    price_levels = identify_key_levels(
        snapshot=snapshot,
        pattern_results={},
        lookback_high=float(df["High"].max()),
        lookback_low=float(df["Low"].min()),
    )
    payload = compose_level_payload(zone_set, price_levels)
    return csv_path, payload


def test_structure_zone_regression_from_csv_fixture():
    _, payload = _build_payload("ALAB")

    assert len(payload["structure_levels"]["demand_zones"]) <= 2
    assert len(payload["structure_levels"]["supply_zones"]) <= 2
    assert len(payload["execution_levels"]) <= 3
    assert payload["structure_levels"]["invalidation"] is None or isinstance(
        payload["structure_levels"]["invalidation"], str
    )


def test_structure_zone_regression_writes_artifact(tmp_path: Path):
    csv_path, payload = _build_payload("ALAB")
    artifact = ZoneTestArtifact(
        schema_version="v1",
        symbol="ALAB",
        csv_path=str(csv_path),
        params={"top_n_per_side": 5},
        candidates=[],
        selected_zones=[
            {
                "structure_levels": payload["structure_levels"],
                "execution_levels": payload["execution_levels"],
            }
        ],
        score_breakdown=[],
    )

    artifact_path = tmp_path / "ALAB-regression.json"
    artifact_path.write_text(
        json.dumps(artifact.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    saved = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact_path.exists()
    assert saved["schema_version"] == "v1"
    assert saved["symbol"] == "ALAB"
    assert (
        saved["selected_zones"][0]["structure_levels"]["demand_zones"]
        == payload["structure_levels"]["demand_zones"]
    )
