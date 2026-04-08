# Invest-Jarvis 설계 문서

**생성일**: 2025-04-08
**버전**: 1.0
**상태**: 승인됨

## 1. 개요

금융 투자 분석을 지원하는 CLI 도구 및 Claude Code 스킬 기반 에이전트.
telegram 프로젝트의 기능을 참고하여 새롭게 재설계.

### 1.1 핵심 목표

- **복합 목적**: 투자 의사결정 지원 + 정보 수집/정리 + 포트폴리오 관리
- **시장 범위**: 한국 + 미국 주식
- **상호작용**: CLI 명령어 + Claude Code 스킬 (대화형)

### 1.2 설계 원칙

- 모듈러 구조로 관심사 분리
- 하이브리드 실행 (파이프라인 + 에이전트)
- 확장 가능한 전략 패턴
- LLM 해석 가능한 구조화된 출력

---

## 2. 아키텍처

### 2.1 하이브리드 실행 모델

```
┌─────────────────────────────────────────────────────────┐
│                      사용자 입력                         │
└─────────────────────────────────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
    ┌───────────────┐           ┌───────────────┐
    │ CLI 명령어     │           │ Claude Code   │
    │ (jarvis ...)  │           │ Skill 호출    │
    └───────────────┘           └───────────────┘
            │                           │
            ▼                           ▼
    ┌───────────────┐           ┌───────────────┐
    │   Pipeline    │           │    Agent      │
    │   Executor    │           │  Orchestrator │
    │ (정해진 순서)  │           │ (LLM이 판단)   │
    └───────────────┘           └───────────────┘
            │                           │
            └───────────┬───────────────┘
                        ▼
              ┌───────────────┐
              │  Shared Tools │
              └───────────────┘
                        │
                        ▼
              ┌───────────────┐
              │    Output     │
              └───────────────┘
```

### 2.2 레이어 구조

```
┌─────────────────────────────────────────────────┐
│                   CLI / Skills                   │
├─────────────────────────────────────────────────┤
│         Pipelines          │       Agent        │
├─────────────────────────────────────────────────┤
│                    Tools                         │
│   (Technical, Fundamental, News, Disclosure)    │
├─────────────────────────────────────────────────┤
│                  Providers                       │
│        (yfinance, KIS, Naver)                   │
├─────────────────────────────────────────────────┤
│                   Storage                        │
│          (Cache, SQLite, Files)                 │
└─────────────────────────────────────────────────┘
```

---

## 3. 프로젝트 구조

