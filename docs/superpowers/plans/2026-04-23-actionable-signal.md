# Actionable Investment Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clear, actionable investment signals to `jarvis analyze` command with timing, signal strength, and concrete reasons

**Architecture:** Enhance existing `DeepDivePipeline` with `ActionableSignalOutput` model + `generate_actionable_signal()` LLM function. Reuse 5 existing tools (technical, news, fundamental, disclosure, flow). Add warnings collection for partial failures.

**Tech Stack:** Python 3.12+, Pydantic, LangChain, Rich (CLI), pytest

---

## File Structure

### Files to Create
- `src/llm/utils.py` - LLM retry utility (moved from daily_report)
- `tests/llm/test_models.py` - Model validation tests
- `tests/llm/test_utils.py` - Retry logic tests  
- `tests/pipelines/test_deep_dive_signal.py` - Integration tests
- `tests/cli/test_analyze_signal.py` - E2E CLI tests

### Files to Modify
- `src/llm/models.py` - Add `ActionableSignalOutput`, `ActionableSignalInput`
- `src/llm/analyzer.py` - Add `generate_actionable_signal()` function
- `src/pipelines/deep_dive.py` - Add warnings collection + actionable_signal field
- `src/pipelines/daily_report/llm_utils.py` - Re-export from src.llm.utils
- `src/cli/main.py` - Add Rich Panel formatting + warnings display

---

## Task 1: ActionableSignalOutput Model

**Files:**
- Modify: `src/llm/models.py`
- Test: `tests/llm/test_models.py` (create)

- [ ] **Step 1: Write failing test for valid ActionableSignalOutput**

```python
# tests/llm/test_models.py
import pytest
from pydantic import ValidationError

from src.llm.models import ActionableSignalOutput


def test_actionable_signal_output_valid():
    """Test valid ActionableSignalOutput creation."""
    signal = ActionableSignalOutput(
        action="매수",
        timing="지금",
        signal_strength=8,
        headline="매수. 지금. 이유: RSI 과매도",
        primary_reason="RSI 28 (과매도)",
        supporting_reasons=["실적 양호", "거래량 증가"],
        risks=["금리 인상 위험"],
        invalidation_point="$145.20",
        confidence=0.82,
    )
    
    assert signal.action == "매수"
    assert signal.timing == "지금"
    assert signal.signal_strength == 8
    assert "매수" in signal.headline
    assert len(signal.supporting_reasons) == 2
    assert len(signal.risks) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_models.py::test_actionable_signal_output_valid -v`  
Expected: FAIL with "ImportError: cannot import name 'ActionableSignalOutput'"

- [ ] **Step 3: Add ActionableSignalOutput model**

```python
# src/llm/models.py
# Add after IntegratedAnalysisOutput

from typing import Literal  # Add to imports at top
from pydantic import Field  # Add to imports at top


# Actionable Signal I/O
class ActionableSignalInput(BaseModel):
    """Input for actionable signal generation."""

    ticker: str
    technical_summary: str  # Formatted string from TechnicalSummaryOutput
    news_analysis: str  # Formatted string from NewsAnalysisOutput
    fundamental_summary: str  # Formatted string from FundamentalSummaryOutput
    disclosure_text: str  # Formatted disclosure items
    flow_text: str  # Formatted investor flow data


class ActionableSignalOutput(BaseModel):
    """명확한 투자 신호 출력."""

    action: Literal["매수", "매도", "관망"]
    timing: Literal["지금", "조정_대기", "보류"]
    signal_strength: int = Field(ge=1, le=10, description="신호 강도 1-10")
    headline: str = Field(description="한 문장 요약 (action + timing + 핵심 이유)")
    primary_reason: str = Field(description="가장 강한 근거 1개 (구체적 숫자 포함)")
    supporting_reasons: list[str] = Field(
        min_length=2, max_length=3, description="부가 근거 2-3개"
    )
    risks: list[str] = Field(min_length=1, description="리스크 요인")
    invalidation_point: str = Field(description="손절가 (stop-loss 가격)")
    confidence: float = Field(ge=0.0, le=1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_models.py::test_actionable_signal_output_valid -v`  
Expected: PASS

- [ ] **Step 5: Write failing test for invalid action value**

```python
# tests/llm/test_models.py

def test_actionable_signal_output_invalid_action():
    """Test that invalid action value raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        ActionableSignalOutput(
            action="홀드",  # Invalid, only "매수/매도/관망" allowed
            timing="지금",
            signal_strength=8,
            headline="홀드. 지금. 이유: 테스트",
            primary_reason="RSI 50",
            supporting_reasons=["테스트1", "테스트2"],
            risks=["테스트 리스크"],
            invalidation_point="$100",
            confidence=0.5,
        )
    
    errors = exc_info.value.errors()
    assert any("action" in str(e["loc"]) for e in errors)
```

- [ ] **Step 6: Run test to verify it passes (Literal validation)**

Run: `uv run pytest tests/llm/test_models.py::test_actionable_signal_output_invalid_action -v`  
Expected: PASS (Pydantic Literal validation already works)

- [ ] **Step 7: Write failing test for signal_strength range**

