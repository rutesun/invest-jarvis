#!/usr/bin/env python
"""Plan 8 engine.evaluate 실데이터 검증 스크립트.

Usage:
    uv run python scripts/verify_plan8_engine.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv


sys.path.insert(0, ".")
load_dotenv(".env")


async def verify_golden_sizing():
    """골든 케이스: 자본 1000만 · 위험1% · 진입5만/손절4.75만 → 40주."""
    from src.tools.playbook.sizing import plan_position

    result = plan_position(
        entry=50_000.0,
        atr_stop=47_500.0,
        invalidation_low=None,
        capital=10_000_000.0,
        risk_pct=0.01,
    )
    print("=== 골든 케이스 sizing ===")
    print(f"  shares={result.shares}, stop={result.stop}, per_share_risk={result.per_share_risk}")
    assert result.shares == 40, f"Expected 40 shares, got {result.shares}"
    print("  PASS: 40주 확인")


async def verify_aapl():
    """AAPL 실데이터 — 미보유 게이트 평가."""
    from src.providers.fmp_provider import FmpProvider
    from src.providers.index_provider import IndexProvider
    from src.providers.yfinance_provider import YFinanceProvider
    from src.tools.playbook.engine import PlaybookEngine
    from src.tools.technical.scorer import TechnicalScorer
    from src.tools.technical.tool import TechnicalAnalysisTool

    yf = YFinanceProvider()
    index_provider = IndexProvider(yf)
    fmp_key = os.getenv("FMP_API_KEY", "")
    fmp_provider = FmpProvider(fmp_key) if fmp_key else None

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=fmp_provider,
        kis_provider=None,
        usd_capital=100_000.0,
        usd_risk_pct=0.01,
    )

    tech_tool = TechnicalAnalysisTool(yf, TechnicalScorer())
    tech_result = await tech_tool.execute("AAPL")

    if not tech_result.success:
        print(f"AAPL technical failed: {tech_result.error}")
        return

    verdict = await engine.evaluate(
        ticker="AAPL",
        technical_result=tech_result.data,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=None,
    )

    print("\n=== AAPL 실측 결과 ===")
    print(f"  headline: {verdict.headline}")
    print(
        f"  market_regime: {verdict.market_regime.regime}, allow={verdict.market_regime.allow_new_buy}"
    )
    print(
        f"  RS: is_strong={verdict.relative_strength.is_strong}, mansfield={verdict.relative_strength.mansfield_rs}"
    )
    print(f"  sector_strength: {verdict.sector_strength}")
    print(f"  canslim.score: {verdict.canslim.score if verdict.canslim else 'N/A'}")
    if verdict.gate:
        print(f"  gate: passed={verdict.gate.passed}, grade={verdict.gate.quality_grade}")
        if verdict.gate.veto_reason:
            print(f"    veto: {verdict.gate.veto_reason}")
    if verdict.position_plan:
        pp = verdict.position_plan
        print(
            f"  position_plan: shares={pp.shares}, entry={pp.entry:.2f}, stop={pp.stop:.2f}, error={pp.error}"
        )


async def verify_samsung():
    """005930.KS (삼성전자) — 미보유 게이트 평가 (KIS 섹터)."""
    from src.providers.index_provider import IndexProvider
    from src.providers.kis import KISProvider
    from src.providers.yfinance_provider import YFinanceProvider
    from src.tools.playbook.engine import PlaybookEngine
    from src.tools.technical.scorer import TechnicalScorer
    from src.tools.technical.tool import TechnicalAnalysisTool

    kis_key = os.getenv("KIS_APP_KEY", "")
    kis_secret = os.getenv("KIS_APP_SECRET", "")

    yf = YFinanceProvider()
    index_provider = IndexProvider(yf)
    kis_provider = KISProvider(kis_key, kis_secret) if kis_key and kis_secret else None

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=None,
        kis_provider=kis_provider,
        krw_capital=10_000_000.0,
        krw_risk_pct=0.01,
    )

    tech_tool = TechnicalAnalysisTool(yf, TechnicalScorer())
    tech_result = await tech_tool.execute("005930.KS")

    if not tech_result.success:
        print(f"005930.KS technical failed: {tech_result.error}")
        return

    verdict = await engine.evaluate(
        ticker="005930.KS",
        technical_result=tech_result.data,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=None,
    )

    print("\n=== 005930.KS (삼성전자) 실측 결과 ===")
    print(f"  headline: {verdict.headline}")
    print(
        f"  market_regime: {verdict.market_regime.regime}, allow={verdict.market_regime.allow_new_buy}"
    )
    print(
        f"  RS: is_strong={verdict.relative_strength.is_strong}, mansfield={verdict.relative_strength.mansfield_rs}"
    )
    print(f"  sector_strength: {verdict.sector_strength}")
    print(f"  canslim.score: {verdict.canslim.score if verdict.canslim else 'N/A'}")
    if verdict.gate:
        print(f"  gate: passed={verdict.gate.passed}, grade={verdict.gate.quality_grade}")
        if verdict.gate.veto_reason:
            print(f"    veto: {verdict.gate.veto_reason}")


async def main():
    await verify_golden_sizing()
    await verify_aapl()
    await verify_samsung()
    print("\n검증 완료.")


if __name__ == "__main__":
    asyncio.run(main())
