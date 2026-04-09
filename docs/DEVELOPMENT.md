# Development Guide

Invest-Jarvis 개발 가이드

## 개발 환경 설정

### 1. 저장소 클론 및 의존성 설치

```bash
git clone <repository-url>
cd invest-jarvis
uv sync
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 API 키 입력
```

### 3. 테스트 실행으로 환경 검증

```bash
uv run pytest tests/ -v --ignore=tests/integration
```

---

## 프로젝트 아키텍처

### 설계 원칙

1. **모듈러 구조**: 관심사 분리, 각 컴포넌트는 단일 책임
2. **인터페이스 기반**: `BaseTool`, `BaseProvider`, `BaseStrategy` 추상 클래스
3. **전략 패턴**: 기술적 분석 전략을 동적으로 추가/제거 가능
4. **의존성 주입**: 테스트 용이성을 위해 생성자로 의존성 주입

### 레이어별 책임

**Core Layer** (`src/core/`)
- 인터페이스 정의 (BaseTool, BaseProvider)
- 공통 모델 (ToolResult)
- 설정 로더

**Provider Layer** (`src/providers/`)
- 외부 데이터 소스와의 통신
- API 래퍼 (thin wrapper)
- 인증 및 토큰 관리

**Tool Layer** (`src/tools/`)
- 비즈니스 로직 구현
- Provider를 사용하여 데이터 가져오기
- 분석 로직 수행

**Pipeline Layer** (`src/pipelines/`)
- 여러 Tool을 조합한 워크플로우
- 실행 순서 관리
- 결과 포맷팅

**CLI Layer** (`src/cli/`)
- 사용자 인터페이스
- 명령어 파싱
- 출력 포맷팅

---

## 코딩 규칙

### 타입 힌트

모든 함수와 메서드에 타입 힌트 사용:

```python
def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate RSI indicator."""
    pass

async def get_quote(self, ticker: str) -> dict[str, Any]:
    """Get current quote."""
    pass
```

### Pydantic 모델

데이터 검증을 위해 Pydantic 모델 사용:

```python
from pydantic import BaseModel

class StrategyResult(BaseModel):
    name: str
    status: str
    confidence: float
    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]
```

### 에러 처리

ToolResult로 성공/실패 래핑:

```python
async def execute(self, ticker: str, **kwargs) -> ToolResult:
    try:
        data = await self._fetch_data(ticker)
        return ToolResult(success=True, data=data)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))
```

### 비동기 함수

I/O 작업은 비동기로 구현:

```python
async def get_quote(self, ticker: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        return response.json()
```

---

## 테스트 작성

### TDD 접근법

1. **테스트 먼저 작성** (Red)
2. **최소 구현** (Green)
3. **리팩토링** (Refactor)

### 테스트 구조

```python
# tests/tools/test_my_tool.py
import pytest
from unittest.mock import AsyncMock
from src.tools.my_tool import MyTool

@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.get_data.return_value = {"data": "test"}
    return provider

@pytest.mark.asyncio
async def test_my_tool_success(mock_provider):
    tool = MyTool(provider=mock_provider)
    result = await tool.execute("TEST")
    
    assert result.success is True
    assert result.data is not None
    mock_provider.get_data.assert_called_once_with("TEST")

@pytest.mark.asyncio
async def test_my_tool_failure(mock_provider):
    mock_provider.get_data.side_effect = Exception("API Error")
    tool = MyTool(provider=mock_provider)
    result = await tool.execute("TEST")
    
    assert result.success is False
    assert result.error == "API Error"
```

### 테스트 실행

```bash
# 전체 테스트
uv run pytest tests/ -v

# 특정 모듈
uv run pytest tests/tools/ -v

# 특정 테스트
uv run pytest tests/tools/test_my_tool.py::test_my_tool_success -v

# 커버리지
uv run pytest tests/ --cov=src --cov-report=term-missing
```

---

## 새 기능 추가 가이드