```python
# tests/llm/test_models.py

def test_actionable_signal_output_signal_strength_range():
    """Test that signal_strength must be 1-10."""
    # Too high
    with pytest.raises(ValidationError):
        ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=11,  # Invalid, > 10
            headline="매수. 지금. 이유: 테스트",
            primary_reason="RSI 28",
            supporting_reasons=["테스트1", "테스트2"],
            risks=["리스크"],
            invalidation_point="$100",
            confidence=0.5,
        )
    
    # Too low
    with pytest.raises(ValidationError):
        ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=0,  # Invalid, < 1
            headline="매수. 지금. 이유: 테스트",
            primary_reason="RSI 28",
            supporting_reasons=["테스트1", "테스트2"],
            risks=["리스크"],
            invalidation_point="$100",
            confidence=0.5,
        )
```

- [ ] **Step 8: Run test to verify it passes (Field validation)**

Run: `uv run pytest tests/llm/test_models.py::test_actionable_signal_output_signal_strength_range -v`  
Expected: PASS (Pydantic Field(ge=1, le=10) validation already works)

- [ ] **Step 9: Commit**

```bash
git add src/llm/models.py tests/llm/test_models.py
git commit -m "feat: add ActionableSignalOutput model with validation

- Add ActionableSignalOutput with action/timing/signal_strength fields
- Add ActionableSignalInput for LLM prompt data
- Literal validation for action (매수/매도/관망) and timing (지금/조정_대기/보류)
- Field validation for signal_strength (1-10), supporting_reasons (2-3), risks (1+)
- Unit tests for valid/invalid cases

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: LLM Retry Utility

**Files:**
- Create: `src/llm/utils.py`
- Modify: `src/pipelines/daily_report/llm_utils.py` (re-export)
- Test: `tests/llm/test_utils.py` (create)

- [ ] **Step 1: Write failing test for successful LLM retry**

```python
# tests/llm/test_utils.py
import asyncio
from unittest.mock import AsyncMock

import pytest

from src.llm.models import ActionableSignalOutput
from src.llm.utils import invoke_llm_with_retry


@pytest.mark.asyncio
async def test_invoke_llm_with_retry_success():
    """Test successful LLM invocation on first try."""
    mock_llm = AsyncMock()
    mock_output = ActionableSignalOutput(
        action="매수",
        timing="지금",
        signal_strength=8,
        headline="매수. 지금. 이유: RSI 과매도",
        primary_reason="RSI 28 (과매도)",
        supporting_reasons=["실적 양호", "거래량 증가"],
        risks=["금리 인상"],
        invalidation_point="$145.20",
        confidence=0.82,
    )
    
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=mock_output
    )
    
    result = await invoke_llm_with_retry(
        llm=mock_llm,
        output_model=ActionableSignalOutput,
        messages=[{"role": "user", "content": "test"}],
        config={},
        max_retries=3,
        timeout_seconds=60.0,
    )
    
    assert result.action == "매수"
    assert result.signal_strength == 8
    assert mock_llm.with_structured_output.return_value.ainvoke.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_utils.py::test_invoke_llm_with_retry_success -v`  
Expected: FAIL with "ImportError: cannot import name 'invoke_llm_with_retry' from 'src.llm.utils'"

- [ ] **Step 3: Create src/llm/utils.py with invoke_llm_with_retry**

```python
# src/llm/utils.py
"""LLM 호출 유틸리티."""

import asyncio
import logging

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ValidationError


logger = logging.getLogger(__name__)


async def invoke_llm_with_retry(
    llm,
    output_model: type[BaseModel],
    messages: list,
    config: dict | None = None,
    max_retries: int = 3,
    timeout_seconds: float = 60.0,
) -> BaseModel:
    """
    타임아웃 + exponential backoff 재시도가 적용된 LLM 호출.

    Args:
        llm: LangChain LLM 인스턴스
        output_model: 구조화된 출력 Pydantic 모델
        messages: LangChain 메시지 리스트
        config: LangSmith 설정
        max_retries: 최대 재시도 횟수
        timeout_seconds: 호출당 타임아웃 (초)

    Returns:
        파싱된 Pydantic 모델 인스턴스

    Raises:
        마지막 시도 실패 시 원본 예외를 그대로 raise
    """
    if config is None:
        config = {}
    
    llm_with_output = llm.with_structured_output(output_model)
    last_exception = None
    original_msg_count = len(messages)
    messages_to_send = list(messages)

    for attempt in range(max_retries):
        try:
            response = await asyncio.wait_for(
                llm_with_output.ainvoke(messages_to_send, config=config),
                timeout=timeout_seconds,
            )
            return response
        except TimeoutError:
            last_exception = TimeoutError(f"LLM call timed out after {timeout_seconds}s")
            logger.warning(
                "LLM timeout (attempt %d/%d, %ds)",
                attempt + 1,
                max_retries,
                timeout_seconds,
            )
        except Exception as e:
            last_exception = e

            # ValidationError면 피드백 메시지를 다음 시도에 추가
            if isinstance(e, ValidationError):
                feedback_parts = ["⚠️ 검증 실패:\n"]
                error_summary = []

                for error in e.errors():
                    field = ".".join(str(loc) for loc in error["loc"])
                    msg = error["msg"]
                    ctx = error.get("ctx", {})

                    feedback_parts.append(f"❌ {field}: {msg}\n")
                    error_summary.append(f"{field}: {msg}")

                    if "spec" in ctx:
                        feedback_parts.append(ctx["spec"])
                        feedback_parts.append("")

                    if "examples" in ctx:
                        feedback_parts.append("✅ 올바른 예시:")
                        for ex in ctx["examples"]:
                            feedback_parts.append(f"- {ex}")
                        feedback_parts.append("")

                feedback_parts.append("위 요구사항을 정확히 지켜서 다시 생성해주세요.")

                feedback_message = HumanMessage(content="\n".join(feedback_parts))
                messages_to_send = messages[:original_msg_count] + [feedback_message]

                logger.warning(
                    "ValidationError (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    "; ".join(error_summary),
                )
            else:
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )

        if attempt < max_retries - 1:
            wait_time = 2**attempt
            await asyncio.sleep(wait_time)

    raise last_exception
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_utils.py::test_invoke_llm_with_retry_success -v`  
Expected: PASS

- [ ] **Step 5: Write failing test for timeout retry**

```python
# tests/llm/test_utils.py

