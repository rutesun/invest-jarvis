# Design: Actionable Investment Signal Enhancement

생성일: 2026-04-23  
상태: APPROVED  
Branch: main  
Repo: invest-jarvis

---

## Problem Statement

invest-jarvis는 이미 8개 기능이 작동 중입니다 (기술적 분석, 딥다이브, 포트폴리오 모니터링, 스크리너, 텔레그램 기반 일일 리포트, 티커 리포트, 텔레그램 수집, 티커 해석). 데이터 수집도 되고, 지표도 나옵니다.

하지만 **핵심 인사이트가 부족합니다**. "지금 이 종목을 사야/팔아야 하는 명확한 이유"를 한 문장으로 말해주지 않습니다. 지표만 나열되고, 사용자가 직접 해석해야 합니다.

**기존 `jarvis analyze` 명령어의 문제:**
- 프롬프트가 일반적 ("brief summary", "key insights")
- 타이밍 정보 없음 ("매수" 추천만 있고 "언제"는 없음)
- 신호 강도 불명확 (confidence 0.7이 뭔지 모름)
- 근거가 추상적 ("기술적 지표 양호" → 구체적 숫자 필요)
- 종합 분석이 단순 나열 (서사 부족)

---

## Solution Overview

**Phase 1: Actionable Signal Enhancement (이 문서의 범위)**

기존 `DeepDivePipeline`에 `ActionableSignalOutput` 모델을 추가하여 명확한 투자 신호를 생성합니다. 새로운 기능을 만드는 것이 아니라 **기존 analyze 명령어를 개선**하는 것입니다.

**핵심 변경:**
1. 새 출력 모델: `ActionableSignalOutput` (action, timing, signal_strength, headline, primary_reason, supporting_reasons, risks, invalidation_point)
2. 새 LLM 함수: `generate_actionable_signal()` (temperature 0.1)
3. CLI 출력 개선: Rich Panel 박스로 신호 시각화
4. 에러 처리 개선: warnings 수집 및 표시

---

## Architecture

### System Structure

```
기존 DeepDivePipeline
  ├─ technical_tool → TechnicalSummaryOutput (8 components)
  ├─ news_tool → NewsAnalysisOutput  
  ├─ fundamental_tool → FundamentalSummaryOutput
  ├─ disclosure_tool → 공시 데이터 (SEC 10-Q/8-K, DART)
  ├─ flow_tool → 수급 데이터 (KIS API, 한국주식만)
  │
  └─ [NEW] LLMAnalyzer.generate_actionable_signal()
         ├─ Input: 위 5개 분석 결과 전체
         ├─ Model: ActionableSignalOutput
         ├─ Temperature: 0.1 (테스트 후 조정)
         └─ Output: action, timing, signal_strength, headline, primary_reason, 
                    supporting_reasons, risks, invalidation_point

CLI Flow:
  jarvis analyze AAPL
    → DeepDivePipeline.run()
    → LLMAnalyzer.generate_actionable_signal()
    → Rich Panel 박스 출력 + warnings
```

### Key Components

**1. ActionableSignalOutput Model** (`src/llm/models.py`)

```python
class ActionableSignalOutput(BaseModel):
    """명확한 투자 신호 출력"""
    
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

**필드 설계 결정:**
- `action`: "매수/매도/관망" 3가지만 (명확성)
- `timing`: "지금/조정_대기/보류" 3가지 (애매한 "3일_기다림" 제외)
- `signal_strength`: **1-10 정수 (5개 팩터 종합 + LLM 판단)**
  - 기술적 지표 (8개 컴포넌트 평균)
  - 뉴스 감성 (긍정/부정 강도)
  - 펀더멘탈 (밸류에이션, 성장성)
  - 공시 (중요 이벤트 영향)
  - 수급 (외인/기관 흐름, 한국만)
  - **규칙 기반 아님 - LLM이 맥락 고려해 최종 판단**
  - **모순 허용** (action="매수" + signal_strength=2 가능, CLI에서 경고만)
- `headline`: "{action}. {timing}. 이유: {핵심}" 형식 강제
- `primary_reason`: 반드시 구체적 숫자 포함 (RSI 28, P/E 12 등)
- `invalidation_point`: 손절 가격 명시 (리스크 관리)

**2. LLM Prompt Template** (`src/llm/analyzer.py`)

```python
async def generate_actionable_signal(
    input_data: ActionableSignalInput,
    llm: BaseChatModel,
) -> ActionableSignalOutput:
    """5개 팩터를 종합한 명확한 투자 신호 생성"""
    
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
"""
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

위 5개 팩터를 종합해서 명확한 투자 신호를 생성하세요."""
        ),
    ])
    
    messages = prompt.format_messages(...)
    
    return await invoke_llm_with_retry(
        llm=llm,
        output_model=ActionableSignalOutput,
        messages=messages,
        config={},
        max_retries=3,
        timeout_seconds=60.0,
    )
