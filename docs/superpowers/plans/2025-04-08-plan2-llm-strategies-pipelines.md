# Plan 2: LLM + Strategies + Macro + News + Pipelines

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `jarvis analyze AAPL`, `jarvis report` 명령어로 LLM 기반 심층 분석 및 일일 리포트 기능 구현

**Architecture:** LLM 멀티 프로바이더 클라이언트 추가, 4개 기술적 분석 전략 구현, Macro/News 도구 추가, Deep Dive/Daily Report 파이프라인 구현

**Tech Stack:** OpenAI/Claude API, httpx (API), pandas-ta (지표), yfinance (데이터)

---

## File Structure

```
invest-jarvis/
├── src/
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py              # LLM 클라이언트
│   │   └── models.py              # Pydantic I/O 모델
│   ├── tools/
│   │   ├── macro.py               # 매크로 지표 도구
│   │   ├── news.py                # 뉴스 도구
│   │   └── technical/strategies/
│   │       ├── oscillator.py      # 모멘텀 전략
│   │       ├── divergence.py      # 다이버전스 전략
│   │       ├── disparity.py       # 이격도 전략
│   │       └── risk.py            # 리스크 전략
│   └── pipelines/
│       ├── deep_dive.py           # 심층 분석 파이프라인
│       └── daily_report.py        # 일일 리포트 파이프라인
└── tests/
    ├── llm/
    ├── tools/
    └── pipelines/
```

---

## Task 1: LLM Models

**Files:**
- Create: `src/llm/__init__.py`
- Create: `src/llm/models.py`
- Test: `tests/llm/test_models.py`

- [ ] **Step 1: Create tests/llm/__init__.py**

Run: `touch tests/llm/__init__.py`

- [ ] **Step 2: Write the failing test**

```python
# tests/llm/test_models.py
import pytest
from src.llm.models import (
    LLMRequest,
    LLMResponse,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


def test_llm_request():
    req = LLMRequest(
        model="gpt-4",
        messages=[{"role": "user", "content": "test"}],
        temperature=0,
        seed=42,
    )
    assert req.model == "gpt-4"
    assert req.temperature == 0
    assert req.seed == 42


def test_llm_response():
    resp = LLMResponse(
        content="response text",
        model="gpt-4",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
    )
    assert resp.content == "response text"
    assert resp.usage["prompt_tokens"] == 10


def test_news_analysis_input():
    input_data = NewsAnalysisInput(
        ticker="AAPL",
        company_name="Apple Inc.",
        news=[
            {"title": "Apple releases new product", "published": "2024-01-01", "summary": "..."}
        ],
    )
    assert input_data.ticker == "AAPL"
    assert len(input_data.news) == 1


def test_news_analysis_output():
    output = NewsAnalysisOutput(
        sentiment="긍정",
        confidence=0.85,
        key_themes=["신제품 출시"],
        summary="애플이 새로운 제품을 출시했습니다.",
        impact_assessment="단기 긍정적 영향 예상",
    )
    assert output.sentiment == "긍정"
    assert output.confidence == 0.85


def test_technical_summary_input():
    input_data = TechnicalSummaryInput(
        ticker="AAPL",
        price=178.50,
        change_pct=2.5,
        strategies=[
            {
                "name": "trend",
                "status": "강세",
                "confidence": 75.0,
                "signals": ["골든크로스"],
                "evidence": ["20일선 > 50일선"],
                "metrics": {"sma_20": 175.0},
            }
        ],
        indicators={
            "sma_20": 175.0,
            "sma_50": 170.0,
            "rsi": 58.3,
        },
    )
    assert input_data.ticker == "AAPL"
    assert len(input_data.strategies) == 1


def test_technical_summary_output():
    output = TechnicalSummaryOutput(
        summary="AAPL은 강한 상승 추세입니다.",
        key_insights=["골든크로스 발생", "RSI 중립권"],
        recommendation="매수",
        confidence=0.75,
        rationale="이동평균선 정배열과 모멘텀 지표 긍정적",
    )
    assert output.summary == "AAPL은 강한 상승 추세입니다."
    assert output.recommendation == "매수"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: Write implementation**

```python
# src/llm/models.py
from typing import Any
from pydantic import BaseModel


class LLMRequest(BaseModel):
    """LLM request with reproducible parameters."""
    model: str
    messages: list[dict[str, str]]
    temperature: float = 0
    seed: int = 42
    max_tokens: int | None = None