@pytest.mark.asyncio
async def test_invoke_llm_with_retry_timeout_then_success():
    """Test successful retry after timeout."""
    mock_llm = AsyncMock()
    mock_output = ActionableSignalOutput(
        action="매수",
        timing="지금",
        signal_strength=7,
        headline="매수. 지금. 이유: 테스트",
        primary_reason="RSI 30",
        supporting_reasons=["테스트1", "테스트2"],
        risks=["테스트 리스크"],
        invalidation_point="$100",
        confidence=0.7,
    )
    
    # First call times out, second succeeds
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=[asyncio.TimeoutError(), mock_output]
    )
    
    result = await invoke_llm_with_retry(
        llm=mock_llm,
        output_model=ActionableSignalOutput,
        messages=[{"role": "user", "content": "test"}],
        config={},
        max_retries=3,
        timeout_seconds=1.0,
    )
    
    assert result.action == "매수"
    assert mock_llm.with_structured_output.return_value.ainvoke.call_count == 2
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_utils.py::test_invoke_llm_with_retry_timeout_then_success -v`  
Expected: PASS

- [ ] **Step 7: Update daily_report llm_utils.py to re-export**

```python
# src/pipelines/daily_report/llm_utils.py
"""Daily report 파이프라인용 LLM 호출 유틸리티."""

# Re-export from common location for backward compatibility
from src.llm.utils import invoke_llm_with_retry


__all__ = ["invoke_llm_with_retry"]
```

- [ ] **Step 8: Run daily_report tests to verify backward compatibility**

Run: `uv run pytest tests/pipelines/daily_report/ -v -k llm`  
Expected: PASS (existing tests still work)

- [ ] **Step 9: Commit**

```bash
git add src/llm/utils.py src/pipelines/daily_report/llm_utils.py tests/llm/test_utils.py
git commit -m "refactor: move invoke_llm_with_retry to src.llm.utils

- Create src/llm/utils.py with invoke_llm_with_retry function
- Support timeout + exponential backoff + ValidationError feedback
- Re-export from daily_report/llm_utils.py for backward compatibility
- Add unit tests for success and retry scenarios

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: generate_actionable_signal() Function

**Files:**
- Modify: `src/llm/analyzer.py`
- Test: Integration test in Task 4

- [ ] **Step 1: Add imports to analyzer.py**

```python
# src/llm/analyzer.py
# Add to existing imports at top

from src.llm.models import (
    # ... existing imports ...
    ActionableSignalInput,
    ActionableSignalOutput,
)
from src.llm.utils import invoke_llm_with_retry
```

- [ ] **Step 2: Add constants for timeout/retries**

```python
# src/llm/analyzer.py
# Add after imports, before functions

ANALYZE_LLM_TIMEOUT = 60.0  # 60 seconds for analyze (vs 180s for daily_report)
ANALYZE_LLM_MAX_RETRIES = 3
```

- [ ] **Step 3: Add generate_actionable_signal() function**

