import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Literal
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from dotenv import load_dotenv

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


def _format_metric_value(metric_name: str, value: float) -> str:
    """지표 타입에 따라 값 포맷팅

    Args:
        metric_name: 지표명
        value: 지표 값

    Returns:
        포맷팅된 문자열
    """
    # 퍼센트 지표
    if metric_name in ["revenue_growth", "earnings_growth", "gross_margin",
                       "operating_margin", "profit_margin", "fcf_yield",
                       "dividend_yield", "roe", "roa", "payout_ratio"]:
        return f"{value*100:.1f}%"

    # 달러 금액 (10억 단위)
    elif metric_name in ["free_cash_flow", "operating_cash_flow", "market_cap"]:
        return f"${value/1e9:.1f}B"

    # 일반 숫자
    else:
        # Format with appropriate precision: 2 decimals if value < 10, else 1
        formatted = f"{value:.2f}" if abs(value) < 10 else f"{value:.1f}"
        # Remove trailing zeros after decimal point
        return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted

from src.core.config import load_config
from src.providers.yfinance_provider import YFinanceProvider
from src.providers.kis import KISProvider
from src.providers.ticker_resolver import TickerResolver
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.fundamental import FundamentalTool, QuarterlyData
from src.tools.macro import MacroTool
from src.tools.news import NewsTool
from src.tools.portfolio import PortfolioTool
from src.pipelines.quick_check import QuickCheckPipeline
from src.pipelines.deep_dive import DeepDivePipeline
from src.pipelines.daily_report import DailyReportPipeline
from src.pipelines.portfolio import PortfolioPipeline
from src.llm.provider import LLMProvider
from src.utils.sector_metrics import SectorMetrics
from src.providers.naver import NaverProvider
from src.tools.screener.universe import UniverseBuilder
from src.tools.screener.evidence import EvidenceCollector
from src.pipelines.screener import ScreenerPipeline

app = typer.Typer(help="Invest Jarvis - Financial Analysis CLI")
console = Console()


def version_callback(value: bool):
    if value:
        console.print("invest-jarvis version 0.3.0")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
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
        raise ValueError(f"Could not resolve ticker for '{query}': {e}")


async def run_quick_check(ticker_or_name: str) -> dict:
    """Run quick check pipeline."""
    # Resolve ticker if company name is provided
    ticker = await resolve_ticker(ticker_or_name)

    provider = YFinanceProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)
    pipeline = QuickCheckPipeline(technical_tool=tool)
    return await pipeline.run(ticker)


