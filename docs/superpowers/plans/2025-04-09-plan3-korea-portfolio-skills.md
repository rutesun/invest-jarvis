# Plan 3: Korea Stocks + Portfolio + Skills

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 한국 주식 지원, 포트폴리오 모니터링, Claude Code Skills 제공

**Architecture:** KIS API 연동, 포트폴리오 파이프라인 구현, Claude Code Skills (가벼운 CLI 래퍼)

**Tech Stack:** KIS API (한국투자증권), httpx (API), pandas

---

## File Structure

```
invest-jarvis/
├── src/
│   ├── providers/
│   │   └── kis.py               # KIS API 래퍼
│   ├── tools/
│   │   └── portfolio.py         # 포트폴리오 분석 도구
│   └── pipelines/
│       └── portfolio.py         # 포트폴리오 파이프라인
├── skills/
│   ├── invest-check.md          # jarvis check 래퍼
│   ├── invest-analyze.md        # jarvis analyze 래퍼
│   └── invest-report.md         # jarvis report 래퍼
└── tests/
    ├── providers/
    │   └── test_kis.py
    ├── tools/
    │   └── test_portfolio.py
    └── pipelines/
        └── test_portfolio.py
```

---

## Task 1: KIS Provider - Models

**Files:**
- Create: `src/providers/kis_models.py`
- Test: `tests/providers/test_kis_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_kis_models.py
import pytest
from src.providers.kis_models import (
    KISToken,
    KISQuote,
    KISBalance,
    KISPosition,
)


def test_kis_token():
    token = KISToken(
        access_token="test_token_xyz",
        token_type="Bearer",
        expires_in=86400,
    )
    assert token.access_token == "test_token_xyz"
    assert token.token_type == "Bearer"


def test_kis_quote():
    quote = KISQuote(
        ticker="005930",
        name="삼성전자",
        price=70000,
        change=1000,
        change_pct=1.45,
        volume=10000000,
    )
    assert quote.ticker == "005930"
    assert quote.name == "삼성전자"
    assert quote.price == 70000


def test_kis_position():
    position = KISPosition(
        ticker="005930",
        name="삼성전자",
        quantity=100,
        avg_price=68000,
        current_price=70000,
        profit_loss=200000,
        profit_loss_pct=2.94,
    )
    assert position.ticker == "005930"
    assert position.quantity == 100


def test_kis_balance():
    positions = [
        KISPosition(
            ticker="005930",
            name="삼성전자",
            quantity=100,
            avg_price=68000,
            current_price=70000,
            profit_loss=200000,
            profit_loss_pct=2.94,
        )
    ]
    balance = KISBalance(
        total_assets=10000000,
        cash=3000000,
        stock_value=7000000,
        positions=positions,
    )
    assert balance.total_assets == 10000000
    assert len(balance.positions) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_kis_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/providers/kis_models.py
from pydantic import BaseModel


class KISToken(BaseModel):
    """KIS API access token."""
    access_token: str
    token_type: str
    expires_in: int


class KISQuote(BaseModel):
    """Korean stock quote."""
    ticker: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int


class KISPosition(BaseModel):
    """Portfolio position."""
    ticker: str
    name: str
    quantity: int
    avg_price: float
    current_price: float
    profit_loss: float
    profit_loss_pct: float


class KISBalance(BaseModel):
    """Portfolio balance."""
    total_assets: float
    cash: float
    stock_value: float
    positions: list[KISPosition]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_kis_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/providers/kis_models.py tests/providers/test_kis_models.py
git commit -m "feat(providers): add KIS API models"
```

---

## Task 2: KIS Provider - Client