```
invest-jarvis/
├── src/
│   ├── core/                    # 핵심 인터페이스 및 설정
│   │   ├── config.py            # 환경설정 로더 (dotenv, yaml)
│   │   ├── models.py            # 공통 Pydantic 모델
│   │   └── interfaces.py        # BaseTool, BaseProvider 추상 클래스
│   │
│   ├── providers/               # 데이터 제공자 (thin wrapper)
│   │   ├── yfinance.py          # yfinance 래퍼 (미국 주식)
│   │   ├── kis.py               # 한국투자증권 API (한국 주식)
│   │   └── naver.py             # 네이버 증권 (테마, 업종)
│   │
│   ├── tools/                   # 분석 도구
│   │   ├── technical/           # 기술적 분석
│   │   │   ├── base.py          # BaseStrategy 인터페이스
│   │   │   ├── models.py        # StrategyResult, TechnicalResult 등
│   │   │   ├── indicators.py    # 지표 계산 (pandas_ta)
│   │   │   ├── registry.py      # 전략 레지스트리
│   │   │   ├── tool.py          # TechnicalAnalysisTool
│   │   │   └── strategies/      # 전략 구현
│   │   │       ├── trend.py
│   │   │       ├── oscillator.py
│   │   │       ├── divergence.py
│   │   │       ├── disparity.py
│   │   │       └── risk.py
│   │   ├── fundamental.py       # 펀더멘털 분석
│   │   ├── macro.py             # 매크로 지표 (VIX, 공포탐욕, 유가, 금리)
│   │   ├── news.py              # 뉴스 분석 (실시간 조회)
│   │   └── disclosure.py        # 공시 분석 (SEC, DART)
│   │
│   ├── collector/               # 데이터 수집 (선택적)
│   │   └── telegram.py          # 텔레그램 수집기
│   │
│   ├── storage/                 # 저장소
│   │   ├── cache.py             # 메모리 캐시 (TTL 기반)
│   │   └── db.py                # SQLite (분석 요약, 히스토리)
│   │
│   ├── agent/                   # 대화형 에이전트
│   │   ├── orchestrator.py      # LLM 기반 도구 오케스트레이션
│   │   └── prompts.py           # 시스템 프롬프트
│   │
│   ├── pipelines/               # 미리 정의된 파이프라인 (LLM 사용)
│   │   ├── deep_dive.py         # 심층 분석 → LLM.generate_report()
│   │   ├── quick_check.py       # 빠른 체크 (LLM 미사용)
│   │   ├── daily_report.py      # 일일 리포트 → LLM.extract_themes(), summarize_news()
│   │   └── portfolio.py         # 포트폴리오 → LLM.summarize_news()
│   │
│   ├── report/                  # 리포트 생성
│   │   ├── generator.py         # 마크다운 리포트 생성
│   │   └── templates/           # 리포트 템플릿
│   │
│   ├── llm/                     # LLM 추상화
│   │   ├── client.py            # 멀티 프로바이더 클라이언트
│   │   └── models.py            # 입출력 Pydantic 모델
│   │
│   └── cli/                     # CLI 진입점
│       └── main.py              # Typer/Click 기반 CLI
│
├── skills/                      # Claude Code 스킬 (가벼운 CLI 래퍼)
│   ├── invest-analyze.md
│   ├── invest-report.md
│   ├── invest-screen.md
│   ├── invest-portfolio.md
│   └── invest-chat.md
│
├── tests/
├── data/                        # 로컬 데이터 (gitignore)
├── reports/                     # 생성된 리포트 (gitignore)
├── config.yaml                  # 설정 파일
├── pyproject.toml
└── .env.example
```

---

## 4. 핵심 인터페이스

### 4.1 BaseTool

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any

class ToolResult(BaseModel):
    success: bool
    data: Any
    error: str | None = None

class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        pass
```

### 4.2 BaseProvider

```python
class BaseProvider(ABC):
    @abstractmethod
    async def get_price_history(self, ticker: str, period: str) -> pd.DataFrame:
        pass

    @abstractmethod
    async def get_quote(self, ticker: str) -> dict:
        pass
```

### 4.3 BaseStrategy (기술적 분석)

```python
class BaseStrategy(ABC):
    name: str
    description: str

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        pass
```

---

## 5. 기술적 분석 모듈

### 5.1 전략 목록

| 전략 | 설명 |
|------|------|
| `trend` | 추세 분석 (이동평균, ADX, 슈퍼트렌드) |
| `oscillator` | 모멘텀 분석 (RSI, MACD, 스토캐스틱) |
| `divergence` | 다이버전스 분석 (가격-지표 괴리) |
| `disparity` | 이격도 분석 (이동평균 대비 괴리율) |
| `risk` | 리스크 분석 (ATR, 지지/저항, 손절가) |

### 5.2 지표 목록

```python
# 이동평균
SMA: 10, 20, 50, 120, 150, 200일

# 모멘텀
RSI: 14일
MACD: 표준(12,26,9), 커스텀(5,35,5)
Stochastic

# 변동성
ATR: 14일
Bollinger Bands: 20일

# 추세
ADX: 14일
Supertrend: 10일, 3.0배수