@app.command()
def check(
    query: str = typer.Argument(..., help="Stock ticker or company name (e.g., AAPL, Apple, 구글)"),
):
    """Quick check - technical analysis without LLM."""
    console.print(f"[bold]Resolving '{query}'...[/bold]")

    try:
        ticker = asyncio.run(resolve_ticker(query))
        console.print(f"[green]✓ Resolved to: {ticker}[/green]\n")
        console.print(f"[bold]Analyzing {ticker}...[/bold]\n")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    result = asyncio.run(run_quick_check(query))

    if not result.get("success", False):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        raise typer.Exit(1)

    pipeline = QuickCheckPipeline(technical_tool=None)  # Just for formatting
    output = pipeline.format_output(result)
    console.print(Markdown(output))


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

    yf_provider = YFinanceProvider()
    scorer = TechnicalScorer()
    technical_tool = TechnicalAnalysisTool(provider=yf_provider, scorer=scorer)
    fundamental_tool = FundamentalTool()
    news_tool = NewsTool()
    llm = LLMProvider.create(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    pipeline = DeepDivePipeline(
        technical_tool=technical_tool,
        news_tool=news_tool,
        llm=llm,
        fundamental_tool=fundamental_tool,
    )

    return await pipeline.run(ticker)


def _render_quarterly_table(quarterly_data: list[QuarterlyData]) -> str:
    """Render quarterly data as Rich Table"""
    if not quarterly_data or len(quarterly_data) == 0:
        return ""

    table = Table(title="분기별 추이 (최근 4분기)", show_header=True, header_style="bold cyan")

    # Add columns
    table.add_column("Metric", style="white", no_wrap=True)
    for q in quarterly_data:
        table.add_column(q.period, justify="right")

    # Revenue row
    revenue_values = []
    for q in quarterly_data:
        if q.revenue is not None:
            revenue_values.append(f"${q.revenue/1e9:.2f}B")
        else:
            revenue_values.append("N/A")
    table.add_row("Revenue", *revenue_values)

    # Revenue YoY row
    yoy_values = []
    for q in quarterly_data:
        if q.revenue_yoy is not None:
            color = "green" if q.revenue_yoy >= 0 else "red"
            yoy_values.append(f"[{color}]{q.revenue_yoy*100:+.2f}%[/{color}]")
        else:
            yoy_values.append("N/A")
    table.add_row("YoY Growth %", *yoy_values)

    # Revenue QoQ row
    qoq_values = []
    for q in quarterly_data:
        if q.revenue_qoq is not None:
            color = "green" if q.revenue_qoq >= 0 else "red"
            qoq_values.append(f"[{color}]{q.revenue_qoq*100:+.2f}%[/{color}]")
        else:
            qoq_values.append("N/A")
    table.add_row("QoQ Growth %", *qoq_values)

    # Earnings row
    earnings_values = []
    for q in quarterly_data:
        if q.earnings is not None:
            earnings_values.append(f"${q.earnings/1e9:.2f}B")
        else:
            earnings_values.append("N/A")
    table.add_row("Earnings", *earnings_values)

    # Earnings YoY row
    yoy_e_values = []
    for q in quarterly_data:
        if q.earnings_yoy is not None:
            color = "green" if q.earnings_yoy >= 0 else "red"
            yoy_e_values.append(f"[{color}]{q.earnings_yoy*100:+.2f}%[/{color}]")
        else:
            yoy_e_values.append("N/A")
    table.add_row("YoY Growth %", *yoy_e_values)

    # Earnings QoQ row
    qoq_e_values = []
    for q in quarterly_data:
        if q.earnings_qoq is not None:
            color = "green" if q.earnings_qoq >= 0 else "red"
            qoq_e_values.append(f"[{color}]{q.earnings_qoq*100:+.2f}%[/{color}]")
        else:
            qoq_e_values.append("N/A")
    table.add_row("QoQ Growth %", *qoq_e_values)

    from io import StringIO
    from rich.console import Console
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True)
    console.print(table)
    return buffer.getvalue()


def _format_growth_rate(value: float | None) -> str:
    """Format growth rate with +/- sign"""
    if value is None:
        return "N/A"
    return f"{value*100:+.2f}%"


