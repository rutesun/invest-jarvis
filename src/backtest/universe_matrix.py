"""유니버스 확장: 베타·섹터별로 어떤 preset이 잘 먹히는지 찾는다.

(preset × 성격) 기댓값 행렬을 만든다. preset 로직은 preset_v0을 재사용.

선택편향 완화: 성과가 아니라 '섹터 소속'으로 종목을 뽑고, 부진주도 일부러 포함한다.
베타는 데이터로 실측(vs SPY). 여전히 현 상장 종목이라 생존편향은 남음(로그로 표면화).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import yfinance as yf

from preset_v0 import add_indicators, buy_hold_return, per_ticker_return, simulate

CACHE_DIR = "tmp/bt_cache"

# 섹터 소속으로 선정 (성과 무관). 부진주 포함.
UNIVERSE = {
    # 반도체 (대체로 고베타)
    "NVDA": "Semis", "AMD": "Semis", "AVGO": "Semis", "MU": "Semis",
    "INTC": "Semis", "QCOM": "Semis", "MRVL": "Semis", "TXN": "Semis",
    # 소프트웨어
    "MSFT": "Software", "CRM": "Software", "ADBE": "Software", "ORCL": "Software",
    "PANW": "Software", "CRWD": "Software", "SNOW": "Software", "NOW": "Software",
    # 인터넷/커뮤니케이션
    "GOOGL": "Internet", "META": "Internet", "NFLX": "Internet",
    "DIS": "Internet", "AMZN": "Internet",
    # 소비 경기민감
    "TSLA": "ConsDisc", "NKE": "ConsDisc", "SBUX": "ConsDisc",
    "LULU": "ConsDisc", "MCD": "ConsDisc", "HD": "ConsDisc",
    # 필수소비 (저베타)
    "PG": "Staples", "KO": "Staples", "PEP": "Staples",
    "COST": "Staples", "WMT": "Staples", "CL": "Staples",
    # 헬스케어
    "LLY": "Health", "JNJ": "Health", "PFE": "Health",
    "ABBV": "Health", "MRK": "Health", "UNH": "Health",
    # 금융
    "JPM": "Financials", "BAC": "Financials", "GS": "Financials",
    "MS": "Financials", "V": "Financials", "MA": "Financials",
    # 에너지
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy",
    # 산업재
    "CAT": "Industrials", "BA": "Industrials", "GE": "Industrials", "DE": "Industrials",
    # 유틸리티 (저베타)
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    # 핀테크/고성장 (고베타, 변동성 큼)
    "HOOD": "Fintech", "PYPL": "Fintech", "SHOP": "Fintech",
    "COIN": "Fintech", "ROKU": "Fintech", "UPST": "Fintech",
}

PRESETS = ["MINERVINI", "ONEIL", "WEINSTEIN"]


def _cache(sym: str) -> str:
    return os.path.join(CACHE_DIR, sym.replace(".", "_") + ".csv")


def load_universe(symbols: list[str]) -> dict[str, pd.DataFrame]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    out: dict[str, pd.DataFrame] = {}
    missing = [s for s in symbols if not os.path.exists(_cache(s))]
    if missing:
        raw = yf.download(
            missing, period="5y", auto_adjust=True,
            group_by="ticker", threads=True, progress=False,
        )
        for s in missing:
            try:
                d = raw[s][["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
                d.index = d.index.tz_localize(None)
                d.index.name = "Date"
                if len(d) > 300:
                    d.to_csv(_cache(s))
            except Exception:
                pass
    for s in symbols:
        if os.path.exists(_cache(s)):
            out[s] = pd.read_csv(_cache(s), parse_dates=["Date"]).set_index("Date")
    return out


def beta_vs_spy(d: pd.DataFrame, spy: pd.DataFrame) -> float:
    a = d["Close"].pct_change().rename("t")
    b = spy["Close"].pct_change().rename("m")
    j = pd.concat([a, b], axis=1).dropna()
    if len(j) < 200 or j["m"].var() == 0:
        return float("nan")
    return float(j["t"].cov(j["m"]) / j["m"].var())


def beta_bucket(beta: float) -> str:
    if np.isnan(beta):
        return "?"
    if beta >= 1.3:
        return "고베타(≥1.3)"
    if beta >= 0.8:
        return "중베타(0.8~1.3)"
    return "저베타(<0.8)"


def agg(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "win": 0.0, "expR": 0.0, "payoff": 0.0}
    R = np.array([t["R"] for t in trades])
    w, l = R[R > 0], R[R <= 0]
    payoff = (w.mean() / abs(l.mean())) if len(w) and len(l) and l.mean() != 0 else float("inf")
    return {
        "n": len(R),
        "win": round(100 * len(w) / len(R), 0),
        "expR": round(R.mean(), 2),
        "payoff": round(payoff, 1),
    }


def print_matrix(title: str, groups: dict[str, dict[str, list[dict]]], order: list[str] | None = None) -> None:
    print("\n" + "=" * 96)
    print(title + "   (셀 = 기댓값R / 승률% / 매매수)")
    print(f"  {'그룹':16} " + "".join(f"{p:>22}" for p in PRESETS))
    keys = order or sorted(groups)
    for g in keys:
        if g not in groups:
            continue
        cells = []
        for p in PRESETS:
            s = agg(groups[g][p])
            cells.append(f"{s['expR']:>6} / {int(s['win']):>3}% / {s['n']:>3}" if s["n"] else f"{'-':>16}")
        print(f"  {g:16} " + "".join(f"{c:>22}" for c in cells))


def main() -> None:
    symbols = list(UNIVERSE) + ["SPY"]
    data = load_universe(symbols)
    spy = data.get("SPY")
    if spy is None:
        raise SystemExit("SPY 데이터 없음")

    loaded = [s for s in UNIVERSE if s in data]
    print(f"유니버스 로드: {len(loaded)}/{len(UNIVERSE)} 종목  (생존편향 잔존 — 현 상장 종목만)")

    # 각 종목: 지표, 베타, 트레이드
    betas: dict[str, float] = {}
    trades_by: dict[str, dict[str, list[dict]]] = {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        betas[s] = beta_vs_spy(data[s], spy)
        trades_by[s] = {p: simulate(d, p) for p in PRESETS}

    # 베타 버킷
    by_beta: dict[str, dict[str, list[dict]]] = {}
    for s in loaded:
        bk = beta_bucket(betas[s])
        by_beta.setdefault(bk, {p: [] for p in PRESETS})
        for p in PRESETS:
            by_beta[bk][p].extend(trades_by[s][p])
    print_matrix(
        "① 베타 버킷별",
        by_beta,
        order=["고베타(≥1.3)", "중베타(0.8~1.3)", "저베타(<0.8)"],
    )

    # 섹터
    by_sector: dict[str, dict[str, list[dict]]] = {}
    for s in loaded:
        sec = UNIVERSE[s]
        by_sector.setdefault(sec, {p: [] for p in PRESETS})
        for p in PRESETS:
            by_sector[sec][p].extend(trades_by[s][p])
    print_matrix("② 섹터별", by_sector)

    # 전체 합계 (v0 대조)
    total = {p: [t for s in loaded for t in trades_by[s][p]] for p in PRESETS}
    print("\n" + "=" * 96)
    print("③ 전체 (편향 완화된 유니버스)")
    for p in PRESETS:
        s = agg(total[p])
        print(f"  {p:10}  기댓값R {s['expR']:>6}  승률 {int(s['win'])}%  payoff {s['payoff']}  매매수 {s['n']}")

    # buy&hold 대비 (성격 요약)
    print("\n  [buy&hold 대비 preset이 이긴 종목 수 / 전체]")
    for p in PRESETS:
        wins = sum(
            1 for s in loaded
            if per_ticker_return(trades_by[s][p]) > buy_hold_return(data[s])
        )
        print(f"    {p:10}: {wins}/{len(loaded)}")

    # 베타 상·하위 몇 종목 표시(투명성)
    sb = sorted(loaded, key=lambda s: (betas[s] if not np.isnan(betas[s]) else -9))
    print("\n  베타 하위/상위 5:")
    print("    저베타:", ", ".join(f"{s}({betas[s]:.2f})" for s in sb[:5]))
    print("    고베타:", ", ".join(f"{s}({betas[s]:.2f})" for s in sb[-5:]))


if __name__ == "__main__":
    main()
