"""섹터별 신규 종목 1개씩 추가 → 섹터 패턴의 티커 단위 out-of-sample 점검 + 종합.

기존 universe_matrix의 로직·유니버스를 재사용하고, 섹터마다 기존에 없던 대표 종목을
하나씩 더 붙여 (a) 신규분만, (b) 전체(기존+신규)로 종합한다.
"""

from __future__ import annotations

import warnings

import numpy as np

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators, buy_hold_return, per_ticker_return, simulate
from universe_matrix import (
    PRESETS,
    UNIVERSE,
    agg,
    beta_bucket,
    beta_vs_spy,
    load_universe,
    print_matrix,
)

# 섹터당 기존에 없던 신규 종목 1개 (성격 대표로 선정)
EXTRA = {
    "AMAT": "Semis",
    "INTU": "Software",
    "UBER": "Internet",
    "LOW": "ConsDisc",
    "MDLZ": "Staples",
    "TMO": "Health",
    "AXP": "Financials",
    "EOG": "Energy",
    "UNP": "Industrials",
    "AEP": "Utilities",
    "AFRM": "Fintech",
}


def build(tickers: dict[str, str], data: dict) -> tuple[dict, dict]:
    """returns trades_by[ticker][preset], betas[ticker]."""
    spy = data["SPY"]
    trades_by, betas = {}, {}
    for s in tickers:
        if s not in data:
            continue
        d = add_indicators(data[s], spy["Close"])
        betas[s] = beta_vs_spy(data[s], spy)
        trades_by[s] = {p: simulate(d, p) for p in PRESETS}
    return trades_by, betas


def sector_groups(tickers: dict[str, str], trades_by: dict) -> dict:
    g: dict = {}
    for s, sec in tickers.items():
        if s not in trades_by:
            continue
        g.setdefault(sec, {p: [] for p in PRESETS})
        for p in PRESETS:
            g[sec][p].extend(trades_by[s][p])
    return g


def main() -> None:
    all_syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(all_syms)

    new_tb, new_beta = build(EXTRA, data)
    old_tb, old_beta = build(UNIVERSE, data)

    loaded_new = list(new_tb)
    print(f"신규 종목 로드: {len(loaded_new)}/{len(EXTRA)}  (섹터당 1개, 티커 단위 OOS 점검)")

    # (A) 신규 종목 개별 결과 (투명성)
    print("\n" + "=" * 96)
    print("(A) 신규 종목 개별  — 셀 = 기댓값R (매매수)")
    print(f"  {'ticker':7}{'sector':13}{'beta':>6}   " + "".join(f"{p:>16}" for p in PRESETS))
    for s in EXTRA:
        if s not in new_tb:
            print(f"  {s:7}{EXTRA[s]:13}{'로드실패':>6}")
            continue
        cells = []
        for p in PRESETS:
            a = agg(new_tb[s][p])
            cells.append(f"{a['expR']:>6} ({a['n']:>2})" if a["n"] else f"{'-':>10}")
        print(f"  {s:7}{EXTRA[s]:13}{new_beta[s]:>6.2f}   " + "".join(f"{c:>16}" for c in cells))

    # (B) 신규분만 섹터별 (OOS)
    print_matrix("(B) 신규분만 섹터별 (티커 OOS)", sector_groups(EXTRA, new_tb))

    # (C) 전체(기존+신규) 종합
    combined_tickers = {**UNIVERSE, **EXTRA}
    combined_tb = {**old_tb, **new_tb}
    combined_beta = {**old_beta, **new_beta}

    print_matrix("(C) 전체(기존+신규) 섹터별", sector_groups(combined_tickers, combined_tb))

    by_beta: dict = {}
    for s in combined_tb:
        bk = beta_bucket(combined_beta[s])
        by_beta.setdefault(bk, {p: [] for p in PRESETS})
        for p in PRESETS:
            by_beta[bk][p].extend(combined_tb[s][p])
    print_matrix(
        "(C) 전체 베타 버킷별", by_beta,
        order=["고베타(≥1.3)", "중베타(0.8~1.3)", "저베타(<0.8)"],
    )

    print("\n" + "=" * 96)
    print("(C) 전체 종합")
    for p in PRESETS:
        pooled = [t for s in combined_tb for t in combined_tb[s][p]]
        a = agg(pooled)
        print(f"  {p:10}  기댓값R {a['expR']:>6}  승률 {int(a['win'])}%  payoff {a['payoff']}  매매수 {a['n']}")
    print(f"  종목수: {len(combined_tb)}")


if __name__ == "__main__":
    main()