```

**프롬프트 설계 원칙:**
- System prompt: 역할 명확화 ("실전 투자자")
- 구체적 규칙: timing 3가지, signal_strength 범위, headline 형식
- Context: 5개 팩터 모두 제공 (technical, news, fundamental, disclosure, flow)
- Temperature: 0.1 (일관성 우선, 테스트 후 조정)

**3. CLI Output** (`src/cli/main.py`)

```python
def format_actionable_signal(signal: ActionableSignalOutput) -> Panel:
    """ActionableSignalOutput → Rich Panel"""
    
    fire_emoji = "🔥" * signal.signal_strength
    
    # 모순 체크 (경고만, 에러 아님)
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

**출력 예시:**

```
┌─ 🎯 투자 신호 ────────────────────────────────────────────┐
│ 매수 | 지금 | 신호 강도: 🔥🔥🔥🔥🔥🔥🔥🔥 (8/10)            │
│                                                            │
│ 매수. 지금. 이유: RSI 과매도 + 외국인 3일 연속 순매수      │
│                                                            │
│ 주 근거: RSI 28 (과매도) + 거래량 평균 대비 2.3배 +        │
│          외국인 3일 +$1.2B 순매수                           │
│                                                            │
│ 부가 근거:                                                 │
│  • 실적 발표 긍정적 (10-Q: EPS 예상치 초과 12%)            │
│  • Supertrend 매수 시그널 (ATR 기반)                       │
│                                                            │
│ 리스크:                                                    │
│  • 연준 금리 인상 시 조정 가능성                           │
│                                                            │
│ 🛑 손절가: $145.20 (200일선)                               │
└────────────────────────────────────────────────────────────┘

⚠️  다음 데이터를 가져올 수 없었습니다:
  • 펀더멘탈 데이터: yfinance API 응답 없음
  • 수급 동향: 미국 주식 (KIS API 미지원)
```

---

## Data Flow

### 전체 흐름 (jarvis analyze AAPL)

```
1. CLI 진입
   └─ ticker="AAPL", provider="openai"

2. DeepDivePipeline.run("AAPL")
   ├─ technical_tool.analyze("AAPL")
   │   └─ 8 components (Minervini, Velocity, CRSI, Volume, Patterns, Supertrend, Divergence, Risk)
   │       → TechnicalSummaryOutput
   │       {recommendation: "매수", confidence: 0.75, rationale: [...]}
   │
   ├─ news_tool.search("AAPL")
   │   └─ NewsAnalysisOutput
   │       {sentiment: "긍정", impact: "높음", themes: [...]}
   │
   ├─ fundamental_tool.analyze("AAPL")
   │   └─ FundamentalSummaryOutput
   │       {valuation: "적정", growth: "양호", ...}
   │
   ├─ disclosure_tool.fetch("AAPL")
   │   ├─ 미국: SEC EDGAR (10-Q, 8-K) 최근 3개월
   │   └─ 한국: OpenDART (키워드 스코어링) 최근 3개월
   │       → dict {filings: [...], key_events: [...]}
   │
   └─ flow_tool.get_investor_flow("AAPL")
       └─ 한국주식만: KIS API (외인/기관 순매수)
           → dict {foreign_1d: +500M, institution_5d: -200M, ...}

3. LLMAnalyzer.generate_actionable_signal()
   ├─ Input: {technical, news, fundamental, disclosure, flow}
   ├─ Temperature: 0.1 (테스트 후 조정)
   ├─ Prompt: "5개 팩터 + Volume 포함 8개 컴포넌트를 종합해서 명확한 투자 신호 생성"
   └─ Output: ActionableSignalOutput
       {
         action: "매수",
         timing: "지금",
         signal_strength: 8,  # LLM 판단
         headline: "매수. 지금. 이유: RSI 과매도 + 외국인 3일 연속 순매수",
         primary_reason: "RSI 28 (과매도) + 거래량 평균 대비 2.3배 + 외국인 3일 +$1.2B 순매수",
         supporting_reasons: [
           "실적 발표 긍정적 (10-Q: EPS 예상치 초과 12%)",
           "Supertrend 매수 시그널 (ATR 기반)"
         ],
         risks: ["연준 금리 인상 시 조정 가능성"],
         invalidation_point: "$145.20 (200일선)",
         confidence: 0.82
       }

4. CLI Rich 출력
   ├─ Panel 박스로 formatted 결과 표시
   └─ 실패한 데이터 소스가 있으면 하단에 warnings 섹션 추가
```

### Fallback 처리