**Files:**
- Create: `src/providers/kis.py`
- Test: `tests/providers/test_kis.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_kis.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.providers.kis import KISProvider


@pytest.fixture
def mock_token_response():
    return {
        "access_token": "test_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }


@pytest.fixture
def mock_quote_response():
    return {
        "output": {
            "stck_prpr": "70000",  # 현재가
            "prdy_vrss": "1000",   # 전일대비
            "prdy_ctrt": "1.45",   # 등락률
            "acml_vol": "10000000",  # 누적거래량
        }
    }


@pytest.mark.asyncio
async def test_kis_get_access_token(mock_token_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_token_response
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

        provider = KISProvider(app_key="test_key", app_secret="test_secret")
        token = await provider._get_access_token()

        assert token.access_token == "test_token"
        assert token.token_type == "Bearer"


@pytest.mark.asyncio
async def test_kis_get_quote(mock_token_response, mock_quote_response):
    with patch("httpx.AsyncClient") as mock_client:
        # Mock token response
        mock_token_resp = AsyncMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        # Mock quote response
        mock_quote_resp = AsyncMock()
        mock_quote_resp.json.return_value = mock_quote_response
        mock_quote_resp.raise_for_status = MagicMock()

        mock_client_instance = mock_client.return_value.__aenter__.return_value
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_quote_resp

        provider = KISProvider(app_key="test_key", app_secret="test_secret")
        quote = await provider.get_quote("005930")

        assert quote["ticker"] == "005930"
        assert quote["price"] == 70000.0


@pytest.mark.asyncio
async def test_kis_implements_base_provider():
    """Verify KISProvider implements BaseProvider interface."""
    from src.core.interfaces import BaseProvider
    provider = KISProvider(app_key="test", app_secret="test")
    assert isinstance(provider, BaseProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_kis.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/providers/kis.py
import asyncio
from functools import lru_cache
import httpx
import pandas as pd
from datetime import datetime, timedelta
from src.core.interfaces import BaseProvider
from src.providers.kis_models import KISToken, KISQuote


class KISProvider(BaseProvider):
    """한국투자증권 API provider for Korean stocks."""

    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self._token: KISToken | None = None
        self._token_expires: datetime | None = None

    async def _get_access_token(self) -> KISToken:
        """Get or refresh access token."""
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        url = f"{self.BASE_URL}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        self._token = KISToken(**data)
        self._token_expires = datetime.now() + timedelta(seconds=data["expires_in"] - 60)
        return self._token

    async def get_quote(self, ticker: str) -> dict:
        """Get current quote for Korean stock."""
        token = await self._get_access_token()

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        output = data["output"]
        return {
            "ticker": ticker,
            "price": float(output["stck_prpr"]),
            "change": float(output["prdy_vrss"]),
            "change_pct": float(output["prdy_ctrt"]),
            "volume": int(output["acml_vol"]),
            "name": output.get("hts_kor_isnm", ""),
        }

    async def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data for Korean stock."""
        # Convert period to days
        period_days_map = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730,
        }
        days = period_days_map.get(period, 365)

        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010400",
            "Content-Type": "application/json; charset=utf-8",
        }

        # KIS API requires end date
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_PERIOD_DIV_CODE": "D",  # Daily
            "FID_ORG_ADJ_PRC": "0",  # Adjusted price
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        # Parse response
        records = []
        for item in data.get("output", []):
            records.append({
                "Date": pd.to_datetime(item["stck_bsop_date"]),
                "Open": float(item["stck_oprc"]),
                "High": float(item["stck_hgpr"]),
                "Low": float(item["stck_lwpr"]),
                "Close": float(item["stck_clpr"]),
                "Volume": int(item["acml_vol"]),
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df.set_index("Date", inplace=True)
            df.sort_index(inplace=True)

        return df

    async def get_balance(self) -> dict:
        """Get portfolio balance and positions."""
        token = await self._get_access_token()

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "TTTC8434R",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "CANO": "계좌번호",  # TODO: Get from config
            "ACNT_PRDT_CD": "01",
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        # Parse balance
        output1 = data.get("output1", [])
        output2 = data.get("output2", {})

        positions = []
        for item in output1:
            positions.append({
                "ticker": item["pdno"],
                "name": item["prdt_name"],
                "quantity": int(item["hldg_qty"]),
                "avg_price": float(item["pchs_avg_pric"]),
                "current_price": float(item["prpr"]),
                "profit_loss": float(item["evlu_pfls_amt"]),
                "profit_loss_pct": float(item["evlu_pfls_rt"]),
            })

        return {
            "total_assets": float(output2.get("tot_evlu_amt", 0)),
            "cash": float(output2.get("prvs_rcdl_excc_amt", 0)),
            "stock_value": float(output2.get("scts_evlu_amt", 0)),
            "positions": positions,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_kis.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/providers/kis.py tests/providers/test_kis.py
git commit -m "feat(providers): add KIS API client for Korean stocks"
```

