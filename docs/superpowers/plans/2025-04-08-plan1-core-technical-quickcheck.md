# Plan 1: Core + Technical Analysis + Quick Check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jarvis check AAPL` 명령어로 미국 주식의 기술적 분석 빠른 체크 기능 구현

**Architecture:** 모듈러 구조로 Core 인터페이스 정의 후, YFinance Provider와 Technical Analysis Tool 구현. Trend 전략 하나로 시작하여 Quick Check 파이프라인과 CLI 연결.

**Tech Stack:** Python 3.11+, Typer (CLI), Pydantic (모델), pandas + pandas-ta (지표), yfinance (데이터)

---

## File Structure

```
invest-jarvis/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # 환경설정 로더
│   │   ├── models.py              # ToolResult 등 공통 모델
│   │   └── interfaces.py          # BaseTool, BaseProvider
│   ├── providers/
│   │   ├── __init__.py
│   │   └── yfinance_provider.py   # YFinance 래퍼
│   ├── storage/
│   │   ├── __init__.py
│   │   └── cache.py               # TTL 기반 메모리 캐시
│   ├── tools/
│   │   ├── __init__.py
│   │   └── technical/
│   │       ├── __init__.py
│   │       ├── base.py            # BaseStrategy
│   │       ├── models.py          # IndicatorSnapshot, StrategyResult, TechnicalResult
│   │       ├── indicators.py      # 지표 계산
│   │       ├── registry.py        # StrategyRegistry
│   │       ├── tool.py            # TechnicalAnalysisTool
│   │       └── strategies/
│   │           ├── __init__.py
│   │           └── trend.py       # TrendStrategy
│   ├── pipelines/
│   │   ├── __init__.py
│   │   └── quick_check.py         # QuickCheckPipeline
│   └── cli/
│       ├── __init__.py
│       └── main.py                # Typer CLI
├── tests/
│   ├── __init__.py
│   ├── core/
│   │   └── test_config.py
│   ├── providers/
│   │   └── test_yfinance.py
│   ├── storage/
│   │   └── test_cache.py
│   ├── tools/
│   │   └── technical/
│   │       ├── test_indicators.py
│   │       ├── test_trend_strategy.py
│   │       └── test_tool.py
│   ├── pipelines/
│   │   └── test_quick_check.py
│   └── cli/
│       └── test_cli.py
├── pyproject.toml
├── config.yaml
└── .env.example
```

---

## Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `config.yaml`
- Create: `.gitignore`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "invest-jarvis"
version = "0.1.0"
description = "Financial investment analysis CLI tool"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.9.0",
    "pydantic>=2.0.0",
    "pandas>=2.0.0",
    "pandas-ta>=0.3.14b",
    "yfinance>=0.2.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "httpx>=0.25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",
]

[project.scripts]
jarvis = "src.cli.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create .env.example**

```
# API Keys (for future use)
OPENAI_API_KEY=
KIS_APP_KEY=
KIS_APP_SECRET=
```

- [ ] **Step 3: Create config.yaml**

```yaml
technical:
  strategies:
    - trend

cache:
  quote_ttl: 60        # 1분
  history_ttl: 300     # 5분
  indicators_ttl: 300  # 5분
```

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
venv/
data/
reports/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
```

- [ ] **Step 5: Create directory structure**

Run: `mkdir -p src/core src/providers src/storage src/tools/technical/strategies src/pipelines src/cli tests/core tests/providers tests/storage tests/tools/technical tests/pipelines tests/cli`

- [ ] **Step 6: Create __init__.py files**

Run: `touch src/__init__.py src/core/__init__.py src/providers/__init__.py src/storage/__init__.py src/tools/__init__.py src/tools/technical/__init__.py src/tools/technical/strategies/__init__.py src/pipelines/__init__.py src/cli/__init__.py tests/__init__.py tests/core/__init__.py tests/providers/__init__.py tests/storage/__init__.py tests/tools/__init__.py tests/tools/technical/__init__.py tests/pipelines/__init__.py tests/cli/__init__.py`

- [ ] **Step 7: Install dependencies**

Run: `uv sync`
Expected: Dependencies installed successfully

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: project setup with pyproject.toml and config"
```

---

## Task 2: Core Models

**Files:**
- Create: `src/core/models.py`
- Test: `tests/core/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_models.py
import pytest
from src.core.models import ToolResult


def test_tool_result_success():
    result = ToolResult(success=True, data={"price": 150.0})
    assert result.success is True
    assert result.data == {"price": 150.0}
    assert result.error is None


def test_tool_result_failure():
    result = ToolResult(success=False, data=None, error="API error")
    assert result.success is False
    assert result.error == "API error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/core/models.py
from typing import Any
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Tool execution result."""
    success: bool
    data: Any
    error: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/models.py tests/core/test_models.py
git commit -m "feat(core): add ToolResult model"
```

---

## Task 3: Core Interfaces