### 1. 새 Provider 추가

**예시: Naver Finance Provider**

```python
# src/providers/naver.py
from src.core.interfaces import BaseProvider
import pandas as pd

class NaverProvider(BaseProvider):
    async def get_quote(self, ticker: str) -> dict:
        # Implementation
        pass
    
    async def get_price_history(self, ticker: str, period: str) -> pd.DataFrame:
        # Implementation
        pass
```

**테스트 작성:**

```python
# tests/providers/test_naver.py
import pytest
from src.providers.naver import NaverProvider

@pytest.mark.asyncio
async def test_naver_get_quote():
    provider = NaverProvider()
    quote = await provider.get_quote("005930")
    assert quote["ticker"] == "005930"
```

### 2. 새 전략 추가

**예시: Volume Strategy**

```python
# src/tools/technical/strategies/volume.py
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult
import pandas as pd

class VolumeStrategy(BaseStrategy):
    name = "volume"
    description = "거래량 기반 분석"
    
    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        signals = []
        evidence = []
        score = 0
        
        # 거래량 분석 로직
        latest_volume = df.iloc[-1]["Volume"]
        avg_volume = df["Volume"].tail(20).mean()
        
        if latest_volume > avg_volume * 2:
            signals.append("거래량 급증")
            evidence.append(f"거래량 {latest_volume:,.0f} > 평균 {avg_volume:,.0f}의 2배")
            score += 20
        
        return StrategyResult(
            name=self.name,
            status="활발" if score > 10 else "보통",
            confidence=min(100, 50 + score),
            signals=signals,
            evidence=evidence,
            metrics={"volume": latest_volume, "avg_volume": avg_volume},
        )
```

**Registry에 등록:**

```python
# src/tools/technical/registry.py
from src.tools.technical.strategies.volume import VolumeStrategy

STRATEGY_MAP = {
    "trend": TrendStrategy,
    "oscillator": OscillatorStrategy,
    # ...
    "volume": VolumeStrategy,  # 추가
}
```

**Config 업데이트:**

```yaml
# config.yaml
technical:
  strategies:
    - trend
    - oscillator
    - volume  # 추가
```

### 3. 새 Tool 추가

**예시: Fundamental Tool**

```python
# src/tools/fundamental.py
from src.core.interfaces import BaseTool, BaseProvider
from src.core.models import ToolResult

class FundamentalTool(BaseTool):
    name = "fundamental"
    description = "펀더멘털 분석"
    
    def __init__(self, provider: BaseProvider):
        self.provider = provider
    
    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        try:
            # 구현
            data = await self._analyze_fundamentals(ticker)
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

### 4. 새 Pipeline 추가

**예시: Screening Pipeline**

```python
# src/pipelines/screening.py
from typing import Any
from src.tools.technical.tool import TechnicalAnalysisTool

class ScreeningPipeline:
    def __init__(self, technical_tool: TechnicalAnalysisTool):
        self.technical_tool = technical_tool
    
    async def run(self, tickers: list[str], filters: dict) -> dict[str, Any]:
        results = []
        for ticker in tickers:
            tech_result = await self.technical_tool.execute(ticker)
            if self._matches_filters(tech_result, filters):
                results.append({
                    "ticker": ticker,
                    "analysis": tech_result.data,
                })
        
        return {
            "matches": results,
            "total": len(results),
        }
```

### 5. 새 CLI 명령어 추가

```python
# src/cli/main.py
@app.command()
def screen(
    tickers: str = typer.Argument(..., help="Comma-separated tickers"),
    min_confidence: float = typer.Option(70.0, help="Minimum confidence"),
):
    """Screen stocks by technical criteria."""
    console.print(f"[bold]Screening {tickers}...[/bold]\n")
    
    result = asyncio.run(run_screening(tickers.split(","), min_confidence))
    
    # 출력 포맷팅
    console.print(Markdown(format_screening_result(result)))