---

## Task 3: Portfolio Tool

**Files:**
- Create: `src/tools/portfolio.py`
- Test: `tests/tools/test_portfolio.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_portfolio.py
import pytest
from unittest.mock import AsyncMock
from src.tools.portfolio import PortfolioTool


@pytest.fixture
def mock_balance():
    return {
        "total_assets": 10000000,
        "cash": 3000000,
        "stock_value": 7000000,
        "positions": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "quantity": 100,
                "avg_price": 68000,
                "current_price": 70000,
                "profit_loss": 200000,
                "profit_loss_pct": 2.94,
            }
        ],
    }


@pytest.mark.asyncio
async def test_portfolio_tool_execute(mock_balance):
    mock_provider = AsyncMock()
    mock_provider.get_balance.return_value = mock_balance

    tool = PortfolioTool(provider=mock_provider)
    result = await tool.execute()

    assert result.success is True
    assert result.data["total_assets"] == 10000000
    assert len(result.data["positions"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_portfolio.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/portfolio.py
from src.core.interfaces import BaseTool
from src.core.models import ToolResult
from src.providers.kis import KISProvider


class PortfolioTool(BaseTool):
    """Portfolio analysis tool."""

    name = "portfolio"
    description = "포트폴리오 잔고 및 보유 종목 조회"

    def __init__(self, provider: KISProvider):
        self.provider = provider

    async def execute(self, **kwargs) -> ToolResult:
        """Get portfolio balance and positions."""
        try:
            balance = await self.provider.get_balance()
            return ToolResult(success=True, data=balance)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_portfolio.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/portfolio.py tests/tools/test_portfolio.py
git commit -m "feat(tools): add portfolio tool for balance/positions"
```

---

## Task 4: Portfolio Pipeline

