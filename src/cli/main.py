import asyncio
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

from src.core.config import load_config
from src.providers.yfinance_provider import YFinanceProvider
from src.providers.kis import KISProvider
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
):
    """Invest Jarvis - Financial Analysis CLI"""
    pass


async def run_quick_check(ticker: str) -> dict:
    """Run quick check pipeline."""
    provider = YFinanceProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)
    pipeline = QuickCheckPipeline(technical_tool=tool)
    return await pipeline.run(ticker)


@app.command()
def check(
    ticker: str = typer.Argument(..., help="Stock ticker symbol (e.g., AAPL)"),
):
    """Quick check - technical analysis without LLM."""
    console.print(f"[bold]Analyzing {ticker}...[/bold]\n")

    result = asyncio.run(run_quick_check(ticker))

    if not result.get("success", False):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        raise typer.Exit(1)

    pipeline = QuickCheckPipeline(technical_tool=None)  # Just for formatting
    output = pipeline.format_output(result)
    console.print(Markdown(output))


async def run_deep_dive(ticker: str, provider: str) -> dict:
    """Run deep dive analysis pipeline."""
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

        if fundamental.sector or fundamental.industry:
            output += f"**Sector/Industry**: {fundamental.sector or 'N/A'} / {fundamental.industry or 'N/A'}\n\n"

        if fundamental.market_cap is not None:
            output += f"- **시가총액**: ${fundamental.market_cap/1e9:.2f}B\n"

        if fundamental.pe_ratio is not None:
            output += f"- **P/E Ratio**: {fundamental.pe_ratio:.1f}\n"
        if fundamental.forward_pe is not None:
            output += f"- **Forward P/E**: {fundamental.forward_pe:.1f}\n"
        if fundamental.peg_ratio is not None:
            output += f"- **PEG Ratio**: {fundamental.peg_ratio:.2f}\n"
        if fundamental.ev_ebitda is not None:
            output += f"- **EV/EBITDA**: {fundamental.ev_ebitda:.1f}\n"

        output += "\n"

        if fundamental.roe is not None:
            output += f"- **ROE**: {fundamental.roe*100:.1f}%\n"
        if fundamental.roa is not None:
            output += f"- **ROA**: {fundamental.roa*100:.1f}%\n"
        if fundamental.gross_margin is not None:
            output += f"- **매출총이익률**: {fundamental.gross_margin*100:.1f}%\n"
        if fundamental.operating_margin is not None:
            output += f"- **영업이익률**: {fundamental.operating_margin*100:.1f}%\n"
        if fundamental.profit_margin is not None:
            output += f"- **순이익률**: {fundamental.profit_margin*100:.1f}%\n"

        output += "\n"

        if fundamental.revenue_growth is not None:
            output += f"- **매출 성장률**: {fundamental.revenue_growth*100:.1f}%\n"
        if fundamental.earnings_growth is not None:
            output += f"- **이익 성장률**: {fundamental.earnings_growth*100:.1f}%\n"

        output += "\n"

        if fundamental.debt_to_equity is not None:
            output += f"- **Debt/Equity**: {fundamental.debt_to_equity:.1f}\n"
        if fundamental.current_ratio is not None:
            output += f"- **유동비율**: {fundamental.current_ratio:.2f}\n"

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
    ticker: str = typer.Argument(..., help="Stock ticker symbol (e.g., AAPL)"),
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
):
    """Deep dive analysis with LLM (technical + news)."""
    console.print(f"[bold]Running deep dive analysis for {ticker}...[/bold]\n")

    try:
        result = asyncio.run(run_deep_dive(ticker, provider))
        output = format_deep_dive_output(result)
        console.print(Markdown(output))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


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
    tickers: str = typer.Option(
        "AAPL,MSFT,NVDA",
        "--tickers",
        "-t",
        help="Comma-separated ticker symbols",
    ),
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
):
    """Daily market report (macro snapshot + ticker analysis)."""
    ticker_list = [t.strip() for t in tickers.split(",")]
    console.print(f"[bold]Generating daily report for {len(ticker_list)} tickers...[/bold]\n")

    try:
        result = asyncio.run(run_daily_report(ticker_list, provider))
        output = format_daily_report_output(result)
        console.print(Markdown(output))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


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


if __name__ == "__main__":
    app()