def format_deep_dive_output(result: dict) -> str:
    """Format deep dive result as markdown."""
    ticker = result["ticker"]
    technical = result["technical"]
    tech_summary = result["technical_summary"]
    news_analysis = result.get("news_analysis")
    fundamental = result.get("fundamental")
    fundamental_summary = result.get("fundamental_summary")

    output = f"# Deep Dive Analysis: {ticker}\n\n"

    # Support both old (indicators) and new (snapshot) field
    snapshot = technical.indicators or technical.snapshot
    output += f"## 가격: ${snapshot.price:.2f} ({snapshot.change_pct:+.2f}%)\n\n"

    # Raw technical indicators
    output += "### 기술적 지표\n\n"

    # Moving averages
    if snapshot.sma_20 is not None:
        output += f"- **20일 이동평균선**: ${snapshot.sma_20:.2f}\n"
    if snapshot.sma_50 is not None:
        output += f"- **50일 이동평균선**: ${snapshot.sma_50:.2f}\n"
    if snapshot.sma_150 is not None:
        output += f"- **150일 이동평균선**: ${snapshot.sma_150:.2f}\n"
    if snapshot.sma_200 is not None:
        output += f"- **200일 이동평균선**: ${snapshot.sma_200:.2f}\n"

    output += "\n"

    # Momentum indicators
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

    # Trend strength
    if snapshot.adx is not None:
        output += f"- **ADX (추세 강도)**: {snapshot.adx:.1f}\n"

    # Supertrend
    if snapshot.supertrend_direction is not None:
        direction = "상승" if snapshot.supertrend_direction == 1 else "하락"
        output += f"- **Supertrend**: {direction}"

        # Get supertrend value and calculate distance from current price
        if technical.components and "supertrend" in technical.components:
            supertrend_metrics = technical.components["supertrend"]["metrics"]
            if "supertrend_value" in supertrend_metrics:
                st_value = supertrend_metrics["supertrend_value"]
                output += f" (라인: ${st_value:.2f})"

                # Calculate distance
                distance = ((snapshot.price - st_value) / st_value) * 100
                if abs(distance) > 0.1:
                    output += f", 현재가 대비 {distance:+.2f}%"

        output += "\n"

    output += "\n"

    # Support/Resistance
    if snapshot.pivot is not None:
        output += f"- **피봇 포인트**: ${snapshot.pivot:.2f}\n"
    if snapshot.support_s1 is not None:
        output += f"- **지지선 S1**: ${snapshot.support_s1:.2f}\n"
    if snapshot.resistance_r1 is not None:
        output += f"- **저항선 R1**: ${snapshot.resistance_r1:.2f}\n"

    # 52-week high/low
    if snapshot.high_52w is not None:
        output += f"- **52주 최고가**: ${snapshot.high_52w:.2f}\n"
    if snapshot.low_52w is not None:
        output += f"- **52주 최저가**: ${snapshot.low_52w:.2f}\n"

    output += "\n"

    output += "### 종합 분석\n\n"
    output += f"**총점**: {technical.total_score}\n\n"
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

        # Sector/Industry 정보는 그대로 유지
        if fundamental.sector or fundamental.industry:
            output += f"**Sector/Industry**: {fundamental.sector or 'N/A'} / {fundamental.industry or 'N/A'}\n\n"

        # 섹터별 우선순위 지표 가져오기
        priority_metrics = SectorMetrics.get_priority_metrics(fundamental.sector)

        # 우선순위 지표를 ⭐와 함께 먼저 렌더링
        for metric_name in priority_metrics:
            value = getattr(fundamental, metric_name, None)
            if value is not None:
                display_name = _get_metric_display_name(metric_name)
                formatted = _format_metric_value(metric_name, value)
                output += f"⭐ **{display_name}**: {formatted}\n\n"

        output += "\n"

        # 나머지 지표 렌더링
        all_metric_names = [
            "market_cap", "pe_ratio", "forward_pe", "peg_ratio", "pb_ratio",
            "ps_ratio", "ev_ebitda", "roe", "roa", "gross_margin",
            "operating_margin", "profit_margin", "revenue_growth",
            "earnings_growth", "debt_to_equity", "current_ratio",
            "quick_ratio", "free_cash_flow", "operating_cash_flow",
            "fcf_yield", "dividend_yield", "payout_ratio"
        ]

        remaining_metrics = [m for m in all_metric_names if m not in priority_metrics]

        for metric_name in remaining_metrics:
            value = getattr(fundamental, metric_name, None)
            if value is not None:
                display_name = _get_metric_display_name(metric_name)
                formatted = _format_metric_value(metric_name, value)
                output += f"- **{display_name}**: {formatted}\n"

        output += "\n"

        # Quarterly Performance section
        if fundamental.quarterly_data is not None and len(fundamental.quarterly_data) > 0:
            output += "### 분기별 실적\n\n"

            # Revenue trends
            output += "**매출 추이:**\n\n"
            for q in fundamental.quarterly_data:
                if q.revenue is not None:
                    revenue_str = f"${q.revenue/1e9:.2f}B"
                    yoy_str = _format_growth_rate(q.revenue_yoy)
                    qoq_str = _format_growth_rate(q.revenue_qoq)
                    output += f"- {q.period}: {revenue_str} (YoY {yoy_str}, QoQ {qoq_str})\n"

            output += "\n"

            # Earnings trends
            output += "**이익 추이:**\n\n"
            for q in fundamental.quarterly_data:
                if q.earnings is not None:
                    earnings_str = f"${q.earnings/1e9:.2f}B"
                    yoy_str = _format_growth_rate(q.earnings_yoy)
                    qoq_str = _format_growth_rate(q.earnings_qoq)
                    output += f"- {q.period}: {earnings_str} (YoY {yoy_str}, QoQ {qoq_str})\n"

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

    return output


