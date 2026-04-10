# LLM Ticker Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** yfinance 검색과 static yml 매핑을 제거하고, GPT-4o + DuckDuckGo Tool Calling Loop로 티커를 해결하며 결과를 유저 캐시에 저장한다.

**Architecture:** `LLMTickerAgent`를 신규 파일로 분리하여 DuckDuckGo 검색 툴을 GPT-4o에 바인딩하는 Tool Calling Loop를 구현한다. `TickerResolver`는 기존 static mapping/yfinance 코드를 제거하고 `LLMTickerAgent`를 3단계 fallback으로 연결한다. 모든 LLM 해결 결과는 `UserMappingCache`에 저장되어 이후 재호출 시 LLM을 우회한다.

**Tech Stack:** `langchain-openai`, `langchain-core`, `duckduckgo-search>=6.0.0`, `pydantic`, `pyyaml`

---

### Task 1: 데이터 모델 간소화

**Files:**
- Modify: `src/providers/ticker_models.py`
- Modify: `tests/providers/test_ticker_models.py`

- [ ] **Step 1: 모델 테스트 재작성**

`tests/providers/test_ticker_models.py` 전체를 아래로 교체한다.

```python
from datetime import datetime
import pytest
from src.providers.ticker_models import CachedMapping, TickerResolution, TickerNotFoundError


def test_ticker_resolution_creation():
    resolution = TickerResolution(
        original_query="삼성전자",
        resolved_ticker="005930.KS",
        display_name="Samsung Electronics Co., Ltd.",
        source="llm_agent"
    )
    assert resolution.original_query == "삼성전자"
    assert resolution.resolved_ticker == "005930.KS"
    assert resolution.display_name == "Samsung Electronics Co., Ltd."
    assert resolution.source == "llm_agent"


def test_ticker_resolution_requires_fields():
    with pytest.raises(Exception):
        TickerResolution(original_query="test")


def test_cached_mapping_creation():
    now = datetime.now()
    mapping = CachedMapping(
        ticker="AAPL",
        display_name="Apple Inc.",
        created_at=now,
        last_used=now,
        use_count=1
    )
    assert mapping.ticker == "AAPL"
    assert mapping.use_count == 1


def test_cached_mapping_rejects_zero_use_count():
    now = datetime.now()
    with pytest.raises(ValueError):
        CachedMapping(
            ticker="AAPL",
            display_name="Apple Inc.",
            created_at=now,
            last_used=now,
            use_count=0
        )
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/providers/test_ticker_models.py -v
```

Expected: `TickerResolution` 생성 테스트 FAIL (`confidence` 등 필드 없어서)

- [ ] **Step 3: `ticker_models.py` 수정**

`src/providers/ticker_models.py` 전체를 아래로 교체한다. 순환 임포트 방지를 위해 예외 클래스도 여기에 정의한다(`llm_ticker_agent` ↔ `ticker_resolver` 상호 임포트 방지).

```python
from datetime import datetime
from pydantic import BaseModel, Field


class TickerResolutionError(Exception):
    """Base exception for ticker resolution"""
    pass


class TickerNotFoundError(TickerResolutionError):
    """No ticker found for query"""
    pass


class TickerResolution(BaseModel):
    """티커 해결 결과"""
    original_query: str
    resolved_ticker: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    source: str = Field(min_length=1)


class CachedMapping(BaseModel):
    """유저 캐시 파일에 저장되는 개별 매핑 항목"""
    ticker: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    created_at: datetime
    last_used: datetime
    use_count: int = Field(ge=1)
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/providers/test_ticker_models.py -v
```

