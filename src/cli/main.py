import asyncio
import contextlib
import logging
import os
import re
from pathlib import Path
from typing import Literal

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

from src.llm.provider import LLMProvider
from src.pipelines.brief import BriefPipeline
from src.pipelines.deep_dive import DeepDivePipeline
from src.pipelines.quick_check import QuickCheckPipeline
from src.pipelines.screener import ScreenerPipeline
from src.providers.kis import KISProvider
from src.providers.naver import NaverProvider
from src.providers.ticker_resolver import TickerResolver
from src.providers.yfinance_provider import YFinanceProvider
from src.tools.disclosure import DARTDisclosureFetcher, DisclosureTool, SECDisclosureFetcher
from src.tools.fundamental import FundamentalTool
from src.tools.macro import MacroTool, TickerMacroSnapshot
from src.tools.news import NewsTool
from src.tools.screener.evidence import EvidenceCollector
from src.tools.screener.universe import UniverseBuilder
from src.tools.technical.presentation import format_long_sma
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool
from src.utils.sector_metrics import SectorMetrics


# Load environment variables from .env file
load_dotenv()

# 지표명 표시 매핑
METRIC_DISPLAY_NAMES = {
    "pe_ratio": "P/E Ratio",
    "forward_pe": "Forward P/E",
    "peg_ratio": "PEG Ratio",
    "pb_ratio": "P/B Ratio",
    "ps_ratio": "PSR",
    "ev_ebitda": "EV/EBITDA",
    "roe": "ROE",
    "roa": "ROA",
    "revenue_growth": "매출 성장률",
    "earnings_growth": "이익 성장률",
    "gross_margin": "매출총이익률",
    "operating_margin": "영업이익률",
    "profit_margin": "순이익률",
    "debt_to_equity": "Debt/Equity",
    "free_cash_flow": "Free Cash Flow",
    "operating_cash_flow": "Operating Cash Flow",
    "fcf_yield": "FCF Yield",
    "dividend_yield": "배당 수익률",
    "payout_ratio": "배당 성향",
    "current_ratio": "유동비율",
    "quick_ratio": "당좌비율",
    "market_cap": "시가총액",
}
_SEC_DISCLOSURE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+\.(htm|html|txt|xml)$")


def _get_metric_display_name(metric_name: str) -> str:
    """지표명을 표시용 이름으로 변환

    Args:
        metric_name: 내부 지표명 (예: "pe_ratio")

    Returns:
        표시용 이름 (예: "P/E Ratio")
    """
    # Camel case로 변환 (fallback)
    if metric_name not in METRIC_DISPLAY_NAMES:
        return " ".join(word.capitalize() for word in metric_name.split("_"))

    return METRIC_DISPLAY_NAMES[metric_name]


def _format_metric_value(metric_name: str, value: float | None) -> str:
    """지표 타입에 따라 값 포맷팅

    Args:
        metric_name: 지표명
        value: 지표 값

    Returns:
        포맷팅된 문자열
    """
    if value is None:
        return "N/A"

    # 퍼센트 지표
    if metric_name in [
        "revenue_growth",
        "earnings_growth",
        "gross_margin",
        "operating_margin",
        "profit_margin",
        "fcf_yield",
        "dividend_yield",
        "roe",
        "roa",
        "payout_ratio",
    ]:
        return f"{value * 100:.1f}%"

    # 달러 금액 (10억 단위)
    elif metric_name in ["free_cash_flow", "operating_cash_flow", "market_cap"]:
        return f"${value / 1e9:.1f}B"

    # 일반 숫자
    else:
        # Format with appropriate precision: 2 decimals if value < 10, else 1
        formatted = f"{value:.2f}" if abs(value) < 10 else f"{value:.1f}"
        # Remove trailing zeros after decimal point
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def _format_disclosure_title(form_type: str, description: str) -> str:
    text = (description or "").strip()
    if not text:
        return f"{form_type} 공시"
    if _SEC_DISCLOSURE_FILENAME_PATTERN.match(text):
        return f"SEC {form_type} 공시"
    return text


logger = logging.getLogger(__name__)

app = typer.Typer(help="Invest Jarvis - Financial Analysis CLI")
report_app = typer.Typer(help="리포트 생성")
console = Console()


def version_callback(value: bool):
    if value:
        console.print("invest-jarvis version 0.3.0")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable debug logging"),
):
    """Invest Jarvis - Financial Analysis CLI"""
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)


async def resolve_ticker(query: str) -> str:
    """Resolve user query to ticker symbol."""
    resolver = TickerResolver()
    try:
        resolution = await resolver.resolve(query)
        return resolution.resolved_ticker
    except Exception as e:
        raise ValueError(f"Could not resolve ticker for '{query}': {e}") from e


async def run_quick_check(ticker_or_name: str) -> dict:
    """Run quick check pipeline."""
    # Resolve ticker if company name is provided
    ticker = await resolve_ticker(ticker_or_name)

    # Auto-detect Korean stocks and use KIS API if available
    is_korean_stock = ticker.endswith((".KS", ".KQ"))
    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    kis_provider = None

    if is_korean_stock and kis_key and kis_secret:
        logger.info(f"한국 주식 {ticker} → KIS API 사용 (실시간)")
        from src.providers.kis_wrapper import KISProviderWrapper

        kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret)

        # KIS API 인증 테스트 (필수)
        try:
            await kis_provider._get_access_token()
            logger.info("KIS API 인증 성공")
        except Exception as e:
            raise ValueError(
                f"KIS API 인증 실패: {e}\n"
                "해결 방법:\n"
                "1. KIS Developers 포털(https://apiportal.koreainvestment.com) 로그인\n"
                "2. '서비스 관리' → APP KEY 확인\n"
                "3. '국내주식시세' 서비스가 '승인' 상태인지 확인\n"
                "4. .env 파일의 KIS_APP_KEY, KIS_APP_SECRET 재확인"
            ) from e

        provider = KISProviderWrapper(kis_provider=kis_provider)
    else:
        if is_korean_stock:
            logger.warning(
                f"한국 주식 {ticker}이지만 KIS API 키가 없습니다. yfinance로 fallback (3일 지연 가능)"
            )
        provider = YFinanceProvider()

    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)
    pipeline = QuickCheckPipeline(technical_tool=tool)
    return await pipeline.run(ticker)


async def run_quick_checks(queries: list[str]) -> list[dict]:
    """Run quick checks independently for each query."""
    results: list[dict] = []
    for query in queries:
        try:
            results.append(await run_quick_check(query))
        except Exception as exc:
            results.append(
                {
                    "ticker": query,
                    "error": str(exc),
                    "success": False,
                }
            )
    return results


@app.command()
def check(
    queries: list[str] = typer.Argument(
        ..., help="One or more stock tickers or company names"
    ),
    detail_history: bool = typer.Option(
        False,
        "--detail-history",
        help="Show multi-line score history context",
    ),
):
    """Quick check - multi-ticker technical analysis without LLM or Macro."""
    results = asyncio.run(run_quick_checks(queries))
    formatter = QuickCheckPipeline(technical_tool=None)
    failed = False

    for result in results:
        if result.get("success", False):
            console.print(
                Markdown(formatter.format_output(result, detailed_history=detail_history))
            )
        else:
            failed = True
            ticker = result.get("ticker", "UNKNOWN")
            console.print(f"[red]{ticker}: {result.get('error', 'Unknown error')}[/red]")

    if failed:
        raise typer.Exit(1)