@app.command()
def analyze(
    query: str = typer.Argument(..., help="Stock ticker or company name (e.g., AAPL, Apple, 구글)"),
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
):
    """Deep dive analysis with LLM (technical + news)."""
    console.print(f"[bold]Resolving '{query}'...[/bold]")

    try:
        ticker = asyncio.run(resolve_ticker(query))
        console.print(f"[green]✓ Resolved to: {ticker}[/green]\n")
        console.print(f"[bold]Running deep dive analysis for {ticker}...[/bold]\n")

        result = asyncio.run(run_deep_dive(query, provider))
        output = format_deep_dive_output(result)
        console.print(Markdown(output))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def create_daily_report_pipeline(provider: str):
    """일일 리포트 파이프라인의 의존성을 조립하여 반환한다.

    테스트 및 스크립트에서 재사용 가능하도록 팩토리 패턴으로 분리.
    """
    import logging
    from src.pipelines.daily_report_v2 import DailyReportV2Pipeline
    from src.pipelines.report_stages.ingest import IngestStage
    from src.pipelines.report_stages.map_issues import MapStage
    from src.pipelines.report_stages.shuffle_filter import ShuffleStage
    from src.pipelines.report_stages.catalyst import CatalystStage
    from src.pipelines.report_stages.synthesize import SynthesizeStage
    from src.pipelines.report_stages.theme_config import ThemeConfig
    from src.tools.telegram_loader import TelegramMessageLoader

    logger = logging.getLogger(__name__)

    api_key_env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"Missing {api_key_env} environment variable")

    map_llm = LLMProvider.create(provider="openai", model="gpt-4o")
    catalyst_llm = LLMProvider.create(provider="openai", model="gpt-4o")
    synthesize_llm = LLMProvider.create(provider=provider)

    macro_tool = MacroTool()
    news_tool = NewsTool()
    ticker_resolver = TickerResolver()
    theme_config = ThemeConfig(Path("themes.yaml"))

    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    if not (kis_key and kis_secret):
        logger.warning(
            "KIS credentials 설정되지 않았습니다. "
            "한국주식 수급 데이터 및 모멘텀 랭킹이 제외됩니다."
        )
        kis_provider = None
    else:
        kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret)

    telegram_loader = TelegramMessageLoader(data_dir=Path("data"))
    logger.info("Telegram 메시지 로더 초기화 완료 (data/ 디렉토리)")

    ingest_stage = IngestStage(
        macro_tool=macro_tool,
        news_tool=news_tool,
        kis_provider=kis_provider,
        telegram_loader=telegram_loader,
    )
    map_stage = MapStage(
        llm=map_llm,
        known_themes=theme_config.as_prompt_string(),
    )
    shuffle_stage = ShuffleStage(
        ticker_resolver=ticker_resolver,
        merge_llm=map_llm,
        known_themes=theme_config.load(),
    )
    catalyst_stage = CatalystStage(
        llm=catalyst_llm,
        news_tool=news_tool,
        ticker_resolver=ticker_resolver,
    )
    synthesize_stage = SynthesizeStage(llm=synthesize_llm)

    return DailyReportV2Pipeline(
        ingest_stage=ingest_stage,
        map_stage=map_stage,
        shuffle_stage=shuffle_stage,
        catalyst_stage=catalyst_stage,
        synthesize_stage=synthesize_stage,
    )


async def run_daily_report_v2(
    provider: str = "openai",
    stage: str | None = None,
    from_stage: str | None = None,
    no_save: bool = False,
) -> dict:
    """V2 일일 리포트 파이프라인을 실행한다."""
    from datetime import datetime

    date_str = datetime.now().strftime("%Y-%m-%d")
    cache_dir = Path(".cache/report") / date_str
    cache_dir.mkdir(parents=True, exist_ok=True)

    pipeline = create_daily_report_pipeline(provider)
    report = await pipeline.run(stage=stage, from_stage=from_stage)

    result = {"report": report, "no_save": no_save}

    if report and not no_save and not stage:
        month_str = datetime.now().strftime("%Y-%m")
        report_dir = Path("reports") / month_str
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{date_str}.md"
        md_content = format_daily_report_v2(report)
        report_path.write_text(md_content, encoding="utf-8")
        result["saved_to"] = str(report_path)

    return result