```python
# src/llm/analyzer.py
# Add at end of file


async def generate_actionable_signal(
    input_data: ActionableSignalInput,
    llm: BaseChatModel,
) -> ActionableSignalOutput:
    """
    5개 팩터를 종합한 명확한 투자 신호 생성.

    Args:
        input_data: Actionable signal input data (formatted summaries)
        llm: LangChain chat model to use for analysis

    Returns:
        Actionable signal with action, timing, signal_strength, reasons, risks
    """
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """당신은 실전 투자자입니다. **지금 뭘 해야 하는지** 명확히 말하세요.

규칙:
- **signal_strength (1-10)**: 5개 팩터 종합 평가
  - 기술적 지표 (8개 컴포넌트 평균)
  - 뉴스 감성 (긍정/부정 강도)
  - 펀더멘탈 (밸류에이션)
  - 공시 (중요 이벤트 영향)
  - 수급 (외인/기관 흐름, 한국만)
  - 1-3: 약한 신호 (불확실성 높음)
  - 4-6: 중간 신호 (추가 관찰 필요)
  - 7-10: 강한 신호 (명확한 방향성)

- **timing 결정**: 
  1. 기술 지표 1차 평가 (8개 컴포넌트 종합)
     - 긍정적 → "지금" 힌트
     - 과매수/과매도 → "조정_대기" 힌트
     - 혼재 → "보류" 힌트
  2. LLM 최종 판단 (모든 팩터 고려)
     - 공시: 수주잔고, 대규모 계약 → 기술 지표 약해도 "지금" 가능
     - 펀더멘탈: 실적 개선, 밸류에이션 매력
     - 매크로: 섹터 모멘텀, 정책 수혜
     - 뉴스: 호재/악재 강도
     - 수급: 외인/기관 집중 매수
  3. Override 원칙: "기술적으로 중립이어도, 강력한 펀더멘탈 모멘텀(예: 수주잔고 급증)이 있으면 '지금' 추천"

- headline: "{action}. {timing}. 이유: {핵심}" 형식
- primary_reason: 반드시 구체적 숫자 포함 (RSI 28, P/E 12, 거래량 2.3배 등)
- supporting_reasons: 2-3개만, 각각 한 문장
- invalidation_point: 손절 가격 명시 (예: "$145.20 (200일선)")
""",
        ),
        (
            "user",
            """종목: {ticker}

**기술적 분석** (8 components: Minervini, Velocity, CRSI, Volume, Patterns, Supertrend, Divergence, Risk):
{technical_summary}

**뉴스 분석**:
{news_analysis}

**펀더멘탈**:
{fundamental_summary}

**공시 (최근 3개월)**:
{disclosure_text}

**수급 동향** (외인/기관 순매수, 한국주식만):
{flow_text}

위 5개 팩터를 종합해서 명확한 투자 신호를 생성하세요.""",
        ),
    ])

    messages = prompt.format_messages(
        ticker=input_data.ticker,
        technical_summary=input_data.technical_summary,
        news_analysis=input_data.news_analysis,
        fundamental_summary=input_data.fundamental_summary,
        disclosure_text=input_data.disclosure_text,
        flow_text=input_data.flow_text,
    )

    return await invoke_llm_with_retry(
        llm=llm,
        output_model=ActionableSignalOutput,
        messages=messages,
        config={},
        max_retries=ANALYZE_LLM_MAX_RETRIES,
        timeout_seconds=ANALYZE_LLM_TIMEOUT,
    )
```

- [ ] **Step 4: Verify analyzer.py syntax**

Run: `uv run python -m py_compile src/llm/analyzer.py`  
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add src/llm/analyzer.py
git commit -m "feat: add generate_actionable_signal() LLM function

- Add generate_actionable_signal() with 5-factor prompt
- System prompt: signal_strength (1-10), timing decision logic, format rules
- User prompt: technical/news/fundamental/disclosure/flow summaries
- Use invoke_llm_with_retry with 60s timeout
- Temperature 0.1 for consistency (set in caller)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: DeepDivePipeline Integration

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Test: `tests/pipelines/test_deep_dive_signal.py` (create)

- [ ] **Step 1: Write failing test for actionable_signal in pipeline**

```python
# tests/pipelines/test_deep_dive_signal.py
from unittest.mock import AsyncMock, Mock

import pytest

from src.llm.models import ActionableSignalOutput, TechnicalSummaryOutput, NewsAnalysisOutput
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.technical.models import TechnicalResult, ComponentResult


@pytest.mark.asyncio
async def test_deep_dive_returns_actionable_signal():
    """Test that DeepDivePipeline.run() returns actionable_signal field."""
    # Mock tools
    mock_tech_tool = AsyncMock()
    mock_tech_tool.execute = AsyncMock(
        return_value=Mock(
            success=True,
            data=TechnicalResult(
                ticker="AAPL",
                price=150.0,
                change_pct=1.5,
                components=[
                    ComponentResult(
                        name="Minervini",
                        status="매수",
                        confidence=0.8,
                        signals=["상승추세"],
                        evidence=["200일선 상향"],
                        score=80,
                    )
                ],
                strategies=[],
            ),
        )
    )
    
    mock_news_tool = AsyncMock()
    mock_news_tool.execute = AsyncMock(
        return_value=Mock(success=True, data=[])
    )
    
    mock_llm = AsyncMock()
    mock_llm.with_structured_output = Mock()
    
    # Mock LLM responses
    tech_summary = TechnicalSummaryOutput(
        summary="매수 신호",
        key_insights=["RSI 과매도"],
        recommendation="매수",
        confidence=0.8,
        rationale="기술적 강세",
    )
    
    news_analysis = NewsAnalysisOutput(
        sentiment="긍정",
        confidence=0.7,
        key_themes=["실적 발표"],
        summary="긍정적 뉴스",
        impact_assessment="호재",
    )
    
    actionable_signal = ActionableSignalOutput(
        action="매수",
        timing="지금",
        signal_strength=8,
        headline="매수. 지금. 이유: RSI 과매도",
        primary_reason="RSI 28 (과매도)",
        supporting_reasons=["실적 양호", "거래량 증가"],
        risks=["금리 인상"],
        invalidation_point="$145.20",
        confidence=0.82,
    )
    
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=[tech_summary, news_analysis, actionable_signal]
    )
    
    pipeline = DeepDivePipeline(
        technical_tool=mock_tech_tool,
        news_tool=mock_news_tool,
        llm=mock_llm,
    )
    
    result = await pipeline.run("AAPL")
    
    assert "actionable_signal" in result
    assert result["actionable_signal"] is not None
    assert result["actionable_signal"].action == "매수"
    assert result["actionable_signal"].timing == "지금"
    assert result["actionable_signal"].signal_strength == 8
    assert "warnings" in result
    assert isinstance(result["warnings"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/test_deep_dive_signal.py::test_deep_dive_returns_actionable_signal -v`  