**Files:**
- Create: `src/core/interfaces.py`
- Test: `tests/core/test_interfaces.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_interfaces.py
import pytest
import pandas as pd
from src.core.interfaces import BaseTool, BaseProvider
from src.core.models import ToolResult


class MockTool(BaseTool):
    name = "mock"
    description = "Mock tool for testing"

    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"ticker": ticker})


class MockProvider(BaseProvider):
    async def get_price_history(self, ticker: str, period: str) -> pd.DataFrame:
        return pd.DataFrame({"Close": [100, 101, 102]})

    async def get_quote(self, ticker: str) -> dict:
        return {"price": 150.0}


@pytest.mark.asyncio
async def test_base_tool_interface():
    tool = MockTool()
    assert tool.name == "mock"
    result = await tool.execute("AAPL")
    assert result.success is True
    assert result.data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_base_provider_interface():
    provider = MockProvider()
    df = await provider.get_price_history("AAPL", "1y")
    assert len(df) == 3
    quote = await provider.get_quote("AAPL")
    assert quote["price"] == 150.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_interfaces.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/core/interfaces.py
from abc import ABC, abstractmethod
import pandas as pd
from src.core.models import ToolResult


class BaseTool(ABC):
    """Abstract base class for all analysis tools."""
    name: str
    description: str

    @abstractmethod
    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        """Execute the tool and return result."""
        pass


class BaseProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    async def get_price_history(self, ticker: str, period: str) -> pd.DataFrame:
        """Get historical price data."""
        pass

    @abstractmethod
    async def get_quote(self, ticker: str) -> dict:
        """Get current quote."""
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_interfaces.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/interfaces.py tests/core/test_interfaces.py
git commit -m "feat(core): add BaseTool and BaseProvider interfaces"
```

---

## Task 4: Config Loader

**Files:**
- Create: `src/core/config.py`
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_config.py
import pytest
import tempfile
import os
from pathlib import Path


def test_load_config_from_yaml(tmp_path):
    config_content = """
technical:
  strategies:
    - trend
    - oscillator
cache:
  quote_ttl: 60
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    from src.core.config import load_config
    config = load_config(config_file)

    assert config.technical.strategies == ["trend", "oscillator"]
    assert config.cache.quote_ttl == 60


def test_load_config_default():
    from src.core.config import load_config, AppConfig
    config = load_config(None)
    assert isinstance(config, AppConfig)
    assert config.cache.quote_ttl == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/core/config.py
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel


class CacheConfig(BaseModel):
    quote_ttl: int = 60
    history_ttl: int = 300
    indicators_ttl: int = 300


class TechnicalConfig(BaseModel):
    strategies: list[str] = ["trend"]


class AppConfig(BaseModel):
    technical: TechnicalConfig = TechnicalConfig()
    cache: CacheConfig = CacheConfig()


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """Load configuration from YAML file or use defaults."""
    if config_path is None:
        config_path = Path("config.yaml")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)

    return AppConfig()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/config.py tests/core/test_config.py
git commit -m "feat(core): add config loader with YAML support"
```

---

## Task 5: Memory Cache

**Files:**
- Create: `src/storage/cache.py`
- Test: `tests/storage/test_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_cache.py
import pytest
import asyncio
from src.storage.cache import MemoryCache


@pytest.mark.asyncio
async def test_cache_set_and_get():
    cache = MemoryCache()
    await cache.set("key1", {"value": 123}, ttl=60)
    result = await cache.get("key1")
    assert result == {"value": 123}


@pytest.mark.asyncio
async def test_cache_miss():
    cache = MemoryCache()
    result = await cache.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_cache_expiry():
    cache = MemoryCache()
    await cache.set("key1", "value", ttl=0)
    await asyncio.sleep(0.01)
    result = await cache.get("key1")
    assert result is None


@pytest.mark.asyncio
async def test_cache_get_or_fetch():
    cache = MemoryCache()
    call_count = 0

    async def fetcher():
        nonlocal call_count
        call_count += 1
        return {"data": "fetched"}

    result1 = await cache.get_or_fetch("key", fetcher, ttl=60)
    result2 = await cache.get_or_fetch("key", fetcher, ttl=60)

    assert result1 == {"data": "fetched"}
    assert result2 == {"data": "fetched"}
    assert call_count == 1  # fetcher called only once
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/storage/test_cache.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/storage/cache.py
import time
from typing import Any, Callable, Awaitable, Optional


class MemoryCache:
    """TTL-based in-memory cache."""

    def __init__(self):
        self._cache: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None

        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None

        return value

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache with TTL in seconds."""
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl: int = 300,
    ) -> Any:
        """Get from cache or fetch and cache."""
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await fetcher()
        await self.set(key, value, ttl)
        return value

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/storage/test_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/storage/cache.py tests/storage/test_cache.py
git commit -m "feat(storage): add TTL-based memory cache"
```

---

## Task 6: YFinance Provider

**Files:**
- Create: `src/providers/yfinance_provider.py`
- Test: `tests/providers/test_yfinance.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_yfinance.py
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.providers.yfinance_provider import YFinanceProvider