Expected: 4개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/ticker_models.py tests/providers/test_ticker_models.py
git commit -m "refactor: simplify TickerResolution model, remove CandidateTicker"
```

---

### Task 2: 의존성 추가 및 static yml 삭제

**Files:**
- Modify: `pyproject.toml`
- Delete: `config/ticker_names.yaml`

- [ ] **Step 1: `pyproject.toml`에 duckduckgo-search 추가**

`pyproject.toml`의 `dependencies` 리스트에 한 줄 추가한다.

```toml
dependencies = [
    "typer>=0.9.0",
    "pydantic>=2.0.0",
    "pandas>=2.0.0",
    "pandas-ta>=0.3.14b",
    "yfinance>=0.2.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "httpx>=0.25.0",
    "langchain-openai>=1.1.12",
    "langchain-anthropic>=1.4.0",
    "langchain-core>=1.2.28",
    "scipy>=1.17.1",
    "duckduckgo-search>=6.0.0",
]
```

- [ ] **Step 2: 패키지 설치**

```bash
pip install duckduckgo-search
```

Expected: Successfully installed duckduckgo-search-...

- [ ] **Step 3: static yml 삭제**

```bash
rm config/ticker_names.yaml
```

- [ ] **Step 4: 커밋**

```bash
git add pyproject.toml
git rm config/ticker_names.yaml
git commit -m "chore: add duckduckgo-search dep, remove static ticker yml"
```

---

### Task 3: LLMTickerAgent 구현 (TDD)

**Files:**
- Create: `tests/providers/test_llm_ticker_agent.py`
- Create: `src/providers/llm_ticker_agent.py`

- [ ] **Step 1: 테스트 파일 작성**

`tests/providers/test_llm_ticker_agent.py` 를 아래 내용으로 생성한다.

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.providers.llm_ticker_agent import LLMTickerAgent
from src.providers.ticker_models import TickerNotFoundError


def test_init_raises_without_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMTickerAgent(api_key="")


@pytest.mark.asyncio
async def test_resolve_with_single_tool_call():
    """DuckDuckGo 1회 검색 후 티커 반환"""
    agent = LLMTickerAgent(api_key="test-key")

    tool_response = MagicMock()
    tool_response.tool_calls = [
        {"id": "call_1", "name": "duckduckgo_search", "args": {"query": "삼성전자 stock ticker KRX"}}
    ]
    tool_response.content = ""

    final_response = MagicMock()
    final_response.tool_calls = []
    final_response.content = '{"ticker": "005930.KS", "display_name": "Samsung Electronics Co., Ltd."}'

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(side_effect=[tool_response, final_response])

    with patch.object(agent.llm, "bind_tools", return_value=mock_bound_llm):
        with patch("src.providers.llm_ticker_agent.duckduckgo_search") as mock_ddg:
            mock_ddg.invoke.return_value = "Samsung Electronics Co., Ltd. trades on KRX as 005930.KS"
            ticker, display_name = await agent.resolve("삼성전자")

    assert ticker == "005930.KS"
    assert display_name == "Samsung Electronics Co., Ltd."


@pytest.mark.asyncio
async def test_resolve_without_tool_call():
    """LLM이 즉시 JSON 반환 (tool 호출 없음)"""
    agent = LLMTickerAgent(api_key="test-key")

    final_response = MagicMock()
    final_response.tool_calls = []
    final_response.content = '{"ticker": "RKLB", "display_name": "Rocket Lab USA, Inc."}'

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(return_value=final_response)

    with patch.object(agent.llm, "bind_tools", return_value=mock_bound_llm):
        ticker, display_name = await agent.resolve("로켓랩")

    assert ticker == "RKLB"
    assert display_name == "Rocket Lab USA, Inc."


@pytest.mark.asyncio
async def test_resolve_raises_on_invalid_json():
    """LLM이 유효하지 않은 JSON 반환 시 TickerNotFoundError"""
    agent = LLMTickerAgent(api_key="test-key")

    bad_response = MagicMock()
    bad_response.tool_calls = []
    bad_response.content = "I cannot find this ticker."

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(return_value=bad_response)

    with patch.object(agent.llm, "bind_tools", return_value=mock_bound_llm):
        with pytest.raises(TickerNotFoundError):
            await agent.resolve("존재하지않는회사")


@pytest.mark.asyncio
async def test_resolve_raises_after_max_iterations():
    """3회 tool 호출 이후에도 미해결 시 TickerNotFoundError"""
    agent = LLMTickerAgent(api_key="test-key")

    tool_response = MagicMock()
    tool_response.tool_calls = [
        {"id": "call_x", "name": "duckduckgo_search", "args": {"query": "some query"}}
    ]
    tool_response.content = ""

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(return_value=tool_response)

    with patch.object(agent.llm, "bind_tools", return_value=mock_bound_llm):
        with patch("src.providers.llm_ticker_agent.duckduckgo_search") as mock_ddg:
            mock_ddg.invoke.return_value = "no relevant results"
            with pytest.raises(TickerNotFoundError):
                await agent.resolve("알수없는종목")
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/providers/test_llm_ticker_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.providers.llm_ticker_agent'`

- [ ] **Step 3: `llm_ticker_agent.py` 구현**

`src/providers/llm_ticker_agent.py` 를 아래 내용으로 생성한다.