Expected: FAIL with "KeyError: 'actionable_signal'" or "'warnings'"

- [ ] **Step 3: Add warnings list to deep_dive.py run() method start**

```python
# src/pipelines/deep_dive.py
# In DeepDivePipeline.run() method, add after docstring

async def run(self, ticker: str) -> dict:
    """Run deep dive analysis for a ticker.

    Returns:
        dict with keys:
            ... (existing keys) ...
            - actionable_signal: ActionableSignalOutput | None (명확한 투자 신호)
            - warnings: list[str] (실패한 도구 경고 메시지)
    """
    warnings: list[str] = []  # Add this line
    
    # ... existing code ...
```

- [ ] **Step 4: Update tool error handling to collect warnings**

```python
# src/pipelines/deep_dive.py
# Replace existing news_tool section with:

news_result = await self.news_tool.execute(ticker, limit=10)
if not news_result.success:
    logger.warning(f"News fetch failed for {ticker}: {news_result.error}")
    warnings.append(f"뉴스 데이터 없음: {news_result.error}")
    news_articles = []
else:
    news_articles: list[NewsArticle] = news_result.data

# Replace existing fundamental_tool section with:

fundamental_data = None
fundamental_summary = None
if self.fundamental_tool:
    fund_result = await self.fundamental_tool.execute(ticker)
    if fund_result.success:
        fundamental_data = fund_result.data
        fundamental_summary = await self._generate_fundamental_summary(
            ticker, fundamental_data
        )
    else:
        logger.warning(f"Fundamental data fetch failed for {ticker}: {fund_result.error}")
        warnings.append(f"펀더멘탈 데이터 없음: {fund_result.error}")

# Update optional tools section:

optional_data: dict = {}
if optional_coros:
    opt_results = await asyncio.gather(*optional_coros, return_exceptions=True)
    for key, res in zip(optional_keys, opt_results, strict=True):
        if isinstance(res, Exception):
            logger.warning(f"선택적 툴 '{key}' 실패 (Exception): {res}")
            warnings.append(f"{key} 데이터 없음: {res}")
            optional_data[key] = None
        elif not res.success:
            logger.warning(f"선택적 툴 '{key}' 실패: {res.error}")
            warnings.append(f"{key} 데이터 없음: {res.error}")
            optional_data[key] = None
        else:
            optional_data[key] = res.data
```

- [ ] **Step 5: Add actionable_signal generation before return**

```python
# src/pipelines/deep_dive.py
# Add after integrated_analysis generation, before return statement

# Generate actionable signal
actionable_signal = await self._generate_actionable_signal(
    ticker=ticker,
    technical_summary=technical_summary,
    news_analysis=news_analysis,
    fundamental_summary=fundamental_summary,
    disclosure_items=disclosure_items,
    flow_data=flow_data,
)

return {
    "ticker": ticker,
    "technical": technical_data,
    "technical_summary": technical_summary,
    "news": news_articles,
    "news_analysis": news_analysis,
    "fundamental": fundamental_data,
    "fundamental_summary": fundamental_summary,
    "disclosure": disclosure_items,
    "flow": flow_data,
    "integrated_analysis": integrated_analysis,
    "actionable_signal": actionable_signal,  # Add this line
    "warnings": warnings,  # Add this line
}
```

- [ ] **Step 6: Add _generate_actionable_signal() helper method**

```python
# src/pipelines/deep_dive.py
# Add at end of class, after _generate_integrated_analysis()

from src.llm.models import ActionableSignalInput, ActionableSignalOutput  # Add to imports
from src.llm.analyzer import generate_actionable_signal  # Add to imports


async def _generate_actionable_signal(
    self,
    ticker: str,
    technical_summary: TechnicalSummaryOutput,
    news_analysis: NewsAnalysisOutput | None,
    fundamental_summary: FundamentalSummaryOutput | None,
    disclosure_items: list[DisclosureItem] | None,
    flow_data: InvestorFlow | None,
) -> ActionableSignalOutput:
    """Generate actionable investment signal from all factors."""
    
    # Format technical summary
    tech_text = f"""{technical_summary.summary}

추천: {technical_summary.recommendation} (신뢰도: {technical_summary.confidence:.0%})
근거: {technical_summary.rationale}
핵심 인사이트:
""" + "\n".join(f"- {insight}" for insight in technical_summary.key_insights)
    
    # Format news analysis
    news_text = "N/A"
    if news_analysis:
        news_text = f"""감성: {news_analysis.sentiment} (신뢰도: {news_analysis.confidence:.0%})
요약: {news_analysis.summary}
영향: {news_analysis.impact_assessment}
주요 테마: {", ".join(news_analysis.key_themes)}"""
    
    # Format fundamental summary
    fund_text = "N/A"
    if fundamental_summary:
        fund_text = f"""{fundamental_summary.summary}

밸류에이션: {fundamental_summary.valuation_assessment}
강점:
""" + "\n".join(f"- {s}" for s in fundamental_summary.strengths)
        
        if fundamental_summary.weaknesses:
            fund_text += "\n약점:\n" + "\n".join(
                f"- {w}" for w in fundamental_summary.weaknesses
            )
    
    # Format disclosure
    disclosure_text = "N/A"
    if disclosure_items:
        disclosure_text = "최근 3개월 주요 공시:\n" + "\n".join(
            f"- {item.date.strftime('%Y-%m-%d')}: {item.title}"
            for item in disclosure_items[:5]
        )
    
    # Format flow
    flow_text = "N/A (미국 주식 또는 데이터 없음)"
    if flow_data:
        flow_text = f"""1일: 외국인 {flow_data.foreign_net_1d:+.0f}백만원, 기관 {flow_data.institution_net_1d:+.0f}백만원
5일: 외국인 {flow_data.foreign_net_5d:+.0f}백만원, 기관 {flow_data.institution_net_5d:+.0f}백만원
10일: 외국인 {flow_data.foreign_net_10d:+.0f}백만원, 기관 {flow_data.institution_net_10d:+.0f}백만원"""
    
    input_data = ActionableSignalInput(
        ticker=ticker,
        technical_summary=tech_text,
        news_analysis=news_text,
        fundamental_summary=fund_text,
        disclosure_text=disclosure_text,
        flow_text=flow_text,
    )
    
    return await generate_actionable_signal(input_data, self.llm)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/test_deep_dive_signal.py::test_deep_dive_returns_actionable_signal -v`  
