import asyncio
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.markdown import Markdown

from src.core.config import load_config
from src.providers.yfinance_provider import YFinanceProvider
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.tool import TechnicalAnalysisTool
from src.pipelines.quick_check import QuickCheckPipeline

app = typer.Typer(help="Invest Jarvis - Financial Analysis CLI")
console = Console()


def version_callback(value: bool):
    if value:
        console.print("invest-jarvis version 0.1.0")
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
    config = load_config()
    provider = YFinanceProvider()
    registry = StrategyRegistry.from_config(config.technical.strategies)
    tool = TechnicalAnalysisTool(provider=provider, registry=registry)
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


if __name__ == "__main__":
    app()
