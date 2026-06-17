"""Plan 7 실데이터 검증: 005930 quarterly_data + AAPL·005930 compute_canslim.

Usage:
    uv run scripts/verify_plan7_canslim.py
"""

import asyncio
import sys
from pathlib import Path


# Load .env from worktree root
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

from dotenv import load_dotenv  # noqa: E402


load_dotenv(root / ".env")

import os  # noqa: E402

from src.providers.kis import KISProvider  # noqa: E402
from src.tools.fundamental import FundamentalTool  # noqa: E402
from src.tools.playbook.accumulation import analyze_accumulation  # noqa: E402
from src.tools.playbook.canslim import compute_canslim  # noqa: E402
from src.tools.playbook.market_regime import assess_market_regime  # noqa: E402
from src.tools.playbook.relative_strength import compute_relative_strength  # noqa: E402
from src.tools.playbook.sector_strength import FmpSectorStrength, KisSectorStrength  # noqa: E402


async def verify_005930_quarterly() -> None:
    """005930 quarterly_data 분기 4개 + eps/eps_yoy 모두 채워지는지 확인."""
    print("=" * 60)
    print("[ 005930.KS — FundamentalTool.execute quarterly_data ]")
    print("=" * 60)
    kis = KISProvider(
        app_key=os.environ["KIS_APP_KEY"],
        app_secret=os.environ["KIS_APP_SECRET"],
    )
    tool = FundamentalTool(kis_provider=kis)
    result = await tool.execute("005930.KS")
    if not result.success:
        print(f"ERROR: {result.error}")
        return

    snap = result.data
    qd = snap.quarterly_data or []
    print(f"quarterly_data count: {len(qd)}")
    for q in qd:
        print(
            f"  period={q.period!r:10s} eps={q.eps!r:12} eps_yoy={q.eps_yoy!r:12}"
            f" revenue={q.revenue!r}"
        )

    # Assertions
    assert len(qd) == 4, f"Expected 4 quarters, got {len(qd)}"
    eps_filled = [q for q in qd if q.eps is not None]
    eps_yoy_filled = [q for q in qd if q.eps_yoy is not None]
    assert len(eps_filled) == 4, f"Expected all 4 eps filled, got {len(eps_filled)}"
    print(f"eps_yoy filled: {len(eps_yoy_filled)}/4")
    # Check no annual rows (period should be YYYY-MM, never YYYY-12 with no prev quarter)
    for q in qd:
        assert len(q.period) == 7 and q.period[4] == "-", f"Unexpected period format: {q.period!r}"
    print("OK: 분기 4개, eps 모두 채워짐, 연간 혼입 없음")
    return snap


async def verify_canslim(ticker: str, kis_provider=None) -> None:
    """ticker의 부품 결과를 조립해 compute_canslim 호출."""
    import yfinance as yf

    print()
    print("=" * 60)
    print(f"[ {ticker} — compute_canslim ]")
    print("=" * 60)

    fundamental_tool = FundamentalTool(kis_provider=kis_provider)
    fund_result = await fundamental_tool.execute(ticker)
    fundamental = fund_result.data if fund_result.success else None
    if fundamental:
        print(
            f"fundamental: quarterly_data={len(fundamental.quarterly_data or [])}q,"
            f" annual_data={len(fundamental.annual_data or [])}y,"
            f" roe={fundamental.roe}"
        )

    # Technical snapshot (price + 52w high from yfinance)
    class TechSnapshot:
        price = None
        high_52w = None

    try:
        t = yf.Ticker(ticker)
        info = t.info
        TechSnapshot.price = info.get("currentPrice") or info.get("regularMarketPrice")
        TechSnapshot.high_52w = info.get("fiftyTwoWeekHigh")
        print(f"snapshot: price={TechSnapshot.price}, high_52w={TechSnapshot.high_52w}")
    except Exception as exc:
        print(f"yfinance snapshot error: {exc}")

    # Volume component stub (no real signal available standalone)
    components = {"volume": {"score": 0, "signals": []}}

    # Accumulation (need price history)
    accumulation = None
    try:
        hist3m = yf.Ticker(ticker).history(period="3mo")
        if not hist3m.empty:
            accumulation = analyze_accumulation(hist3m)
            print(
                f"accumulation: {accumulation.accumulation_ratio:.2f} is_acc={accumulation.is_accumulating}"
            )
    except Exception as exc:
        print(f"accumulation error: {exc}")

    # Sector strength
    sector_strength = None
    try:
        is_korean = ticker.endswith((".KS", ".KQ"))
        if is_korean and kis_provider:
            ss = KisSectorStrength(kis_provider=kis_provider)
            sector_strength = await ss.evaluate(ticker, fundamental=fundamental)
        else:
            ss = FmpSectorStrength(api_key=os.environ.get("FMP_API_KEY", ""))
            sector_strength = await ss.evaluate(ticker, fundamental=fundamental)
        print(
            f"sector_strength: is_strong={sector_strength.is_strong}, trend={sector_strength.trend}"
        )
    except Exception as exc:
        print(f"sector_strength error: {exc}")

    # Relative strength
    relative_strength = None
    try:
        hist1y = yf.Ticker(ticker).history(period="1y")
        if not hist1y.empty:
            index_symbol = "^KS11" if ticker.endswith((".KS", ".KQ")) else "SPY"
            index_hist1y = yf.Ticker(index_symbol).history(period="1y")
            if not index_hist1y.empty:
                relative_strength = compute_relative_strength(
                    hist1y, index_hist1y, index_symbol=index_symbol
                )
                print(
                    f"relative_strength: mansfield_rs={relative_strength.mansfield_rs:.2f}, is_strong={relative_strength.is_strong}"
                )
    except Exception as exc:
        print(f"relative_strength error: {exc}")

    # Market regime (use SPY or KOSPI)
    market_regime = None
    try:
        index_ticker = "^KS11" if ticker.endswith((".KS", ".KQ")) else "SPY"
        index_hist = yf.Ticker(index_ticker).history(period="1y")
        if not index_hist.empty:
            market_regime = assess_market_regime(index_hist, index_symbol=index_ticker)
            print(
                f"market_regime: {market_regime.regime}, allow_new_buy={market_regime.allow_new_buy}"
            )
    except Exception as exc:
        print(f"market_regime error: {exc}")

    result = compute_canslim(
        snapshot=TechSnapshot,
        components=components,
        fundamental=fundamental,
        accumulation=accumulation,
        sector_strength=sector_strength,
        relative_strength=relative_strength,
        market_regime=market_regime,
    )

    print()
    print(f"CAN SLIM Result: score={result.score}")
    print(f"  summary: {result.summary}")
    for label, verdict in [
        ("C", result.c),
        ("A", result.a),
        ("N", result.n),
        ("S", result.s),
        ("L", result.l),
        ("I", result.i),
        ("M", result.m),
    ]:
        met_str = {True: "✅", False: "❌", None: "—"}[verdict.met]
        print(f"  {label}{met_str}: {verdict.detail}")


async def main() -> None:
    kis = KISProvider(
        app_key=os.environ.get("KIS_APP_KEY", ""),
        app_secret=os.environ.get("KIS_APP_SECRET", ""),
    )

    # Task 2 검증
    await verify_005930_quarterly()
    # 순차 호출 (rate limit)
    await asyncio.sleep(1)

    # Task 3 검증 — AAPL (US)
    await verify_canslim("AAPL")
    await asyncio.sleep(1)

    # Task 3 검증 — 005930 (KR)
    await verify_canslim("005930.KS", kis_provider=kis)


if __name__ == "__main__":
    asyncio.run(main())