Expected: PASS

- [ ] **Step 8: Write test for warnings collection**

```python
# tests/pipelines/test_deep_dive_signal.py

@pytest.mark.asyncio
async def test_deep_dive_collects_warnings():
    """Test that failed optional tools add warnings to result."""
    mock_tech_tool = AsyncMock()
    mock_tech_tool.execute = AsyncMock(
        return_value=Mock(
            success=True,
            data=TechnicalResult(
                ticker="AAPL",
                price=150.0,
                change_pct=1.5,
                components=[],
                strategies=[],
            ),
        )
    )
    
    # News tool fails
    mock_news_tool = AsyncMock()
    mock_news_tool.execute = AsyncMock(
        return_value=Mock(success=False, error="API rate limit exceeded")
    )
    
    mock_llm = AsyncMock()
    mock_llm.with_structured_output = Mock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=[
            TechnicalSummaryOutput(
                summary="테스트",
                key_insights=["테스트"],
                recommendation="중립",
                confidence=0.5,
                rationale="테스트",
            ),
            ActionableSignalOutput(
                action="관망",
                timing="보류",
                signal_strength=5,
                headline="관망. 보류. 이유: 데이터 부족",
                primary_reason="뉴스 데이터 없음",
                supporting_reasons=["기술적 중립", "테스트"],
                risks=["데이터 부족"],
                invalidation_point="N/A",
                confidence=0.5,
            ),
        ]
    )
    
    pipeline = DeepDivePipeline(
        technical_tool=mock_tech_tool,
        news_tool=mock_news_tool,
        llm=mock_llm,
    )
    
    result = await pipeline.run("AAPL")
    
    assert len(result["warnings"]) > 0
    assert any("뉴스 데이터 없음" in w for w in result["warnings"])
    assert "API rate limit exceeded" in result["warnings"][0]
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/test_deep_dive_signal.py::test_deep_dive_collects_warnings -v`  
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/pipelines/deep_dive.py tests/pipelines/test_deep_dive_signal.py
git commit -m "feat: integrate actionable_signal into DeepDivePipeline

- Add warnings list to collect failed tool errors
- Update error handling to append warnings (news/fundamental/disclosure/flow)
- Add _generate_actionable_signal() helper to format 5 factors
- Return actionable_signal + warnings in pipeline result dict
- Integration tests for signal generation and warnings collection

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: CLI Output with Rich Panel

**Files:**
- Modify: `src/cli/main.py`
- Test: `tests/cli/test_analyze_signal.py` (create)

- [ ] **Step 1: Write failing CLI test**

```python
# tests/cli/test_analyze_signal.py
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app


runner = CliRunner()


def test_analyze_shows_actionable_signal_panel(monkeypatch):
    """Test that analyze command displays actionable signal in Rich Panel."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    # This test will fail until we implement format_actionable_signal
    with patch("src.cli.main.asyncio.run") as mock_run:
        mock_run.return_value = {
            "ticker": "AAPL",
            "actionable_signal": {
                "action": "매수",
                "timing": "지금",
                "signal_strength": 8,
                "headline": "매수. 지금. 이유: RSI 과매도",
                "primary_reason": "RSI 28 (과매도)",
                "supporting_reasons": ["실적 양호", "거래량 증가"],
                "risks": ["금리 인상"],
                "invalidation_point": "$145.20",
                "confidence": 0.82,
            },
            "warnings": [],
        }
        
        result = runner.invoke(app, ["analyze", "AAPL"])
        
        assert result.exit_code == 0
        assert "🎯 투자 신호" in result.output
        assert "매수 | 지금" in result.output
        assert "🔥" in result.output
        assert "🛑 손절가: $145.20" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_analyze_signal.py::test_analyze_shows_actionable_signal_panel -v`  
Expected: FAIL (missing format_actionable_signal or Panel output)