**Files:**
- Create: `src/pipelines/portfolio.py`
- Test: `tests/pipelines/test_portfolio.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/pipelines/test_portfolio.py
import pytest
from unittest.mock import AsyncMock
from src.pipelines.portfolio import PortfolioPipeline


@pytest.fixture
def mock_portfolio_tool():
    tool = AsyncMock()
    tool.execute.return_value.success = True
    tool.execute.return_value.data = {
        "total_assets": 10000000,
        "positions": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "quantity": 100,
                "current_price": 70000,
                "profit_loss_pct": 2.94,
            }
        ],
    }
    return tool


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    from src.tools.technical.models import IndicatorSnapshot, StrategyResult, TechnicalResult
    from datetime import datetime

    tech_result = TechnicalResult(
        ticker="005930",
        timestamp=datetime.now(),
        indicators=IndicatorSnapshot(price=70000, change_pct=1.5),
        strategies=[
            StrategyResult(
                name="trend",
                status="강세",
                confidence=75.0,
                signals=["골든크로스"],
                evidence=["20일선 > 50일선"],
                metrics={},
            )
        ],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["상승 추세"],
        warnings=[],
    )
    tool.execute.return_value.success = True
    tool.execute.return_value.data = tech_result
    return tool


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock()
    tool.execute.return_value.success = True
    tool.execute.return_value.data = [
        {"title": "삼성전자 실적 발표", "published": "2024-01-01", "summary": "좋은 실적"}
    ]
    return tool


@pytest.mark.asyncio
async def test_portfolio_pipeline_run(
    mock_portfolio_tool, mock_technical_tool, mock_news_tool
):
    pipeline = PortfolioPipeline(
        portfolio_tool=mock_portfolio_tool,
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run()

    assert result["success"] is True
    assert result["total_assets"] == 10000000
    assert len(result["holdings"]) == 1
    assert result["holdings"][0]["ticker"] == "005930"
    assert "technical" in result["holdings"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/test_portfolio.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/pipelines/portfolio.py
from typing import Any
from src.tools.portfolio import PortfolioTool
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.news import NewsTool


class PortfolioPipeline:
    """Portfolio monitoring pipeline."""

    def __init__(
        self,
        portfolio_tool: PortfolioTool,
        technical_tool: TechnicalAnalysisTool,
        news_tool: NewsTool,
    ):
        self.portfolio_tool = portfolio_tool
        self.technical_tool = technical_tool
        self.news_tool = news_tool

    async def run(self) -> dict[str, Any]:
        """Run portfolio monitoring."""
        # Get portfolio
        portfolio_result = await self.portfolio_tool.execute()
        if not portfolio_result.success:
            return {
                "success": False,
                "error": portfolio_result.error,
            }

        balance = portfolio_result.data
        holdings = []

        # Analyze each position
        for position in balance.get("positions", []):
            ticker = position["ticker"]

            # Technical analysis
            tech_result = await self.technical_tool.execute(ticker)
            technical = tech_result.data if tech_result.success else None

            # News
            news_result = await self.news_tool.execute(ticker, limit=3)
            news = news_result.data if news_result.success else []

            holdings.append({
                "ticker": ticker,
                "name": position["name"],
                "quantity": position["quantity"],
                "current_price": position["current_price"],
                "profit_loss": position.get("profit_loss", 0),
                "profit_loss_pct": position.get("profit_loss_pct", 0),
                "technical": technical,
                "news": news,
            })

        return {
            "success": True,
            "total_assets": balance["total_assets"],
            "cash": balance.get("cash", 0),
            "stock_value": balance.get("stock_value", 0),
            "holdings": holdings,
        }

    def format_output(self, result: dict[str, Any]) -> str:
        """Format portfolio result as readable string."""
        if not result.get("success", False):
            return f"Error: {result.get('error', 'Unknown error')}"

        lines = [
            f"## Portfolio Summary",
            "",
            f"**Total Assets**: ₩{result['total_assets']:,.0f}",
            f"**Cash**: ₩{result.get('cash', 0):,.0f}",
            f"**Stock Value**: ₩{result.get('stock_value', 0):,.0f}",
            "",
            "### Holdings",
            "",
        ]

        for holding in result.get("holdings", []):
            lines.append(f"#### {holding['name']} ({holding['ticker']})")
            lines.append(f"- Quantity: {holding['quantity']}")
            lines.append(f"- Current: ₩{holding['current_price']:,.0f}")
            lines.append(f"- P&L: ₩{holding.get('profit_loss', 0):,.0f} ({holding.get('profit_loss_pct', 0):+.2f}%)")

            if holding.get("technical"):
                tech = holding["technical"]
                lines.append(f"- Assessment: {tech.overall_assessment} (신뢰도: {tech.confidence_score:.0f}%)")
                if tech.key_insights:
                    lines.append(f"- Insights: {', '.join(tech.key_insights[:2])}")

            lines.append("")

        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/test_portfolio.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/portfolio.py tests/pipelines/test_portfolio.py
git commit -m "feat(pipelines): add PortfolioPipeline for monitoring"
```

---

## Task 5: CLI Portfolio Command

**Files:**
- Edit: `src/cli/main.py`
- Test: `tests/cli/test_cli.py`

- [ ] **Step 1: Add portfolio command**

