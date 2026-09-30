"""추격 진입 실험: 돌파(이상적 진입)를 놓친 뒤 얼마나 위까지 사도 되나.

옵션 A: 손절을 돌파 구조에 '고정' → 늦게(높이) 살수록 위험폭↑ → R 하락.
사용자 질문: "리스크를 더 지더라도 먹을 게 남는 한계가 어디냐" → R과 절대수익%를 같이 본다.
경계 = R이 1(보상=위험) 아래로 떨어지는 추격 거리. 거래비용 미반영.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_entry_quality import entry_plain
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, load_universe


AVOID = {"ConsDisc", "Energy"}  # 손실섹터 제외 유니버스
CHASE = [0.0, 0.02, 0.05, 0.10, 0.15, 0.20]
FILL_WINDOW = 20  # 돌파 후 이 거래일 안에 추격 레벨 닿으면 체결


def breakout_signals(d: pd.DataFrame) -> list[int]:
    return [
        i for i in range(60, len(d) - 1) if entry_plain(d, i) and not pd.isna(d.iloc[i]["SMA150"])
    ]


def chase_outcome(d: pd.DataFrame, i: int, chase: float) -> dict | None:
    """한 돌파 신호에 대해 chase 레벨 진입 결과. 미체결이면 filled=False(=놓침)."""
    n = len(d)
    r = d.iloc[i]
    pivot = r["Close"]
    stop = min(r["SMA150"], d["Low"].iloc[max(0, i - 9) : i + 1].min())
    target = pivot * (1 + chase)
    if stop >= target:
        return None
    fill_idx = None
    for j in range(i + 1, min(i + 1 + FILL_WINDOW, n)):
        rj = d.iloc[j]
        if rj["Low"] <= stop:
            break
        if rj["High"] >= target:
            fill_idx = j
            break
    if fill_idx is None:
        return {"filled": False}  # 그 레벨 못 감 = 횡보/실패로 놓침
    entry = target
    risk = entry - stop
    exit_price = None
    for k in range(fill_idx, n):
        rk = d.iloc[k]
        if rk["Low"] <= stop:
            exit_price, _exit_idx = stop, k
            break
        if not pd.isna(rk["SMA150"]) and rk["Close"] < rk["SMA150"]:
            exit_price, _exit_idx = rk["Close"], k
            break
    if exit_price is None:
        exit_price, _exit_idx = d.iloc[n - 1]["Close"], n - 1
    return {"filled": True, "R": (exit_price - entry) / risk, "ret": (exit_price / entry - 1) * 100}


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    keys = [s for s in tickers if s in data and tickers[s] not in AVOID]

    prepared = {s: add_indicators(data[s], spy["Close"]) for s in keys}
    # 모든 돌파 신호를 고정(분모) — 추격 레벨마다 같은 신호 집합에 적용
    signals = {s: breakout_signals(prepared[s]) for s in keys}
    total_signals = sum(len(v) for v in signals.values())

    print(f"추격 진입 실험 (옵션 A: 손절 돌파구조 고정)   유니버스=손실섹터제외 {len(keys)}종목")
    print(
        f"전체 돌파 신호 {total_signals}개를 분모로 고정 → 놓친 것(횡보/실패)도 포함   거래비용 미반영"
    )
    print("\n" + "=" * 96)
    print("  체결분 = 그 레벨까지 온 것만(승자편향) / 신호당 = 전체 돌파 대비(놓친 것=0, 정직)")
    print(
        f"  {'추격':>6}{'체결%':>7}{'체결분평균%':>12}{'체결분승률':>10}{'신호당평균%':>13}{'신호당expR':>11}"
    )

    for x in CHASE:
        outs = [chase_outcome(prepared[s], i, x) for s in keys for i in signals[s]]
        outs = [o for o in outs if o is not None]
        filled = [o for o in outs if o["filled"]]
        if not outs:
            continue
        fill_pct = 100 * len(filled) / len(outs)
        filled_ret = np.mean([o["ret"] for o in filled]) if filled else 0
        filled_win = 100 * np.mean([o["R"] > 0 for o in filled]) if filled else 0
        # 신호당 = 놓친 것(미체결)은 0으로 (사지 못했으니 수익 0)
        per_sig_ret = sum(o["ret"] for o in filled) / len(outs)
        per_sig_R = sum(o["R"] for o in filled) / len(outs)
        print(
            f"  {int(x * 100):>5}%{fill_pct:>6.0f}%{filled_ret:>12.1f}{filled_win:>9.0f}%"
            f"{per_sig_ret:>13.1f}{per_sig_R:>11.2f}"
        )

    # 0% 진입 시 전체 돌파의 '팔자' 분포 (패자·횡보 몫)
    base = [chase_outcome(prepared[s], i, 0.0) for s in keys for i in signals[s]]
    base = [o for o in base if o and o["filled"]]
    rets = np.array([o["ret"] for o in base])
    print("\n" + "=" * 96)
    print(f"돌파를 0%(돌파시점)에 다 샀을 때 결과 분포  (n={len(rets)})")
    print(
        f"  큰 승(+20%↑): {100 * np.mean(rets >= 20):>4.0f}%   "
        f"소폭(0~+20%): {100 * np.mean((rets >= 0) & (rets < 20)):>4.0f}%   "
        f"패(<0): {100 * np.mean(rets < 0):>4.0f}%"
    )
    print(
        f"  → 돌파의 {100 * np.mean(rets < 0):.0f}%는 손실(횡보/실패). 높이 쫓기는 이 패자·횡보를 '건너뛰는' 대신"
    )
    print("    승자마저 대부분(체결% 만큼) 놓친다. 신호당 지표가 진짜 기댓값.")


if __name__ == "__main__":
    main()