async def run_deep_dive(ticker_or_name: str, provider: str) -> dict:
    """Run deep dive analysis pipeline."""
    # Resolve ticker if company name is provided
    ticker = await resolve_ticker(ticker_or_name)

    api_key_env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    base_url_env = "OPENAI_BASE_URL" if provider == "openai" else "ANTHROPIC_BASE_URL"
    api_key = os.getenv(api_key_env)
    base_url = os.getenv(base_url_env)
    if not api_key:
        raise ValueError(f"Missing {api_key_env} environment variable")

    # Price data provider: 한국 주식이면 KIS API, 아니면 yfinance
    from src.providers.kis import KISProvider

    is_korean_stock = ticker.endswith((".KS", ".KQ"))
    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    kis_provider = None

    if is_korean_stock and kis_key and kis_secret:
        # 한국 주식 + KIS API 키 있음 → KIS 사용 (실시간)
        # KIS API는 .KS/.KQ 접미사 없이 종목코드만 사용
        logger.info(f"한국 주식 {ticker} → KIS API 사용 (실시간)")
        from src.providers.kis_wrapper import KISProviderWrapper

        kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret)

        # KIS API 인증 테스트 (필수)
        try:
            await kis_provider._get_access_token()
            logger.info("KIS API 인증 성공")
        except Exception as e:
            raise ValueError(
                f"KIS API 인증 실패: {e}\n"
                "해결 방법:\n"
                "1. KIS Developers 포털(https://apiportal.koreainvestment.com) 로그인\n"
                "2. '서비스 관리' → APP KEY 확인\n"
                "3. '국내주식시세' 서비스가 '승인' 상태인지 확인\n"
                "4. .env 파일의 KIS_APP_KEY, KIS_APP_SECRET 재확인"
            ) from e

        price_provider = KISProviderWrapper(kis_provider=kis_provider)
    else:
        # 미국 주식 또는 KIS 키 없음 → yfinance fallback
        if is_korean_stock:
            logger.warning(
                f"한국 주식 {ticker}이지만 KIS API 키가 없습니다. "
                "yfinance로 fallback (3일 지연 가능)"
            )
        price_provider = YFinanceProvider()

    scorer = TechnicalScorer()
    technical_tool = TechnicalAnalysisTool(provider=price_provider, scorer=scorer)
    fundamental_tool = FundamentalTool(kis_provider=kis_provider if is_korean_stock else None)
    news_tool = NewsTool()
    llm = LLMProvider.create(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    sec_fetcher = SECDisclosureFetcher()
    opendart_key = os.getenv("OPENDART_API_KEY")
    if not opendart_key:
        logger.warning("OPENDART_API_KEY가 설정되지 않았습니다. 한국주식 공시 데이터가 제외됩니다.")
    dart_fetcher = DARTDisclosureFetcher(api_key=opendart_key) if opendart_key else None
    disclosure_tool = DisclosureTool(sec_fetcher=sec_fetcher, dart_fetcher=dart_fetcher)

    # 수급 툴: KIS API (get_investor_trend) 사용. 키 없으면 FlowTool이 graceful failure 처리
    from src.tools.flow import FlowTool

    if not (kis_key and kis_secret):
        logger.warning(
            "KIS_APP_KEY 또는 KIS_APP_SECRET이 설정되지 않았습니다. "
            "한국주식 수급 데이터가 제외됩니다."
        )
    flow_provider = (
        KISProvider(app_key=kis_key, app_secret=kis_secret) if kis_key and kis_secret else None
    )
    flow_tool = FlowTool(kis_provider=flow_provider)

    # PlaybookEngine 주입: index/fmp/kis provider 있으면 생성
    playbook_engine = None
    try:
        from src.providers.index_provider import IndexProvider
        from src.tools.playbook.engine import PlaybookEngine
        from src.tools.playbook.holdings import load_holdings

        holdings_config = load_holdings()
        capital_usd, risk_pct_usd = holdings_config.usd_capital, holdings_config.usd_risk_pct
        capital_krw, risk_pct_krw = holdings_config.krw_capital, holdings_config.krw_risk_pct

        fmp_api_key = os.getenv("FMP_API_KEY")
        fmp_provider = None
        if fmp_api_key:
            with contextlib.suppress(Exception):
                from src.providers.fmp_provider import FmpProvider

                fmp_provider = FmpProvider(api_key=fmp_api_key)

        playbook_engine = PlaybookEngine(
            index_provider=IndexProvider(),
            fmp_provider=fmp_provider,
            kis_provider=kis_provider,
            usd_capital=capital_usd,
            usd_risk_pct=risk_pct_usd or 0.01,
            krw_capital=capital_krw,
            krw_risk_pct=risk_pct_krw or 0.01,
        )
    except Exception as _e:
        logger.debug("PlaybookEngine 초기화 실패 (플레이북 섹션 생략): %s", _e)

    pipeline = DeepDivePipeline(
        technical_tool=technical_tool,
        news_tool=news_tool,
        llm=llm,
        fundamental_tool=fundamental_tool,
        disclosure_tool=disclosure_tool,
        flow_tool=flow_tool,
        playbook_engine=playbook_engine,
        macro_tool=MacroTool(),
    )

    return await pipeline.run(ticker)


def _format_growth_rate(value: float | None) -> str:
    """Format growth rate with +/- sign"""
    if value is None:
        return "N/A"
    return f"{value * 100:+.2f}%"


def _format_factor_label(value: str) -> str:
    return {
        "technical": "가격",
        "flow": "수급",
        "event": "이벤트",
        "valuation": "밸류에이션",
    }.get(value, value)


def _format_timing_label(value: str) -> str:
    return {
        "조정_대기": "조정 대기",
        "보류": "보류",
        "지금": "지금",
    }.get(value, value)


def _format_top_summary(decision_summary) -> str:
    lines = [
        "## 판단 요약",
        "",
        f"- **주도 팩터**: {_format_factor_label(decision_summary.leader)}",
        f"- **핵심 변수**: {', '.join(decision_summary.core_variables)}",
        f"- **액션**: {decision_summary.action} | {_format_timing_label(decision_summary.timing)}",
        f"- **한줄 판단**: {decision_summary.action_sentence}",
    ]
    if decision_summary.defer_reason:
        lines.append(f"- **보류 이유**: {decision_summary.defer_reason}")
    lines.append("")
    return "\n".join(lines)


def _format_macro_section(macro: TickerMacroSnapshot | None) -> str:
    if macro is None:
        return ""
    return "\n".join(
        [
            "## Macro",
            f"- **VIX**: {macro.vix:.2f} ({macro.vix_change:+.2f})",
            f"- **Fear & Greed**: {macro.fear_greed} ({macro.fear_greed_label})",
            f"- **WTI**: ${macro.wti:.2f} ({macro.wti_change:+.2f})",
            f"- **US 10Y**: {macro.us_10y:.2f}%",
            f"- **US 2Y**: {macro.us_2y:.2f}%",
            f"- **10Y-2Y Spread**: {macro.yield_spread:+.2f}%p",
            f"- **DXY**: {macro.dxy:.2f} ({macro.dxy_change:+.2f})",
        ]
    )


def _format_factor_section(factor_assessments: list) -> str:
    lines = ["## 팩터 분류", ""]
    for role in ("주도", "보조", "참고"):
        filtered = [item for item in factor_assessments if item.role == role]
        if not filtered:
            continue
        lines.append(f"### {role}")
        lines.append("")
        for item in filtered:
            lines.append(f"- **{_format_factor_label(item.factor_type)}**: {item.summary}")
            lines.append(f"  이유: {item.role_reason}")
        lines.append("")
    return "\n".join(lines)


def _format_scenario_section(scenarios: list) -> str:
    lines = ["## 액션 시나리오", ""]
    for scenario in scenarios:
        lines.append(f"### {scenario.name}")
        lines.append("")
        lines.append(f"- **가격 레벨**: {', '.join(scenario.trigger_price_levels)}")
        lines.append(f"- **확인 조건**: {', '.join(scenario.confirming_factors)}")
        lines.append(f"- **무효화 조건**: {', '.join(scenario.invalidation_conditions)}")
        lines.append(f"- **예상 경로**: {scenario.expected_path}")
        lines.append(f"- **대응**: {scenario.recommended_action}")
        lines.append("")
    return "\n".join(lines)


def _format_pattern_section(chart_patterns: dict | None) -> str:
    if not isinstance(chart_patterns, dict):
        return ""

    detected_items: list[dict] = []
    for item in chart_patterns.values():
        payload = _to_payload_dict(item)
        if not isinstance(payload, dict):
            continue
        if not payload.get("detected"):
            continue
        detected_items.append(payload)

    lines = ["## 패턴 분석", ""]
    if not detected_items:
        lines.append("- 감지된 유효 패턴 없음")
        lines.append("")
        return "\n".join(lines)

    def _sort_key(item: dict) -> tuple[int, float]:
        days_ago = item.get("days_ago")
        if isinstance(days_ago, int):
            return (days_ago, -(float(item.get("confidence") or 0.0)))
        return (10**9, -(float(item.get("confidence") or 0.0)))

    for item in sorted(detected_items, key=_sort_key):
        pattern_name = str(item.get("pattern_name") or "패턴")
        confidence = float(item.get("confidence") or 0.0)
        days_ago = item.get("days_ago")
        timing = (
            "오늘 완성"
            if days_ago == 0
            else f"{days_ago}일 전 완성"
            if isinstance(days_ago, int)
            else "완성 시점 미확인"
        )
        description = str(item.get("description") or "").strip()
        if description:
            lines.append(
                f"- **{pattern_name}**: {timing} | 신뢰도 {confidence * 100:.0f}% | {description}"
            )
        else:
            lines.append(f"- **{pattern_name}**: {timing} | 신뢰도 {confidence * 100:.0f}%")
    lines.append("")
    return "\n".join(lines)


def _to_payload_dict(item):
    if item is None:
        return None
    return item if isinstance(item, dict) else item.model_dump()


def _format_zone_bounds(zone) -> str:
    zone_dict = _to_payload_dict(zone)
    return f"{zone_dict['lower_bound']:.2f}~{zone_dict['upper_bound']:.2f}"


def _split_supply_zones_by_price(supply_zones, current_price: float) -> tuple[list, list]:
    active_supply = []
    absorbed_supply = []
    for zone in supply_zones:
        zone_dict = _to_payload_dict(zone)
        if zone_dict["upper_bound"] <= current_price:
            absorbed_supply.append(zone)
        else:
            active_supply.append(zone)
    return active_supply, absorbed_supply


def _format_structure_levels(structure_levels, current_price: float) -> str:
    if not structure_levels:
        return ""

    structure_dict = _to_payload_dict(structure_levels)
    demand_zones = structure_dict.get("demand_zones")
    supply_zones = structure_dict.get("supply_zones")
    balance_zones = structure_dict.get("balance_zones")
    if demand_zones is None and supply_zones is None:
        demand_zones = structure_dict.get("support_zones") or []
        supply_zones = structure_dict.get("resistance_zones") or []
        balance_zones = structure_dict.get("former_levels") or []
    demand_zones = demand_zones or []
    supply_zones = supply_zones or []
    balance_zones = balance_zones or []
    active_supply, absorbed_supply = _split_supply_zones_by_price(supply_zones, current_price)
    invalidation = _to_payload_dict(structure_dict.get("invalidation"))

    lines = ["## 구조 레벨", ""]
    lines.append(
        f"- **수요 존**: {', '.join(_format_zone_bounds(zone) for zone in demand_zones) if demand_zones else '없음'}"
    )
    lines.append(
        f"- **공급 존**: {', '.join(_format_zone_bounds(zone) for zone in active_supply) if active_supply else '없음'}"
    )
    lines.append(
        f"- **흡수 공급 존**: {', '.join(_format_zone_bounds(zone) for zone in absorbed_supply) if absorbed_supply else '없음'}"
    )
    lines.append(
        f"- **밸런스 존**: {', '.join(_format_zone_bounds(zone) for zone in balance_zones) if balance_zones else '없음'}"
    )
    lines.append(f"- **무효화 기준**: {invalidation['label'] if invalidation else '없음'}")
    lines.append("")
    return "\n".join(lines)


def _format_execution_levels(execution_levels) -> str:
    if not execution_levels:
        return ""

    lines = ["## 실행 레벨", ""]
    for level in execution_levels:
        level_dict = _to_payload_dict(level)
        lines.append(
            f"- **{level_dict['description']}**: ${level_dict['price']:.2f} ({level_dict['distance_pct']:+.1f}%)"
        )
    lines.append("")
    return "\n".join(lines)


def _format_presented_structure(presented_structure) -> str:
    if not presented_structure:
        return ""
    payload = _to_payload_dict(presented_structure)
    blocks = payload.get("cli_blocks") or []
    if not blocks:
        return ""
    text = "\n".join(blocks)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _format_raw_analysis_sections(result: dict) -> str:
    ticker = result.get("ticker", "")
    technical = result["technical"]
    tech_summary = result["technical_summary"]
    news_analysis = result.get("news_analysis")
    fundamental = result.get("fundamental")
    fundamental_summary = result.get("fundamental_summary")
    snapshot = technical.indicators or technical.snapshot
    long_sma_snapshot = technical.snapshot

    output = ""

    perf_parts = []
    if snapshot.perf_1m is not None:
        perf_parts.append(f"1M: {snapshot.perf_1m:+.2f}%")
    if snapshot.perf_3m is not None:
        perf_parts.append(f"3M: {snapshot.perf_3m:+.2f}%")
    if snapshot.perf_6m is not None:
        perf_parts.append(f"6M: {snapshot.perf_6m:+.2f}%")
    if snapshot.perf_1y is not None:
        perf_parts.append(f"1Y: {snapshot.perf_1y:+.2f}%")
    if perf_parts:
        output += f"**퍼포먼스**: {' | '.join(perf_parts)}\n\n"

    output += "## 원시 데이터\n\n"
    output += "### 기술적 지표\n\n"

    if snapshot.sma_20 is not None:
        output += f"- **20일 이동평균선**: ${snapshot.sma_20:.2f}\n"
    if snapshot.sma_50 is not None:
        output += f"- **50일 이동평균선**: ${snapshot.sma_50:.2f}\n"
    output += (
        f"- **SMA 100**: {format_long_sma(long_sma_snapshot.sma_100, long_sma_snapshot.sma_100_slope_pct)}\n"
    )
    if snapshot.sma_150 is not None:
        output += f"- **150일 이동평균선**: ${snapshot.sma_150:.2f}\n"
    output += (
        f"- **SMA 200**: {format_long_sma(long_sma_snapshot.sma_200, long_sma_snapshot.sma_200_slope_pct)}\n"
    )

    output += "\n"

    if snapshot.rsi is not None:
        output += f"- **RSI (14일)**: {snapshot.rsi:.1f}\n"
    if snapshot.crsi is not None:
        output += f"- **Cycle RSI**: {snapshot.crsi:.1f}"
        if snapshot.crsi_high_band is not None and snapshot.crsi_low_band is not None:
            output += f" (밴드: {snapshot.crsi_low_band:.1f} - {snapshot.crsi_high_band:.1f})"
        output += "\n"
    if snapshot.macd is not None:
        output += f"- **MACD**: {snapshot.macd:.2f}"
        if snapshot.macd_signal is not None:
            output += f" (시그널: {snapshot.macd_signal:.2f})"
        output += "\n"

    output += "\n"

    if snapshot.adx is not None:
        output += f"- **ADX (추세 강도)**: {snapshot.adx:.1f}\n"

    if snapshot.supertrend_direction is not None:
        direction = "상승" if snapshot.supertrend_direction == 1 else "하락"
        output += f"- **Supertrend**: {direction}"

        if technical.components and "supertrend" in technical.components:
            supertrend_metrics = technical.components["supertrend"]["metrics"]
            if "supertrend_value" in supertrend_metrics:
                st_value = supertrend_metrics["supertrend_value"]
                output += f" (라인: ${st_value:.2f})"
                distance = ((snapshot.price - st_value) / st_value) * 100
                if abs(distance) > 0.1:
                    output += f", 현재가 대비 {distance:+.2f}%"

        output += "\n"

    output += "\n"

    if snapshot.pivot is not None:
        output += f"- **피봇 포인트**: ${snapshot.pivot:.2f}\n"
    if snapshot.support_s1 is not None:
        output += f"- **지지선 S1**: ${snapshot.support_s1:.2f}\n"
    if snapshot.resistance_r1 is not None:
        output += f"- **저항선 R1**: ${snapshot.resistance_r1:.2f}\n"
    if snapshot.high_52w is not None:
        output += f"- **52주 최고가**: ${snapshot.high_52w:.2f}\n"
    if snapshot.low_52w is not None:
        output += f"- **52주 최저가**: ${snapshot.low_52w:.2f}\n"

    output += "\n"

    output += "### 기술 요약\n\n"
    output += f"**총점**: {technical.total_score}\n\n"
    if getattr(technical, "component_raw_total", None) is not None:
        output += f"**Component Raw Total**: {technical.component_raw_total}\n\n"
    if getattr(technical, "adjusted_score", None) is not None:
        output += f"**Adjusted Score**: {technical.adjusted_score}\n\n"
    if getattr(technical, "technical_verdict", None):
        verdict = technical.technical_verdict
        output += f"**기술 Verdict**: {verdict.action}"
        verdict_parts = []
        if verdict.reasons:
            verdict_parts.append(verdict.reasons[0])
        if verdict.cautions:
            verdict_parts.append(f"주의: {verdict.cautions[0]}")
        if verdict.invalidation_level is not None:
            verdict_parts.append(f"무효화: {verdict.invalidation_level:.2f}")
        if verdict.score_trend_summary:
            verdict_parts.append(verdict.score_trend_summary)
        if verdict_parts:
            output += f" — {' / '.join(verdict_parts)}"
        output += "\n\n"
    if getattr(technical, "score_history", None):
        output += "**최근 점수 추이**:\n"
        for point in technical.score_history:
            output += (
                f"- {point.date}: close {point.close:,.2f}, "
                f"raw {point.component_raw_total}, adjusted {point.adjusted_score}, "
                f"{point.verdict_action} — {point.one_line_reason}\n"
            )
        output += "\n"
    output += f"**요약**: {tech_summary.summary}\n\n"
    output += f"**추천**: {tech_summary.recommendation} (신뢰도: {tech_summary.confidence * 100:.0f}%)\n\n"
    output += f"**근거**: {tech_summary.rationale}\n\n"

    if tech_summary.key_insights:
        output += "**핵심 인사이트**:\n"
        for insight in tech_summary.key_insights:
            output += f"- {insight}\n"
        output += "\n"

    if fundamental and fundamental_summary:
        output += "## Fundamental Analysis\n\n"
        output += "### Key Metrics\n\n"

        output += f"**Sector/Industry**: {fundamental.sector or 'N/A'} / {fundamental.industry or 'N/A'}\n\n"

        priority_metrics = SectorMetrics.get_priority_metrics(fundamental.sector or "")

        for metric_name in priority_metrics:
            value = getattr(fundamental, metric_name, None)
            display_name = _get_metric_display_name(metric_name)
            formatted = _format_metric_value(metric_name, value)
            output += f"⭐ **{display_name}**: {formatted}\n\n"

        output += "\n"

        all_metric_names = [
            "market_cap",
            "pe_ratio",
            "forward_pe",
            "peg_ratio",
            "pb_ratio",
            "ps_ratio",
            "ev_ebitda",
            "roe",
            "roa",
            "gross_margin",
            "operating_margin",
            "profit_margin",
            "revenue_growth",
            "earnings_growth",
            "debt_to_equity",
            "current_ratio",
            "quick_ratio",
            "free_cash_flow",
            "operating_cash_flow",
            "fcf_yield",
            "dividend_yield",
            "payout_ratio",
        ]

        remaining_metrics = [m for m in all_metric_names if m not in priority_metrics]

        for metric_name in remaining_metrics:
            value = getattr(fundamental, metric_name, None)
            display_name = _get_metric_display_name(metric_name)
            formatted = _format_metric_value(metric_name, value)
            output += f"- **{display_name}**: {formatted}\n"

        output += "\n"

        if fundamental.quarterly_data is not None and len(fundamental.quarterly_data) > 0:
            is_korean = ticker.endswith((".KS", ".KQ"))
            output += "### 분기별 실적\n\n"
            output += "**매출 추이:**\n\n"
            for q in fundamental.quarterly_data:
                if q.revenue is not None:
                    revenue_str = f"{q.revenue:.0f}억" if is_korean else f"${q.revenue / 1e9:.2f}B"
                    yoy_str = _format_growth_rate(q.revenue_yoy)
                    qoq_str = _format_growth_rate(q.revenue_qoq)
                    output += f"- {q.period}: {revenue_str} (YoY {yoy_str}, QoQ {qoq_str})\n"

            output += "\n"
            output += "**이익 추이:**\n\n"
            for q in fundamental.quarterly_data:
                if q.earnings is not None:
                    earnings_str = (
                        f"{q.earnings:.0f}억" if is_korean else f"${q.earnings / 1e9:.2f}B"
                    )
                    yoy_str = _format_growth_rate(q.earnings_yoy)
                    qoq_str = _format_growth_rate(q.earnings_qoq)
                    output += f"- {q.period}: {earnings_str} (YoY {yoy_str}, QoQ {qoq_str})\n"

            output += "\n"

        # EPS 추이 (분기 YoY + 연간 시계열)
        if fundamental.quarterly_data is not None:
            eps_quarters = [q for q in fundamental.quarterly_data if q.eps is not None]
            if eps_quarters:
                output += "**분기 EPS 추이:**\n\n"
                for q in eps_quarters:
                    yoy_str = _format_growth_rate(q.eps_yoy)
                    output += f"- {q.period}: EPS {q.eps:,.2f} (YoY {yoy_str})\n"
                output += "\n"

        annual_data = getattr(fundamental, "annual_data", None)
        if annual_data is not None and len(annual_data) > 0:
            output += "**연간 EPS 추이:**\n\n"
            for a in annual_data:
                if a.eps is not None:
                    output += f"- {a.year}: EPS {a.eps:,.2f}\n"
            output += "\n"

        output += "### LLM Analysis\n\n"
        output += f"**Summary**: {fundamental_summary.summary}\n\n"
        output += f"**Valuation**: {fundamental_summary.valuation_assessment} (신뢰도: {fundamental_summary.confidence * 100:.0f}%)\n\n"

        if fundamental_summary.strengths:
            output += "**Strengths**:\n"
            for strength in fundamental_summary.strengths:
                output += f"- {strength}\n"
            output += "\n"

        if fundamental_summary.weaknesses:
            output += "**Weaknesses**:\n"
            for weakness in fundamental_summary.weaknesses:
                output += f"- {weakness}\n"
            output += "\n"

    if news_analysis:
        output += "## News Analysis\n\n"
        output += f"**Sentiment**: {news_analysis.sentiment} (신뢰도: {news_analysis.confidence * 100:.0f}%)\n\n"
        output += f"**Summary**: {news_analysis.summary}\n\n"
        output += f"**Impact Assessment**: {news_analysis.impact_assessment}\n\n"

        if news_analysis.key_themes:
            output += "**Key Themes**: " + ", ".join(news_analysis.key_themes) + "\n\n"

    disclosure = result.get("disclosure")
    if disclosure:
        output += "## 공시 분석\n\n"
        output += f"최근 3개월 주요 공시 {len(disclosure)}건:\n\n"
        for i, item in enumerate(disclosure, 1):
            display_title = _format_disclosure_title(item.form_type, item.description)
            output += f"{i}. **[{item.form_type}] {display_title}** ({item.date})\n"
            output += f"   → [공시 원문 보기]({item.url})\n\n"

    flow = result.get("flow")
    if flow:
        output += "## 수급 동향\n\n"
        output += "| 투자자 | 1일 | 5일 | 10일 | 10일 순매수 일수 |\n"
        output += "|--------|-----|-----|------|------------------|\n"
        output += (
            f"| 외국인 "
            f"| {flow.foreign_direction_1d} ({flow.foreign_net_1d:+,}) "
            f"| {flow.foreign_direction_5d} ({flow.foreign_net_5d:+,}) "
            f"| {flow.foreign_direction_10d} ({flow.foreign_net_10d:+,}) "
            f"| {flow.foreign_buy_days}/10일 |\n"
        )
        output += (
            f"| 기관 "
            f"| {flow.institution_direction_1d} ({flow.institution_net_1d:+,}) "
            f"| {flow.institution_direction_5d} ({flow.institution_net_5d:+,}) "
            f"| {flow.institution_direction_10d} ({flow.institution_net_10d:+,}) "
            f"| {flow.institution_buy_days}/10일 |\n"
        )
        output += "\n"

    explanation = result.get("integrated_explanation")
    if explanation:
        output += "## 종합 해설\n\n"
        output += f"{explanation.decision_explanation}\n\n"
        if explanation.rationale:
            output += "**근거**:\n"
            for r in explanation.rationale:
                output += f"- {r}\n"
            output += "\n"
        if explanation.risks:
            output += "**리스크**:\n"
            for r in explanation.risks:
                output += f"- {r}\n"
            output += "\n"
        if explanation.monitoring_points:
            output += "**모니터링 포인트**:\n"
            for m in explanation.monitoring_points:
                output += f"- {m}\n"
            output += "\n"

    return output


def _format_playbook_section(verdict) -> str:
    """PlaybookVerdict를 §15 형식으로 렌더링한다."""
    out = "## 📋 플레이북 평가\n\n"

    # 판정 헤드라인
    gate = verdict.gate
    if gate is not None:
        if gate.passed:
            grade = gate.quality_grade or "?"
            out += f"**판정**: 매수 적격 (Grade={grade})\n\n"
        else:
            out += "**판정**: 매수 부적격\n\n"
            if gate.veto_reason:
                out += f"- 사유: {gate.veto_reason}\n\n"

        # 체크리스트 A·B·C·E
        if gate.checklist:
            out += "**체크리스트**:\n\n"
            sym = {True: "✅", False: "❌", None: "—"}
            for check in gate.checklist:
                mark = sym.get(check.met, "—")
                req_tag = "(필수)" if check.required else "(선택)"
                out += f"- {mark} {check.name} {req_tag}: {check.reason}\n"
            out += "\n"

    # CAN SLIM 요약 + 7요소 상세 지표
    canslim = verdict.canslim
    if canslim is not None:
        out += f"**CAN SLIM**: {canslim.summary}\n\n"
        sym = {True: "✅", False: "❌", None: "—"}
        elements = [
            ("C", "분기EPS", canslim.c),
            ("A", "연간EPS+ROE", canslim.a),
            ("N", "신고가 근접", canslim.n),
            ("S", "거래량", canslim.s),
            ("L", "주도주(업종+RS)", canslim.l),
            ("I", "기관 매집", canslim.i),
            ("M", "시장환경", canslim.m),
        ]
        for key, label, element in elements:
            mark = sym.get(element.met, "—")
            detail = f": {element.detail}" if element.detail else ""
            out += f"- {mark} {key} ({label}){detail}\n"
        out += "\n"

    # 포지션 플랜 (미보유 + 게이트 통과 시)
    position_plan = verdict.position_plan
    if position_plan is not None and position_plan.error is None:
        out += "**포지션 플랜**:\n\n"
        out += f"- 진입가: {position_plan.entry:.2f}\n"
        out += f"- 손절가: {position_plan.stop:.2f} ({position_plan.stop_basis})\n"
        if position_plan.shares is not None:
            out += f"- 수량: {position_plan.shares}주\n"
        if position_plan.position_value is not None:
            out += f"- 포지션 금액: {position_plan.position_value:,.0f}\n"
        if position_plan.weight_pct is not None:
            out += f"- 자본 비중: {position_plan.weight_pct:.1f}%\n"
        for label, price in position_plan.r_targets.items():
            out += f"- 목표 {label}: {price:.2f}\n"
        out += "\n"

    # 매도 판정 (보유 시)
    exit_verdict = verdict.exit_verdict
    if exit_verdict is not None:
        action_label = {"liquidate": "청산", "reduce": "비중축소", "hold": "보유유지"}.get(
            exit_verdict.action, exit_verdict.action
        )
        out += f"**보유 판정**: {action_label}\n\n"
        out += f"- 세부사항: {exit_verdict.detail}\n"
        if exit_verdict.current_r is not None:
            out += f"- 현재 R: {exit_verdict.current_r:.2f}R\n"
        if exit_verdict.trailing_stop is not None:
            out += f"- 추적 손절가: {exit_verdict.trailing_stop:.2f}\n"
        out += "\n"

    return out


def format_deep_dive_output(result: dict) -> str:
    """Format deep dive result as markdown."""
    ticker = result["ticker"]
    technical = result["technical"]
    snapshot = technical.indicators or technical.snapshot
    decision_summary = result.get("decision_summary")
    factor_assessments = result.get("factor_assessments", [])
    scenarios = result.get("scenarios", [])
    chart_patterns = result.get("chart_patterns")
    presented_structure = result.get("presented_structure")
    structure_levels = result.get("structure_levels")
    execution_levels = result.get("execution_levels")
    playbook_verdict = result.get("playbook_verdict")

    output = f"# Deep Dive Analysis: {ticker}\n\n"
    output += f"## 가격: ${snapshot.price:.2f} ({snapshot.change_pct:+.2f}%)\n\n"
    macro_section = _format_macro_section(result.get("macro"))
    if macro_section:
        output += f"{macro_section}\n\n"

    if decision_summary:
        output += _format_top_summary(decision_summary)
    if factor_assessments:
        output += _format_factor_section(factor_assessments) + "\n"
    output += _format_pattern_section(chart_patterns)
    if scenarios:
        output += _format_scenario_section(scenarios) + "\n"
    if presented_structure:
        output += _format_presented_structure(presented_structure)
    elif structure_levels:
        output += "## 구조 레벨\n\n- presenter payload 누락\n\n"
    if execution_levels and not presented_structure:
        output += _format_execution_levels(execution_levels)

    if playbook_verdict is not None:
        output += _format_playbook_section(playbook_verdict)

    output += "\n"
    output += _format_raw_analysis_sections(result)
    return output


@app.command()
def analyze(
    query: str = typer.Argument(..., help="Stock ticker or company name (e.g., AAPL, Apple, 구글)"),
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
):
    """Deep dive analysis with LLM (technical + news + disclosure + flow)."""
    console.print(f"[bold]Resolving '{query}'...[/bold]")

    try:
        ticker = asyncio.run(resolve_ticker(query))
        console.print(f"[green]✓ Resolved to: {ticker}[/green]\n")
        console.print(f"[bold]Running deep dive analysis for {ticker}...[/bold]\n")

        result = asyncio.run(run_deep_dive(query, provider))
        output = format_deep_dive_output(result)
        console.print(Markdown(output))

        # Display chart path if available
        chart_result = result.get("chart")
        if chart_result and chart_result.success:
            console.print(f"\n[green]📊 차트 저장: {chart_result.path}[/green]")
            # Auto-open chart on macOS/Linux
            import platform
            import subprocess

            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["open", chart_result.path], check=False)
            elif system == "Linux":
                subprocess.run(["xdg-open", chart_result.path], check=False)
        elif chart_result and not chart_result.success:
            console.print(f"\n[yellow]⚠️  차트 생성 실패: {chart_result.error}[/yellow]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def brief(
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="LLM 문장화 없이 규칙 원문만 출력"),
):
    """일일 포트 액션 브리핑 — playbook.yaml 보유+워치 전 종목 평가."""
    console.print("[bold]Daily brief 생성 중...[/bold]")

    try:
        result = asyncio.run(run_brief(provider, use_llm=not no_llm))
        pipeline = result.pop("_pipeline")
        console.print(Markdown(pipeline.format_output(result)))
        report_path = pipeline.save_report(result)
        console.print(f"\n[green]리포트 저장: {report_path}[/green]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


async def run_brief(provider: str, use_llm: bool) -> dict:
    """brief 파이프라인 조립·실행. run_deep_dive와 동일한 도구 조립 패턴."""
    from src.providers.index_provider import IndexProvider
    from src.providers.kis_wrapper import KISProviderWrapper
    from src.tools.flow import FlowTool
    from src.tools.playbook.engine import PlaybookEngine
    from src.tools.playbook.holdings import load_holdings

    config = load_holdings()
    if not config.holdings and not config.watchlist:
        raise ValueError("playbook.yaml에 holdings/watchlist가 없습니다")

    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    kis_provider = (
        KISProvider(app_key=kis_key, app_secret=kis_secret) if kis_key and kis_secret else None
    )

    scorer = TechnicalScorer()
    us_tool = TechnicalAnalysisTool(provider=YFinanceProvider(), scorer=scorer)
    kr_tool = (
        TechnicalAnalysisTool(provider=KISProviderWrapper(kis_provider), scorer=scorer)
        if kis_provider
        else us_tool
    )

    fmp_provider = None
    fmp_api_key = os.getenv("FMP_API_KEY")
    if fmp_api_key:
        with contextlib.suppress(Exception):
            from src.providers.fmp_provider import FmpProvider

            fmp_provider = FmpProvider(api_key=fmp_api_key)

    engine = PlaybookEngine(
        index_provider=IndexProvider(),
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
        usd_capital=config.usd_capital,
        usd_risk_pct=config.usd_risk_pct or 0.01,
        krw_capital=config.krw_capital,
        krw_risk_pct=config.krw_risk_pct or 0.01,
    )

    opendart_key = os.getenv("OPENDART_API_KEY")
    dart_fetcher = DARTDisclosureFetcher(api_key=opendart_key) if opendart_key else None

    llm = None
    if use_llm:
        try:
            llm = LLMProvider.create(provider=provider, temperature=0)
        except Exception as e:
            console.print(f"[yellow]LLM 초기화 실패 — 규칙 원문으로 진행: {e}[/yellow]")

    pipeline = BriefPipeline(
        technical_tools={"KR": kr_tool, "US": us_tool},
        playbook_engine=engine,
        macro_tool=MacroTool(),
        news_tool=NewsTool(),
        disclosure_tool=DisclosureTool(
            sec_fetcher=SECDisclosureFetcher(),
            dart_fetcher=dart_fetcher,
        ),
        flow_tool=FlowTool(kis_provider=kis_provider),
        llm=llm,
    )
    result = await pipeline.run(config)
    result["_pipeline"] = pipeline
    return result


async def run_screen(market: str) -> dict:
    """Run screener pipeline."""
    naver_provider = NaverProvider()
    kis_provider = None

    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    if kis_key and kis_secret:
        kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret)

    yf_provider = YFinanceProvider()
    news_tool = NewsTool()

    universe_builder = UniverseBuilder(
        naver_provider=naver_provider,
        kis_provider=kis_provider,
        yf_provider=yf_provider,
    )
    evidence_collector = EvidenceCollector(
        kis_provider=kis_provider,
        yf_provider=yf_provider,
    )
    pipeline = ScreenerPipeline(
        universe_builder=universe_builder,
        evidence_collector=evidence_collector,
        news_tool=news_tool,
    )

    return await pipeline.run(market)