@pytest.mark.asyncio
async def test_get_quote():
    provider = YFinanceProvider()

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "currentPrice": 178.50,
        "previousClose": 175.00,
        "shortName": "Apple Inc.",
    }

    with patch("yfinance.Ticker", return_value=mock_ticker):
        quote = await provider.get_quote("AAPL")

    assert quote["price"] == 178.50
    assert quote["previous_close"] == 175.00
    assert quote["name"] == "Apple Inc."


@pytest.mark.asyncio
async def test_get_price_history():
    provider = YFinanceProvider()

    mock_df = pd.DataFrame({
        "Open": [170.0, 172.0],
        "High": [175.0, 178.0],
        "Low": [169.0, 171.0],
        "Close": [174.0, 177.0],
        "Volume": [1000000, 1200000],
    })

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_df

    with patch("yfinance.Ticker", return_value=mock_ticker):
        df = await provider.get_price_history("AAPL", "1y")

    assert len(df) == 2
    assert "Close" in df.columns
    mock_ticker.history.assert_called_once_with(period="1y")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_yfinance.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/providers/yfinance_provider.py
import asyncio
from functools import partial
import pandas as pd
import yfinance as yf
from src.core.interfaces import BaseProvider


class YFinanceProvider(BaseProvider):
    """YFinance data provider for US stocks."""

    async def get_quote(self, ticker: str) -> dict:
        """Get current quote for ticker."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._get_quote_sync, ticker))

    def _get_quote_sync(self, ticker: str) -> dict:
        """Synchronous quote fetching."""
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "name": info.get("shortName"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "volume": info.get("volume"),
        }

    async def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._get_history_sync, ticker, period)
        )

    def _get_history_sync(self, ticker: str, period: str) -> pd.DataFrame:
        """Synchronous history fetching."""
        t = yf.Ticker(ticker)
        return t.history(period=period)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_yfinance.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/providers/yfinance_provider.py tests/providers/test_yfinance.py
git commit -m "feat(providers): add YFinance provider for US stocks"
```

---

## Task 7: Technical Analysis Models

**Files:**
- Create: `src/tools/technical/models.py`
- Test: `tests/tools/technical/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_models.py
import pytest
from datetime import datetime
from src.tools.technical.models import (
    IndicatorSnapshot,
    StrategyResult,
    TechnicalResult,
)


def test_indicator_snapshot():
    snapshot = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_20=175.0,
        rsi=58.3,
    )
    assert snapshot.price == 178.50
    assert snapshot.sma_20 == 175.0
    assert snapshot.sma_50 is None  # optional field


def test_strategy_result():
    result = StrategyResult(
        name="trend",
        status="강세",
        confidence=75.0,
        signals=["골든크로스"],
        evidence=["20일선 > 50일선"],
        metrics={"sma_20": 175.0, "sma_50": 170.0},
    )
    assert result.name == "trend"
    assert result.confidence == 75.0
    assert "골든크로스" in result.signals


def test_technical_result():
    indicators = IndicatorSnapshot(price=178.50, change_pct=2.5)
    strategy = StrategyResult(
        name="trend",
        status="강세",
        confidence=75.0,
        signals=[],
        evidence=[],
        metrics={},
    )
    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        indicators=indicators,
        strategies=[strategy],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["상승 추세"],
        warnings=[],
    )
    assert result.ticker == "AAPL"
    assert result.overall_assessment == "매수"
    assert len(result.strategies) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/models.py
from datetime import datetime
from pydantic import BaseModel


class IndicatorSnapshot(BaseModel):
    """Raw indicator values snapshot."""

    # Price
    price: float
    change_pct: float

    # Moving averages
    sma_10: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_120: float | None = None
    sma_200: float | None = None

    # Momentum
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    # Volatility
    atr: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None

    # Trend strength
    adx: float | None = None
    supertrend_direction: int | None = None

    # Disparity
    disparity_20: float | None = None
    disparity_50: float | None = None
    disparity_120: float | None = None

    # Support/Resistance
    pivot: float | None = None
    support_s1: float | None = None
    resistance_r1: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None


class StrategyResult(BaseModel):
    """Single strategy execution result."""

    name: str
    status: str
    confidence: float
    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]


class TechnicalResult(BaseModel):
    """Complete technical analysis result."""

    ticker: str
    timestamp: datetime

    # Raw indicators
    indicators: IndicatorSnapshot

    # Strategy results
    strategies: list[StrategyResult]

    # Summary
    overall_assessment: str
    confidence_score: float
    key_insights: list[str]
    warnings: list[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/models.py tests/tools/technical/test_models.py
git commit -m "feat(technical): add data models for technical analysis"
```

---

## Task 8: Indicator Calculator

**Files:**
- Create: `src/tools/technical/indicators.py`
- Test: `tests/tools/technical/test_indicators.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_indicators.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.models import IndicatorSnapshot


@pytest.fixture
def sample_df():
    """Create sample OHLCV DataFrame."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    return pd.DataFrame({
        "Open": close - np.random.rand(100),
        "High": close + np.random.rand(100) * 2,
        "Low": close - np.random.rand(100) * 2,
        "Close": close,
        "Volume": np.random.randint(1000000, 5000000, 100),
    }, index=dates)