# 기타
52주 High/Low
Volume SMA: 20, 50, 120일
Pivot Points: S1, R1
Disparity: 20, 50, 120일
```

### 5.3 데이터 모델

```python
class IndicatorSnapshot(BaseModel):
    """Raw 지표 스냅샷"""

    # 가격
    price: float
    change_pct: float

    # 이동평균
    sma_20: float | None
    sma_50: float | None
    sma_120: float | None
    sma_200: float | None

    # 모멘텀
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None

    # 변동성
    atr: float | None
    bb_upper: float | None
    bb_lower: float | None

    # 추세 강도
    adx: float | None
    supertrend_direction: int | None

    # 이격도
    disparity_20: float | None
    disparity_50: float | None
    disparity_120: float | None

    # 지지/저항
    pivot: float | None
    support_s1: float | None
    resistance_r1: float | None
    high_52w: float | None
    low_52w: float | None


class StrategyResult(BaseModel):
    """전략 실행 결과 (단순화된 공통 모델)"""

    name: str                        # "trend", "oscillator", etc.
    status: str                      # "강세", "과매수", "중립" 등
    confidence: float                # 0-100
    signals: list[str]               # ["골든크로스", "RSI 과매수"]
    evidence: list[str]              # ["20일선 > 50일선", "RSI 78.5"]
    metrics: dict[str, float]        # {"sma_20": 145.0, "rsi": 78.5}


class TechnicalResult(BaseModel):
    """전체 기술적 분석 결과"""

    ticker: str
    timestamp: datetime

    # Raw 지표 (LLM 직접 해석 가능)
    indicators: IndicatorSnapshot

    # 전략별 결과
    strategies: list[StrategyResult]

    # 종합
    overall_assessment: str          # "매수" | "중립" | "매도"
    confidence_score: float          # 0-100
    key_insights: list[str]
    warnings: list[str]
```

### 5.4 전략 레지스트리

```python
class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy):
        self._strategies[strategy.name] = strategy

    def unregister(self, name: str):
        del self._strategies[name]

    def get_all(self) -> list[BaseStrategy]:
        return list(self._strategies.values())
```

### 5.5 설정 기반 활성화

```yaml
# config.yaml
technical:
  strategies:
    - trend
    - oscillator
    - divergence
    - disparity
    - risk
```

---

## 6. LLM 클라이언트

### 6.1 멀티 프로바이더 지원

```python
class LLMClient:
    def __init__(self, config: LLMConfig):
        self.providers = {
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
        }
        self.default = config.default_provider
        self.params = config.params  # temperature=0, seed=42 등
```

### 6.2 용도별 메서드 (Pydantic 입출력)

```python
class NewsArticle(BaseModel):
    title: str
    source: str
    published_at: str
    content: str
    url: str | None = None

class NewsSummary(BaseModel):
    key_points: list[str]
    sentiment: str
    impact: str
    related_tickers: list[str]

class LLMClient:
    async def summarize_news(self, articles: list[NewsArticle]) -> NewsSummary:
        pass

    async def analyze_technical(self, data: TechnicalInput) -> TechnicalAnalysis:
        pass

    async def generate_report(self, data: ReportInput) -> str:
        pass

    async def extract_themes(self, messages: list[str]) -> list[str]:
        pass
```

### 6.3 재현성 파라미터

```yaml
# config.yaml
llm:
  default_provider: openai
  params:
    temperature: 0
    top_p: 1
    seed: 42
  models:
    summary: gpt-4o-mini
    analysis: gpt-4o
    report: gpt-4o