| 도구 | 실패 시 동작 | 로그 | 리포트 워닝 |
|------|------------|------|-----------|
| **technical_tool** | **에러 종료** (필수) | `logger.error("technical_tool 실패: {error}")` | N/A (종료) |
| **news_tool** | 빈 리스트로 계속 | `logger.warning("news_tool 실패: {error}")` | "⚠️ 뉴스 데이터 없음: {이유}" |
| **fundamental_tool** | "N/A"로 계속 | `logger.warning("fundamental_tool 실패: {error}")` | "⚠️ 펀더멘탈 데이터 없음: {이유}" |
| **disclosure_tool** | 빈 dict로 계속 | `logger.warning("disclosure_tool 실패: {error}")` | "⚠️ 공시 데이터 없음: {이유}" |
| **flow_tool** | 빈 dict로 계속 | `logger.warning("flow_tool 실패 (정상, 미국주식): {error}")` | "⚠️ 수급 동향 없음: {이유}" |
| **LLM 호출** | 재시도 1-3회 → fallback | `logger.error("LLM 호출 실패, fallback 사용: {error}")` | "⚠️ 신호 생성 실패, 기본 분석 사용" |

---

## Error Handling

### 1. 기존 ToolResult 모델 활용

```python
# src/core/models.py (이미 존재)
class ToolResult(BaseModel):
    success: bool
    data: Any
    error: str | None = None
```

### 2. 파이프라인 에러 핸들링 (기존 패턴 개선)

```python
# src/pipelines/deep_dive.py

async def run(self, ticker: str) -> dict:
    warnings: list[str] = []  # 수집
    
    # 필수: technical_tool (현재 패턴 유지)
    tech_result = await self.technical_tool.execute(ticker)
    if not tech_result.success:
        raise RuntimeError(f"Technical analysis failed: {tech_result.error}")
    
    # 선택: news_tool (RuntimeError → warning으로 변경)
    news_articles = []
    news_result = await self.news_tool.execute(ticker, limit=10)
    if not news_result.success:
        logger.warning(f"News fetch failed for {ticker}: {news_result.error}")
        warnings.append(f"뉴스 데이터 없음: {news_result.error}")
    else:
        news_articles = news_result.data
    
    # 선택: fundamental_tool (현재 패턴 유지 + warnings 추가)
    fundamental_data = None
    if self.fundamental_tool:
        fund_result = await self.fundamental_tool.execute(ticker)
        if fund_result.success:
            fundamental_data = fund_result.data
        else:
            logger.warning(f"Fundamental data fetch failed for {ticker}: {fund_result.error}")
            warnings.append(f"펀더멘탈 데이터 없음: {fund_result.error}")
    
    # 선택: disclosure, flow (현재 asyncio.gather 패턴 유지 + warnings 추가)
    optional_coros = []
    optional_keys: list[str] = []
    
    if self.disclosure_tool:
        optional_coros.append(self.disclosure_tool.execute(ticker))
        optional_keys.append("disclosure")
    
    if self.flow_tool and is_korean_ticker(ticker):
        optional_coros.append(self.flow_tool.execute(extract_kr_code(ticker)))
        optional_keys.append("flow")
    
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
    
    return {
        ...,
        "warnings": warnings,  # CLI로 전달
    }
```

### 3. LLM 재시도 (기존 함수 재사용)

**함수 위치 조정:**

```python
# src/llm/utils.py (새 파일)
"""LLM 호출 유틸리티."""

# src/pipelines/daily_report/llm_utils.py의 invoke_llm_with_retry를 이동
# (exponential backoff, ValidationError 피드백, timeout 지원)

async def invoke_llm_with_retry(
    llm,
    output_model: type[BaseModel],
    messages: list,
    config: dict | None = None,
    max_retries: int = 3,
    timeout_seconds: float = 60.0,
) -> BaseModel:
    # ... (기존 구현 그대로)
```

**기존 코드 호환성 유지:**

```python
# src/pipelines/daily_report/llm_utils.py
from src.llm.utils import invoke_llm_with_retry  # re-export
# 기존 import 경로 그대로 작동
```

**analyzer.py에서 사용:**

```python
# src/llm/analyzer.py

from src.llm.utils import invoke_llm_with_retry

ANALYZE_LLM_TIMEOUT = 60.0  # daily_report는 180초, analyze는 60초
ANALYZE_LLM_MAX_RETRIES = 3

async def analyze_news(...) -> NewsAnalysisOutput:
    prompt = ChatPromptTemplate.from_messages([...])
    messages = prompt.format_messages(...)
    
    return await invoke_llm_with_retry(
        llm=llm,
        output_model=NewsAnalysisOutput,
        messages=messages,
        config={},
        max_retries=ANALYZE_LLM_MAX_RETRIES,
        timeout_seconds=ANALYZE_LLM_TIMEOUT,
    )

# generate_technical_summary, generate_fundamental_summary,
# generate_integrated_analysis, generate_actionable_signal도 동일 패턴
```

### 4. CLI 환경변수 체크 (강화)