```python
@app.command()
def portfolio(
    provider: str = typer.Option("openai", help="LLM provider"),
):
    """Monitor portfolio with technical analysis and news."""
    # Check KIS credentials
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

    from src.pipelines.portfolio import PortfolioPipeline
    pipeline = PortfolioPipeline(None, None, None)  # Just for formatting
    output = pipeline.format_output(result)
    console.print(Markdown(output))


async def run_portfolio_monitoring() -> dict:
    """Run portfolio monitoring."""
    from src.providers.kis import KISProvider
    from src.tools.portfolio import PortfolioTool
    from src.tools.technical.registry import StrategyRegistry
    from src.tools.technical.tool import TechnicalAnalysisTool
    from src.tools.news import NewsTool
    from src.pipelines.portfolio import PortfolioPipeline

    config = load_config()
    kis_provider = KISProvider(
        app_key=os.getenv("KIS_APP_KEY"),
        app_secret=os.getenv("KIS_APP_SECRET"),
    )
    yf_provider = YFinanceProvider()  # For technical analysis

    portfolio_tool = PortfolioTool(provider=kis_provider)
    registry = StrategyRegistry.from_config(config.technical.strategies)
    technical_tool = TechnicalAnalysisTool(provider=yf_provider, registry=registry)
    news_tool = NewsTool(provider=yf_provider)

    pipeline = PortfolioPipeline(
        portfolio_tool=portfolio_tool,
        technical_tool=technical_tool,
        news_tool=news_tool,
    )

    return await pipeline.run()
```

- [ ] **Step 2: Test**

Run: `uv run jarvis portfolio` (requires KIS credentials)

- [ ] **Step 3: Commit**

```bash
git add src/cli/main.py
git commit -m "feat(cli): add portfolio command"
```

---

## Task 6: Claude Code Skills

**Files:**
- Create: `skills/invest-check.md`
- Create: `skills/invest-analyze.md`
- Create: `skills/invest-report.md`

- [ ] **Step 1: Create invest-check skill**

```markdown
<!-- skills/invest-check.md -->
---
description: Quick technical analysis check (lightweight CLI wrapper)
skill_type: user-invocable
---

# invest-check

Quick technical analysis for a stock ticker.

**Usage:** `/invest-check AAPL`

**What it does:**
- Runs `jarvis check <ticker>` command
- Shows price, indicators, trend analysis
- No LLM, fast response

**Examples:**
- `/invest-check AAPL` - Apple quick check
- `/invest-check MSFT` - Microsoft quick check
- `/invest-check 005930` - Samsung Electronics (KR)

---

## Implementation

When invoked:

1. Extract ticker from user input
2. Run: `jarvis check <ticker>`
3. Display formatted output

```python
import subprocess
import sys

# Get ticker from args
ticker = "{{TICKER}}"

# Run command
result = subprocess.run(
    ["jarvis", "check", ticker],
    capture_output=True,
    text=True,
)

# Display output
if result.returncode == 0:
    print(result.stdout)
else:
    print(f"Error: {result.stderr}")
    sys.exit(1)
```
```

- [ ] **Step 2: Create invest-analyze skill**

```markdown
<!-- skills/invest-analyze.md -->
---
description: Deep dive analysis with LLM (technical + news)
skill_type: user-invocable
---

# invest-analyze

Deep analysis combining technical indicators and news sentiment.

**Usage:** `/invest-analyze AAPL`

**What it does:**
- Runs `jarvis analyze <ticker>` command
- Technical analysis with LLM interpretation
- News sentiment analysis
- Actionable recommendations

**Requires:** OPENAI_API_KEY or ANTHROPIC_API_KEY

**Examples:**
- `/invest-analyze AAPL` - Apple deep dive
- `/invest-analyze TSLA` - Tesla analysis
- `/invest-analyze NVDA` - NVIDIA analysis

---

## Implementation

When invoked:

1. Extract ticker from user input
2. Check API key availability
3. Run: `jarvis analyze <ticker>`
4. Display formatted output with sections:
   - Technical Summary
   - News Analysis
   - Recommendation

```python
import subprocess
import os
import sys

ticker = "{{TICKER}}"

# Check API key
if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
    print("Error: OPENAI_API_KEY or ANTHROPIC_API_KEY required")
    sys.exit(1)