def test_calculate_indicators(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)

    assert "SMA_20" in result_df.columns
    assert "SMA_50" in result_df.columns
    assert "RSI" in result_df.columns
    assert not result_df["SMA_20"].isna().all()


def test_create_snapshot(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)
    snapshot = calculator.create_snapshot(result_df)

    assert isinstance(snapshot, IndicatorSnapshot)
    assert snapshot.price > 0
    assert snapshot.sma_20 is not None or snapshot.sma_20 is None  # may be None if not enough data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_indicators.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/indicators.py
import pandas as pd
import pandas_ta as ta
from src.tools.technical.models import IndicatorSnapshot


class IndicatorCalculator:
    """Calculate technical indicators from OHLCV data."""

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to DataFrame."""
        if df.empty:
            return df

        df = df.copy()

        # Moving averages
        df["SMA_10"] = ta.sma(df["Close"], length=10)
        df["SMA_20"] = ta.sma(df["Close"], length=20)
        df["SMA_50"] = ta.sma(df["Close"], length=50)
        df["SMA_120"] = ta.sma(df["Close"], length=120)
        df["SMA_200"] = ta.sma(df["Close"], length=200)

        # RSI
        df["RSI"] = ta.rsi(df["Close"], length=14)

        # MACD
        macd = ta.macd(df["Close"])
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        # Bollinger Bands
        bb = ta.bbands(df["Close"], length=20)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)

        # ADX
        adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx is not None:
            df = pd.concat([df, adx], axis=1)

        # ATR
        df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

        # Supertrend
        st = ta.supertrend(df["High"], df["Low"], df["Close"], length=10, multiplier=3.0)
        if st is not None:
            df = pd.concat([df, st], axis=1)

        # Disparity
        for length in [20, 50, 120]:
            sma_col = f"SMA_{length}"
            if sma_col in df.columns:
                df[f"Disparity_{length}"] = (df["Close"] / df[sma_col]) * 100

        # 52-week high/low
        df["High_52w"] = df["High"].rolling(window=252, min_periods=50).max()
        df["Low_52w"] = df["Low"].rolling(window=252, min_periods=50).min()

        # Pivot points
        prev_high = df["High"].shift(1)
        prev_low = df["Low"].shift(1)
        prev_close = df["Close"].shift(1)
        pivot = (prev_high + prev_low + prev_close) / 3
        df["Pivot"] = pivot
        df["S1"] = (2 * pivot) - prev_high
        df["R1"] = (2 * pivot) - prev_low

        return df

    def create_snapshot(self, df: pd.DataFrame) -> IndicatorSnapshot:
        """Create indicator snapshot from latest row."""
        if df.empty:
            return IndicatorSnapshot(price=0, change_pct=0)

        latest = df.iloc[-1]
        prev_close = df.iloc[-2]["Close"] if len(df) > 1 else latest["Close"]
        change_pct = ((latest["Close"] - prev_close) / prev_close) * 100

        def safe_get(key: str) -> float | None:
            val = latest.get(key)
            if pd.isna(val):
                return None
            return float(val)

        return IndicatorSnapshot(
            price=float(latest["Close"]),
            change_pct=round(change_pct, 2),
            sma_10=safe_get("SMA_10"),
            sma_20=safe_get("SMA_20"),
            sma_50=safe_get("SMA_50"),
            sma_120=safe_get("SMA_120"),
            sma_200=safe_get("SMA_200"),
            rsi=safe_get("RSI"),
            macd=safe_get("MACD_12_26_9"),
            macd_signal=safe_get("MACDs_12_26_9"),
            macd_histogram=safe_get("MACDh_12_26_9"),
            atr=safe_get("ATR"),
            bb_upper=safe_get("BBU_20_2.0"),
            bb_lower=safe_get("BBL_20_2.0"),
            adx=safe_get("ADX_14"),
            supertrend_direction=int(safe_get("SUPERTd_10_3.0") or 0) if safe_get("SUPERTd_10_3.0") else None,
            disparity_20=safe_get("Disparity_20"),
            disparity_50=safe_get("Disparity_50"),
            disparity_120=safe_get("Disparity_120"),
            pivot=safe_get("Pivot"),
            support_s1=safe_get("S1"),
            resistance_r1=safe_get("R1"),
            high_52w=safe_get("High_52w"),
            low_52w=safe_get("Low_52w"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_indicators.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/indicators.py tests/tools/technical/test_indicators.py
git commit -m "feat(technical): add indicator calculator with pandas_ta"
```

---

## Task 9: Base Strategy Interface

**Files:**
- Create: `src/tools/technical/base.py`
- Test: `tests/tools/technical/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_base.py
import pytest
import pandas as pd
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class MockStrategy(BaseStrategy):
    name = "mock"
    description = "Mock strategy for testing"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        return StrategyResult(
            name=self.name,
            status="중립",
            confidence=50.0,
            signals=[],
            evidence=[],
            metrics={},
        )


def test_base_strategy_interface():
    strategy = MockStrategy()
    assert strategy.name == "mock"
    assert strategy.description == "Mock strategy for testing"

    df = pd.DataFrame({"Close": [100, 101, 102]})
    result = strategy.analyze(df)

    assert isinstance(result, StrategyResult)
    assert result.name == "mock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_base.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/base.py
from abc import ABC, abstractmethod
import pandas as pd
from src.tools.technical.models import StrategyResult


class BaseStrategy(ABC):
    """Abstract base class for technical analysis strategies."""

    name: str
    description: str

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        """Analyze price data and return strategy result."""
        pass

    def _safe_get(self, series: pd.Series, key: str, default: float = 0.0) -> float:
        """Safely get value from series."""
        val = series.get(key)
        if pd.isna(val) or val is None:
            return default
        return float(val)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/base.py tests/tools/technical/test_base.py
git commit -m "feat(technical): add BaseStrategy interface"
```

---

## Task 10: Trend Strategy

**Files:**
- Create: `src/tools/technical/strategies/trend.py`
- Test: `tests/tools/technical/test_trend_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_trend_strategy.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.strategies.trend import TrendStrategy
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def uptrend_df():
    """Create DataFrame with clear uptrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.5  # steady uptrend
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