```python
# src/cli/main.py analyze 커맨드

@app.command()
def analyze(
    query: str = typer.Argument(...),
    provider: str = typer.Option("openai", "--provider", "-p"),
):
    # LLM 키 체크 (필수)
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            console.print("[red]❌ OPENAI_API_KEY 환경변수 필요[/red]")
            raise typer.Exit(1)
    elif provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            console.print("[red]❌ ANTHROPIC_API_KEY 환경변수 필요[/red]")
            raise typer.Exit(1)
    
    # 선택 키는 경고만
    if not os.getenv("OPENDART_API_KEY"):
        console.print("[yellow]⚠️  OPENDART_API_KEY 없음 (한국주식 공시 생략)[/yellow]")
    
    if not os.getenv("KIS_APP_KEY"):
        console.print("[yellow]⚠️  KIS_APP_KEY 없음 (수급 동향 생략)[/yellow]")
    
    # ... run analysis
    result = asyncio.run(run_deep_dive(query, provider))
    
    # warnings 출력
    if result.get("warnings"):
        console.print("\n[yellow]⚠️  다음 데이터를 가져올 수 없었습니다:[/yellow]")
        for warning in result["warnings"]:
            console.print(f"  [yellow]• {warning}[/yellow]")
```

### 5. 티커 검증 (기존 TickerResolver 활용)

```python
# src/cli/main.py (이미 존재)
async def resolve_ticker(query: str) -> str:
    resolver = TickerResolver()
    try:
        resolution = await resolver.resolve(query)
        return resolution.resolved_ticker
    except Exception as e:
        raise ValueError(f"Could not resolve ticker for '{query}': {e}") from e

# check/analyze 명령어에서 이미 사용 중
```

### 6. Rate Limit (현재 구현 상태)

| API | 현재 구현 | 추가 필요 |
|-----|----------|----------|
| SEC EDGAR | User-Agent 설정됨 | ✅ 없음 |
| OpenDART | 6시간 캐시 | ✅ 없음 |
| KIS API | 단일 호출만 | ✅ 없음 (병렬 호출 시 추가) |
| OpenAI/Anthropic | LangChain 내장 | ✅ 재시도만 추가 |

### 7. 타임아웃 (추가)

```python
# src/pipelines/deep_dive.py

TOOL_TIMEOUT = 30.0
LLM_TIMEOUT = 60.0

async def run(self, ticker: str) -> dict:
    try:
        tech_result = await asyncio.wait_for(
            self.technical_tool.execute(ticker),
            timeout=TOOL_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error(f"technical_tool 타임아웃 ({TOOL_TIMEOUT}초)")
        raise RuntimeError("Technical analysis timeout")
```

---

## Testing Strategy

### 1. 단위 테스트 (Unit Tests)

**모델 검증:**

```python
# tests/llm/test_models.py
def test_actionable_signal_output_validation():
    # Valid case
    signal = ActionableSignalOutput(
        action="매수",
        timing="지금",
        signal_strength=8,
        headline="매수. 지금. 이유: RSI 과매도",
        primary_reason="RSI 28 (과매도)",
        supporting_reasons=["실적 양호"],
        risks=["금리 인상 위험"],
        invalidation_point="$145.20",
        confidence=0.82,
    )
    assert signal.action == "매수"
    
    # Invalid cases
    with pytest.raises(ValidationError):
        ActionableSignalOutput(action="홀드", ...)  # "매수/매도/관망"만 허용
    
    with pytest.raises(ValidationError):
        ActionableSignalOutput(timing="내일", ...)  # "지금/조정_대기/보류"만 허용
    
    with pytest.raises(ValidationError):
        ActionableSignalOutput(signal_strength=11, ...)  # 1-10만 허용
```

**재시도 로직:**

```python
# tests/llm/test_utils.py
@pytest.mark.asyncio
async def test_invoke_llm_with_retry_success():
    mock_llm = AsyncMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=ActionableSignalOutput(...)
    )
    
    result = await invoke_llm_with_retry(...)
    
    assert result.action == "매수"
    assert mock_llm.with_structured_output.return_value.ainvoke.call_count == 1

@pytest.mark.asyncio
async def test_invoke_llm_with_retry_timeout_then_success():
    mock_llm = AsyncMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=[asyncio.TimeoutError(), ActionableSignalOutput(...)]
    )
    
    result = await invoke_llm_with_retry(...)
    
    assert result.action == "매수"
    assert mock_llm.with_structured_output.return_value.ainvoke.call_count == 2
```

### 2. 통합 테스트 (Integration Tests)

