"""적응형 규칙 홀드아웃 확인: 필터가 숨긴 기간(OOS)에서도 expR을 유지하나.

기본 시스템(단순 돌파 + 넓은 추적)에 성격 필터를 걸고, 진입일 기준 IS/OOS로 나눠
per-trade expR을 비교. 필터를 in-sample에서 뽑았으므로 OOS 유지 여부가 과적합 판정.
거래비용 미반영.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_entry_quality import entry_plain, simulate_widetrail
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, agg, beta_vs_spy, load_universe

CUTOFF = pd.Timestamp("2024-09-29").date()
AVOID = {"ConsDisc", "Energy"}

VARIANTS = {
    "BASE (전체)": lambda b, sec: True,
    "손실섹터 제외": lambda b, sec: sec not in AVOID,
    "손실섹터 제외 + β≥1.0": lambda b, sec: sec not in AVOID and b >= 1.0,
    "고베타만 β≥1.3": lambda b, sec: (not np.isnan(b)) and b >= 1.3,
}


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]

    trades_by: dict[str, list[dict]] = {}
    betas: dict[str, float] = {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        betas[s] = beta_vs_spy(data[s], spy)
        trades_by[s] = simulate_widetrail(d, entry_plain)

    print(f"적응형 규칙 홀드아웃  IS=~{CUTOFF} 이전 / OOS=이후   종목 {len(loaded)}   거래비용 미반영")
    print("\n" + "=" * 84)
    print(f"  {'변형':22}{'IS expR':>9}{'IS n':>6}{'IS승률':>7}   {'OOS expR':>9}{'OOS n':>7}{'OOS승률':>8}")
    for name, elig in VARIANTS.items():
        keys = [s for s in loaded if elig(betas[s], tickers[s])]
        is_t = [t for s in keys for t in trades_by[s] if t["entry_date"] < CUTOFF]
        oos_t = [t for s in keys for t in trades_by[s] if t["entry_date"] >= CUTOFF]
        a, b = agg(is_t), agg(oos_t)
        print(
            f"  {name:22}{a['expR']:>9}{a['n']:>6}{int(a['win']):>6}%   "
            f"{b['expR']:>9}{b['n']:>7}{int(b['win']):>7}%"
        )
    print("\n  판정: OOS expR이 IS 대비 유지되면 견고, 붕괴하면 과적합.")


if __name__ == "__main__":
    main()