@app.command()
def screen(
    market: str = typer.Option("all", "--market", "-m", help="kr, us, or all"),
    notion: bool = typer.Option(False, "--notion", help="Upload to Notion"),
):
    """Scan market for leading stocks and themes."""
    console.print(f"[bold]Scanning {market} market...[/bold]\n")

    try:
        result = asyncio.run(run_screen(market))

        # Format and display
        pipeline = ScreenerPipeline(
            universe_builder=None,
            evidence_collector=None,
            news_tool=None,
        )
        output = pipeline.format_output(result)
        console.print(Markdown(output))

        # Save report
        report_path = pipeline.save_report(result)
        console.print(f"\n[green]Report saved to {report_path}[/green]")

        # Notion upload (optional)
        if notion:
            try:
                from src.integrations.notion import update_screener_report

                date = result["timestamp"].strftime("%Y-%m-%d")
                page_url = update_screener_report(result, date)
                console.print(f"[green]✓ Notion uploaded: {page_url}[/green]")
            except Exception as e:
                console.print(f"[red]✗ Notion upload failed: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


cache_app = typer.Typer(help="Manage user ticker cache")
app.add_typer(cache_app, name="cache")


@cache_app.command("list")
def cache_list():
    """List all cached ticker mappings."""
    from src.providers.ticker_cache import UserMappingCache

    cache = UserMappingCache()
    mappings = cache.list_mappings()

    if not mappings:
        console.print("[yellow]No cached mappings found.[/yellow]")
        return

    console.print("[bold]Cached Ticker Mappings[/bold]\n")
    for mapping in mappings:
        console.print(
            f"[green]{mapping['query']}[/green] → [cyan]{mapping['ticker']}[/cyan] "
            f"({mapping['display_name']}) - used {mapping['use_count']} times"
        )


@cache_app.command("clear")
def cache_clear(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Clear all cached ticker mappings."""
    from src.providers.ticker_cache import UserMappingCache

    if not confirm:
        response = typer.confirm("Are you sure you want to clear all cached mappings?")
        if not response:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    cache = UserMappingCache()
    cache.clear()
    console.print("[green]✓ Cache cleared successfully.[/green]")


# --- Report 서브커맨드 ---
app.add_typer(report_app, name="report")


@report_app.command("upload")
def report_upload(
    start_date: str = typer.Argument(None, help="시작 날짜 (YYYY-MM-DD). 미지정 시 전체"),
    end_date: str = typer.Argument(None, help="종료 날짜 (YYYY-MM-DD). 미지정 시 시작 날짜만"),
    report_type: str = typer.Option("all", "--type", "-t", help="all, daily, screener"),
):
    """Upload existing reports to Notion."""
    from pathlib import Path

    from src.integrations.notion import upload_report_from_file

    # reports/ 디렉토리 스캔
    reports_dir = Path("reports")
    if not reports_dir.exists():
        console.print("[red]reports/ 디렉토리가 없습니다.[/red]")
        raise typer.Exit(1)

    # MD 파일 찾기
    pattern_map = {
        "daily": "daily_*.md",
        "screener": "screen-*.md",
        "all": "*.md",
    }
    pattern = pattern_map.get(report_type, "*.md")
    md_files = list(reports_dir.rglob(pattern))

    if not md_files:
        console.print(f"[yellow]업로드할 리포트가 없습니다. (패턴: {pattern})[/yellow]")
        return

    # 날짜 필터링
    filtered_files = []
    for file_path in md_files:
        # 파일명에서 날짜 추출
        filename = file_path.stem
        if filename.startswith("daily_"):
            date_str = filename.replace("daily_", "")
        elif filename.startswith("screen-"):
            date_str = filename.replace("screen-", "")
        else:
            continue

        # 날짜 범위 체크
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue

        filtered_files.append((file_path, date_str))

    if not filtered_files:
        console.print("[yellow]날짜 범위에 해당하는 리포트가 없습니다.[/yellow]")
        return

    # 업로드
    console.print(f"[bold]{len(filtered_files)}개 리포트를 Notion에 업로드합니다...[/bold]\n")
    success_count = 0
    fail_count = 0

    for file_path, date_str in filtered_files:
        try:
            page_url = upload_report_from_file(file_path, date_str)
            console.print(f"[green]✓ {file_path.name} → {page_url}[/green]")
            success_count += 1
        except Exception as e:
            console.print(f"[red]✗ {file_path.name} 실패: {e}[/red]")
            fail_count += 1

    # 결과 요약
    console.print(f"\n[bold]완료: 성공 {success_count}, 실패 {fail_count}[/bold]")


@report_app.command("daily")
def report_daily(
    date: str = typer.Argument(
        None,
        help="분석할 날짜 (YYYY-MM-DD). 미지정 시 전날.",
    ),
    data_dir: str = typer.Option("data", "--data-dir", "-d", help="데이터 디렉토리"),
    notion: bool = typer.Option(False, "--notion", help="Notion에 업데이트"),
):
    """텔레그램 메시지 기반 일일 시장 리포트 생성."""
    from datetime import datetime as dt
    from datetime import timedelta
    from pathlib import Path

    from src.pipelines.daily_report.pipeline import format_report, run_pipeline

    if date is None:
        date = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    console.print(f"[bold]Daily Report 생성 중... (날짜: {date})[/bold]\n")

    try:
        # 파이프라인 실행
        report = run_pipeline(date, data_dir)
        output = format_report(report)

        # 터미널 출력
        console.print(Markdown(output))

        # MD 파일 저장 (필수)
        year_month = date[:7]  # YYYY-MM
        report_dir = Path(f"reports/{year_month}")
        report_dir.mkdir(parents=True, exist_ok=True)

        output_file = report_dir / f"daily_{date}.md"
        output_file.write_text(output, encoding="utf-8")
        console.print(f"\n[green]✓ 리포트 저장: {output_file}[/green]")

        # Notion 업데이트 (옵션)
        if notion:
            try:
                from src.integrations.notion import update_daily_report

                page_url = update_daily_report(report, date, data_dir)
                console.print(f"[green]✓ Notion 업데이트 완료: {page_url}[/green]")
            except ImportError:
                console.print(
                    "[yellow]⚠ Notion 연동 모듈이 없습니다. 구현 필요: src/integrations/notion.py[/yellow]"
                )
            except Exception as e:
                console.print(f"[red]✗ Notion 업데이트 실패: {e}[/red]")

    except FileNotFoundError as e:
        console.print(f"[red]오류: {e}[/red]")
        console.print(f"[yellow]힌트: 먼저 'uv run jarvis telegram fetch {date}' 실행[/yellow]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1) from None


@report_app.command("daily-v2")
def report_daily_v2(
    date: str = typer.Argument(
        None,
        help="분석할 날짜 (YYYY-MM-DD). 미지정 시 전날.",
    ),
    data_dir: str = typer.Option("data", "--data-dir", "-d", help="데이터 디렉토리"),
    provider: str = typer.Option("openai", "--provider", "-p", help="LLM provider"),
    config_path: str = typer.Option(
        "config.yaml", "--config-path", help="stock report 설정 파일 경로"
    ),
    taxonomy_path: str = typer.Option(
        "config/stock_report_vocabulary.yaml",
        "--taxonomy-path",
        help="taxonomy vocabulary 파일 경로",
    ),
    preview_limit: int = typer.Option(
        12, "--preview-limit", help="canonical_summary 미리보기 개수"
    ),
    google_grounding: bool = typer.Option(
        False,
        "--google-grounding/--no-google-grounding",
        help="Gemini Google Search Grounding 실험 경로를 함께 실행한다 (T09-B). GOOGLE_API_KEY 필요.",
    ),
):
    """Stock Report Engine V2 (Phase 1) 실행."""
    from datetime import datetime as dt
    from datetime import timedelta

    from src.pipelines.stock_report.pipeline import format_daily_v2_report, run_daily_v2

    if date is None:
        date = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    console.print(f"[bold]Daily Report V2 생성 중... (날짜: {date})[/bold]\n")
    if google_grounding:
        console.print("[dim]Google Search Grounding 실험 경로 활성화됨[/dim]\n")

    try:
        result = run_daily_v2(
            date=date,
            data_dir=data_dir,
            provider=provider,
            config_path=config_path,
            taxonomy_path=taxonomy_path,
            preview_limit=preview_limit,
            google_grounding=google_grounding,
        )
        output = format_daily_v2_report(result)
        console.print(Markdown(output))

        year_month = date[:7]
        report_dir = Path(f"reports/{year_month}")
        report_dir.mkdir(parents=True, exist_ok=True)
        output_file = report_dir / f"daily_v2_{date}.md"
        output_file.write_text(output, encoding="utf-8")
        console.print(f"\n[green]✓ 리포트 저장: {output_file}[/green]")

        if result.google_grounding_markdown:
            google_file = report_dir / f"daily_v2_{date}.google.md"
            google_file.write_text(result.google_grounding_markdown, encoding="utf-8")
            console.print(f"[green]✓ Google Grounding 리포트 저장: {google_file}[/green]")
        elif google_grounding:
            console.print("[yellow]⚠ Google Grounding 실행 실패 — 로그를 확인하세요[/yellow]")
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1) from None


@report_app.command("daily-v2-google")
def report_daily_v2_google(
    date: str = typer.Argument(
        None,
        help="분석할 날짜 (YYYY-MM-DD). 미지정 시 전날.",
    ),
):
    """DB에 저장된 데이터로 Google Search Grounding 리포트만 생성한다 (T09-B 단독 실행). GOOGLE_API_KEY 필요."""
    from datetime import datetime as dt
    from datetime import timedelta

    from src.pipelines.stock_report.pipeline import run_google_grounding_only

    if date is None:
        date = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    console.print(f"[bold]Google Grounding 리포트 생성 중... (날짜: {date})[/bold]\n")
    console.print("[dim]DB 저장 데이터 기반 — ingest/classify 단계 생략[/dim]\n")

    try:
        result = run_google_grounding_only(date=date)

        console.print(Markdown(result.google_grounding_markdown))
        console.print(
            f"\n[dim]chunks: {result.chunk_count} | "
            f"categories: {result.category_bucket_count} | "
            f"themes: {result.theme_bucket_count} | "
            f"tickers: {result.focus_ticker_count} | "
            f"model: {result.model}[/dim]"
        )

        year_month = date[:7]
        report_dir = Path(f"reports/{year_month}")
        report_dir.mkdir(parents=True, exist_ok=True)
        google_file = report_dir / f"daily_v2_{date}.google.md"
        google_file.write_text(result.google_grounding_markdown, encoding="utf-8")
        console.print(f"[green]✓ Google Grounding 리포트 저장: {google_file}[/green]")
    except ValueError as e:
        console.print(f"[yellow]{e}[/yellow]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1) from None


@report_app.command("ingest-pdf")
def report_ingest_pdf(
    date: str = typer.Argument(None, help="적재할 날짜 (YYYY-MM-DD). 미지정 시 전날."),
    input_dir: str = typer.Option(
        None, "--input-dir", "-i", help="PDF 디렉토리. 기본 data/files/{date}"
    ),
    use_hybrid: bool = typer.Option(
        False, "--use-hybrid", help="docling hybrid 파싱(느림, 서버 필요)"
    ),
    ocr_lang: str = typer.Option(None, "--ocr-lang", help="OCR 언어(hybrid 백엔드 필요)"),
    embed_missing: bool = typer.Option(
        False, "--embed-missing", help="패스2만: pending/failed 임베딩 재시도"
    ),
    reembed: bool = typer.Option(False, "--reembed", help="재파스+재청킹+재임베딩(전체 재적재)"),
    provider: str = typer.Option(
        "openai", "--provider", help="분류 LLM provider (openai/anthropic)"
    ),
):
    """증권사 PDF를 documents/document_chunks에 적재하고 임베딩한다 (Phase 2)."""
    from datetime import datetime as dt
    from datetime import timedelta

    from src.pipelines.stock_report.pdf_ingest import run_ingest_pdf

    if date is None:
        date = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    console.print(f"[bold]PDF 인제스트 중... (날짜: {date})[/bold]\n")
    try:
        summary = run_ingest_pdf(
            date=date,
            input_dir=input_dir,
            provider=provider,
            use_hybrid=use_hybrid,
            ocr_lang=ocr_lang,
            embed_missing=embed_missing,
            reembed=reembed,
        )
        console.print(
            f"[green]✓ 완료[/green] PDF {summary.total_pdfs}개 → "
            f"문서 {summary.documents_upserted} / 청크 {summary.chunks_inserted} / "
            f"임베딩 {summary.embedded} / skip {summary.skipped} / "
            f"중복 {summary.duplicates} / low_conf {summary.low_confidence} / 실패 {summary.failed}"
        )
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1) from None


# --- Telegram 서브커맨드 ---

telegram_app = typer.Typer(help="Telegram 채널 메시지 수집")
app.add_typer(telegram_app, name="telegram")


async def run_telegram_fetch(date_str: str, config_path: str) -> dict:
    """지정 날짜의 텔레그램 메시지를 수집한다."""
    from src.pipelines.telegram_pipeline import TelegramPipeline

    try:
        pipeline = await TelegramPipeline.create(Path(config_path))
        try:
            total = await pipeline.fetch(date_str)
            return {"success": True, "total": total, "date": date_str}
        finally:
            await pipeline.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


async def run_telegram_catchup(config_path: str) -> dict:
    """마지막 수집 이후 누락분을 보충한다."""
    from src.pipelines.telegram_pipeline import TelegramPipeline

    try:
        pipeline = await TelegramPipeline.create(Path(config_path))
        try:
            total = await pipeline.catch_up()
            return {"success": True, "total": total}
        finally:
            await pipeline.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@telegram_app.command("fetch")
def telegram_fetch(
    date: str = typer.Argument(
        None,
        help="수집할 날짜 (YYYY-MM-DD). 미지정 시 전날.",
    ),
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="config.yaml 경로"),
):
    """특정 날짜의 텔레그램 메시지를 일괄 수집한다."""
    from datetime import datetime as dt
    from datetime import timedelta

    if date is None:
        date = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    console.print(f"[bold]Telegram 메시지 수집 중... (날짜: {date})[/bold]\n")

    try:
        result = asyncio.run(run_telegram_fetch(date, config_path))
        if result["success"]:
            console.print(f"[green]완료: {result['total']}건 수집됨 ({result['date']})[/green]")
        else:
            console.print(f"[red]오류: {result['error']}[/red]")
            raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1) from None


@telegram_app.command("catch-up")
def telegram_catchup(
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="config.yaml 경로"),
):
    """마지막 수집 이후 누락분을 보충 수집한다."""
    console.print("[bold]Telegram catch-up 수집 중...[/bold]\n")

    try:
        result = asyncio.run(run_telegram_catchup(config_path))
        if result["success"]:
            console.print(f"[green]완료: {result['total']}건 보충 수집됨[/green]")
        else:
            console.print(f"[red]오류: {result['error']}[/red]")
            raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
