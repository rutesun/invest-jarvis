# 아키텍처

## 공통 차트 사실과 Quality의 책임

원시 시세를 받은 Tools가 버전이 명시된 입력·지표·Event/Observation/Risk를 계산합니다. Strategies는 공통 사실을 선택·조합하고 매수·청산·상태 전이를 소유합니다. Quality는 같은 공통 계층의 strict 특성을 소비하는 독립 상태 요약이며 기존 전략의 입력·판정을 교체하지 않습니다.

Pipelines는 요청 한 번의 불변 분석 묶음과 FactRef를 전달합니다. 동일 표시 사실은 화면에서만 합치고 모든 참조와 선택 이유를 보존합니다. 공통 renderer가 `check`·`analyze`·`brief`에 사실 → Quality를 한 번 출력하며 detail 선택 시 FactRef와 전략 선택 audit를 추가합니다. LLM 입력에는 계산된 설명 자료만 넣고 기존 deterministic action(규칙이 확정한 행동)을 유지합니다.

날짜 계산은 API가 반환한 마지막 관측 세션 T를 기준으로 2년 전 날짜부터의 입력을 준비합니다. 외부 거래일 달력과 대조하거나 응답에 없는 날짜의 행을 생성하지 않습니다. 반환된 OHLCV·finality·최소 봉 수를 검사하며 API 자체의 행 누락은 휴장과 구분하지 않습니다. 기간의 날짜별 계산은 같은 T의 단일 조회와 같은 입력을 사용합니다. 요청 날짜에 봉이 없으면 직전 관측 봉을 사용하고 요청 날짜는 표시 metadata로 보존합니다. 기본·history·기간 조회도 실제 응답 세션을 선택합니다.

기존 분석에서는 이미 받은 raw·실제 공급 기간·봉 finality로 별도 strict 계산을 수행합니다. canonical 원점이 부족하면 세 통합 명령의 AnalysisStrategyService에서 기존 provider의 3y 입력을 최대 한 번 보충합니다. 보충 raw는 Quality 전용이며 원래 전략 raw를 교체하지 않습니다. 날짜·timezone을 정규화하고 평가일까지 자르며 겹치는 유효 OHLCV의 불일치를 거부합니다. 관측 첫날을 상장일로 추정하지 않습니다. 이 경로의 Quality 오류는 신규 표시 metadata로만 전달하며 기존 verdict·warning·직렬화·recorder payload를 변경하지 않습니다. 신규 raw/provider metadata는 기존 serializer에서 제외합니다. supplied-chart의 과거 FINAL 추론은 live range API 검증과 구분합니다.

PositionPlanner는 동일 보유·계좌 입력에서 전략별 독립 수량을 계산합니다. pipeline 결과의 `position_plans`는 strategy_id로 식별하며 단일 `position_plan`은 기존 소비자 호환용입니다. 화면은 keyed plans를 사용하고 수량을 합산하거나 대표 전략을 선택하지 않습니다. verdict 기반 계획 모두에 기존 실행 확인 safeguard를 적용합니다.

독립 날짜/범위 조회의 live transport는 `STUB_ONLY`입니다. offline raw·주입 provider 검증과 기존 normalized 시장 입력 parity는 fresh raw transport 계약 검증을 대신하지 않습니다. 결과 저장소·영속 cache·backfill을 추가하지 않았고 기존 별도 운영 진단 기록은 그대로 유지합니다.

## 레이어 구조

