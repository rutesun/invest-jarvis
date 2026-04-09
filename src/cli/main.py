import asyncio
import os
from pathlib import Path
from typing import Optional, Literal
import typer
from rich.console import Console
from rich.markdown import Markdown
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from src.core.config import load_config
from src.providers.yfinance_provider import YFinanceProvider
from src.providers.kis import KISProvider
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool
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
    )

    return await pipeline.run(ticker)


def format_deep_dive_output(result: dict) -> str:
    """Format deep dive result as markdown."""
    ticker = result["ticker"]
    technical = result["technical"]
    tech_summary = result["technical_summary"]
    news_analysis = result.get("news_analysis")

    output = f"# Deep Dive Analysis: {ticker}\n\n"

    # Support both old (indicators) and new (snapshot) field
    snapshot = technical.indicators or technical.snapshot
    output += f"## Price: ${snapshot.price:.2f} ({snapshot.change_pct:+.2f}%)\n\n"

    output += "## Technical Analysis\n\n"
    output += f"**Total Score**: {technical.total_score}\n\n"
    output += f"**Summary**: {tech_summary.summary}\n\n"
    output += f"**Recommendation**: {tech_summary.recommendation} (신뢰도: {tech_summary.confidence * 100:.0f}%)\n\n"
    output += f"**Rationale**: {tech_summary.rationale}\n\n"

    if tech_summary.key_insights:
        output += "**Key Insights**:\n"
        for insight in tech_summary.key_insights:
            output += f"- {insight}\n"
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