```

---

## LLM 통합

### LLM Client 사용

```python
from src.llm.client import LLMClient
from src.llm.models import NewsAnalysisInput

# 클라이언트 초기화
llm = LLMClient(
    provider="openai",
    api_key=os.getenv("OPENAI_API_KEY"),
)

# 뉴스 분석
input_data = NewsAnalysisInput(
    ticker="AAPL",
    company_name="Apple Inc.",
    news=[...],
)
result = await llm.analyze_news(input_data)
```

### 새 LLM 메서드 추가

```python
# src/llm/models.py
class MyAnalysisInput(BaseModel):
    # 입력 필드 정의
    pass

class MyAnalysisOutput(BaseModel):
    # 출력 필드 정의
    pass

# src/llm/client.py
async def my_custom_analysis(self, input_data: MyAnalysisInput) -> MyAnalysisOutput:
    prompt = f"""분석 요청: {input_data.field}
    
    JSON 형식으로 응답:
    {{
      "result": "...",
      "confidence": 0.0-1.0
    }}"""
    
    request = LLMRequest(
        model=self.model,
        messages=[
            {"role": "system", "content": "You are an analyst."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        seed=42,
    )
    
    response = await self._call_api(request)
    data = json.loads(response.content)
    return MyAnalysisOutput(**data)
```

---

## 디버깅

### 로깅 추가

```python
import logging

logger = logging.getLogger(__name__)

async def execute(self, ticker: str) -> ToolResult:
    logger.info(f"Executing analysis for {ticker}")
    try:
        data = await self._fetch_data(ticker)
        logger.debug(f"Fetched data: {data}")
        return ToolResult(success=True, data=data)
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return ToolResult(success=False, data=None, error=str(e))
```

### pytest 디버그 모드

```bash
# 상세 출력
uv run pytest tests/ -vv

# print 출력 보기
uv run pytest tests/ -s

# 특정 테스트만
uv run pytest tests/tools/test_my_tool.py::test_my_tool_success -vv -s

# 실패 시 pdb 진입
uv run pytest tests/ --pdb
```

---

## 성능 최적화

### 캐싱

```python
# src/storage/cache.py 사용
cache = MemoryCache()

async def get_data_with_cache(self, ticker: str):
    return await cache.get_or_fetch(
        key=f"quote:{ticker}",
        fetcher=lambda: self.provider.get_quote(ticker),
        ttl=60,  # 1분
    )
```

### 병렬 처리

```python
import asyncio

async def analyze_multiple(self, tickers: list[str]):
    tasks = [self.analyze_one(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

---

## 배포

### 버전 업데이트

```bash
# pyproject.toml 버전 업데이트
version = "0.4.0"

# git 태그
git tag -a v0.4.0 -m "Release v0.4.0: New features"
git push origin v0.4.0
```

### 빌드

```bash
# 배포용 빌드
uv build

# 생성된 파일
# dist/invest_jarvis-0.4.0-py3-none-any.whl
# dist/invest_jarvis-0.4.0.tar.gz
```

---

## 문제 해결

### 자주 발생하는 이슈

**1. Import 에러**
```
ModuleNotFoundError: No module named 'src'
```
→ `uv sync` 실행하여 의존성 재설치

**2. API 키 에러**
```
Error: OPENAI_API_KEY required
```
→ `.env` 파일에 API 키 설정 확인

**3. 테스트 실패**
```
AssertionError: expected True, got False
```
→ Mock 설정 확인, 테스트 데이터 검증

**4. 비동기 에러**
```
RuntimeError: no running event loop
```
→ `@pytest.mark.asyncio` 데코레이터 확인

---

## 참고 자료

- [Pydantic 문서](https://docs.pydantic.dev/)
- [httpx 문서](https://www.python-httpx.org/)
- [pandas-ta 문서](https://github.com/twopirllc/pandas-ta)
- [Typer 문서](https://typer.tiangolo.com/)
- [pytest 문서](https://docs.pytest.org/)