```python
# tests/pipelines/test_deep_dive.py

@pytest.mark.asyncio
async def test_deep_dive_with_actionable_signal(mock_llm):
    pipeline = DeepDivePipeline(...)
    result = await pipeline.run("AAPL")
    
    assert result["ticker"] == "AAPL"
    assert result["actionable_signal"] is not None
    assert result["actionable_signal"].action in ["매수", "매도", "관망"]
    assert 1 <= result["actionable_signal"].signal_strength <= 10
    assert len(result["warnings"]) >= 0

@pytest.mark.asyncio
async def test_deep_dive_with_partial_failure():
    mock_news_tool = AsyncMock()
    mock_news_tool.execute = AsyncMock(
        return_value=ToolResult(success=False, data=None, error="API rate limit")
    )
    
    pipeline = DeepDivePipeline(news_tool=mock_news_tool, ...)
    result = await pipeline.run("AAPL")
    
    assert "뉴스 데이터 없음: API rate limit" in result["warnings"]
    assert result["actionable_signal"] is not None
```

### 3. 프롬프트 평가 (Prompt Evaluation)

```python
# tests/llm/test_actionable_signal_prompt.py

@pytest.mark.integration
@pytest.mark.asyncio
async def test_actionable_signal_prompt_with_real_llm():
    """실제 LLM으로 10개 종목 테스트 (CI skip, 로컬 실행)"""
    tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", 
               "005930.KS", "000660.KS", "035420.KS", "035720.KS", "051910.KS"]
    
    llm = LLMProvider.create("openai", model="gpt-4o", temperature=0.1)
    
    for ticker in tickers:
        pipeline = DeepDivePipeline(...)
        result = await pipeline.run(ticker)
        signal = result["actionable_signal"]
        
        # 포맷 체크
        assert signal.action in signal.headline  # headline에 action 포함
        assert any(char.isdigit() for char in signal.primary_reason)  # 숫자 포함
        assert len(signal.supporting_reasons) >= 2
        assert signal.invalidation_point.startswith("$") or "원" in signal.invalidation_point
```

### 4. CLI 테스트 (E2E)

```python
# tests/cli/test_analyze_command.py

def test_analyze_command_success(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "--provider", "openai"])
    
    assert result.exit_code == 0
    assert "🎯 투자 신호" in result.output
    assert "🔥" in result.output
    assert "🛑 손절가:" in result.output

def test_analyze_command_missing_api_key():
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL"])
    
    assert result.exit_code == 1
    assert "OPENAI_API_KEY 환경변수 필요" in result.output

def test_analyze_command_with_warnings(mock_disclosure_failure):
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL"])
    
    assert result.exit_code == 0
    assert "⚠️  다음 데이터를 가져올 수 없었습니다:" in result.output
    assert "공시 데이터 없음" in result.output
```

### 5. 테스트 실행

```bash
# 빠른 테스트 (unit + mock integration)
uv run pytest tests/llm/ tests/pipelines/ -v

# 실제 LLM 사용 (로컬만, CI skip)
uv run pytest tests/llm/test_actionable_signal_prompt.py -m integration

# 커버리지
uv run pytest --cov=src/llm --cov=src/pipelines --cov-report=html
```

### 6. 성공 기준 (Phase 1)

| 항목 | 기준 | 테스트 방법 |
|------|------|-----------|
| **응답 속도** | 10개 종목 < 3초/건 | 통합 테스트 타이머 |
| **headline 형식** | 100% "{action}. {timing}. 이유: {핵심}" | 정규식 검증 |
| **primary_reason 숫자** | 100% 구체적 숫자 포함 | `any(char.isdigit() for char in reason)` |
| **signal_strength 범위** | 100% 1-10 | Pydantic validation |
| **타임아웃 재시도** | 1회 실패 후 성공 | mock 테스트 |
| **warnings 출력** | 실패한 도구마다 1줄 | CLI 출력 검증 |

---

## Implementation Plan

**Phase 1 작업 항목:** (ROADMAP.md 참조)

| # | 작업 | 파일 | 예상 시간 |
|---|------|------|-----------|
| 1.1 | `ActionableSignalOutput` 모델 추가 | `src/llm/models.py` | 10분 |
| 1.2 | `invoke_llm_with_retry` 이동 | `src/llm/utils.py` (새 파일) | 15분 |
| 1.3 | `generate_actionable_signal()` 함수 작성 | `src/llm/analyzer.py` | 30분 |
| 1.4 | 파이프라인 통합 (`actionable_signal` + `warnings` 반환) | `src/pipelines/deep_dive.py` | 20분 |
| 1.5 | CLI 출력 개선 (Rich Panel + warnings + 모순 경고) | `src/cli/main.py` | 20분 |
| 1.6 | 평가 데이터셋 레이블링 (50-100개) | `evaluations/test_cases/actionable_signal.yaml` | **2시간** |
| 1.7 | 평가 메트릭 구현 | `evaluations/metrics_signal.py` | 30분 |
| 1.8 | 10개 종목 테스트 및 프롬프트 튜닝 | - | 30분 |

**총 예상 시간:** 4.5시간 (데이터셋 레이블링 2시간 포함)