def format_daily_report_v2(report) -> str:
    """DailyReport를 텔레그램 스타일로 디테일이 살아있는 마크다운 문자열로 렌더링한다."""
    from src.llm.daily_report_models import DailyReport

    if not isinstance(report, DailyReport):
        return "리포트 생성에 실패했습니다."

    lines = [
        f"# Daily Market Report — {report.date}",
        "",
        "## 1. 시장 온도 (Market Pulse)",
        "",
        report.market_pulse,
        "",
    ]
    
    lines.extend([
        "## 2. 시장 내러티브 & 주목 테마",
        ""
    ])
    
    if not report.themes:
        lines.append("- 특별히 감지된 테마가 없습니다.\n")
    else:
        for theme in report.themes:
            lines.append(f"### {theme.name} ({theme.sentiment.upper()})")
            lines.append(f"- **Summary**: {theme.narrative}")
            lines.append(f"- **Stocks**: {', '.join(theme.stocks)}")
            
            # 원문(Evidence) 출력
            if theme.source_ids and report.ref_lookup:
                lines.append("")
                lines.append("**[근거/원문]**")
                for src_id in theme.source_ids:
                    text = report.ref_lookup.get(src_id)
                    if text:
                        compact_text = " ".join(text.split())
                        lines.append(f"- [{src_id}] {compact_text}")
            lines.append("")

    lines.extend([
        "## 3. 주도주 및 촉매 분석",
        ""
    ])
    
    if not report.catalysts:
        lines.append("- 분석된 주도주 촉매가 없습니다.\n")
    else:
        for cat in report.catalysts:
            lines.append(f"### {cat.ticker}")
            if cat.themes:
                lines.append(f"- **관련 테마**: {', '.join(cat.themes)}")
            
            detail = report.stock_details.get(cat.ticker)
            if detail:
                flow = detail.flow_score if detail.flow_score is not None else "N/A"
                mom = detail.volume_score if detail.volume_score is not None else "N/A"
                lines.append(f"- **수급/모멘텀**: 기관/외인 순매수(금액) {flow}, 모멘텀 점수 {mom}")
                
            lines.append(f"- **촉매분석**: {cat.catalyst_summary}")
            
            if cat.news:
                lines.append("")
                lines.append("**[최신 뉴스]**")
                for n in cat.news:
                    lines.append(n if n.startswith("-") else f"- {n}")
            lines.append("")
            
    lines.extend([
        "## 4. 주요 인사이트 (Featured Analysis)",
        "",
        report.featured_analysis
    ])

    return "\n".join(lines)