class LLMResponse(BaseModel):
    """LLM response."""
    content: str
    model: str
    usage: dict[str, int]


# News Analysis I/O
class NewsAnalysisInput(BaseModel):
    """Input for news analysis."""
    ticker: str
    company_name: str
    news: list[dict[str, Any]]  # [{title, published, summary, url?}]


class NewsAnalysisOutput(BaseModel):
    """Output from news analysis."""
    sentiment: str  # "긍정", "부정", "중립"
    confidence: float  # 0-1
    key_themes: list[str]
    summary: str
    impact_assessment: str


# Technical Summary I/O
class TechnicalSummaryInput(BaseModel):
    """Input for technical summary."""
    ticker: str
    price: float
    change_pct: float
    strategies: list[dict[str, Any]]
    indicators: dict[str, float]


class TechnicalSummaryOutput(BaseModel):
    """Output from technical summary."""
    summary: str
    key_insights: list[str]
    recommendation: str  # "매수", "매도", "중립"
    confidence: float  # 0-1
    rationale: str
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/llm/ tests/llm/
git commit -m "feat(llm): add Pydantic models for LLM I/O"
```

---

## Task 2: LLM Client

**Files:**
- Create: `src/llm/client.py`
- Test: `tests/llm/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_client.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.llm.client import LLMClient
from src.llm.models import NewsAnalysisInput, TechnicalSummaryInput