**완료 기준:**
- `jarvis analyze AAPL` 실행 시 박스 형태로 명확한 신호 출력
- headline: "{action}. {timing}. 이유: {핵심}" 형식
- timing: "지금" | "조정_대기" | "보류" 중 하나
- signal_strength: 1-10 시각화 (🔥 이모지), 5개 팩터 종합 판단
- primary_reason: 구체적 숫자 포함 (RSI 28, P/E 12 등)
- invalidation_point: stop-loss 가격 명시
- warnings: 실패한 데이터 소스 리스트 하단 표시
- 모순 경고: `action="매수" + signal_strength<5` 시 "⚠️ 약한 신호로 명확한 액션" 표시
- **평가 통과**: timing_accuracy > 70%, clarity_score > 4.0/5.0, signal_strength_correlation > 0.6 (50개 테스트)

**의존성:** 없음 (기존 코드 활용)

---

## Open Questions (모두 해결됨)

| 질문 | 결정 | 근거 |
|------|------|------|
| **1. signal_strength 계산** | **5개 팩터 종합 + LLM 판단** | 기술적 분석만으로는 공시/뉴스 영향 반영 불가. LLM이 technical + news + fundamental + disclosure + flow를 종합해서 1-10 판단 |
| **2. timing 결정 로직** | **하이브리드: 기술 지표 1차 → LLM 최종** | 기술 지표로 힌트 제공하되, LLM이 펀더멘탈/공시(수주잔고 등)/매크로 고려해서 Override 가능. "기술적으로 약해도 강력한 펀더멘탈 있으면 '지금' 추천" |
| **3. 출시 기준** | **엄격: timing_accuracy > 70%, clarity_score > 4.0/5.0, signal_strength_correlation > 0.6 (50개 테스트)** | 정확도 우선. 미달 시 프롬프트 개선 반복 |
| **4. 평가 데이터셋** | **히스토리 데이터 + 수동 레이블링 (~2시간)** | 과거 `jarvis analyze` 결과 50-100개 선별 → action/timing/signal_strength 수동 레이블. 현실적 데이터 확보 |
| **5. action-signal_strength 모순** | **허용 + CLI 경고 표시** | Pydantic validator 없음. "매수 + signal_strength=2" 같은 엣지 케이스 허용하되 `⚠️ 약한 신호로 명확한 액션 - 재확인 필요` 경고 |
| LLM temperature | 0.1 시작, 테스트 후 조정 | 일관성 우선 |
| 백테스팅 프레임워크 | Phase 2에서 결정 | - |
| 과거 데이터 범위 | Phase 2에서 결정 | - |

---

## Future Phases (Phase 2 이후)

**Phase 2: Backtesting Engine** (3-4시간)
- 전략 정확도 검증
- 과거 데이터로 시뮬레이션
- "정확도: XX%" 표시

**Phase 3: Web Dashboard** (반나절)
- Streamlit/Gradio 기반
- 차트 시각화
- 백테스트 결과 표시

**Phase 4: Advanced Features** (장기, 선택적)
- 리스크 경고 시스템
- 섹터별 전략 추천
- 포트폴리오 최적화
- 매매 타이밍 예측 (ML)

---

## Prompt Evaluation System

프롬프트 개선을 위한 샘플 데이터 기반 평가 시스템 (daily_report evaluation 패턴 참고).

### 1. 테스트 데이터셋

**위치:** `evaluations/datasets/actionable_signal_cases.json`

```json
{
  "version": "1.0",
  "description": "Actionable signal prompt evaluation test cases",
  "test_cases": [
    {
      "id": "case_001",
      "name": "강한_매수_신호_AAPL",
      "ticker": "AAPL",
      "mock_data": {
        "technical": {"rsi": 28, "recommendation": "매수", ...},
        "news": {"sentiment": "긍정", ...},
        "fundamental": {"pe_ratio": 25.3, ...},
        "disclosure": [...],
        "flow": {"foreign_net_1d": 120000000, ...}
      },
      "expected": {
        "action": "매수",
        "timing": "지금",
        "signal_strength_min": 7,
        "signal_strength_max": 10,
        "must_include_numbers": ["28", "RSI"],
        "must_have_invalidation_point": true,
        "headline_pattern": "^매수\\. 지금\\. 이유:",
        "min_supporting_reasons": 2,
        "min_risks": 1
      }
    },
    {
      "id": "case_002",
      "name": "조정_대기_신호_TSLA",
      "ticker": "TSLA",
      "mock_data": {...},
      "expected": {
        "action": "매수",
        "timing": "조정_대기",
        "signal_strength_min": 5,
        "signal_strength_max": 7,
        ...
      }
    },
    {
      "id": "case_003",
      "name": "매도_신호_과열_종목",
      ...
    }
  ]
}
```

**데이터 수집 방법 (히스토리 데이터 + 수동 레이블링, ~2시간):**