```python
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from duckduckgo_search import DDGS
from src.providers.ticker_models import TickerNotFoundError

_SYSTEM_PROMPT = """You are a financial ticker resolution assistant. Find the exact stock exchange ticker symbol for a given company name or query.

Use the duckduckgo_search tool to look up the company's stock ticker.

Rules:
- Korean KOSPI stocks use .KS suffix (e.g., 005930.KS for Samsung Electronics)
- Korean KOSDAQ stocks use .KQ suffix (e.g., 035720.KQ for Kakao)
- US stocks use plain symbol without suffix (e.g., AAPL, RKLB)
- Return ONLY valid exchange-listed tickers

After finding the ticker, respond with ONLY this JSON (no other text):
{"ticker": "SYMBOL", "display_name": "Full Company Name"}"""


@tool
def duckduckgo_search(query: str) -> str:
    """Search DuckDuckGo for stock ticker information. Returns top 5 results."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "No results found."
    return "\n".join(f"- {r['title']}: {r['body']}" for r in results)


class LLMTickerAgent:
    """GPT-4o + DuckDuckGo Tool Calling Loop으로 회사명을 티커로 해결한다."""

    MAX_ITERATIONS = 3

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for LLMTickerAgent")
        self.llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)

    async def resolve(self, query: str) -> tuple[str, str]:
        """
        회사명/쿼리를 (ticker, display_name) 튜플로 해결한다.
        해결 실패 시 TickerNotFoundError 발생.
        """
        llm_with_tools = self.llm.bind_tools([duckduckgo_search])
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Find the stock ticker for: {query}"),
        ]

        for _ in range(self.MAX_ITERATIONS):
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                try:
                    result = json.loads(response.content)
                    return result["ticker"], result["display_name"]
                except (json.JSONDecodeError, KeyError):
                    raise TickerNotFoundError(f"Could not resolve: {query}")

            for tool_call in response.tool_calls:
                tool_result = duckduckgo_search.invoke({"query": tool_call["args"]["query"]})
                messages.append(ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call["id"],
                ))

        raise TickerNotFoundError(f"Could not resolve after {self.MAX_ITERATIONS} iterations: {query}")
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/providers/test_llm_ticker_agent.py -v
```

Expected: 5개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/llm_ticker_agent.py tests/providers/test_llm_ticker_agent.py
git commit -m "feat: add LLMTickerAgent with GPT-4o + DuckDuckGo tool calling"
```

---

### Task 4: TickerResolver 리팩토링 (TDD)

**Files:**
- Modify: `tests/providers/test_ticker_resolver.py`
- Modify: `src/providers/ticker_resolver.py`

- [ ] **Step 1: Resolver 테스트 재작성**

`tests/providers/test_ticker_resolver.py` 전체를 아래로 교체한다.

```python
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from src.providers.ticker_resolver import TickerResolver
from src.providers.ticker_models import TickerNotFoundError


@pytest.mark.asyncio
async def test_resolve_direct_us_ticker():
    resolver = TickerResolver(openai_api_key="test-key")
    result = await resolver.resolve("AAPL")
    assert result.resolved_ticker == "AAPL"
    assert result.source == "direct_ticker"


@pytest.mark.asyncio
async def test_resolve_direct_korean_ticker():
    resolver = TickerResolver(openai_api_key="test-key")
    result = await resolver.resolve("005930.KS")
    assert result.resolved_ticker == "005930.KS"
    assert result.source == "direct_ticker"


@pytest.mark.asyncio
async def test_resolve_korean_ticker_normalization():
    resolver = TickerResolver(openai_api_key="test-key")
    result = await resolver.resolve("005930")
    assert result.resolved_ticker == "005930.KS"
    assert result.source == "direct_ticker"


@pytest.mark.asyncio
async def test_resolve_from_user_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.user_cache.save("애플", "AAPL", "Apple Inc.")

        result = await resolver.resolve("애플")

        assert result.resolved_ticker == "AAPL"
        assert result.display_name == "Apple Inc."
        assert result.source == "user_cache"


@pytest.mark.asyncio
async def test_resolve_cache_updates_usage():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.user_cache.save("Tesla", "TSLA", "Tesla, Inc.")
        initial_count = resolver.user_cache.get("Tesla").use_count

        await resolver.resolve("Tesla")

        assert resolver.user_cache.get("Tesla").use_count == initial_count + 1


@pytest.mark.asyncio
async def test_resolve_via_llm_agent():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.llm_agent.resolve = AsyncMock(
            return_value=("005930.KS", "Samsung Electronics Co., Ltd.")
        )

        result = await resolver.resolve("삼성전자")

        assert result.resolved_ticker == "005930.KS"
        assert result.display_name == "Samsung Electronics Co., Ltd."
        assert result.source == "llm_agent"


