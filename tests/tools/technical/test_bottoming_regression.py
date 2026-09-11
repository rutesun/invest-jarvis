"""바닥 그라데이션 실데이터 회귀 — 루브릭을 고정한다.

평가세트: BE(바닥 다지기) / NVDA(확인된 강세, 판정 불변) / LULU(끝까지 하락, avoid 유지).
raw 응답을 tests/fixtures/technical/scoring/*.csv에 박제하고 전체 경로(raw→adjusted/action)를
고정한다. 골든 규약: 로직이 잘못 바뀌면 여기서 깨진다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.tools.technical.aggregator import ACCUMULATE_FLOOR, BOTTOMING_CEILING
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer


FIXTURE_DIR = Path("tests/fixtures/technical/scoring")


def _load(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURE_DIR / name, parse_dates=["Date"], index_col="Date")


def _trajectory(df: pd.DataFrame, start: str, end: str) -> list[tuple[str, int, str, bool]]:
    """(date, adjusted, action, has_bottoming_trace) per trading day in [start, end]."""
    out: list[tuple[str, int, str, bool]] = []
    for date in df.index:
        if not (pd.Timestamp(start) <= date <= pd.Timestamp(end)):
            continue
        sliced = IndicatorCalculator().calculate(df.loc[:date])
        r = TechnicalScorer().score(sliced, include_history=False)
        has_bottom = any(t.rule == "bottoming_gradient_bonus" for t in r.aggregation_trace)
        out.append((str(date.date()), r.adjusted_score, r.technical_verdict.action, has_bottom))
    return out


def test_be_bottoming_window_gets_accumulate_gradation():
    df = _load("be_bottoming_2025-01-01_2026-09-09.csv")
    # SMA50 아래에서 저점을 계단식으로 높이던 구간(재탈환 이전).
    traj = _trajectory(df, "2026-08-03", "2026-09-02")

    actions = [a for _, _, a, _ in traj]

    # 재탈환(확인) 전에 accumulate 밴드가 여러 날 나타나 avoid→hold 사이 그라데이션을
    # 만든다(조기 관찰 단계). 단발이 아니라 지속적 신호여야 한다.
    accumulate_days = sum(1 for a in actions if a == "accumulate")
    assert accumulate_days >= 5, f"바닥 그라데이션 부족: accumulate {accumulate_days}일"
    # accumulate로 판정된 날은 밴드 안이어야 한다(상한으로 규율 유지).
    for _, adj, action, _ in traj:
        if action == "accumulate":
            assert ACCUMULATE_FLOOR <= adj <= BOTTOMING_CEILING


def test_be_reclaim_still_confirms_trend():
    df = _load("be_bottoming_2025-01-01_2026-09-09.csv")
    # 바닥 가점은 상한이 있어 SMA50 재탈환(확인) 판정 자체를 막지 않는다.
    traj = _trajectory(df, "2026-09-04", "2026-09-09")
    actions = [a for _, _, a, _ in traj]

    assert any(a in {"hold", "buy", "add"} for a in actions)


def test_nvda_strong_uptrend_never_accumulates():
    df = _load("nvda_2025-01-01_2026-09-09.csv")
    # SMA50 위에서 확인된 강세 국면(2026-08 이후) — 바닥 가점은 no-op이어야.
    traj = _trajectory(df, "2026-08-06", "2026-09-09")

    # 이평 위 강세주는 바닥 가점 대상이 아니다 — accumulate/바닥 trace 금지.
    assert all(action != "accumulate" for _, _, action, _ in traj)
    assert all(not has_bottom for _, _, _, has_bottom in traj)
    # 판정 불변: 강세 구간은 진입/보유(buy/add/hold) 유지.
    assert any(a in {"buy", "add", "hold"} for _, _, a, _ in traj)


def test_lulu_downtrend_stays_avoid_no_false_bottom():
    df = _load("lulu_2025-01-01_2026-09-09.csv")
    # lower-lows로 끝까지 흘러내린 구간 (close 157→119).
    traj = _trajectory(df, "2026-03-13", "2026-05-15")

    actions = [a for _, _, a, _ in traj]
    # 하락주는 진입/보유로 뒤집히지 않는다.
    assert not any(a in {"buy", "add", "hold"} for a in actions)
    # lower-lows에는 바닥 구조가 성립하지 않아 가짜 accumulate가 거의 없어야 한다.
    accumulate_days = sum(1 for a in actions if a == "accumulate")
    assert accumulate_days <= 2, f"하락주에 가짜 바닥 가점 과다: {accumulate_days}일"