- [ ] **Step 3: Add format_actionable_signal() function to main.py**

```python
# src/cli/main.py
# Add after existing imports

from rich.panel import Panel  # Add to imports if not present

from src.llm.models import ActionableSignalOutput  # Add to imports


def format_actionable_signal(signal: ActionableSignalOutput) -> Panel:
    """Format ActionableSignalOutput as Rich Panel.
    
    Args:
        signal: Actionable signal output
        
    Returns:
        Rich Panel with formatted signal
    """
    fire_emoji = "🔥" * signal.signal_strength
    
    # Check for contradiction warning
    warning_line = ""
    if signal.action in ["매수", "매도"] and signal.signal_strength < 5:
        warning_line = "\n[yellow]⚠️  약한 신호로 명확한 액션 추천 - 재확인 필요[/yellow]\n"
    
    content = f"""[bold cyan]{signal.action} | {signal.timing} | 신호 강도: {fire_emoji} ({signal.signal_strength}/10)[/bold cyan]
{warning_line}
[bold white]{signal.headline}[/bold white]

[bold]주 근거:[/bold] {signal.primary_reason}

[bold]부가 근거:[/bold]
""" + "\n".join(f" • {reason}" for reason in signal.supporting_reasons) + f"""

[bold]리스크:[/bold]
""" + "\n".join(f" • {risk}" for risk in signal.risks) + f"""

[red bold]🛑 손절가: {signal.invalidation_point}[/red bold]
"""
    
    return Panel(content, title="🎯 투자 신호", border_style="cyan")
```

- [ ] **Step 4: Update analyze command to display actionable_signal**

```python
# src/cli/main.py
# In analyze() function, add after integrated_analysis display section:

# Display actionable signal
if result.get("actionable_signal"):
    signal = result["actionable_signal"]
    # Convert dict to ActionableSignalOutput if needed
    if isinstance(signal, dict):
        signal = ActionableSignalOutput(**signal)
    
    console.print("\n")
    console.print(format_actionable_signal(signal))

# Display warnings if any
if result.get("warnings"):
    console.print("\n[yellow]⚠️  다음 데이터를 가져올 수 없었습니다:[/yellow]")
    for warning in result["warnings"]:
        console.print(f"  [yellow]• {warning}[/yellow]")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_analyze_signal.py::test_analyze_shows_actionable_signal_panel -v`  
Expected: PASS

- [ ] **Step 6: Write test for warnings display**

```python
# tests/cli/test_analyze_signal.py

def test_analyze_shows_warnings(monkeypatch):
    """Test that analyze command displays warnings when tools fail."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    with patch("src.cli.main.asyncio.run") as mock_run:
        mock_run.return_value = {
            "ticker": "AAPL",
            "actionable_signal": {
                "action": "관망",
                "timing": "보류",
                "signal_strength": 5,
                "headline": "관망. 보류. 이유: 데이터 부족",
                "primary_reason": "일부 데이터 없음",
                "supporting_reasons": ["기술적 중립", "뉴스 부족"],
                "risks": ["불확실성"],
                "invalidation_point": "N/A",
                "confidence": 0.5,
            },
            "warnings": [
                "뉴스 데이터 없음: API rate limit",
                "펀더멘탈 데이터 없음: yfinance timeout",
            ],
        }
        
        result = runner.invoke(app, ["analyze", "AAPL"])
        
        assert result.exit_code == 0
        assert "⚠️  다음 데이터를 가져올 수 없었습니다:" in result.output
        assert "뉴스 데이터 없음" in result.output
        assert "펀더멘탈 데이터 없음" in result.output
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_analyze_signal.py::test_analyze_shows_warnings -v`  
Expected: PASS

- [ ] **Step 8: Write test for contradiction warning**

```python
# tests/cli/test_analyze_signal.py

def test_analyze_shows_contradiction_warning(monkeypatch):
    """Test that contradiction warning appears for weak signal + strong action."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    with patch("src.cli.main.asyncio.run") as mock_run:
        mock_run.return_value = {
            "ticker": "AAPL",
            "actionable_signal": {
                "action": "매수",  # Strong action
                "timing": "지금",
                "signal_strength": 3,  # Weak signal (< 5)
                "headline": "매수. 지금. 이유: 테스트",
                "primary_reason": "테스트 이유",
                "supporting_reasons": ["테스트1", "테스트2"],
                "risks": ["테스트 리스크"],
                "invalidation_point": "$100",
                "confidence": 0.4,
            },
            "warnings": [],
        }
        
        result = runner.invoke(app, ["analyze", "AAPL"])
        
        assert result.exit_code == 0
        assert "⚠️  약한 신호로 명확한 액션 추천 - 재확인 필요" in result.output
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_analyze_signal.py::test_analyze_shows_contradiction_warning -v`  
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/cli/main.py tests/cli/test_analyze_signal.py
git commit -m "feat: add actionable signal Rich Panel to analyze command

- Add format_actionable_signal() to format signal as Rich Panel
- Display signal strength with 🔥 emoji (1-10 scale)
- Show contradiction warning for weak signal + strong action
- Display warnings section for failed tools
- E2E CLI tests for panel display and warnings

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: End-to-End Manual Test

**Files:**
- None (manual testing)