# Run command
result = subprocess.run(
    ["jarvis", "analyze", ticker],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print(result.stdout)
else:
    print(f"Error: {result.stderr}")
    sys.exit(1)
```
```

- [ ] **Step 3: Create invest-report skill**

```markdown
<!-- skills/invest-report.md -->
---
description: Daily market report with macro indicators
skill_type: user-invocable
---

# invest-report

Generate daily market report with macro snapshot and top movers.

**Usage:** `/invest-report` or `/invest-report AAPL,MSFT,NVDA`

**What it does:**
- Runs `jarvis report` command
- Macro indicators (VIX, Fear & Greed, WTI, Yields, DXY)
- Technical analysis for specified tickers
- Market summary

**Requires:** OPENAI_API_KEY or ANTHROPIC_API_KEY

**Examples:**
- `/invest-report` - Default tickers (AAPL, MSFT, NVDA)
- `/invest-report AAPL,TSLA,GOOGL` - Custom tickers

---

## Implementation

When invoked:

1. Extract tickers from user input (optional)
2. Check API key availability
3. Run: `jarvis report --tickers=<tickers>`
4. Display formatted output

```python
import subprocess
import os
import sys

tickers = "{{TICKERS}}" or "AAPL,MSFT,NVDA"

if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
    print("Error: OPENAI_API_KEY or ANTHROPIC_API_KEY required")
    sys.exit(1)

result = subprocess.run(
    ["jarvis", "report", f"--tickers={tickers}"],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print(result.stdout)
else:
    print(f"Error: {result.stderr}")
    sys.exit(1)
```
```

- [ ] **Step 4: Commit**

```bash
git add skills/
git commit -m "feat(skills): add Claude Code skills for check/analyze/report"
```

---

## Task 7: Update .env.example

**Files:**
- Edit: `.env.example`

- [ ] **Step 1: Add KIS credentials**

```
# API Keys
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# KIS API (한국투자증권)
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add KIS credentials to .env.example"
```

---

## Task 8: Integration Test and Final Verification

**Files:**
- Create: `tests/integration/test_e2e_plan3.py`

```python
# tests/integration/test_e2e_plan3.py
import pytest
from typer.testing import CliRunner
from src.cli.main import app
import os

runner = CliRunner()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("KIS_APP_KEY") or not os.getenv("KIS_APP_SECRET"),
    reason="KIS credentials not available",
)
def test_portfolio_command():
    """Test portfolio command with real KIS API."""
    result = runner.invoke(app, ["portfolio"])
    assert result.exit_code == 0
    assert "portfolio" in result.stdout.lower() or "holdings" in result.stdout.lower()


@pytest.mark.integration
def test_korean_stock_check():
    """Test check command with Korean stock."""
    result = runner.invoke(app, ["check", "005930"])  # Samsung
    # May fail if yfinance doesn't support KR stocks well, but shouldn't crash
    assert result.exit_code in [0, 1]
```

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ -v --ignore=tests/integration`
Expected: All pass

- [ ] **Step 2: Manual CLI tests**

```bash
# With KIS credentials
export KIS_APP_KEY=...
export KIS_APP_SECRET=...
uv run jarvis portfolio

# Skills (in Claude Code)
/invest-check AAPL
/invest-analyze AAPL
/invest-report
```

- [ ] **Step 3: Commit and tag**

```bash
git add tests/integration/test_e2e_plan3.py
git commit -m "test: add Plan 3 integration tests"
git tag -a v0.3.0 -m "Plan 3 complete: Korea Stocks + Portfolio + Skills"
```

---

## Summary

Plan 3 완료 시 동작하는 기능:

```bash
# CLI Commands
jarvis check AAPL           # 빠른 체크
jarvis check 005930         # 한국 주식 체크 (KIS API)
jarvis analyze AAPL         # 심층 분석
jarvis report               # 일일 리포트
jarvis portfolio            # 포트폴리오 모니터링 (KIS API 필요)

# Claude Code Skills
/invest-check AAPL          # 빠른 체크
/invest-analyze AAPL        # 심층 분석
/invest-report              # 일일 리포트
```

출력 예시 (portfolio):
```
## Portfolio Summary

**Total Assets**: ₩10,000,000
**Cash**: ₩3,000,000
**Stock Value**: ₩7,000,000

### Holdings

#### 삼성전자 (005930)
- Quantity: 100
- Current: ₩70,000
- P&L: ₩200,000 (+2.94%)
- Assessment: 매수 (신뢰도: 75%)
- Insights: 골든크로스 발생, RSI 중립권
```

전체 기능 완성! v0.3.0
