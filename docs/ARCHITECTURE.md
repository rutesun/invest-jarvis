# 아키텍처

## 레이어 구조

```
Providers → Tools → Pipelines → CLI
```

### Providers (데이터 수집)
**위치**: `src/providers/`

| 모듈 | 역할 |
|------|------|
| `yfinance_provider.py` | 미국/글로벌 주식 가격 데이터 |
| `kis.py` | 한국투자증권 API (한국 주식, 포트폴리오) |
| `naver.py` | 네이버 금융 테마, 시가총액 순위 |
| `telegram/` | 텔레그램 채널 메시지 수집 |
| `ticker_resolver.py` | LLM 기반 회사명→티커 변환 (6개월 캐시) |

### Tools (도메인 로직)
**위치**: `src/tools/`

| 모듈 | 역할 |
|------|------|
| `technical/` | 5-전략 시스템 (Trend, Oscillator, Divergence, Disparity, Risk) |
| `fundamental.py` | 기본적 분석 (P/E, EPS 등) |
| `macro.py` | 매크로 지표 (VIX, Fear & Greed, 금리, DXY) |
| `news.py` | 뉴스 검색 및 감성 분석 |
| `screener/` | 유니버스 빌더 + 증거 스코어링 |

### Pipelines (워크플로우 오케스트레이션)
**위치**: `src/pipelines/`

| 파일 | 역할 |
|------|------|
| `quick_check.py` | 빠른 기술적 분석 (LLM 불필요) |
| `deep_dive.py` | 심층 분석 (기술 + 뉴스 + LLM) |
| `daily_market_report.py` | 매크로 + 다중 종목 리포트 |
| `portfolio.py` | 포트폴리오 모니터링 |
| `screener.py` | 시장 스크리너 |
| `daily_report/` | 텔레그램 메시지 MapReduce 파이프라인 |

### LLM (AI 통합)
**위치**: `src/llm/`

| 파일 | 역할 |
|------|------|
| `provider.py` | OpenAI/Anthropic/Bedrock 추상화 |
| `analyzer.py` | 투자 분석 생성 |

### CLI (사용자 인터페이스)
**위치**: `src/cli/main.py`

Typer 기반, Rich 출력

---

## 기술적 분석 전략 시스템

**위치**: `src/tools/technical/`

### 5가지 전략
1. **Trend**: SMA 골든/데드 크로스, ADX 추세 강도
2. **Oscillator**: RSI, Stochastic 과매수/과매도
3. **Divergence**: 가격-지표 다이버전스 패턴
4. **Disparity**: 이격도 극단 진입
5. **Risk**: 변동성, 하락폭, 지지/저항 분석

### 종합 평가
- 각 전략의 시그널을 가중 합산
- 신뢰도 점수 계산 (전략 간 일치도)
- 매수/매도/중립 추천

---

## Daily Report 파이프라인

**위치**: `src/pipelines/daily_report/`

### 5단계 MapReduce

```
Ingest → Map → Shuffle → Reduce → Wrapup
```

| Stage | 역할 | LLM |
|-------|------|-----|
| **Ingest** | 텔레그램 메시지 로드, 필터링 | ❌ |
| **Map** | 메시지 → 투자 이슈 추출, 카테고리 분류 | ✅ (Haiku 4.5) |
| **Shuffle** | 카테고리 그룹핑 + 테마 정규화 | ✅ (Haiku 4.5) |
| **Reduce** | 테마별 분석 리포트 | ✅ (Haiku 4.5) |
| **Wrapup** | 종합 시장 인사이트 도출 | ✅ (Haiku 4.5) |

### 주요 모델

```python
TelegramMessage       # 원본 메시지
MappedIssue          # Map 출력 (category, themes, keywords)
ShuffleResult        # Shuffle 출력 (category_groups)
ThemeAnalysis        # Reduce LLM 출력 (category 제외)
NewsItem             # Reduce 출력 (테마별 분석, category 포함)
DailyReport          # Wrapup 출력 (최종 리포트)
```

**설계 스펙**: `docs/superpowers/specs/2026-04-17-category-field-design.md`

---

## 데이터 흐름 예시

### Quick Check (AAPL)
```
CLI → QuickCheckPipeline
  → YFinanceProvider (가격 데이터)
  → TechnicalTool (5-전략 분석)
  → CLI (Rich 출력)
```

### Deep Dive (AAPL)
```
CLI → DeepDivePipeline
  → YFinanceProvider (가격)
  → TechnicalTool (기술 분석)
  → NewsTool (최근 뉴스)
  → LLMAnalyzer (종합 분석)
  → CLI (Rich 출력)
```

### Daily Report
```
CLI → DailyReportPipeline
  → IngestStage (텔레그램 메시지)
  → MapStage (이슈 추출)
  → ShuffleStage (테마 클러스터링)
  → ReduceStage (테마별 분석)
  → WrapupStage (종합 인사이트)
  → CLI (Markdown 저장)
```

---

## 캐싱 전략

| 캐시 | 위치 | TTL | 용도 |
|------|------|-----|------|
| Ticker Mapping | `~/.cache/invest-jarvis/user_mappings.yaml` | 6개월 | 회사명→티커 변환 |
| LLM Ticker Resolve | SQLite | 6개월 | LLM 티커 해석 결과 |
| 가격 데이터 | 메모리 | 세션 | yfinance API 중복 호출 방지 |
| LLM Prompt | Anthropic API | 5분 | System prompt 캐싱 (`cache_control`, Anthropic만) |
| Fear & Greed | `requests-cache` | 1분 | CNN Fear & Greed Index (`fear-and-greed` 패키지 내장) |

---

## 의존성 관리

**패키지 매니저**: `uv`

**주요 의존성**:
- `yfinance`: 미국 주식 데이터
- `fear-and-greed`: CNN Fear & Greed Index
- `pandas`, `numpy`: 데이터 처리
- `typer`, `rich`: CLI 인터페이스
- `pydantic`: 데이터 검증
- `langchain`: LLM 추상화
- `telethon`: 텔레그램 API
- `pytest`: 테스트