```

---

## 7. 매크로 지표 도구

### 7.1 지표 목록

| 지표 | 설명 | 데이터 소스 |
|------|------|------------|
| VIX | 변동성 지수 | yfinance (^VIX) |
| Fear & Greed | 공포탐욕 지수 | CNN API |
| WTI | 유가 | yfinance (CL=F) |
| US 10Y | 미국 10년물 금리 | yfinance (^TNX) |
| US 2Y | 미국 2년물 금리 | yfinance (^IRX 또는 API) |
| DXY | 달러 인덱스 | yfinance (DX-Y.NYB) |

### 7.2 데이터 모델

```python
class MacroSnapshot(BaseModel):
    """매크로 지표 스냅샷"""

    timestamp: datetime

    # 변동성
    vix: float
    vix_change: float

    # 심리
    fear_greed: int              # 0-100
    fear_greed_label: str        # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"

    # 원자재
    wti: float
    wti_change: float

    # 금리
    us_10y: float
    us_2y: float
    yield_spread: float          # 10Y - 2Y (장단기 금리차)

    # 달러
    dxy: float
    dxy_change: float
```

### 7.3 daily_report에서의 사용

```python
class DailyReportPipeline:
    async def run(self, date: str) -> Report:
        # 1. 매크로 지표 조회 (항상 포함)
        macro = await self.tools["macro"].execute()

        # 2. 뉴스/텔레그램 데이터 로드
        news_data = await self.load_news(date)

        # 3. LLM으로 테마 추출 및 요약
        themes = await self.llm.extract_themes(news_data)
        summary = await self.llm.summarize_news(news_data)

        # 4. 리포트 생성 (매크로 섹션 포함)
        return Report(
            date=date,
            macro=macro,        # 항상 포함
            themes=themes,
            summary=summary,
        )
```

---

## 8. 파이프라인-LLM 상호작용

각 파이프라인에서 LLM이 담당하는 역할:

| 파이프라인 | LLM 사용 | 호출 메서드 |
|-----------|----------|------------|
| `deep_dive.py` | 종합 리포트 생성 | `LLM.generate_report()` |
| `quick_check.py` | 미사용 | - |
| `daily_report.py` | 매크로 지표 + 테마 추출 + 뉴스 요약 | `LLM.extract_themes()`, `LLM.summarize_news()` |
| `portfolio.py` | 종목별 뉴스 요약 | `LLM.summarize_news()` |

### 예시: deep_dive.py

```python
class DeepDivePipeline:
    def __init__(self, llm: LLMClient, tools: dict[str, BaseTool]):
        self.llm = llm
        self.tools = tools

    async def run(self, ticker: str) -> Report:
        # 1. 병렬로 데이터 수집 (LLM 미사용)
        tech_result = await self.tools["technical"].execute(ticker)
        fund_result = await self.tools["fundamental"].execute(ticker)
        news_result = await self.tools["news"].execute(ticker)

        # 2. LLM으로 종합 리포트 생성
        report = await self.llm.generate_report(
            ReportInput(
                ticker=ticker,
                technical=tech_result,
                fundamental=fund_result,
                news=news_result,
            )
        )

        return report
```

---

## 9. CLI 명령어

```bash
# 종목 분석
jarvis analyze AAPL              # 심층 분석
jarvis analyze 005930            # 한국 주식
jarvis check AAPL                # 빠른 체크 (현재가 + 기본 지표)

# 리포트
jarvis report                    # 오늘 일일 리포트
jarvis report --date 2025-04-07  # 특정 날짜
jarvis report --market KR        # 한국 시장만

# 스크리닝
jarvis screen --market US        # 미국 시장
jarvis screen --market KR        # 한국 시장
jarvis screen --theme 반도체     # 테마별

# 포트폴리오
jarvis portfolio                 # 전체 포트폴리오 현황
jarvis portfolio --ticker AAPL   # 특정 종목만

# 뉴스
jarvis news AAPL                 # 종목 관련 최근 뉴스
jarvis news --market KR          # 한국 시장 뉴스
```

---

## 10. Claude Code Skills

가벼운 CLI 래퍼로 구현:

### 10.1 /invest-analyze

```markdown
name: invest-analyze
description: 종목 심층 분석

## 동작
jarvis analyze <ticker>
```

### 10.2 /invest-report

```markdown
name: invest-report
description: 시장 일일 리포트 생성

