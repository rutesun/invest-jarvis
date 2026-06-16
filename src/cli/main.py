import asyncio
import contextlib
import logging
import os
from pathlib import Path
from typing import Literal

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.cli.analyze_render import format_deep_dive_output  # noqa: F401 (re-export for compat)
from src.llm.models import ActionableSignalOutput
from src.llm.provider import LLMProvider
from src.pipelines.deep_dive import DeepDivePipeline
from src.pipelines.portfolio import PortfolioPipeline
from src.pipelines.quick_check import QuickCheckPipeline
from src.pipelines.screener import ScreenerPipeline
from src.pipelines.ticker_report import TickerReportPipeline
from src.providers.kis import KISProvider
from src.providers.naver import NaverProvider
from src.providers.ticker_resolver import TickerResolver
from src.providers.yfinance_provider import YFinanceProvider
from src.tools.fundamental import FundamentalTool
from src.tools.macro import MacroTool
from src.tools.news import NewsTool
from src.tools.portfolio import PortfolioTool
from src.tools.screener.evidence import EvidenceCollector
from src.tools.screener.universe import UniverseBuilder
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool


# Load environment variables from .env file
load_dotenv()


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
        raise typer.Exit(1) from None

    result = asyncio.run(run_quick_check(query))

    if not result.get("success", False):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        raise typer.Exit(1) from None

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

    # 공시 툴: SEC는 항상 사용 가능, DART는 API 키 있을 때만
    from src.tools.disclosure import DARTDisclosureFetcher, DisclosureTool, SECDisclosureFetcher

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

    # CriteriaEngine 주입: index/fmp/kis provider 있으면 생성
    criteria_engine = None
    try:
        from src.providers.index_provider import IndexProvider
        from src.tools.criteria.engine import CriteriaEngine
        from src.tools.criteria.holdings import load_holdings

        holdings_config = load_holdings()
        capital_usd, risk_pct_usd = holdings_config.usd_capital, holdings_config.usd_risk_pct
        capital_krw, risk_pct_krw = holdings_config.krw_capital, holdings_config.krw_risk_pct

        fmp_api_key = os.getenv("FMP_API_KEY")
        fmp_provider = None
        if fmp_api_key:
            with contextlib.suppress(Exception):
                from src.providers.fmp_provider import FmpProvider

                fmp_provider = FmpProvider(api_key=fmp_api_key)

        criteria_engine = CriteriaEngine(
            index_provider=IndexProvider(),
            fmp_provider=fmp_provider,
            kis_provider=kis_provider,
            usd_capital=capital_usd,
            usd_risk_pct=risk_pct_usd or 0.01,
            krw_capital=capital_krw,
            krw_risk_pct=risk_pct_krw or 0.01,
        )
    except Exception as _e:
        logger.debug("CriteriaEngine 초기화 실패 (기준 평가 섹션 생략): %s", _e)

    pipeline = DeepDivePipeline(
        technical_tool=technical_tool,
        news_tool=news_tool,
        llm=llm,
        fundamental_tool=fundamental_tool,
        disclosure_tool=disclosure_tool,
        flow_tool=flow_tool,
        criteria_engine=criteria_engine,
    )

    return await pipeline.run(ticker)


def display_actionable_signal(signal: ActionableSignalOutput) -> Panel:
    """Display actionable investment signal as Rich Panel."""
    # Determine panel color based on action
    color_map = {
        "매수": "green",
        "매도": "red",
        "관망": "yellow",
    }
    border_color = color_map.get(signal.action, "white")

    # Build panel content
    content = []

    # Headline
    content.append(f"[bold]{signal.headline}[/bold]\n")

    # Action and Timing
    content.append(
        f"🎯 **액션**: {signal.action} | ⏰ **타이밍**: {signal.timing} | 💪 **강도**: {signal.signal_strength}/10\n"
    )

    # Primary reason
    content.append(f"🔑 **핵심 이유**: {signal.primary_reason}\n")

    # Supporting reasons
    if signal.supporting_reasons:
        content.append("✅ **부차 이유**:")
        for reason in signal.supporting_reasons:
            content.append(f"  • {reason}")
        content.append("")

    # Risks
    if signal.risks:
        content.append("⚠️  **리스크**:")
        for risk in signal.risks:
            content.append(f"  • {risk}")
        content.append("")

    # Invalidation point
    if signal.invalidation_point:
        content.append(f"🛑 **손절/청산 가격**: {signal.invalidation_point}\n")

    # Confidence
    content.append(f"📊 **신뢰도**: {signal.confidence * 100:.0f}%")

    # Phase 2 fields: Pattern insights and price levels
    if signal.pattern_insight:
        content.append(f"\n📈 **패턴 분석**: {signal.pattern_insight}")

    if signal.target_price:
        content.append(f"🎯 **목표가**: {signal.target_price}")

    if signal.entry_zone:
        content.append(f"✅ **진입 구간**: {signal.entry_zone}")

    if signal.key_levels:
        content.append(f"📍 **주요 레벨**: {signal.key_levels}")

    panel = Panel(
        "\n".join(content),
        title="[bold]🚀 실행 가능한 투자 시그널[/bold]",
        border_style=border_color,
        expand=False,
    )

    return panel


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

        # Display actionable signal panel if available
        actionable_signal = result.get("actionable_signal")
        if actionable_signal and not result.get("decision_summary"):
            console.print("\n")
            panel = display_actionable_signal(actionable_signal)
            console.print(panel)

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

    pipeline = TickerReportPipeline(
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

    output = "# Daily Market Report\n\n"
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


@report_app.command("ticker")
def report_ticker(
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
    """티커 기반 시장 리포트 (매크로 + 티커 분석)."""
    ticker_list = [t.strip() for t in tickers.split(",")]
    console.print(f"[bold]Generating daily report for {len(ticker_list)} tickers...[/bold]\n")

    try:
        result = asyncio.run(run_daily_report(ticker_list, provider))
        output = format_daily_report_output(result)
        console.print(Markdown(output))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None


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
        raise typer.Exit(1) from None

    console.print("[bold]Loading portfolio...[/bold]\n")

    result = asyncio.run(run_portfolio_monitoring())

    if not result.get("success", False):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        raise typer.Exit(1) from None

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