@pytest.fixture
def mock_openai_response():
    return {
        "choices": [
            {
                "message": {
                    "content": '{"sentiment": "긍정", "confidence": 0.85, "key_themes": ["신제품"], "summary": "긍정적", "impact_assessment": "좋음"}'
                }
            }
        ],
        "model": "gpt-4",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


@pytest.mark.asyncio
async def test_llm_client_analyze_news(mock_openai_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_openai_response
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

        client = LLMClient(provider="openai", api_key="test-key")
        input_data = NewsAnalysisInput(
            ticker="AAPL",
            company_name="Apple Inc.",
            news=[{"title": "Test", "published": "2024-01-01", "summary": "Test"}],
        )
        result = await client.analyze_news(input_data)

        assert result.sentiment == "긍정"
        assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_llm_client_generate_technical_summary(mock_openai_response):
    mock_openai_response["choices"][0]["message"]["content"] = '{"summary": "강세", "key_insights": ["골든크로스"], "recommendation": "매수", "confidence": 0.75, "rationale": "좋음"}'

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_openai_response
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

        client = LLMClient(provider="openai", api_key="test-key")
        input_data = TechnicalSummaryInput(
            ticker="AAPL",
            price=178.50,
            change_pct=2.5,
            strategies=[],
            indicators={},
        )
        result = await client.generate_technical_summary(input_data)

        assert result.summary == "강세"
        assert result.recommendation == "매수"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_client.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/llm/client.py
import json
import httpx
from typing import Literal
from src.llm.models import (
    LLMRequest,
    LLMResponse,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


class LLMClient:
    """Multi-provider LLM client with purpose-specific methods."""

    def __init__(
        self,
        provider: Literal["openai", "anthropic"] = "openai",
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.provider = provider
        self.api_key = api_key
        self.model = model or self._get_default_model()

    def _get_default_model(self) -> str:
        """Get default model for provider."""
        if self.provider == "openai":
            return "gpt-4-turbo-preview"
        elif self.provider == "anthropic":
            return "claude-3-5-sonnet-20241022"
        return "gpt-4-turbo-preview"

    async def _call_api(self, request: LLMRequest) -> LLMResponse:
        """Call LLM API."""
        if self.provider == "openai":
            return await self._call_openai(request)
        elif self.provider == "anthropic":
            return await self._call_anthropic(request)
        raise ValueError(f"Unsupported provider: {self.provider}")

    async def _call_openai(self, request: LLMRequest) -> LLMResponse:
        """Call OpenAI API."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "seed": request.seed,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage=data["usage"],
        )

    async def _call_anthropic(self, request: LLMRequest) -> LLMResponse:
        """Call Anthropic API."""
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # Convert OpenAI format to Anthropic format
        system_msg = None
        messages = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                messages.append(msg)

        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data["content"][0]["text"],
            model=data["model"],
            usage=data["usage"],
        )

    async def analyze_news(self, input_data: NewsAnalysisInput) -> NewsAnalysisOutput:
        """Analyze news sentiment and impact."""
        news_text = "\n".join(
            [f"- {n['title']}: {n.get('summary', '')}" for n in input_data.news]
        )

        prompt = f"""Analyze the following news for {input_data.ticker} ({input_data.company_name}):

{news_text}

Provide analysis in JSON format:
{{
  "sentiment": "긍정|부정|중립",
  "confidence": 0.0-1.0,
  "key_themes": ["theme1", "theme2"],
  "summary": "brief summary in Korean",
  "impact_assessment": "impact analysis in Korean"
}}"""

        request = LLMRequest(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a financial news analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            seed=42,
        )

        response = await self._call_api(request)
        data = json.loads(response.content)
        return NewsAnalysisOutput(**data)

    async def generate_technical_summary(
        self, input_data: TechnicalSummaryInput
    ) -> TechnicalSummaryOutput:
        """Generate technical analysis summary."""
        strategies_text = "\n".join(
            [
                f"- {s['name']}: {s['status']} (신뢰도: {s['confidence']:.0f}%)\n  시그널: {', '.join(s['signals'])}\n  근거: {', '.join(s['evidence'])}"
                for s in input_data.strategies
            ]
        )

        indicators_text = "\n".join(
            [f"- {k}: {v:.2f}" for k, v in input_data.indicators.items()]
        )

        prompt = f"""Analyze the following technical data for {input_data.ticker}:

**Current Price**: ${input_data.price:.2f} ({input_data.change_pct:+.2f}%)

**Strategy Results**:
{strategies_text}

**Key Indicators**:
{indicators_text}

Provide summary in JSON format:
{{
  "summary": "brief overall summary in Korean",
  "key_insights": ["insight1", "insight2"],
  "recommendation": "매수|매도|중립",
  "confidence": 0.0-1.0,
  "rationale": "reasoning in Korean"
}}"""

        request = LLMRequest(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a technical analysis expert.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            seed=42,
        )

        response = await self._call_api(request)
        data = json.loads(response.content)
        return TechnicalSummaryOutput(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/llm/client.py tests/llm/test_client.py
git commit -m "feat(llm): add multi-provider LLM client"
```

---

## Task 3: Oscillator Strategy

**Files:**
- Create: `src/tools/technical/strategies/oscillator.py`
- Test: `tests/tools/technical/test_oscillator_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_oscillator_strategy.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.strategies.oscillator import OscillatorStrategy
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def overbought_df():
    """Create DataFrame with overbought conditions."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.8  # strong uptrend
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_oscillator_strategy_overbought(overbought_df):
    strategy = OscillatorStrategy()
    result = strategy.analyze(overbought_df)

    assert result.name == "oscillator"
    assert result.status == "과매수"
    assert len(result.evidence) > 0
    assert len(result.metrics) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_oscillator_strategy.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/strategies/oscillator.py
import pandas as pd
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class OscillatorStrategy(BaseStrategy):
    """Oscillator analysis using RSI, Stochastic, CCI."""

    name = "oscillator"
    description = "RSI, 스토캐스틱, CCI 기반 모멘텀 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 20:
            return self._neutral_result("데이터 부족")

        latest = df.iloc[-1]
        signals = []
        evidence = []
        metrics = {}
        score = 0

        # RSI
        rsi = self._safe_get(latest, "RSI")
        if rsi:
            metrics["rsi"] = round(rsi, 2)
            if rsi > 70:
                signals.append("RSI 과매수")
                evidence.append(f"RSI {rsi:.1f} > 70")
                score -= 20
            elif rsi < 30:
                signals.append("RSI 과매도")
                evidence.append(f"RSI {rsi:.1f} < 30")
                score += 20
            elif 40 <= rsi <= 60:
                evidence.append(f"RSI {rsi:.1f} (중립권)")

        # Stochastic (if available)
        stoch_k = self._safe_get(latest, "STOCHk_14_3_3")
        stoch_d = self._safe_get(latest, "STOCHd_14_3_3")
        if stoch_k and stoch_d:
            metrics["stoch_k"] = round(stoch_k, 2)
            metrics["stoch_d"] = round(stoch_d, 2)

            if stoch_k > 80:
                signals.append("스토캐스틱 과매수")
                evidence.append(f"Stochastic K {stoch_k:.1f} > 80")
                score -= 15
            elif stoch_k < 20:
                signals.append("스토캐스틱 과매도")
                evidence.append(f"Stochastic K {stoch_k:.1f} < 20")
                score += 15

            # Golden/Death cross
            if len(df) > 1:
                prev_k = self._safe_get(df.iloc[-2], "STOCHk_14_3_3")
                prev_d = self._safe_get(df.iloc[-2], "STOCHd_14_3_3")
                if prev_k and prev_d:
                    if prev_k < prev_d and stoch_k > stoch_d and stoch_k < 50:
                        signals.append("스토캐스틱 골든크로스")
                        score += 15
                    elif prev_k > prev_d and stoch_k < stoch_d and stoch_k > 50:
                        signals.append("스토캐스틱 데드크로스")
                        score -= 15

        # CCI
        cci = self._safe_get(latest, "CCI_14_0.015")
        if cci:
            metrics["cci"] = round(cci, 2)
            if cci > 100:
                signals.append("CCI 과매수")
                evidence.append(f"CCI {cci:.1f} > 100")
                score -= 10
            elif cci < -100:
                signals.append("CCI 과매도")
                evidence.append(f"CCI {cci:.1f} < -100")
                score += 10

        # Determine status
        if score > 30:
            status = "과매도"
        elif score > 10:
            status = "약과매도"
        elif score < -30:
            status = "과매수"
        elif score < -10:
            status = "약과매수"
        else:
            status = "중립"

        confidence = min(100, max(0, 50 + abs(score)))

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

- [ ] **Step 4: Update IndicatorCalculator to add Stochastic and CCI**

```python
# In src/tools/technical/indicators.py, add to calculate() method:

        # Stochastic
        stoch = ta.stoch(df["High"], df["Low"], df["Close"], k=14, d=3, smooth_k=3)
        if stoch is not None:
            df = pd.concat([df, stoch], axis=1)

        # CCI
        df["CCI_14_0.015"] = ta.cci(df["High"], df["Low"], df["Close"], length=14)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_oscillator_strategy.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/technical/strategies/oscillator.py src/tools/technical/indicators.py tests/tools/technical/test_oscillator_strategy.py
git commit -m "feat(technical): add OscillatorStrategy with RSI/Stoch/CCI"
```

---

## Task 4: Divergence Strategy

**Files:**
- Create: `src/tools/technical/strategies/divergence.py`
- Test: `tests/tools/technical/test_divergence_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/technical/test_divergence_strategy.py
import pytest
import pandas as pd
import numpy as np
from src.tools.technical.strategies.divergence import DivergenceStrategy
from src.tools/technical.indicators import IndicatorCalculator


@pytest.fixture
def sample_df():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    df = pd.DataFrame({
        "Open": close - np.random.rand(100),
        "High": close + np.random.rand(100) * 2,
        "Low": close - np.random.rand(100) * 2,
        "Close": close,
        "Volume": np.random.randint(1000000, 5000000, 100),
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_divergence_strategy(sample_df):
    strategy = DivergenceStrategy()
    result = strategy.analyze(sample_df)

    assert result.name == "divergence"
    assert result.status in ["강세", "약세", "중립"]
    assert isinstance(result.confidence, float)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_divergence_strategy.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/technical/strategies/divergence.py
import pandas as pd
import numpy as np
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class DivergenceStrategy(BaseStrategy):
    """Divergence analysis between price and indicators."""

    name = "divergence"
    description = "가격과 지표 간 다이버전스 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 30:
            return self._neutral_result("데이터 부족")

        signals = []
        evidence = []
        metrics = {}
        score = 0

        # Check RSI divergence
        rsi_div = self._check_rsi_divergence(df)
        if rsi_div:
            score += rsi_div["score"]
            signals.append(rsi_div["signal"])
            evidence.append(rsi_div["evidence"])

        # Check MACD divergence
        macd_div = self._check_macd_divergence(df)
        if macd_div:
            score += macd_div["score"]
            signals.append(macd_div["signal"])
            evidence.append(macd_div["evidence"])

        # Determine status
        if score > 20:
            status = "강세"
        elif score < -20:
            status = "약세"
        else:
            status = "중립"

        confidence = min(100, max(0, 50 + abs(score) * 2))

        return StrategyResult(
            name=self.name,
            status=status,
            confidence=confidence,
            signals=signals,
            evidence=evidence,
            metrics=metrics,
        )

    def _check_rsi_divergence(self, df: pd.DataFrame) -> dict | None:
        """Check RSI divergence."""
        if "RSI" not in df.columns:
            return None

        recent = df.tail(20)
        price_peaks = self._find_peaks(recent["Close"].values)
        rsi_peaks = self._find_peaks(recent["RSI"].values)

        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            # Bullish divergence: price lower lows, RSI higher lows
            if (
                recent["Close"].iloc[price_peaks[-1]]
                < recent["Close"].iloc[price_peaks[-2]]
                and recent["RSI"].iloc[rsi_peaks[-1]]
                > recent["RSI"].iloc[rsi_peaks[-2]]
            ):
                return {
                    "signal": "RSI 강세 다이버전스",
                    "evidence": "가격 저점 하락, RSI 저점 상승",
                    "score": 25,
                }
            # Bearish divergence: price higher highs, RSI lower highs
            elif (
                recent["Close"].iloc[price_peaks[-1]]
                > recent["Close"].iloc[price_peaks[-2]]
                and recent["RSI"].iloc[rsi_peaks[-1]]
                < recent["RSI"].iloc[rsi_peaks[-2]]
            ):
                return {
                    "signal": "RSI 약세 다이버전스",
                    "evidence": "가격 고점 상승, RSI 고점 하락",
                    "score": -25,
                }

        return None

    def _check_macd_divergence(self, df: pd.DataFrame) -> dict | None:
        """Check MACD divergence."""
        if "MACD_12_26_9" not in df.columns:
            return None

        recent = df.tail(20)
        price_peaks = self._find_peaks(recent["Close"].values)
        macd_peaks = self._find_peaks(recent["MACD_12_26_9"].values)

        if len(price_peaks) >= 2 and len(macd_peaks) >= 2:
            # Bullish divergence
            if (
                recent["Close"].iloc[price_peaks[-1]]
                < recent["Close"].iloc[price_peaks[-2]]
                and recent["MACD_12_26_9"].iloc[macd_peaks[-1]]
                > recent["MACD_12_26_9"].iloc[macd_peaks[-2]]
            ):
                return {
                    "signal": "MACD 강세 다이버전스",
                    "evidence": "가격 저점 하락, MACD 저점 상승",
                    "score": 20,
                }
            # Bearish divergence
            elif (
                recent["Close"].iloc[price_peaks[-1]]
                > recent["Close"].iloc[price_peaks[-2]]
                and recent["MACD_12_26_9"].iloc[macd_peaks[-1]]
                < recent["MACD_12_26_9"].iloc[macd_peaks[-2]]
            ):
                return {
                    "signal": "MACD 약세 다이버전스",
                    "evidence": "가격 고점 상승, MACD 고점 하락",
                    "score": -20,
                }

        return None

    def _find_peaks(self, data: np.ndarray) -> list[int]:
        """Find local peaks in data."""
        peaks = []
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1]:
                peaks.append(i)
        return peaks

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

Run: `uv run pytest tests/tools/technical/test_divergence_strategy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/technical/strategies/divergence.py tests/tools/technical/test_divergence_strategy.py
git commit -m "feat(technical): add DivergenceStrategy for RSI/MACD divergence"
```

---

## Task 5: Disparity & Risk Strategies

**Files:**
- Create: `src/tools/technical/strategies/disparity.py`
- Create: `src/tools/technical/strategies/risk.py`
- Test: `tests/tools/technical/test_disparity_strategy.py`
- Test: `tests/tools/technical/test_risk_strategy.py`

[Similar TDD pattern for Disparity and Risk strategies - testing 20/50/120 day disparity and ATR/BB-based risk assessment]

Brief implementation:

```python
# src/tools/technical/strategies/disparity.py
class DisparityStrategy(BaseStrategy):
    """이격도 기반 과열/침체 분석."""
    name = "disparity"
    # Analyze Disparity_20, Disparity_50, Disparity_120
    # >110: 과열, <90: 침체

# src/tools/technical/strategies/risk.py
class RiskStrategy(BaseStrategy):
    """변동성 및 리스크 분석."""
    name = "risk"
    # Analyze ATR, Bollinger Bands width, 52w high/low distance
```

- [ ] **Commit**

```bash
git add src/tools/technical/strategies/disparity.py src/tools/technical/strategies/risk.py tests/tools/technical/test_*
git commit -m "feat(technical): add Disparity and Risk strategies"
```

---

## Task 6: Update Strategy Registry

**Files:**
- Edit: `src/tools/technical/registry.py`
- Edit: `config.yaml`

- [ ] **Step 1: Update STRATEGY_MAP**

```python
# In src/tools/technical/registry.py
from src.tools.technical.strategies.trend import TrendStrategy
from src.tools.technical.strategies.oscillator import OscillatorStrategy
from src.tools.technical.strategies.divergence import DivergenceStrategy
from src.tools.technical.strategies.disparity import DisparityStrategy
from src.tools.technical.strategies.risk import RiskStrategy

STRATEGY_MAP = {
    "trend": TrendStrategy,
    "oscillator": OscillatorStrategy,
    "divergence": DivergenceStrategy,
    "disparity": DisparityStrategy,
    "risk": RiskStrategy,
}
```

- [ ] **Step 2: Update config.yaml**

```yaml
technical:
  strategies:
    - trend
    - oscillator
    - divergence
    - disparity
    - risk
```

- [ ] **Step 3: Test with all strategies**

Run: `uv run pytest tests/tools/technical/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/tools/technical/registry.py config.yaml
git commit -m "feat(technical): enable all 5 strategies in registry"
```

---

## Task 7: Macro Tool

**Files:**
- Create: `src/tools/macro.py`
- Test: `tests/tools/test_macro.py`

[Implementation for fetching VIX, Fear&Greed Index, WTI, US 10Y/2Y yields, DXY using yfinance and external APIs]

```python
# src/tools/macro.py
class MacroTool(BaseTool):
    """Macro indicators tool."""
    name = "macro"
    
    async def execute(self, **kwargs) -> ToolResult:
        # Fetch VIX (^VIX), WTI (CL=F), DXY (DX-Y.NYB), yields
        # Return MacroSnapshot
```

- [ ] **Commit**

```bash
git add src/tools/macro.py tests/tools/test_macro.py
git commit -m "feat(tools): add macro indicators tool (VIX/Fear&Greed/WTI/Yields/DXY)"
```

---

## Task 8: News Tool

**Files:**
- Create: `src/tools/news.py`
- Test: `tests/tools/test_news.py`

[Implementation for fetching news from yfinance or external news APIs]

```python
# src/tools/news.py
class NewsTool(BaseTool):
    """News aggregation tool."""
    name = "news"
    
    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        # Fetch recent news for ticker
        # Return list of {title, published, summary, url}
```

- [ ] **Commit**

```bash
git add src/tools/news.py tests/tools/test_news.py
git commit -m "feat(tools): add news aggregation tool"
```

---

## Task 9: Deep Dive Pipeline

**Files:**
- Create: `src/pipelines/deep_dive.py`
- Test: `tests/pipelines/test_deep_dive.py`

```python
# src/pipelines/deep_dive.py
class DeepDivePipeline:
    """Deep dive analysis with LLM."""
    
    def __init__(
        self,
        technical_tool: TechnicalAnalysisTool,
        news_tool: NewsTool,
        llm_client: LLMClient,
    ):
        self.technical_tool = technical_tool
        self.news_tool = news_tool
        self.llm = llm_client
    
    async def run(self, ticker: str) -> dict:
        # 1. Technical analysis
        tech_result = await self.technical_tool.execute(ticker)
        
        # 2. Fetch news
        news_result = await self.news_tool.execute(ticker)
        
        # 3. LLM analysis
        tech_summary = await self.llm.generate_technical_summary(...)
        news_analysis = await self.llm.analyze_news(...)
        
        return {
            "ticker": ticker,
            "technical": tech_result.data,
            "technical_summary": tech_summary,
            "news": news_result.data,
            "news_analysis": news_analysis,
        }
```

- [ ] **Commit**

```bash
git add src/pipelines/deep_dive.py tests/pipelines/test_deep_dive.py
git commit -m "feat(pipelines): add DeepDivePipeline with LLM"
```

---

## Task 10: Daily Report Pipeline

**Files:**
- Create: `src/pipelines/daily_report.py`
- Test: `tests/pipelines/test_daily_report.py`

```python
# src/pipelines/daily_report.py
class DailyReportPipeline:
    """Daily market report with macro + top movers."""
    
    def __init__(
        self,
        macro_tool: MacroTool,
        technical_tool: TechnicalAnalysisTool,
        llm_client: LLMClient,
    ):
        self.macro_tool = macro_tool
        self.technical_tool = technical_tool
        self.llm = llm_client
    
    async def run(self, tickers: list[str]) -> dict:
        # 1. Macro snapshot
        macro_result = await self.macro_tool.execute()
        
        # 2. Technical analysis for each ticker
        ticker_analyses = []
        for ticker in tickers:
            result = await self.technical_tool.execute(ticker)
            ticker_analyses.append(result)
        
        # 3. LLM summarization
        # Extract themes, summarize market condition
        
        return {
            "date": datetime.now(),
            "macro": macro_result.data,
            "tickers": ticker_analyses,
        }
```

- [ ] **Commit**

```bash
git add src/pipelines/daily_report.py tests/pipelines/test_daily_report.py
git commit -m "feat(pipelines): add DailyReportPipeline with macro"
```

---

## Task 11: CLI Commands

**Files:**
- Edit: `src/cli/main.py`
- Test: `tests/cli/test_cli.py`

- [ ] **Step 1: Add analyze command**

```python
@app.command()
def analyze(
    ticker: str = typer.Argument(..., help="Stock ticker"),
    provider: str = typer.Option("openai", help="LLM provider"),
):
    """Deep dive analysis with LLM."""
    # Run DeepDivePipeline
    # Display formatted output
```

- [ ] **Step 2: Add report command**

```python
@app.command()
def report(
    tickers: str = typer.Option("AAPL,MSFT,NVDA", help="Comma-separated tickers"),
    provider: str = typer.Option("openai", help="LLM provider"),
):
    """Generate daily market report."""
    # Run DailyReportPipeline
    # Display formatted output
```

- [ ] **Step 3: Test**

Run: `uv run jarvis analyze AAPL`
Run: `uv run jarvis report`

- [ ] **Step 4: Commit**

```bash
git add src/cli/main.py tests/cli/test_cli.py
git commit -m "feat(cli): add analyze and report commands"
```

---

## Task 12: Integration Test

**Files:**
- Create: `tests/integration/test_e2e_plan2.py`

```python
@pytest.mark.integration
def test_analyze_command():
    """Test analyze command with real API."""
    result = runner.invoke(app, ["analyze", "AAPL"])
    assert result.exit_code == 0
    assert "technical" in result.stdout.lower()

@pytest.mark.integration
def test_report_command():
    """Test report command with real API."""
    result = runner.invoke(app, ["report", "--tickers=AAPL"])
    assert result.exit_code == 0
    assert "vix" in result.stdout.lower() or "macro" in result.stdout.lower()
```

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ -v --ignore=tests/integration`
Expected: All pass

- [ ] **Step 2: Run integration tests (requires API keys)**

Run: `uv run pytest tests/integration/ -v -m integration`
Expected: PASS

- [ ] **Step 3: Commit and tag**

```bash
git add tests/integration/test_e2e_plan2.py
git commit -m "test: add Plan 2 integration tests"
git tag -a v0.2.0 -m "Plan 2 complete: LLM + Strategies + Macro + News + Pipelines"
```

---

## Summary

Plan 2 완료 시 동작하는 기능:

```bash
# 기존 (Plan 1)
jarvis check AAPL

# 신규 (Plan 2)
jarvis analyze AAPL    # LLM 기반 심층 분석 (기술 + 뉴스)
jarvis report          # 일일 시장 리포트 (매크로 + 주요 종목)
```

출력 예시 (analyze):
```
## AAPL Deep Dive Analysis

### Technical Analysis
**평가**: 매수 (신뢰도: 78%)
**요약**: AAPL은 강한 상승 추세를 보이고 있으며, 모든 이동평균선이 정배열 상태입니다.

**주요 인사이트**:
- 골든크로스 발생으로 중기 상승 추세 확인
- RSI는 중립권으로 추가 상승 여력 존재
- 볼린저밴드 상단 근접으로 단기 조정 가능성

### News Analysis
**심리**: 긍정 (신뢰도: 85%)
**주요 테마**: 신제품 출시, 실적 개선, AI 투자 확대

**영향 평가**: 신제품 출시 호재로 단기 긍정적 영향 예상. 다만 밸류에이션 부담 존재.
```

다음 Plan 3에서 추가될 기능:
- 한국 주식 지원 (KIS API)
- 포트폴리오 모니터링
- Claude Code Skills