1. **과거 `jarvis analyze` 결과 50-100개 선별**
   - 다양한 종목: 미국 5개 (AAPL, MSFT, NVDA, TSLA, GOOGL), 한국 5개 (삼성전자, SK하이닉스, NAVER, 카카오, 현대차)
   - 다양한 시나리오: 상승장/하락장/횡보, 호재/악재, 실적 발표 시점
   - 극단 케이스: 급등/급락, 공시 이벤트, 데이터 부족 상황

2. **수동 레이블링 (ground truth 작성)**
   - `action`: 매수/매도/관망 (당신이 직접 판단)
   - `timing`: 지금/조정_대기/보류 (실제 상황에서 어떻게 했을지)
   - `signal_strength`: 1-10 (종합 판단)
   - `headline` 적절성: 0-5점 (이상적 headline 작성)

3. **Mock 데이터 저장**
   - 당시 technical/news/fundamental/disclosure/flow 데이터를 JSON으로 저장
   - 재현 가능하도록 normalize (API 호출 없이 테스트 가능)

4. **작업 시간: ~2시간** (구현 계획에 포함)

5. **저장 위치:** `evaluations/test_cases/actionable_signal.yaml`

### 2. 평가 메트릭

**규칙 기반 메트릭** (`evaluations/metrics_signal.py`):

```python
def format_compliance(signal: ActionableSignalOutput, expected: dict) -> float:
    """포맷 준수율: headline 패턴, timing 값 등"""
    score = 0.0
    total = 0.0
    
    # headline 패턴 검증
    pattern = expected.get("headline_pattern")
    if pattern and re.match(pattern, signal.headline):
        score += 1.0
    total += 1.0
    
    # timing 값 검증
    if expected.get("timing") == signal.timing:
        score += 1.0
    total += 1.0
    
    return score / total if total > 0 else 0.0

def number_inclusion(signal: ActionableSignalOutput, expected: dict) -> float:
    """숫자 포함 여부: primary_reason에 구체적 숫자 포함"""
    required_numbers = expected.get("must_include_numbers", [])
    if not required_numbers:
        return 1.0
    
    primary_text = signal.primary_reason
    found = sum(1 for n in required_numbers if n in primary_text)
    return found / len(required_numbers)

def signal_strength_range(signal: ActionableSignalOutput, expected: dict) -> float:
    """신호 강도 범위: 예상 범위 내인지"""
    min_expected = expected.get("signal_strength_min", 1)
    max_expected = expected.get("signal_strength_max", 10)
    return 1.0 if min_expected <= signal.signal_strength <= max_expected else 0.0

def invalidation_point_present(signal: ActionableSignalOutput, expected: dict) -> float:
    """손절가 명시 여부"""
    if not expected.get("must_have_invalidation_point", True):
        return 1.0
    return 1.0 if signal.invalidation_point else 0.0

def reason_count(signal: ActionableSignalOutput, expected: dict) -> float:
    """근거 개수 적절성"""
    min_supporting = expected.get("min_supporting_reasons", 2)
    min_risks = expected.get("min_risks", 1)
    
    supporting_ok = len(signal.supporting_reasons) >= min_supporting
    risks_ok = len(signal.risks) >= min_risks
    
    return (int(supporting_ok) + int(risks_ok)) / 2.0
```

**LLM-as-Judge 메트릭**:

```python
def signal_quality_llm(signal: ActionableSignalOutput, expected: dict, llm) -> tuple[float, str]:
    """LLM이 신호의 적절성 평가"""
    
    judge_prompt = f"""다음 투자 신호가 적절한지 평가하세요:

action: {signal.action}
timing: {signal.timing}
signal_strength: {signal.signal_strength}
headline: {signal.headline}
primary_reason: {signal.primary_reason}
supporting_reasons: {signal.supporting_reasons}
risks: {signal.risks}
invalidation_point: {signal.invalidation_point}

평가 기준:
1. primary_reason에 구체적 숫자 포함? (RSI 28, P/E 12 등)
2. timing이 action과 일관성 있는가?
3. signal_strength가 근거와 매칭되는가?
4. risks가 현실적인가?
5. invalidation_point가 명확한가?

점수: 0.0-1.0 (0.8 이상이면 우수)
이유: 한 문장으로 설명
"""
    
    # LLM 호출 (structured output)
    result = llm.invoke(judge_prompt)
    return result.score, result.reason
```

### 3. 평가 스크립트

**로컬 실행** (`evaluations/evaluate_signal.py`):

```bash
# 기본 평가 (규칙 기반)
uv run python evaluations/evaluate_signal.py

# 프롬프트 버전 명시
uv run python evaluations/evaluate_signal.py --prompt-version v2_numbers_emphasis

# LLM-as-Judge 포함 (느리지만 정확)
uv run python evaluations/evaluate_signal.py --llm-judge

# 결과 저장 안함 (빠른 테스트)
uv run python evaluations/evaluate_signal.py --no-save
```