```
Providers → Tools → Strategies → Pipelines → CLI
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
| `technical/` | 8-컴포넌트 시스템 (Minervini, Velocity, CRSI, Volume, Patterns, Supertrend, Divergence, Risk) |
| `fundamental.py` | 기본적 분석 (P/E, EPS 등) |
| `macro.py` | 매크로 지표 (VIX, Fear & Greed, 금리, DXY) |
| `news.py` | 뉴스 검색 및 감성 분석 |
| `screener/` | 유니버스 빌더 + 증거 스코어링 |

### Pipelines (워크플로우 오케스트레이션)
**위치**: `src/pipelines/`

| 파일 | 역할 |
|------|------|
| `quick_check.py` | 빠른 기술적 분석 (LLM 불필요, 다중 티커 지원) |
| `deep_dive.py` | 심층 분석 (기술 + 뉴스 + 재무 + 공시 + 수급 + Macro + 설명 전용 LLM) |
| `brief.py` | playbook.yaml(보유+워치) 기반 일일 액션 브리핑 |
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

## 기술적 분석 컴포넌트 시스템

**위치**: `src/tools/technical/`

**상세 명세**: [`docs/FEATURES.md`](FEATURES.md) 섹션 1 참조

### 8개 컴포넌트
Minervini (추세 추종), Velocity (모멘텀), CRSI (과매수/과매도), Volume (거래량), Patterns (캔들스틱), Supertrend (ATR 추세), Divergence (RSI/MACD), Risk (낙폭/변동성)

### 종합 평가
- 각 컴포넌트 점수 합산
- 시그널/경고/증거 구조화 출력

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
| **Shuffle** | 카테고리 그룹핑 + 기술적 테마 정규화 | ✅ (Haiku 4.5) |
| **Reduce** | 기술적 테마 → 투자 인사이트 변환, 테마별 분석 | ✅ (Haiku 4.5) |
| **Wrapup** | 테마 간 관계 + 매크로 연결, 종합 인사이트 | ✅ (Haiku 4.5) |

### 주요 모델

```python
TelegramMessage       # 원본 메시지
MappedIssue          # Map 출력 (category, themes, keywords)
ShuffleResult        # Shuffle 출력 (category_groups)
ThemeAnalysis        # Reduce LLM 출력 (investment_theme, keywords)
NewsItem             # Reduce 출력 (technical_theme + investment_theme)
DailyReport          # Wrapup 출력 (key_insights + news)
```

### 테마 아키텍처

**이중 테마 시스템**:
- `technical_theme`: Shuffle에서 정규화한 기술적 테마명 (안정적 검색 키)
- `investment_theme`: Reduce LLM이 생성한 투자 인사이트 (표시명)

**검색 흐름**:
1. 사용자 쿼리로 `technical_theme` + `keywords` 검색
2. 매칭된 `NewsItem` 반환
3. UI에는 `investment_theme` 표시

**투자 테마 패턴**:
- 패턴 1: `[트렌드] + [방향성] + [수혜/리스크]`
- 패턴 2: `[원인] + [결과] + [투자 액션]`
- 패턴 3: `[현상] + [구체적 종목/섹터]`
- 길이: 20-40자, 방향성 명확 (가속/둔화/전환)

**설계 스펙**: 
- `docs/superpowers/specs/2026-04-17-category-field-design.md` (카테고리)
- `docs/superpowers/specs/2026-04-19-investment-theme-design.md` (투자 테마)

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

### Notebook → Notion

`src/tools/notebook`은 원본 항목의 identity·metadata와 본문 변환을 담당하고 `src/integrations/notebook_notion`은 Notion 조회·계획·적용을 담당한다. CLI는 기본 read-only client로 snapshot을 읽고 manifest를 만든다. apply는 같은 원본·schema·remote 상태를 재검증하고 journal에 단계별 상태를 기록한다. page ID 할당 → 본문 append → 전체 read-back → property 확정 → 기존 page archive 순서다.

hash는 실제 page ID에 종속되지 않는 logical wikilink를 사용한다. target ID 변경의 참조 page들은 별도 RELINK 후보로 함께 검토한다. 일반 sync는 legacy와 orphan을 변경하지 않는다. 원본 Markdown은 로컬 notebook에 보존하며 Notion에는 읽기용 block만 만든다. 2026-10-26 사용자 지시로 중복 raw 부록을 제거했으며 projection/hash version은 notebook-v2다.

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


notebook의 종목 분류는 `src/providers/stock_search.py`의 Naver 검색 경계와 `src/tools/notebook/stocks.py`의 근거 기반 분류로 분리한다. parser는 raw metadata만 추출한다. CLI는 private 검색 cache와 검토 manifest의 frozen evidence를 관리하며, apply 시 검색을 새로 호출하지 않는다.
