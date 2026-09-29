"""대가 preset 3종(Minervini / O'Neil / Weinstein) vs buy&hold 최소 백테스트 (v0).

목적: "저울이 정직한가"를 확인하며 대가 전략을 있는 그대로 비교한다.
설계 근거: docs/trading-system-implementation-design.md

원칙(리뷰 반영):
- look-ahead 차단: 신호는 t 종가로 계산, 체결은 t+1 시가.
- 스탑·목표 동시 도달 시 스탑 우선(보수적).
- 지표는 전용 경량 계산(스냅샷 컴포넌트를 매 스텝 재호출하지 않음).

주의: 티커셋이 사후 선택된 소수 샘플이라 이 결과는 통계적 결론이 아니라
      '저울 점검 + 대가 성격 비교'의 첫 관찰이다.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = {
    "BE": "BE",
    "HOOD": "HOOD",
    "NVDA": "NVDA",
    "PANW": "PANW",
    "LULU": "LULU",
    "삼성전기": "009150.KS",
    "삼성전자": "005930.KS",
    "SPY": "SPY",  # 시장 기준 참고
}

CACHE_DIR = "tmp/bt_cache"


def fetch(symbol: str, period: str = "5y") -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, symbol.replace(".", "_") + ".csv")
    if os.path.exists(path):
        return pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
    df = yf.Ticker(symbol).history(period=period, auto_adjust=True)[
        ["Open", "High", "Low", "Close", "Volume"]
    ]
    df.index = df.index.tz_localize(None)
    df.index.name = "Date"
    df.to_csv(path)
    return df


def add_indicators(df: pd.DataFrame, market_close: pd.Series | None = None) -> pd.DataFrame:
    d = df.copy()
    for w in (10, 20, 50, 150, 200):
        d[f"SMA{w}"] = d["Close"].rolling(w).mean()
    tr = pd.concat(
        [
            d["High"] - d["Low"],
            (d["High"] - d["Close"].shift()).abs(),
            (d["Low"] - d["Close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["ATR"] = tr.rolling(14).mean()
    d["volSMA20"] = d["Volume"].rolling(20).mean()
    d["hi252"] = d["High"].rolling(252).max()  # 52주 고가 (Trend Template용)
    # 직전 N일 고가(오늘 제외) — 오늘 종가가 이걸 넘으면 돌파
    d["hi50_prev"] = d["High"].rolling(50).max().shift(1)
    d["SMA150_slope"] = d["SMA150"] - d["SMA150"].shift(21)
    d["SMA200_slope"] = d["SMA200"] - d["SMA200"].shift(21)
    if market_close is not None:  # 6개월 상대강도(vs 시장) — Minervini RS 근사
        mkt_ret = market_close.reindex(d.index).ffill().pct_change(126)
        d["rs6"] = d["Close"].pct_change(126) - mkt_ret
    return d


def _breakout50(d: pd.DataFrame, i: int) -> bool:
    r, pr = d.iloc[i], d.iloc[i - 1]
    if pd.isna(r["hi50_prev"]) or pd.isna(pr["hi50_prev"]):
        return False
    today = r["Close"] > r["hi50_prev"]
    yesterday = pr["Close"] > pr["hi50_prev"]
    return bool(today and not yesterday)  # 돌파 첫날만


def entry_signal(d: pd.DataFrame, i: int, preset: str) -> bool:
    r = d.iloc[i]
    if any(pd.isna(r[k]) for k in ("SMA50", "SMA150", "SMA200", "ATR", "volSMA20", "hi252")):
        return False
    vol = r["Volume"]
    if preset == "MINERVINI":
        stage2 = r["Close"] > r["SMA50"] > r["SMA150"] > r["SMA200"] and r["SMA200_slope"] > 0
        rs_ok = True
        if "rs6" in d.columns:  # RS>70 근사: 시장 대비 6개월 상대강도 우위
            if pd.isna(r["rs6"]):
                return False
            rs_ok = r["rs6"] > 0
        return bool(
            stage2
            and _breakout50(d, i)
            and vol > 1.4 * r["volSMA20"]
            and r["Close"] >= 0.75 * r["hi252"]  # 52주 고가 75%↑ (Trend Template)
            and r["Close"] < r["SMA50"] * 1.30  # 과열 차단
            and rs_ok
        )
    if preset == "ONEIL":
        uptrend = r["Close"] > r["SMA50"] and r["SMA50"] > r["SMA200"]
        return bool(uptrend and _breakout50(d, i) and vol > 1.5 * r["volSMA20"])
    if preset == "WEINSTEIN":
        stage2 = r["Close"] > r["SMA150"] and r["SMA150_slope"] > 0
        return bool(stage2 and _breakout50(d, i) and vol > 2.0 * r["volSMA20"])  # 거래량 2배(실제 규칙)
    raise ValueError(preset)


def init_stop(d: pd.DataFrame, i: int, entry: float, preset: str) -> float:
    r = d.iloc[i]
    if preset == "MINERVINI":
        return entry * 0.92  # -8% (canonical, 8%가 임계)
    if preset == "ONEIL":
        return entry * 0.92  # 하드 -8%
    if preset == "WEINSTEIN":
        return min(r["SMA150"], entry - 3 * r["ATR"])  # 넓게(30주선)
    raise ValueError(preset)


def simulate(
    d: pd.DataFrame,
    preset: str,
    entry_from: pd.Timestamp | None = None,
    entry_to: pd.Timestamp | None = None,
    market_ok: pd.Series | None = None,
) -> list[dict]:
    """entry_from/entry_to: 진입 시점을 이 기간으로 제한(홀드아웃 분할용).
    market_ok: 진입일이 시장 상승국면일 때만 진입(시장 국면 필터). None이면 필터 없음.

    진입은 [entry_from, entry_to) 안에서만 허용하고, 청산은 자연 종료까지 둔다.
    """
    trades: list[dict] = []
    n = len(d)
    i = 60
    while i < n - 1:
        sig_date = d.index[i]
        if entry_to is not None and sig_date >= entry_to:
            break  # 진입 허용 기간 종료
        if entry_from is not None and sig_date < entry_from:
            i += 1
            continue
        if not entry_signal(d, i, preset):
            i += 1
            continue
        if market_ok is not None and not bool(market_ok.get(sig_date, False)):
            i += 1  # 시장 하락국면 → 진입 보류
            continue
        entry = d.iloc[i + 1]["Open"]  # t+1 시가 체결
        if pd.isna(entry) or entry <= 0:
            i += 1
            continue
        stop = init_stop(d, i, entry, preset)
        if stop >= entry:
            i += 1
            continue
        entry_idx = i + 1
        risk = entry - stop
        cur_stop = stop
        exit_price = exit_idx = reason = None
        partial_done = False  # 오닐 전용(+25% 절반)
        partial_price = 0.0
        leader = False
        max_gain = 0.0
        j = entry_idx
        while j < n:
            rj = d.iloc[j]
            age = j - entry_idx
            max_gain = max(max_gain, rj["Close"] / entry - 1)
            if rj["Low"] <= cur_stop:  # 손절 우선(보수적)
                exit_price, exit_idx, reason = cur_stop, j, "stop"
                break

            if preset == "MINERVINI":  # 단기 회전형: 빠른 익절 + dead money 교체
                if not leader and rj["High"] >= entry * 1.20:
                    if age <= 15:  # 1~3주 내 +20% 급등 → 주도주 보유
                        leader = True
                    else:  # 느리게 도달 → 즉시 익절
                        exit_price, exit_idx, reason = entry * 1.20, j, "target20"
                        break
                if not leader and age >= 10 and max_gain < 0.05:  # 2주 내 안 오르면 교체(dead money)
                    exit_price, exit_idx, reason = rj["Close"], j, "dead_money"
                    break
                ma = rj["SMA50"] if leader else rj["SMA20"]  # 일반=단기(SMA20), 주도주=여유(SMA50)
                if not pd.isna(ma) and rj["Close"] < ma:
                    exit_price, exit_idx, reason = rj["Close"], j, "flow_break"
                    break

            elif preset == "ONEIL":
                if rj["High"] >= entry * 1.20 and age <= 15:
                    leader = True  # 8주 보유 대상
                if not partial_done and not leader and rj["High"] >= entry * 1.25:
                    partial_price, partial_done = entry * 1.25, True  # +25% 절반 익절
                if not (leader and age < 40):  # 급등주도주 8주 청산 유예
                    ma = rj["SMA50"]
                    if not pd.isna(ma) and rj["Close"] < ma:
                        exit_price, exit_idx, reason = rj["Close"], j, "sma50_break"
                        break

            else:  # WEINSTEIN — 넓은 추적
                ma = rj["SMA150"]
                if not pd.isna(ma) and rj["Close"] < ma:
                    exit_price, exit_idx, reason = rj["Close"], j, "sma150_break"
                    break
            j += 1
        if exit_price is None:
            exit_price, exit_idx, reason = d.iloc[n - 1]["Close"], n - 1, "end"
        final_ret = exit_price / entry - 1
        if partial_done:  # 오닐 분할익절분 + 잔여분 가중 평균
            ret = 0.5 * (partial_price / entry - 1) + 0.5 * final_ret
            r_mult = (0.5 * (partial_price - entry) + 0.5 * (exit_price - entry)) / risk
        else:
            ret = final_ret
            r_mult = (exit_price - entry) / risk
        trades.append(
            {
                "entry_date": d.index[entry_idx].date(),
                "entry": entry,
                "exit_date": d.index[exit_idx].date(),
                "exit": exit_price,
                "ret": ret * 100,
                "R": r_mult,
                "days": exit_idx - entry_idx,
                "reason": reason,
                "partial": partial_done,
            }
        )
        i = exit_idx + 1
    return trades


def per_ticker_return(trades: list[dict]) -> float:
    """각 트레이드에 전액 투입 가정한 복리 수익률(%)."""
    eq = 1.0
    for t in trades:
        eq *= 1 + t["ret"] / 100
    return (eq - 1) * 100


def buy_hold_return(d: pd.DataFrame) -> float:
    c = d["Close"].dropna()
    return (c.iloc[-1] / c.iloc[0] - 1) * 100


def summarize(name: str, all_trades: list[dict]) -> dict:
    if not all_trades:
        return {"preset": name, "trades": 0}
    R = np.array([t["R"] for t in all_trades])
    wins, losses = R[R > 0], R[R <= 0]
    return {
        "preset": name,
        "trades": len(R),
        "win%": round(100 * len(wins) / len(R), 1),
        "avgWinR": round(wins.mean(), 2) if len(wins) else 0.0,
        "avgLossR": round(losses.mean(), 2) if len(losses) else 0.0,
        "payoff": round(wins.mean() / abs(losses.mean()), 2)
        if len(wins) and len(losses) and losses.mean() != 0
        else float("inf"),
        "expectancyR": round(R.mean(), 3),
        "medDays": int(np.median([t["days"] for t in all_trades])),
    }


def main() -> None:
    presets = ["MINERVINI", "ONEIL", "WEINSTEIN"]
    raw = {name: fetch(sym) for name, sym in TICKERS.items()}
    spy_close = raw["SPY"]["Close"]
    data = {name: add_indicators(df, spy_close) for name, df in raw.items()}

    print("=" * 92)
    print("데이터 구간 / buy&hold 기준")
    for name, d in data.items():
        c = d["Close"].dropna()
        print(f"  {name:8} {c.index[0].date()} ~ {c.index[-1].date()}  B&H {buy_hold_return(d):+8.1f}%")

    pooled: dict[str, list[dict]] = {p: [] for p in presets}
    per_ticker: dict[str, dict[str, float]] = {}

    for name, d in data.items():
        per_ticker[name] = {"B&H": buy_hold_return(d)}
        for p in presets:
            tr = simulate(d, p)
            pooled[p].extend(tr)
            per_ticker[name][p] = per_ticker_return(tr)

    print("\n" + "=" * 92)
    print("preset별 종합 (전 티커 트레이드 풀링)  — R = 수익÷초기위험")
    hdr = f"  {'preset':10} {'trades':>7} {'win%':>6} {'avgWinR':>8} {'avgLossR':>9} {'payoff':>7} {'expR':>7} {'medDays':>8}"
    print(hdr)
    for p in presets:
        s = summarize(p, pooled[p])
        if s["trades"] == 0:
            print(f"  {p:10} {'0':>7}")
            continue
        print(
            f"  {p:10} {s['trades']:>7} {s['win%']:>6} {s['avgWinR']:>8} "
            f"{s['avgLossR']:>9} {s['payoff']:>7} {s['expectancyR']:>7} {s['medDays']:>8}"
        )

    print("\n" + "=" * 92)
    print("티커별 복리 수익률(%)  (각 트레이드 전액투입 가정)")
    print(f"  {'ticker':8} {'B&H':>10} {'MINERVINI':>11} {'ONEIL':>9} {'WEINSTEIN':>11}")
    for name in TICKERS:
        r = per_ticker[name]
        print(
            f"  {name:8} {r['B&H']:>10.1f} {r['MINERVINI']:>11.1f} "
            f"{r['ONEIL']:>9.1f} {r['WEINSTEIN']:>11.1f}"
        )

    # buy&hold 대비 승리 종목 수
    print("\n  [buy&hold보다 나은 종목 수]")
    for p in presets:
        wins = sum(1 for name in TICKERS if per_ticker[name][p] > per_ticker[name]["B&H"])
        print(f"    {p:10}: {wins}/{len(TICKERS)}")


if __name__ == "__main__":
    main()
