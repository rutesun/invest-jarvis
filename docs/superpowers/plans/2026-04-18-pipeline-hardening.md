# Daily Report 파이프라인 강화 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CNN Fear & Greed 원본 데이터 도입 + 매크로 데이터 리트라이 + Anthropic 프롬프트 캐싱 적용

**Architecture:** (1) `fear-and-greed` 패키지로 CNN 원본 Fear & Greed Index 수집, VIX 추정 로직 삭제 (2) 매크로 데이터 수집 전체에 3회 리트라이 적용 (3) LangChain ChatAnthropic의 `cache_control`로 system prompt 캐싱

**Tech Stack:** Python 3.12, Pydantic, LangChain (langchain-anthropic), yfinance, fear-and-greed

---

## 파일 구조

| 파일 | 역할 | 변경 |
|------|------|------|
| `src/pipelines/daily_report/stages/ingest_stage.py` | CNN Fear & Greed + 매크로 리트라이 | 수정 |
| `tests/pipelines/daily_report/test_ingest_stage.py` | 리트라이/폴백 테스트 | 수정 |
| `src/pipelines/daily_report/stages/map_stage.py` | 캐싱 적용 | 수정 |
| `src/pipelines/daily_report/stages/shuffle_stage.py` | 캐싱 적용 | 수정 |
| `src/pipelines/daily_report/stages/reduce_stage.py` | 캐싱 적용 | 수정 |
| `src/pipelines/daily_report/stages/wrapup_stage.py` | 캐싱 적용 | 수정 |
| `pyproject.toml` | `fear-and-greed` 의존성 추가 | 수정 |

---

## Task 1: CNN Fear & Greed + 매크로 데이터 리트라이

현재 `_fetch_macro()`는 VIX를 3단계(30/50/70)로 이산 분류하고, API 실패 시 로그만 남기고 0.0으로 폴백한다. CNN 원본 Fear & Greed를 사용하고, 모든 매크로 데이터 수집에 3회 리트라이를 적용한다.

**Files:**
- Modify: `pyproject.toml` (의존성 추가)
- Modify: `src/pipelines/daily_report/stages/ingest_stage.py`
- Modify: `tests/pipelines/daily_report/test_ingest_stage.py`

- [ ] **Step 1: `fear-and-greed` 의존성 추가**

```bash
cd .worktrees/refactor/daily-pipeline-improvements && uv add fear-and-greed
```

- [ ] **Step 2: 리트라이 헬퍼 + CNN Fear & Greed 테스트 작성**

`tests/pipelines/daily_report/test_ingest_stage.py`에 추가:

```python
from unittest.mock import MagicMock, patch

from src.pipelines.daily_report.stages.ingest_stage import _fetch_with_retry


def test_fetch_with_retry_succeeds_first_try():
    """첫 시도에 성공하면 바로 반환."""
    fn = MagicMock(return_value=42.0)
    assert _fetch_with_retry(fn, "test") == 42.0
    assert fn.call_count == 1


def test_fetch_with_retry_succeeds_after_failures():
    """2회 실패 후 3회째 성공."""
    fn = MagicMock(side_effect=[Exception("fail"), Exception("fail"), 42.0])
    assert _fetch_with_retry(fn, "test") == 42.0
    assert fn.call_count == 3


def test_fetch_with_retry_all_fail_returns_none():
    """3회 모두 실패하면 None 반환."""
    fn = MagicMock(side_effect=Exception("fail"))
    assert _fetch_with_retry(fn, "test") is None
    assert fn.call_count == 3


@patch("src.pipelines.daily_report.stages.ingest_stage.fear_and_greed")
def test_fetch_macro_uses_cnn_fear_greed(mock_fg):
    """CNN Fear & Greed 값을 사용하는지 확인."""
    from src.pipelines.daily_report.stages.ingest_stage import _fetch_fear_greed

    mock_fg.get.return_value = MagicMock(value=65.3)
    result = _fetch_fear_greed()
    assert result == 65


@patch("src.pipelines.daily_report.stages.ingest_stage.fear_and_greed")
def test_fetch_fear_greed_failure_returns_none(mock_fg):
    """CNN API 실패 시 None 반환."""
    from src.pipelines.daily_report.stages.ingest_stage import _fetch_fear_greed

    mock_fg.get.side_effect = Exception("CNN down")
    result = _fetch_fear_greed()
    assert result is None
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `cd .worktrees/refactor/daily-pipeline-improvements && uv run pytest tests/pipelines/daily_report/test_ingest_stage.py::test_fetch_with_retry_succeeds_first_try -xvs`
Expected: FAIL (ImportError - `_fetch_with_retry` 미정의)

- [ ] **Step 4: 리트라이 헬퍼 + CNN Fear & Greed 구현**

`src/pipelines/daily_report/stages/ingest_stage.py` 수정:

import 추가:
```python
import time
from typing import Any, Callable

import fear_and_greed
```

리트라이 헬퍼 함수 추가:
```python
MACRO_MAX_RETRIES = 3
MACRO_RETRY_DELAY = 1.0