- [ ] **Step 1: Set environment variables**

```bash
export OPENAI_API_KEY=<your-key>
# Optional:
export ANTHROPIC_API_KEY=<your-key>
export OPENDART_API_KEY=<your-key>
export KIS_APP_KEY=<your-key>
export KIS_APP_SECRET=<your-secret>
```

- [ ] **Step 2: Test with US stock (AAPL)**

Run: `uv run jarvis analyze AAPL --provider openai`  

Expected output:
- ✅ 🎯 투자 신호 Panel appears
- ✅ action: "매수/매도/관망"
- ✅ timing: "지금/조정_대기/보류"
- ✅ signal_strength: 1-10 with 🔥 emoji
- ✅ headline matches "{action}. {timing}. 이유: {핵심}" format
- ✅ primary_reason contains specific numbers (e.g., "RSI 28")
- ✅ supporting_reasons: 2-3 items
- ✅ risks: 1+ items
- ✅ invalidation_point: stop-loss price (e.g., "$145.20")
- ✅ warnings section shows "수급 동향 없음: 미국 주식" (if no KIS_APP_KEY)

- [ ] **Step 3: Test with Korean stock (005930.KS)**

Run: `uv run jarvis analyze 삼성전자 --provider openai`  

Expected:
- ✅ Same panel structure as AAPL
- ✅ If KIS_APP_KEY set: flow data included, no warning
- ✅ If OPENDART_API_KEY set: disclosure data included, no warning
- ✅ If keys missing: appropriate warnings displayed

- [ ] **Step 4: Test with Anthropic provider**

Run: `uv run jarvis analyze MSFT --provider anthropic`  

Expected:
- ✅ Works with Claude model
- ✅ Same output structure

- [ ] **Step 5: Test error case (invalid ticker)**

Run: `uv run jarvis analyze INVALID123`  

Expected:
- ✅ Error message or fallback behavior
- ✅ No crash

- [ ] **Step 6: Verify response time**

Run: `time uv run jarvis analyze NVDA`  

Expected:
- ✅ Completes in < 10 seconds (LLM + data fetching)
- ✅ No timeout errors

- [ ] **Step 7: Test 10 tickers from spec**

```bash
for ticker in AAPL MSFT NVDA TSLA GOOGL 삼성전자 SK하이닉스 NAVER 카카오 현대차; do
  echo "Testing $ticker..."
  uv run jarvis analyze "$ticker" --provider openai
  sleep 2
done
```

Expected:
- ✅ All 10 tickers complete successfully
- ✅ headline format consistent across all
- ✅ primary_reason contains numbers in all cases
- ✅ signal_strength values distributed across 1-10 range

- [ ] **Step 8: Document any issues or inconsistencies**

Create: `MANUAL_TEST_RESULTS.md` (if issues found)

```markdown
# Manual Test Results - 2026-04-23

## Summary
- Tested: 10 tickers (5 US, 5 KR)
- Success rate: X/10
- Issues found: X

## Issues
1. [Issue description]
   - Ticker: AAPL
   - Problem: primary_reason missing numbers
   - Screenshot: [attach if needed]

2. ...

## Recommendations
- [Any prompt tuning needed]
- [Any field validation needed]
```

- [ ] **Step 9: Run all unit + integration tests**

Run: `uv run pytest tests/llm/ tests/pipelines/ tests/cli/ -v`  

Expected:
- ✅ All tests pass
- ✅ No warnings or errors

- [ ] **Step 10: Commit manual test results (if issues found)**

```bash
git add MANUAL_TEST_RESULTS.md  # Only if created
git commit -m "test: manual E2E testing results for actionable signal

Tested 10 tickers across US/KR markets with OpenAI/Anthropic.
[Summary of findings]

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Spec Self-Review

### 1. Spec Coverage

✅ **ActionableSignalOutput model** - Task 1  
✅ **LLM retry utility (moved)** - Task 2  
✅ **generate_actionable_signal() function** - Task 3  
✅ **Pipeline integration (warnings + signal)** - Task 4  
✅ **CLI Rich Panel display** - Task 5  
✅ **Contradiction warning (weak signal + strong action)** - Task 5, Step 3 & Test  
✅ **Warnings display for failed tools** - Task 4 & 5  
✅ **Manual E2E testing (10 tickers)** - Task 6  

**No gaps found.** All spec requirements covered by tasks.

### 2. Placeholder Scan

✅ No "TBD", "TODO", or "implement later"  
✅ All code blocks complete with actual implementation  
✅ All test cases have exact assertions  
✅ All commands have expected output

### 3. Type Consistency

✅ `ActionableSignalOutput` defined in Task 1, used consistently in Tasks 3-6  
✅ `ActionableSignalInput` defined in Task 1, used in Task 3  
✅ `invoke_llm_with_retry` signature consistent across Tasks 2-3  
✅ `warnings: list[str]` type consistent in Tasks 4-5

### 4. Task Dependencies

- Task 2 (utils) must complete before Task 3 (analyzer) ✅
- Task 3 (analyzer) must complete before Task 4 (pipeline) ✅
- Task 4 (pipeline) must complete before Task 5 (CLI) ✅
- Task 5 (CLI) must complete before Task 6 (manual test) ✅

**All dependencies correctly ordered.**

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-actionable-signal.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