async def run_daily_report(tickers: list[str], provider: str) -> dict:
    """Run daily report pipeline."""
    api_key_env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    base_url_env = "OPENAI_BASE_URL" if provider == "openai" else "ANTHROPIC_BASE_URL"
    api_key = os.getenv(api_key_env)
    base_url = os.getenv(base_url_env)
    if not api_key:
        raise ValueError(f"Missing {api_key_env} environment variable")

    yf_provider = YFinanceProvider()
    scorer = TechnicalScorer()
    technical_tool = TechnicalAnalysisTool(provider=yf_provider, scorer=scorer)
    macro_tool = MacroTool()
    llm = LLMProvider.create(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    pipeline = DailyReportPipeline(
        macro_tool=macro_tool,
        technical_tool=technical_tool,
        llm=llm,
    )

    return await pipeline.run(tickers)


def format_daily_report_output(result: dict) -> str:
    """Format daily report result as markdown."""
    date = result["date"].strftime("%Y-%m-%d %H:%M")
    macro = result["macro"]
    tickers = result["tickers"]

    output = f"# Daily Market Report\n\n"
    output += f"**Date**: {date}\n\n"

    output += "## Macro Snapshot\n\n"
    output += f"- **VIX**: {macro.vix:.2f} ({macro.vix_change:+.2f})\n"
    output += f"- **Fear & Greed**: {macro.fear_greed} ({macro.fear_greed_label})\n"
    output += f"- **WTI Oil**: ${macro.wti:.2f} ({macro.wti_change:+.2f})\n"
    output += f"- **US 10Y Yield**: {macro.us_10y:.2f}%\n"
    output += f"- **US 2Y Yield**: {macro.us_2y:.2f}%\n"
    output += f"- **Yield Spread**: {macro.yield_spread:.2f}%\n"
    output += f"- **DXY**: {macro.dxy:.2f} ({macro.dxy_change:+.2f})\n\n"

    output += "## Ticker Analysis\n\n"

    for ticker_data in tickers:
        ticker = ticker_data["ticker"]
        technical = ticker_data.get("technical")
        error = ticker_data.get("error")

        output += f"### {ticker}\n\n"

        if error:
            output += f"**Error**: {error}\n\n"
            continue

        if technical:
            # Support both old (indicators) and new (snapshot) field
            snapshot = technical.indicators or technical.snapshot
            price = snapshot.price
            change_pct = snapshot.change_pct

            output += f"**Price**: ${price:.2f} ({change_pct:+.2f}%)\n"
            output += f"**Total Score**: {technical.total_score}\n"

            # Collect signals from components (new format) or key_insights (old format)
            if technical.components:
                all_signals = []
                for comp in technical.components.values():
                    all_signals.extend(comp.get("signals", []))
                if all_signals:
                    output += f"**Signals**: {', '.join(all_signals[:5])}\n"  # Limit to 5
            elif technical.key_insights:
                output += f"**Signals**: {', '.join(technical.key_insights)}\n"

            if technical.warnings:
                output += f"**Warnings**: {', '.join(technical.warnings)}\n"

            output += "\n"

    return output


@app.command()
def report(
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
    stage: str = typer.Option(None, "--stage", help="단일 스테이지 실행 (ingest|map|shuffle|catalyst|synthesize)"),
    from_stage: str = typer.Option(None, "--from", help="해당 스테이지부터 끝까지 실행"),
    no_save: bool = typer.Option(False, "--no-save", help="리포트 파일 저장 생략"),
):
    """일일 시장 리포트 (V2: 테마 중심 내러티브)"""
    console.print("\n[bold]Daily Market Report V2[/bold]\n")

    result = asyncio.run(run_daily_report_v2(
        provider=provider,
        stage=stage,
        from_stage=from_stage,
        no_save=no_save,
    ))

    report_obj = result.get("report")
    if report_obj:
        md = format_daily_report_v2(report_obj)
        console.print(Markdown(md))
        if "saved_to" in result:
            console.print(f"\n[dim]저장 위치: {result['saved_to']}[/dim]")
    elif stage:
        console.print(f"[green]스테이지 '{stage}' 완료. .cache/report/ 에서 결과를 확인하세요.[/green]")
    else:
        console.print("[red]리포트 생성에 실패했습니다.[/red]")


async def run_portfolio_monitoring() -> dict:
    """Run portfolio monitoring."""
    kis_provider = KISProvider(
        app_key=os.getenv("KIS_APP_KEY"),
        app_secret=os.getenv("KIS_APP_SECRET"),
    )
    yf_provider = YFinanceProvider()

    portfolio_tool = PortfolioTool(provider=kis_provider)
    scorer = TechnicalScorer()
    technical_tool = TechnicalAnalysisTool(provider=yf_provider, scorer=scorer)
    news_tool = NewsTool()

    pipeline = PortfolioPipeline(
        portfolio_tool=portfolio_tool,
        technical_tool=technical_tool,
        news_tool=news_tool,
    )

    return await pipeline.run()


@app.command()
def portfolio(
    provider: str = typer.Option("openai", help="LLM provider"),
):
    """Monitor portfolio with technical analysis and news."""
    kis_app_key = os.getenv("KIS_APP_KEY")
    kis_app_secret = os.getenv("KIS_APP_SECRET")
    if not kis_app_key or not kis_app_secret:
        console.print("[red]Error: KIS_APP_KEY and KIS_APP_SECRET required[/red]")
        raise typer.Exit(1)

    console.print("[bold]Loading portfolio...[/bold]\n")

    result = asyncio.run(run_portfolio_monitoring())

    if not result.get("success", False):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        raise typer.Exit(1)

    pipeline = PortfolioPipeline(None, None, None)
    output = pipeline.format_output(result)
    console.print(Markdown(output))


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

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


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
    confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    )
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
    from datetime import datetime as dt, timedelta

    if date is None:
        date = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    console.print(f"[bold]Telegram 메시지 수집 중... (날짜: {date})[/bold]\n")

    try:
        result = asyncio.run(run_telegram_fetch(date, config_path))
        if result["success"]:
            console.print(f"[green]완료: {result['total']}건 수집됨 ({result['date']})[/green]")
        else:
            console.print(f"[red]오류: {result['error']}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1)


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
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