def _fetch_with_retry(
    fn: Callable[[], Any],
    label: str,
    max_retries: int = MACRO_MAX_RETRIES,
) -> Any | None:
    """매크로 데이터 수집 공통 리트라이. 모두 실패 시 None 반환."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            logger.warning("%s fetch failed (attempt %d/%d): %s", label, attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                time.sleep(MACRO_RETRY_DELAY)
    return None
```

CNN Fear & Greed 함수 추가:
```python
def _fetch_fear_greed() -> int | None:
    """CNN Fear & Greed Index 조회. 실패 시 None."""
    result = _fetch_with_retry(fear_and_greed.get, "Fear & Greed")
    if result is None:
        return None
    return round(result.value)
```

- [ ] **Step 5: `_fetch_macro`를 리트라이 기반으로 리팩토링**

`_fetch_macro` 전체를 교체:

```python
def _fetch_macro(date: str) -> MacroSnapshot:
    """주어진 날짜의 매크로 지표 수집."""

    def _get_pct_change(ticker: str) -> float | None:
        data = yf.Ticker(ticker).history(period="2d")
        if len(data) < 2:
            return None
        return round(
            (data["Close"].iloc[-1] - data["Close"].iloc[-2]) / data["Close"].iloc[-2] * 100, 2
        )

    # 미국 시장
    us_tickers = {"S&P500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI"}
    us_markets = {}
    for name, symbol in us_tickers.items():
        result = _fetch_with_retry(lambda s=symbol: _get_pct_change(s), f"US:{name}")
        us_markets[name] = result if result is not None else 0.0

    # 한국 시장
    kr_tickers = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    kr_markets = {}
    for name, symbol in kr_tickers.items():
        result = _fetch_with_retry(lambda s=symbol: _get_pct_change(s), f"KR:{name}")
        kr_markets[name] = result if result is not None else 0.0

    # VIX
    def _get_vix() -> float:
        data = yf.Ticker("^VIX").history(period="1d")
        return round(data["Close"].iloc[-1], 1)

    vix = _fetch_with_retry(_get_vix, "VIX")
    if vix is None:
        vix = 0.0

    # Fear & Greed (CNN)
    fear_greed = _fetch_fear_greed()
    if fear_greed is None:
        fear_greed = 50

    # KRW/USD
    def _get_krw_usd() -> float:
        data = yf.Ticker("KRW=X").history(period="1d")
        return round(data["Close"].iloc[-1], 1)

    krw_usd = _fetch_with_retry(_get_krw_usd, "KRW/USD")
    if krw_usd is None:
        krw_usd = 0.0

    return MacroSnapshot(
        date=date,
        us_markets=us_markets,
        kr_markets=kr_markets,
        vix=vix,
        fear_greed=fear_greed,
        krw_usd=krw_usd,
    )
```

기존 VIX 기반 Fear & Greed 계산 로직(if/elif/else 블록) 삭제. `from datetime import timedelta` import도 삭제 (사용처 없음).

- [ ] **Step 6: 기존 테스트 업데이트**

`test_fetch_macro_handles_api_failures`에서 `fear_and_greed` mock 추가:

```python
@patch("src.pipelines.daily_report.stages.ingest_stage.fear_and_greed")
@patch("yfinance.Ticker")
def test_fetch_macro_handles_api_failures(mock_ticker, mock_fg):
    """_fetch_macro가 API 실패 시 기본값을 반환하는지 테스트."""
    mock_ticker.return_value.history.side_effect = Exception("yfinance 다운")
    mock_fg.get.side_effect = Exception("CNN 다운")

    macro = _fetch_macro("2026-04-14")

    assert macro.vix == 0.0
    assert macro.fear_greed == 50  # CNN 실패 시 50
    assert macro.us_markets["S&P500"] == 0.0
    assert macro.kr_markets["KOSPI"] == 0.0
    assert macro.krw_usd == 0.0
```

- [ ] **Step 7: 전체 테스트 실행**

Run: `cd .worktrees/refactor/daily-pipeline-improvements && uv run pytest tests/pipelines/daily_report/test_ingest_stage.py -xvs -k "not real_data"`
Expected: ALL PASS

- [ ] **Step 8: 커밋**

```bash
git add pyproject.toml uv.lock src/pipelines/daily_report/stages/ingest_stage.py tests/pipelines/daily_report/test_ingest_stage.py
git commit -m "feat(ingest): use CNN Fear & Greed Index + add macro data retry"
```

---

## Task 2: Provider 조건부 프롬프트 캐싱

Anthropic API는 `cache_control: {"type": "ephemeral"}`로 프롬프트 캐싱을 지원하지만 OpenAI에선 미지원. `StageLLMConfig.build_messages()`에서 provider에 따라 조건부 적용한다.

**Files:**
- Modify: `src/pipelines/daily_report/config.py` (`build_messages` 메서드 추가)
- Modify: `src/pipelines/daily_report/stages/map_stage.py`
- Modify: `src/pipelines/daily_report/stages/shuffle_stage.py`
- Modify: `src/pipelines/daily_report/stages/reduce_stage.py`
- Modify: `src/pipelines/daily_report/stages/wrapup_stage.py`
- Create: `tests/pipelines/daily_report/test_config.py`

- [ ] **Step 1: `build_messages` 테스트 작성**

`tests/pipelines/daily_report/test_config.py` 생성:

```python
"""StageLLMConfig 테스트."""

from langchain_core.messages import HumanMessage, SystemMessage

from src.pipelines.daily_report.config import StageLLMConfig


def test_build_messages_anthropic_has_cache_control():
    """Anthropic provider일 때 system message에 cache_control 추가."""
    cfg = StageLLMConfig(provider="anthropic", model="test-model", temperature=0.2)
    messages = cfg.build_messages("system prompt", "user prompt")

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == "system prompt"
    assert messages[0].additional_kwargs["cache_control"] == {"type": "ephemeral"}
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "user prompt"


def test_build_messages_openai_no_cache_control():
    """OpenAI provider일 때 cache_control 없음."""
    cfg = StageLLMConfig(provider="openai", model="test-model", temperature=0.2)
    messages = cfg.build_messages("system prompt", "user prompt")

    assert len(messages) == 2
    assert messages[0].additional_kwargs == {}
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd .worktrees/refactor/daily-pipeline-improvements && uv run pytest tests/pipelines/daily_report/test_config.py -xvs`
Expected: FAIL (AttributeError - `build_messages` 미정의)

- [ ] **Step 3: `StageLLMConfig.build_messages` 구현**

`src/pipelines/daily_report/config.py` 수정 - `StageLLMConfig`에 메서드 추가:

import 추가:
```python
from langchain_core.messages import HumanMessage, SystemMessage
```

`StageLLMConfig`에 메서드 추가:
```python
    def build_messages(self, system_prompt: str, user_prompt: str) -> list:
        """LLM 메시지 리스트 생성. Anthropic이면 system prompt 캐싱 적용."""
        kwargs = {}
        if self.provider == "anthropic":
            kwargs["cache_control"] = {"type": "ephemeral"}
        return [
            SystemMessage(content=system_prompt, additional_kwargs=kwargs),
            HumanMessage(content=user_prompt),
        ]
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `cd .worktrees/refactor/daily-pipeline-improvements && uv run pytest tests/pipelines/daily_report/test_config.py -xvs`
Expected: ALL PASS

- [ ] **Step 5: 4개 스테이지에서 `build_messages` 사용**

각 스테이지에서 `SystemMessage`/`HumanMessage` 직접 생성을 `build_messages` 호출로 교체.

**map_stage.py** (`_analyze_chunk` 함수):
```python
    # Before:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # After:
    messages = MAP_LLM.build_messages(system_prompt, user_prompt)
```

`SystemMessage`, `HumanMessage` import 삭제 (더 이상 직접 사용 안 함).

**shuffle_stage.py** (`_normalize_themes` 함수):
```python
    # Before:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # After:
    messages = SHUFFLE_LLM.build_messages(system_prompt, user_prompt)
```

`SystemMessage`, `HumanMessage` import 삭제.

**reduce_stage.py** (`_analyze_theme` 함수):
```python
    # Before:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # After:
    messages = REDUCE_LLM.build_messages(system_prompt, user_prompt)
```

`SystemMessage`, `HumanMessage` import 삭제.

**wrapup_stage.py** (`_generate_insights` 함수):
```python
    # Before:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # After:
    messages = WRAPUP_LLM.build_messages(system_prompt, user_prompt)
```

`SystemMessage`, `HumanMessage` import 삭제.

- [ ] **Step 6: 전체 테스트 통과 확인**

Run: `cd .worktrees/refactor/daily-pipeline-improvements && uv run pytest tests/pipelines/daily_report/ -xvs -k "not real_data and not test_models"`
Expected: ALL PASS

- [ ] **Step 7: 커밋**

```bash
git add src/pipelines/daily_report/config.py tests/pipelines/daily_report/test_config.py src/pipelines/daily_report/stages/map_stage.py src/pipelines/daily_report/stages/shuffle_stage.py src/pipelines/daily_report/stages/reduce_stage.py src/pipelines/daily_report/stages/wrapup_stage.py
git commit -m "perf(pipeline): add provider-aware prompt caching via StageLLMConfig.build_messages"
```

---

## 예상 절감 효과 (Task 2)

| Stage | System Prompt 크기 | 호출 횟수/일 | 캐싱 절감 |
|-------|-------------------|-------------|----------|
| Map | ~2,500 토큰 (V4 + 예시) | 2-4 (청크) | ~90% (동일 프롬프트) |
| Shuffle | ~200 토큰 | 5-15 (카테고리) | ~90% |
| Reduce | ~300 토큰 | 10-30 (테마) | ~90% |
| Wrapup | ~200 토큰 | 1 | 0% (단일 호출) |

Anthropic 캐싱 가격: 캐시 쓰기 25% 할증, 캐시 읽기 90% 할인. 2회차부터 절감.
OpenAI로 전환 시: `cache_control` 자동 제외, 동작 변경 없음.
