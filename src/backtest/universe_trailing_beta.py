"""베타 look-ahead 제거 후 재비교.

기존 실험의 고베타 필터는 5년 전체 수익률로 계산한 베타라 숨긴 기간 정보가 섞였다.
여기서는 신호일 기준 과거 252거래일 베타만 쓰고, 매수 시점 관문으로 적용한다.
청산은 새 규칙(150일선 2일 연속 이탈 또는 150일선-1R 아래). 거래비용 미반영.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, beta_vs_spy, load_universe
from universe_transition import AVOID, CUTOFF, prepare, row, simulate

BETA_WINDOW = 252
CANDIDATES = {
    "확정 시스템": dict(T=False, D=False),
    "+ 바닥 경로 D": dict(T=False, D=True),
    "+ 전환 T + 바닥 D": dict(T=True, D=True),
}


def trailing_beta(close: pd.Series, spy_close: pd.Series) -> np.ndarray:
    r = close.pct_change()
    m = spy_close.reindex(close.index).ffill().pct_change()
    cov = r.rolling(BETA_WINDOW).cov(m)
    var = m.rolling(BETA_WINDOW).var()
    return (cov / var).values


def main() -> None:
    data = load_universe(list(UNIVERSE) + list(EXTRA) + ["SPY"])
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]
    full_beta = {s: beta_vs_spy(data[s], spy) for s in loaded}
    prepared, tbeta = {}, {}
    for s in loaded:
        prepared[s] = prepare(add_indicators(data[s], spy["Close"]))
        tbeta[s] = trailing_beta(data[s]["Close"], spy["Close"])

    head = (f"  {'방식':34}{'횟수':>5}{'승률':>7}{'평균R':>7}{'합계R':>8}{'보유일':>6}"
            f"{'IS R':>7}{'OOS R':>7}{'비용후R':>8}")
    print("베타 look-ahead 제거 재비교  (청산=150일선 2일 연속 또는 150일선-1R 아래)")
    for name, cfg in CANDIDATES.items():
        print("\n" + "=" * 96)
        print(f"[{name}]")
        print(head)
        base = {s: simulate(prepared[s], exit150="2d1R", X=None, **cfg) for s in loaded}
        print(row("필터 없음 (73종목 전체)", [x for s in loaded for x in base[s]]))
        old_keys = [s for s in loaded if full_beta[s] >= 1.3 and tickers[s] not in AVOID]
        print(row("기존: 5년 베타로 분류(look-ahead)", [x for s in old_keys for x in base[s]]))
        gated = []
        for s in loaded:
            if tickers[s] in AVOID:
                continue
            elig = np.nan_to_num(tbeta[s], nan=0.0) >= 1.3
            gated += simulate(prepared[s], exit150="2d1R", X=None, eligible=elig, **cfg)
        print(row("수정: 신호일 과거 1년 베타 관문", gated))
        if cfg["D"] or cfg["T"]:
            for kind, label in (("S", "  └ 기존 돌파 S"), ("T", "  └ 전환 T"), ("D", "  └ 바닥 D")):
                sub = [x for x in gated if x["kind"] == kind]
                if sub:
                    print(row(label, sub))

    # 5년 베타와 과거 1년 베타가 얼마나 다른지
    n_old = sum(1 for s in loaded if full_beta[s] >= 1.3)
    share = np.mean([np.nanmean(np.nan_to_num(tbeta[s], nan=0) >= 1.3) for s in loaded
                     if full_beta[s] >= 1.3])
    print(f"\n  5년 베타 ≥1.3 종목 {n_old}개: 이 종목들이 과거1년 베타 ≥1.3인 날 비율 평균 {share*100:.0f}%")


if __name__ == "__main__":
    main()