@pytest.mark.asyncio
async def test_resolve_llm_result_saved_to_cache():
    """LLM으로 해결된 결과가 캐시에 저장되어 다음 호출은 cache hit"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.llm_agent.resolve = AsyncMock(
            return_value=("035720.KQ", "Kakao Corp.")
        )

        await resolver.resolve("카카오")
        # 두 번째 호출은 cache hit이어야 함
        resolver.llm_agent.resolve = AsyncMock(side_effect=Exception("should not be called"))
        result = await resolver.resolve("카카오")

        assert result.resolved_ticker == "035720.KQ"
        assert result.source == "user_cache"


@pytest.mark.asyncio
async def test_resolve_raises_when_llm_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.llm_agent.resolve = AsyncMock(side_effect=TickerNotFoundError("not found"))

        with pytest.raises(TickerNotFoundError):
            await resolver.resolve("존재하지않는회사xyz")
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/providers/test_ticker_resolver.py -v
```

Expected: `source` 필드 없음, `openai_api_key` 파라미터 없음 등으로 FAIL

- [ ] **Step 3: `ticker_resolver.py` 리팩토링**

`src/providers/ticker_resolver.py` 전체를 아래로 교체한다.

```python
import os
import re
from typing import Optional
from pathlib import Path

from src.providers.ticker_models import TickerResolution, TickerNotFoundError, TickerResolutionError
from src.providers.ticker_cache import UserMappingCache
from src.providers.llm_ticker_agent import LLMTickerAgent


class TickerResolver:
    """사용자 쿼리를 티커 심볼로 해결한다."""

    def __init__(
        self,
        user_cache_path: Optional[Path] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.user_cache = UserMappingCache(user_cache_path)
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.llm_agent = LLMTickerAgent(api_key=api_key)

    async def resolve(self, query: str) -> TickerResolution:
        """
        사용자 쿼리를 티커 심볼로 해결한다.

        우선순위:
        1. Direct ticker 감지
        2. 유저 캐시 조회
        3. LLM Agent (GPT-4o + DuckDuckGo)
        """
        query = query.strip()

        if self._is_direct_ticker(query):
            normalized = self._normalize_ticker(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=normalized,
                display_name=normalized,
                source="direct_ticker",
            )

        cached = self.user_cache.get(query)
        if cached:
            self.user_cache.update_usage(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=cached.ticker,
                display_name=cached.display_name,
                source="user_cache",
            )

        ticker, display_name = await self.llm_agent.resolve(query)
        self.user_cache.save(query, ticker, display_name)
        return TickerResolution(
            original_query=query,
            resolved_ticker=ticker,
            display_name=display_name,
            source="llm_agent",
        )

    def _is_direct_ticker(self, query: str) -> bool:
        patterns = [
            r'^[A-Z]{1,5}$',
            r'^\d{6}\.KS$',
            r'^\d{6}\.KQ$',
            r'^\d{6}$',
        ]
        return any(re.match(p, query) for p in patterns)

    def _normalize_ticker(self, query: str) -> str:
        if re.match(r'^\d{6}$', query):
            return f"{query}.KS"
        return query
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/providers/test_ticker_resolver.py -v
```

Expected: 8개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/ticker_resolver.py tests/providers/test_ticker_resolver.py
git commit -m "refactor: replace yfinance/static-mapping with LLMTickerAgent in TickerResolver"
```

---

### Task 5: 전체 테스트 검증 및 파이널 정리

**Files:**
- Modify: `src/cli/main.py` (TickerResolver 생성자 파라미터 정리)

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest tests/ -v --tb=short 2>&1 | head -80
```

Expected: `test_ticker_models`, `test_llm_ticker_agent`, `test_ticker_resolver`, `test_ticker_cache` 관련 테스트 PASS. 다른 테스트에서 `TickerResolution` 필드 참조 오류 있으면 확인.

- [ ] **Step 2: CLI main.py의 `resolve_ticker` 함수 확인**

`src/cli/main.py:48-55` 의 `resolve_ticker`는 `resolution.resolved_ticker`만 사용하므로 변경 불필요. `TickerResolver()` 생성자 호출도 `openai_api_key` 미전달 시 환경변수에서 읽으므로 변경 불필요. 확인만 한다.

```bash
grep -n "TickerResolver\|resolution\." src/cli/main.py
```

Expected: `TickerResolver()` 생성자 호출 1건, `resolution.resolved_ticker` 참조 1건 — 둘 다 변경 불필요.

- [ ] **Step 3: providers 전체 테스트 통과 확인**

```bash
pytest tests/providers/ -v
```

Expected: 전체 PASS

- [ ] **Step 4: 커밋**

```bash
git add -p
git commit -m "test: verify full test suite passes after LLM ticker resolver refactor"
```