## 동작
jarvis report [--date DATE] [--market MARKET]
```

### 10.3 /invest-screen

```markdown
name: invest-screen
description: 종목 스크리닝

## 동작
jarvis screen [--market MARKET] [--theme THEME]
```

### 10.4 /invest-portfolio

```markdown
name: invest-portfolio
description: 포트폴리오 모니터링

## 동작
jarvis portfolio [--ticker TICKER]
```

### 10.5 /invest-chat

```markdown
name: invest-chat
description: 대화형 투자 분석

## 동작
1. 자연어 질문에서 티커/의도 파싱
2. 필요한 도구 결정 (기술적 분석, 뉴스, 공시 등)
3. jarvis CLI로 각 도구 실행
4. 결과를 Claude Code가 종합하여 답변

예시:
  입력: "NVDA 지금 들어가도 될까?"
  실행: jarvis analyze NVDA + jarvis news NVDA
  출력: Claude Code가 결과 해석하여 답변
```

---

## 11. 저장소

### 11.1 구조

```
data/
├── cache/                    # 메모리 캐시 (TTL 기반)
├── telegram/                 # 텔레그램 수집 데이터 (선택적)
│   └── 2025-04/
│       └── 2025-04-08-channel.csv
└── db/
    └── jarvis.db             # SQLite
```

### 11.2 캐싱 전략

| 데이터 | TTL | 저장 방식 |
|--------|-----|----------|
| 실시간 시세 | 1분 | 메모리 |
| 기술적 지표 | 5분 | 메모리 |
| 뉴스 | 1시간 | 메모리 |
| 텔레그램 | 영구 | CSV |
| 분석 요약 | 영구 | SQLite |

---

## 12. 데이터 소스

### 12.1 필수

- **뉴스**: yfinance, DuckDuckGo 검색
- **가격 데이터**: yfinance (미국), KIS/Naver (한국)
- **공시**: SEC (미국), DART (한국)

### 12.2 선택적

- **텔레그램**: 투자 정보 채널 모니터링

---

## 13. 포트폴리오 기능

### 13.1 설정

```yaml
# config.yaml
portfolio:
  - ticker: AAPL
    shares: 10
    avg_price: 150.00
  - ticker: 005930
    shares: 50
    avg_price: 72000
```

### 13.2 출력 예시

```
## 포트폴리오 현황 (2025-04-08)

### AAPL (Apple Inc.)
- 보유: 10주 @ $150.00 → 현재 $178.50 (+19.0%)
- 기술적 분석:
  - 추세: 상승 (20일선 위)
  - 지지선: $172 / 저항선: $185
  - RSI: 58.3 (중립)
- 주요 뉴스:
  - Apple, AI 기능 강화한 iOS 19 발표 예정

### 005930 (삼성전자)
- 보유: 50주 @ ₩72,000 → 현재 ₩78,500 (+9.0%)
- 기술적 분석:
  - 추세: 횡보 (박스권)
  - 지지선: ₩75,000 / 저항선: ₩82,000
- 주요 뉴스:
  - HBM3E 양산 본격화
```

---

## 14. 의존성

```toml
# pyproject.toml
[project]
dependencies = [
    "typer",           # CLI
    "pydantic",        # 데이터 모델
    "pandas",          # 데이터 처리
    "pandas-ta",       # 기술적 지표
    "yfinance",        # 미국 주식 데이터
    "httpx",           # HTTP 클라이언트
    "openai",          # LLM (OpenAI)
    "anthropic",       # LLM (Anthropic)
    "python-dotenv",   # 환경변수
    "pyyaml",          # 설정 파일
]

[project.optional-dependencies]
telegram = ["telethon"]  # 텔레그램 수집 (선택적)
```

---

## 15. 향후 확장

- **RAG**: 수집된 데이터 벡터DB 저장 및 시맨틱 검색
- **추가 전략**: 볼륨 프로파일, 하모닉 패턴 등
- **알림**: 특정 조건 발생 시 알림 (현재 미포함)
