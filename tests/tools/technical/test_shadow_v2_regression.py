"""A′ shadow 실데이터 회귀 — 합의 매트릭스(floor+ceiling+악화 사다리)를 4개 국면으로 고정.

BE(바닥) / NVDA(확인된 강세) / LULU(하락) / ARM(Stage2 후 붕괴). shadow는 cutover 전이라
기존 action과 별개로 action_v2만 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.tools.technical.context import build_market_context
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.shadow_v2 import compute_shadow_v2


FIXTURE_DIR = Path("tests/fixtures/technical/scoring")


def _shadow_window(name: str, start: str, end: str):
    df = pd.read_csv(FIXTURE_DIR / name, parse_dates=["Date"], index_col="Date")
    out = []
    for date in df.index:
        if not (pd.Timestamp(start) <= date <= pd.Timestamp(end)):
            continue
        sliced = IndicatorCalculator().calculate(df.loc[:date])
        result = TechnicalScorer().score(sliced, include_history=False)
        ctx = build_market_context(sliced)
        out.append((str(date.date()), compute_shadow_v2(sliced, result.components, ctx)))
    return out


def test_nvda_stage2_stays_hold_no_false_demotion():
    # 확인된 강세(Stage2+ST up)는 움직임 setup 음수여도 hold 유지 — reduce/avoid 오강등 금지.
    rows = _shadow_window("nvda_2025-01-01_2026-09-09.csv", "2026-08-27", "2026-09-09")
    stage2_up = [(d, sv) for d, sv in rows if sv.regime == "Stage2" and sv.st_up]
    assert stage2_up, "Stage2/up 구간 없음"
    assert all(sv.action_v2 == "hold" for _, sv in stage2_up)


def test_be_bottoming_no_avoid_to_hold_jump():
    rows = _shadow_window("be_bottoming_2025-01-01_2026-09-09.csv", "2026-08-12", "2026-09-09")
    actions = [sv.action_v2 for _, sv in rows]
    # weak 구간엔 조기 관찰(accumulate) 존재, Stage2 도달 시 hold. buy로 직행하지 않음.
    assert "accumulate" in actions
    assert "hold" in actions
    assert "buy" not in actions


def test_lulu_downtrend_no_buy_hold_and_no_false_bottoming():
    rows = _shadow_window("lulu_2025-01-01_2026-09-09.csv", "2026-03-13", "2026-05-15")
    assert all(sv.action_v2 not in {"buy", "add", "hold"} for _, sv in rows)
    # SMA200 아래 하락주는 bottoming_watch가 켜지지 않는다.
    assert all(not sv.bottoming_watch for _, sv in rows)


def test_arm_stage2_collapse_derisks_not_trapped_in_hold():
    # 고점 후 붕괴: 정점(Stage2/up)의 hold는 정당하나, 붕괴가 시작(reduce/avoid 등장)된 뒤에는
    # hold/buy로 복귀하지 않고 de-risk 유지. 갓 무너진 첫 다리엔 가짜 바닥(accumulate) 없음.
    rows = _shadow_window("arm_2025-01-01_2026-09-09.csv", "2026-06-30", "2026-08-05")
    actions = [sv.action_v2 for _, sv in rows]

    assert "buy" not in actions
    first_risk = next((i for i, a in enumerate(actions) if a in {"reduce", "avoid"}), None)
    assert first_risk is not None, "붕괴 구간에 리스크 액션이 없음"
    assert all(a != "hold" for a in actions[first_risk:]), "위험 발생 후 hold로 복귀"
    # 확립된 약세 가드로 갓 무너진 첫 다리의 가짜 accumulate가 없어야 한다.
    assert "accumulate" not in actions