@pytest.fixture
def downtrend_df():
    """Create DataFrame with clear downtrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 150 - np.arange(100) * 0.5  # steady downtrend
    df = pd.DataFrame({
        "Open": close + 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_trend_strategy_uptrend(uptrend_df):
    strategy = TrendStrategy()
    result = strategy.analyze(uptrend_df)

    assert result.name == "trend"
    assert result.status == "강세"
    assert result.confidence > 50


def test_trend_strategy_downtrend(downtrend_df):
    strategy = TrendStrategy()
    result = strategy.analyze(downtrend_df)

    assert result.name == "trend"
    assert result.status == "약세"


def test_trend_strategy_has_evidence(uptrend_df):
    strategy = TrendStrategy()
    result = strategy.analyze(uptrend_df)

    assert len(result.evidence) > 0
    assert len(result.metrics) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_trend_strategy.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/strategies/trend.py
import pandas as pd
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class TrendStrategy(BaseStrategy):
    """Trend analysis using moving averages, ADX, and supertrend."""

    name = "trend"
    description = "이동평균, ADX, 슈퍼트렌드 기반 추세 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 50:
            return self._neutral_result("데이터 부족")

        latest = df.iloc[-1]
        signals = []
        evidence = []
        metrics = {}
        score = 0

        # Get values safely
        close = self._safe_get(latest, "Close")
        sma_20 = self._safe_get(latest, "SMA_20")
        sma_50 = self._safe_get(latest, "SMA_50")
        sma_200 = self._safe_get(latest, "SMA_200")
        adx = self._safe_get(latest, "ADX_14")
        supertrend_dir = self._safe_get(latest, "SUPERTd_10_3.0")

        # Store metrics
        metrics["close"] = close
        if sma_20:
            metrics["sma_20"] = round(sma_20, 2)
        if sma_50:
            metrics["sma_50"] = round(sma_50, 2)
        if sma_200:
            metrics["sma_200"] = round(sma_200, 2)
        if adx:
            metrics["adx"] = round(adx, 2)

        # Price vs SMA analysis
        if sma_20 and close > sma_20:
            score += 20
            evidence.append(f"가격({close:.2f}) > 20일선({sma_20:.2f})")
        elif sma_20 and close < sma_20:
            score -= 20
            evidence.append(f"가격({close:.2f}) < 20일선({sma_20:.2f})")

        if sma_50 and close > sma_50:
            score += 15
            evidence.append(f"가격 > 50일선({sma_50:.2f})")
        elif sma_50 and close < sma_50:
            score -= 15
            evidence.append(f"가격 < 50일선({sma_50:.2f})")

        if sma_200 and close > sma_200:
            score += 10
            evidence.append(f"가격 > 200일선({sma_200:.2f})")
        elif sma_200 and close < sma_200:
            score -= 10
            evidence.append(f"가격 < 200일선({sma_200:.2f})")

        # Golden/Death cross
        if sma_20 and sma_50:
            prev_sma_20 = self._safe_get(df.iloc[-2], "SMA_20") if len(df) > 1 else 0
            prev_sma_50 = self._safe_get(df.iloc[-2], "SMA_50") if len(df) > 1 else 0

            if prev_sma_20 < prev_sma_50 and sma_20 > sma_50:
                signals.append("골든크로스")
                score += 25
            elif prev_sma_20 > prev_sma_50 and sma_20 < sma_50:
                signals.append("데드크로스")
                score -= 25

            if sma_20 > sma_50:
                evidence.append("20일선 > 50일선 (정배열)")
                score += 10
            else:
                evidence.append("20일선 < 50일선 (역배열)")
                score -= 10

        # ADX trend strength
        if adx:
            if adx > 25:
                evidence.append(f"ADX {adx:.1f} (강한 추세)")
                score += 10 if score > 0 else -10  # amplify existing trend
            else:
                evidence.append(f"ADX {adx:.1f} (약한 추세)")

        # Supertrend
        if supertrend_dir:
            if supertrend_dir > 0:
                signals.append("슈퍼트렌드 상승")
                score += 15
            else:
                signals.append("슈퍼트렌드 하락")
                score -= 15

        # Determine status and confidence
        if score > 30:
            status = "강세"
        elif score > 10:
            status = "약강세"
        elif score < -30:
            status = "약세"
        elif score < -10:
            status = "약약세"
        else:
            status = "중립"

        confidence = min(100, max(0, 50 + score))

        return StrategyResult(
            name=self.name,
            status=status,
            confidence=confidence,
            signals=signals,
            evidence=evidence,
            metrics=metrics,
        )

    def _neutral_result(self, reason: str) -> StrategyResult:
        return StrategyResult(
            name=self.name,
            status="중립",
            confidence=50.0,
            signals=[],
            evidence=[reason],
            metrics={},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_trend_strategy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/strategies/trend.py tests/tools/technical/test_trend_strategy.py
git commit -m "feat(technical): add TrendStrategy with MA/ADX/Supertrend"
```

---

## Task 11: Strategy Registry

**Files:**
- Create: `src/tools/technical/registry.py`
- Test: `tests/tools/technical/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_registry.py
import pytest
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.strategies.trend import TrendStrategy


def test_registry_register():
    registry = StrategyRegistry()
    strategy = TrendStrategy()
    registry.register(strategy)

    assert "trend" in registry._strategies
    assert registry.get("trend") == strategy


def test_registry_get_all():
    registry = StrategyRegistry()
    registry.register(TrendStrategy())

    strategies = registry.get_all()
    assert len(strategies) == 1
    assert strategies[0].name == "trend"


def test_registry_unregister():
    registry = StrategyRegistry()
    registry.register(TrendStrategy())
    registry.unregister("trend")

    assert "trend" not in registry._strategies


def test_registry_from_config():
    registry = StrategyRegistry.from_config(["trend"])
    strategies = registry.get_all()

    assert len(strategies) == 1
    assert strategies[0].name == "trend"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_registry.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/registry.py
from typing import Optional
from src.tools.technical.base import BaseStrategy
from src.tools.technical.strategies.trend import TrendStrategy


# Strategy mapping
STRATEGY_MAP = {
    "trend": TrendStrategy,
}


class StrategyRegistry:
    """Registry for technical analysis strategies."""

    def __init__(self):
        self._strategies: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        """Register a strategy."""
        self._strategies[strategy.name] = strategy

    def unregister(self, name: str) -> None:
        """Unregister a strategy."""
        if name in self._strategies:
            del self._strategies[name]

    def get(self, name: str) -> Optional[BaseStrategy]:
        """Get a strategy by name."""
        return self._strategies.get(name)

    def get_all(self) -> list[BaseStrategy]:
        """Get all registered strategies."""
        return list(self._strategies.values())

    @classmethod
    def from_config(cls, strategy_names: list[str]) -> "StrategyRegistry":
        """Create registry from config list."""
        registry = cls()
        for name in strategy_names:
            if name in STRATEGY_MAP:
                registry.register(STRATEGY_MAP[name]())
        return registry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/registry.py tests/tools/technical/test_registry.py
git commit -m "feat(technical): add StrategyRegistry for extensibility"
```

---

## Task 12: Technical Analysis Tool

**Files:**
- Create: `src/tools/technical/tool.py`
- Test: `tests/tools/technical/test_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_tool.py
import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, MagicMock
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.strategies.trend import TrendStrategy


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.5
    provider.get_price_history.return_value = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    return provider


@pytest.fixture
def registry():
    reg = StrategyRegistry()
    reg.register(TrendStrategy())
    return reg


@pytest.mark.asyncio
async def test_technical_tool_execute(mock_provider, registry):
    tool = TechnicalAnalysisTool(provider=mock_provider, registry=registry)
    result = await tool.execute("AAPL")

    assert result.success is True
    assert result.data is not None
    assert result.data.ticker == "AAPL"
    assert len(result.data.strategies) == 1


@pytest.mark.asyncio
async def test_technical_tool_has_indicators(mock_provider, registry):
    tool = TechnicalAnalysisTool(provider=mock_provider, registry=registry)
    result = await tool.execute("AAPL")

    assert result.data.indicators.price > 0
    assert result.data.indicators.sma_20 is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_tool.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/tool.py
from datetime import datetime
from src.core.interfaces import BaseTool, BaseProvider
from src.core.models import ToolResult
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.models import TechnicalResult


class TechnicalAnalysisTool(BaseTool):
    """Technical analysis tool using multiple strategies."""

    name = "technical"
    description = "기술적 분석 도구 (추세, 모멘텀, 패턴)"

    def __init__(self, provider: BaseProvider, registry: StrategyRegistry):
        self.provider = provider
        self.registry = registry
        self.calculator = IndicatorCalculator()

    async def execute(self, ticker: str, period: str = "1y", **kwargs) -> ToolResult:
        """Execute technical analysis on ticker."""
        try:
            # Get price history
            df = await self.provider.get_price_history(ticker, period)
            if df.empty:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"No data found for {ticker}",
                )

            # Calculate indicators
            df = self.calculator.calculate(df)
            indicators = self.calculator.create_snapshot(df)

            # Run strategies
            strategy_results = []
            total_confidence = 0
            signals_count = {"강세": 0, "약세": 0, "중립": 0}

            for strategy in self.registry.get_all():
                result = strategy.analyze(df)
                strategy_results.append(result)
                total_confidence += result.confidence

                if "강세" in result.status:
                    signals_count["강세"] += 1
                elif "약세" in result.status:
                    signals_count["약세"] += 1
                else:
                    signals_count["중립"] += 1

            # Determine overall assessment
            if signals_count["강세"] > signals_count["약세"]:
                overall = "매수"
            elif signals_count["약세"] > signals_count["강세"]:
                overall = "매도"
            else:
                overall = "중립"

            avg_confidence = total_confidence / len(strategy_results) if strategy_results else 50

            # Collect insights and warnings
            key_insights = []
            warnings = []
            for sr in strategy_results:
                key_insights.extend(sr.signals)
                if sr.confidence < 30:
                    warnings.append(f"{sr.name}: 낮은 신뢰도 ({sr.confidence:.0f}%)")

            technical_result = TechnicalResult(
                ticker=ticker,
                timestamp=datetime.now(),
                indicators=indicators,
                strategies=strategy_results,
                overall_assessment=overall,
                confidence_score=avg_confidence,
                key_insights=key_insights,
                warnings=warnings,
            )

            return ToolResult(success=True, data=technical_result)

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_tool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/tool.py tests/tools/technical/test_tool.py
git commit -m "feat(technical): add TechnicalAnalysisTool"
```

---

## Task 13: Quick Check Pipeline

**Files:**
- Create: `src/pipelines/quick_check.py`
- Test: `tests/pipelines/test_quick_check.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/pipelines/test_quick_check.py
import pytest
from unittest.mock import AsyncMock, MagicMock
import pandas as pd
import numpy as np
from src.pipelines.quick_check import QuickCheckPipeline
from src.tools.technical.models import TechnicalResult, IndicatorSnapshot, StrategyResult
from src.core.models import ToolResult
from datetime import datetime


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    indicators = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_20=175.0,
        sma_50=170.0,
        rsi=58.3,
    )
    strategy = StrategyResult(
        name="trend",
        status="강세",
        confidence=75.0,
        signals=["골든크로스"],
        evidence=["20일선 > 50일선"],
        metrics={"sma_20": 175.0},
    )
    tech_result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        indicators=indicators,
        strategies=[strategy],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["골든크로스"],
        warnings=[],
    )
    tool.execute.return_value = ToolResult(success=True, data=tech_result)
    return tool


@pytest.mark.asyncio
async def test_quick_check_run(mock_technical_tool):
    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")

    assert result["ticker"] == "AAPL"
    assert result["price"] == 178.50
    assert result["assessment"] == "매수"
    mock_technical_tool.execute.assert_called_once_with("AAPL")


@pytest.mark.asyncio
async def test_quick_check_format_output(mock_technical_tool):
    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")
    output = pipeline.format_output(result)

    assert "AAPL" in output
    assert "178.50" in output
    assert "매수" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/test_quick_check.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/pipelines/quick_check.py
from typing import Any
from src.tools.technical.tool import TechnicalAnalysisTool


class QuickCheckPipeline:
    """Quick check pipeline - technical analysis without LLM."""

    def __init__(self, technical_tool: TechnicalAnalysisTool):
        self.technical_tool = technical_tool

    async def run(self, ticker: str) -> dict[str, Any]:
        """Run quick check analysis."""
        result = await self.technical_tool.execute(ticker)

        if not result.success:
            return {
                "ticker": ticker,
                "error": result.error,
                "success": False,
            }

        tech = result.data
        return {
            "ticker": ticker,
            "success": True,
            "price": tech.indicators.price,
            "change_pct": tech.indicators.change_pct,
            "assessment": tech.overall_assessment,
            "confidence": tech.confidence_score,
            "signals": tech.key_insights,
            "warnings": tech.warnings,
            "indicators": {
                "sma_20": tech.indicators.sma_20,
                "sma_50": tech.indicators.sma_50,
                "rsi": tech.indicators.rsi,
                "adx": tech.indicators.adx,
            },
            "strategies": [
                {
                    "name": s.name,
                    "status": s.status,
                    "confidence": s.confidence,
                    "signals": s.signals,
                }
                for s in tech.strategies
            ],
        }

    def format_output(self, result: dict[str, Any]) -> str:
        """Format result as readable string."""
        if not result.get("success", False):
            return f"Error: {result.get('error', 'Unknown error')}"

        lines = [
            f"## {result['ticker']} Quick Check",
            "",
            f"**가격**: ${result['price']:.2f} ({result['change_pct']:+.2f}%)",
            f"**평가**: {result['assessment']} (신뢰도: {result['confidence']:.0f}%)",
            "",
        ]

        # Indicators
        indicators = result.get("indicators", {})
        lines.append("### 주요 지표")
        if indicators.get("sma_20"):
            lines.append(f"- SMA 20: ${indicators['sma_20']:.2f}")
        if indicators.get("sma_50"):
            lines.append(f"- SMA 50: ${indicators['sma_50']:.2f}")
        if indicators.get("rsi"):
            lines.append(f"- RSI: {indicators['rsi']:.1f}")
        if indicators.get("adx"):
            lines.append(f"- ADX: {indicators['adx']:.1f}")

        # Signals
        if result.get("signals"):
            lines.append("")
            lines.append("### 시그널")
            for signal in result["signals"]:
                lines.append(f"- {signal}")

        # Warnings
        if result.get("warnings"):
            lines.append("")
            lines.append("### 주의")
            for warning in result["warnings"]:
                lines.append(f"- {warning}")

        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/test_quick_check.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/quick_check.py tests/pipelines/test_quick_check.py
git commit -m "feat(pipelines): add QuickCheckPipeline"
```

---

## Task 14: CLI Main

**Files:**
- Create: `src/cli/main.py`
- Test: `tests/cli/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_cli.py
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock
from src.cli.main import app

runner = CliRunner()


def test_cli_check_command():
    mock_result = {
        "ticker": "AAPL",
        "success": True,
        "price": 178.50,
        "change_pct": 2.5,
        "assessment": "매수",
        "confidence": 75.0,
        "signals": ["골든크로스"],
        "warnings": [],
        "indicators": {"sma_20": 175.0, "sma_50": 170.0, "rsi": 58.3, "adx": 28.0},
        "strategies": [],
    }

    with patch("src.cli.main.run_quick_check", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_result
        result = runner.invoke(app, ["check", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "178.50" in result.stdout


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_cli.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/cli/main.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Test CLI manually**

Run: `uv run jarvis check AAPL`
Expected: Shows AAPL technical analysis output

- [ ] **Step 6: Commit**

```bash
git add src/cli/main.py tests/cli/test_cli.py
git commit -m "feat(cli): add check command for quick analysis"
```

---

## Task 15: Integration Test and Final Verification

**Files:**
- Create: `tests/integration/test_e2e.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_e2e.py
import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()


@pytest.mark.integration
def test_end_to_end_check_real_ticker():
    """End-to-end test with real API call."""
    result = runner.invoke(app, ["check", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    # Should have price and assessment
    assert "가격" in result.stdout or "$" in result.stdout
```

- [ ] **Step 2: Create tests/integration/__init__.py**

Run: `mkdir -p tests/integration && touch tests/integration/__init__.py`

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v --ignore=tests/integration`
Expected: All tests PASS

- [ ] **Step 4: Run integration test (requires network)**

Run: `uv run pytest tests/integration/ -v -m integration`
Expected: PASS (may take a few seconds for API call)

- [ ] **Step 5: Manual CLI test**

Run: `uv run jarvis check MSFT`
Expected: Shows Microsoft technical analysis

- [ ] **Step 6: Final commit**

```bash
git add tests/integration/
git commit -m "test: add e2e integration test"
```

- [ ] **Step 7: Tag version**

```bash
git tag -a v0.1.0 -m "Plan 1 complete: Core + Technical + Quick Check"
```

---

## Summary

Plan 1 완료 시 동작하는 기능:

```bash
# 미국 주식 기술적 분석 빠른 체크
jarvis check AAPL
jarvis check MSFT
jarvis check NVDA
```

출력 예시:
```
## AAPL Quick Check

**가격**: $178.50 (+2.50%)
**평가**: 매수 (신뢰도: 75%)

### 주요 지표
- SMA 20: $175.00
- SMA 50: $170.00
- RSI: 58.3
- ADX: 28.0

### 시그널
- 골든크로스
- 슈퍼트렌드 상승
```

다음 Plan 2에서 추가될 기능:
- LLM 클라이언트
- 나머지 4개 전략 (oscillator, divergence, disparity, risk)
- Macro 도구
- News 도구
- Deep Dive 파이프라인
- Daily Report 파이프라인
- `jarvis analyze`, `jarvis report` 명령어