**LangSmith 연동** (`evaluations/langsmith_eval_signal.py`):

```bash
# 데이터셋 생성 (최초 1회)
uv run python evaluations/langsmith_eval_signal.py --create-dataset

# 평가 실행 (LangSmith UI에서 결과 확인)
uv run python evaluations/langsmith_eval_signal.py --experiment v1_baseline

# 프롬프트 변경 후 재평가
uv run python evaluations/langsmith_eval_signal.py --experiment v2_improved
```

### 4. 결과 저장 및 비교

**저장 위치:** `evaluations/results/signal/`

```
evaluations/results/signal/
  ├─ 2026-04-23_1430_v1_baseline.json
  ├─ 2026-04-23_1545_v2_numbers_emphasis.json
  └─ 2026-04-23_1623_v3_timing_clarity.json
```

**비교 스크립트** (`evaluations/compare_signal.py`):

```bash
# 두 버전 비교
uv run python evaluations/compare_signal.py v1_baseline v2_improved

# 출력 예시:
#                         v1_baseline  v2_improved  Δ
# format_compliance           0.85         0.92   +0.07
# number_inclusion            0.73         0.89   +0.16
# signal_strength_range       0.91         0.94   +0.03
# invalidation_point_present  0.82         0.88   +0.06
# reason_count                0.79         0.85   +0.06
# signal_quality_llm          0.76         0.83   +0.07
# ──────────────────────────────────────────────────
# AVERAGE                     0.81         0.88   +0.07 ✅
```

### 5. 프롬프트 개선 워크플로우

```
1. 초기 프롬프트 작성 (temperature 0.1)
   └─ evaluations/evaluate_signal.py --prompt-version v1_baseline

2. 평가 결과 확인
   └─ 어떤 메트릭이 낮은지 확인 (예: number_inclusion 0.73)

3. 프롬프트 개선 (analyzer.py)
   └─ System prompt에 "primary_reason에 반드시 구체적 숫자 포함" 강조

4. 재평가
   └─ evaluations/evaluate_signal.py --prompt-version v2_numbers_emphasis

5. 성능 비교
   └─ evaluations/compare_signal.py v1_baseline v2_numbers_emphasis

6. 개선 확인되면 temperature 조정 테스트
   └─ 0.1 → 0.2 → 0.3 순차 테스트

7. 최종 버전 선택 및 배포
```

### 6. 테스트 케이스 확장

**케이스 타입:**
- 강한 매수 신호 (RSI 과매도 + 외인 순매수)
- 조정 대기 신호 (과열 상태, 타이밍 애매)
- 매도 신호 (악재 발생, 기술적 하락)
- 관망 신호 (믹스드 팩터, 불명확)
- 데이터 부족 상황 (일부 팩터 missing)

**10개 종목 커버리지:**
- 미국 주식: AAPL, MSFT, NVDA, TSLA, GOOGL
- 한국 주식: 삼성전자, SK하이닉스, NAVER, 카카오, 현대차

### 7. 성공 기준 (Evaluation Metrics + Launch Gate)

**메트릭 목표:**

| 메트릭 | 목표 | 측정 방법 |
|--------|------|----------|
| format_compliance | ≥ 0.90 | headline 패턴, timing 값 검증 |
| number_inclusion | ≥ 0.85 | primary_reason 숫자 포함 |
| signal_strength_range | ≥ 0.90 | 예상 범위 내 |
| invalidation_point_present | 1.00 | 100% 명시 |
| reason_count | ≥ 0.85 | supporting 2-3개, risks 1개 이상 |
| signal_quality_llm | ≥ 0.80 | LLM-as-Judge 종합 평가 |

**평균 점수:**
- Baseline (v1): 0.80 목표
- Production: 0.85 이상 유지

**출시 기준 (Launch Gate - 엄격):**

프롬프트 v1은 다음 **모든 조건을 동시 충족**할 때만 출시:

| 메트릭 | 임계값 | 측정 데이터 |
|--------|--------|-----------|
| **timing_accuracy** | > 70% | 50개 테스트 케이스 |
| **clarity_score** | > 4.0/5.0 | LLM-as-Judge (headline + 전체 신호 명확성) |
| **signal_strength_correlation** | > 0.6 | ground truth vs 예측 (Pearson correlation) |

**미달 시:** 프롬프트 개선 반복 (temperature 조정, 규칙 강화, 예시 추가)

---

## References

- **기존 디자인 문서:** `~/.gstack/projects/rutesun-invest-jarvis/user-main-design-20260423-103958.md`
- **개발 로드맵:** `ROADMAP.md`
- **아키텍처:** `docs/ARCHITECTURE.md`
- **기능 명세:** `docs/FEATURES.md`
- **개발 가이드:** `docs/DEVELOPMENT.md`
- **Evaluation 참고:** `evaluations/evaluate_map.py`, `evaluations/langsmith_eval.py`
