"""적응형 필터 비교: 기본 시스템(단순 돌파+넓은 추적)에 성격 필터를 걸어 buy&hold와 비교.

기본 = universe_entry_quality.entry_plain + simulate_widetrail (와인스타인식).
필터 변형: 손실 섹터 제외(ConsDisc/Energy), 고베타 집중.
지도(실험 2~5)에서 나온 규칙을 실제로 적용하면 나아지나 + B&H를 이기나.

주의: 필터를 이 데이터에서 뽑아 이 데이터로 평가 → in-sample. 채택 시 홀드아웃 재확인 필요.
거래비용 미반영. 전략 수익률은 각 트레이드 전액투입·순차 가정(공백 무시, B&H보다 시장노출 적음).
"""

from __future__ import annotations

import warnings

import numpy as np


warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_entry_quality import entry_plain, simulate_widetrail
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, agg, beta_vs_spy, load_universe


AVOID = {"ConsDisc", "Energy"}

VARIANTS = {
    "BASE (전체)": lambda b, sec: True,
    "손실섹터 제외": lambda b, sec: sec not in AVOID,
    "손실섹터 제외 + β≥1.0": lambda b, sec: sec not in AVOID and b >= 1.0,
    "고베타만 β≥1.3": lambda b, sec: (not np.isnan(b)) and b >= 1.3,
}


def compounded(trades: list[dict]) -> float:
    eq = 1.0
    for t in trades:
        eq *= 1 + t["ret"] / 100
    return (eq - 1) * 100


def bh(d) -> float:
    c = d["Close"].dropna()
    return (c.iloc[-1] / c.iloc[0] - 1) * 100


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]

    trades_by: dict[str, list[dict]] = {}
    betas: dict[str, float] = {}
    bh_by: dict[str, float] = {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        betas[s] = beta_vs_spy(data[s], spy)
        trades_by[s] = simulate_widetrail(d, entry_plain)
        bh_by[s] = bh(data[s])

    spy_bh = bh(spy)
    print(
        f"적응형 필터 vs buy&hold   종목 {len(loaded)}   SPY B&H {spy_bh:+.0f}%   거래비용 미반영"
    )
    print("\n" + "=" * 104)
    print(
        f"  {'변형':22}{'종목수':>6}{'expR':>7}{'승률':>6}{'매매수':>7}{'전략평균%':>10}{'대상B&H평균%':>13}{'B&H이긴비율':>11}"
    )

    for name, elig in VARIANTS.items():
        keys = [s for s in loaded if elig(betas[s], tickers[s])]
        keys = [s for s in keys if trades_by[s]]  # 실제 매매한 종목만
        pooled = [t for s in keys for t in trades_by[s]]
        a = agg(pooled)
        strat = [compounded(trades_by[s]) for s in keys]
        bhs = [bh_by[s] for s in keys]
        beat = 100 * np.mean([compounded(trades_by[s]) > bh_by[s] for s in keys]) if keys else 0
        print(
            f"  {name:22}{len(keys):>6}{a['expR']:>7}{int(a['win']):>5}%{a['n']:>7}"
            f"{np.mean(strat):>10.0f}{np.mean(bhs):>13.0f}{beat:>10.0f}%"
        )

    print(
        "\n  주: '전략평균%'는 각 트레이드 전액투입·순차 가정(공백/현금 보유 무시) → 완전투자 B&H보다 시장노출이 적어"
    )
    print("      강세장에선 총수익이 낮게 나옴. 핵심은 변형 간 expR·B&H이긴비율의 개선 여부.")


if __name__ == "__main__":
    main()
