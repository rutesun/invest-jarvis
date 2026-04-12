# Daily Report V2 설계서

**작성일**: 2026-04-12  
**상위 문서**: [Daily Report V1 설계서](2026-04-12-daily-report-design.md)  
**참고 문서**: [데일리 투자 리포트 파이프라인 구축](../../데일리-투자-리포트-파이프라인-구축.md)  
**커맨드**: `jarvis report`  
**선행 작업**: [Telegram 수집 파이프라인](2026-04-12-telegram-collection-design.md) 구현 완료

---

## 목표

V1 대비 핵심 변경:
- **테마/내러티브 중심** 리포트 (종목 나열 → 시장 스토리)
- **병렬 데이터 수집** + **수급/거래량 교차 보강**
- **LLM tool calling**으로 주도주 촉매 뉴스 자동 매칭
- **각 Stage를 독립 실행/튜닝 가능**한 구조

---

## 파이프라인 아키텍처

```
┌─────────── Stage 1: Parallel Ingestion ───────────┐
│  Telegram CSV | MacroTool | 시장뉴스 | KIS수급/US모멘텀 │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─────────── Stage 2: LLM Map ──────────────────────┐
│  텔레그램 50건 청크 → gpt-4o-mini 병렬              │
│  → List[IssueExtract]                              │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─────────── Stage 3: Shuffle & Filter (코드+LLM) ───┐
│  테마 병합(LLM) → 정규화 → 그룹핑 → 수급/거래량 보강  │
│  → List[Theme]                                     │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─────────── Stage 4: LLM Catalyst ─────────────────┐
│  주도주별 뉴스 검색 (NewsTool + TickerResolver)      │
│  → List[StockCatalyst]                             │
└──────────────────────┬────────────────────────────┘
                       ▼
┌─────────── Stage 5: LLM Synthesize ───────────────┐
│  전체 통합 → 최종 리포트 3섹션 생성                   │
│  → DailyReport                                     │
└──────────────────────┬────────────────────────────┘
                       ▼
              터미널 Rich 출력 + MD 파일 저장
```

**설계 원칙:**
- Stage 1, 2: 속도 (병렬 수집, 저비용 모델)
- Stage 3: 정확성 (코드로 확정적 필터링, LLM 환각 방지)
- Stage 4: 깊이 (tool calling으로 촉매 검증)
- Stage 5: 통찰 (고급 모델로 내러티브 합성)

---

## Stage별 독립 실행 구조

각 Stage는 **입력 JSON을 받아 출력 JSON을 생성**하는 독립 단위.
중간 결과를 파일로 저장/로드하여 반복 튜닝 가능.

```bash
# 전체 파이프라인 실행
uv run jarvis report

# Stage별 독립 실행 (튜닝용)
uv run jarvis report --stage ingest       # Stage 1만 실행 → .cache/report/1_ingest.json
uv run jarvis report --stage map          # Stage 2만 실행 (1 결과 로드) → .cache/report/2_map.json
uv run jarvis report --stage shuffle      # Stage 3만 실행 (2 결과 로드) → .cache/report/3_shuffle.json
uv run jarvis report --stage catalyst     # Stage 4만 실행 (3 결과 로드) → .cache/report/4_catalyst.json
uv run jarvis report --stage synthesize   # Stage 5만 실행 (3+4 결과 로드) → .cache/report/5_synthesize.json

# 특정 Stage부터 이어서 실행
uv run jarvis report --from shuffle       # Stage 3부터 끝까지 (1,2 캐시 사용)
```

### 중간 결과 저장 경로

```
.cache/report/
  YYYY-MM-DD/
    1_ingest.json       # Stage 1 출력
    2_map.json          # Stage 2 출력
    3_shuffle.json      # Stage 3 출력
    4_catalyst.json     # Stage 4 출력
    5_synthesize.json   # Stage 5 출력
```

- 각 Stage 실행 시 이전 Stage 결과를 `.cache/report/YYYY-MM-DD/`에서 자동 로드
- `--stage` 실행 시 해당 Stage의 이전 결과가 없으면 에러
- 전체 실행(`jarvis report`)은 항상 Stage 1부터 시작, 모든 중간 결과 저장

---

## 데이터 모델

```python
from pydantic import BaseModel
from typing import Literal

# ─── Stage 1 Ingest 출력 ───

class IngestResult(BaseModel):
    telegram_messages: list[dict] # 텔레그램 CSV 로드 결과 [{id, channel, text, timestamp}, ...]
    macro_snapshot: dict          # MacroSnapshot 직렬화 (VIX, F&G, 금리, DXY, WTI)
    market_news: list[dict]       # 시장 주요 뉴스 [{title, summary, source, url}, ...]
    kr_flow: list[dict]           # KIS 외인/기관 순매수 Top N [{ticker, name, foreign_net, inst_net}, ...]
    momentum: list[dict]       # 거래량/등락률 상위 [{ticker, price, change_pct, volume_ratio}, ...]

# ─── Stage 2 Map 출력 ───

class IssueExtract(BaseModel):
    theme: str                    # "CPO/광통신", "AI 반도체", "방산"
    tickers: list[str]            # 원문 그대로 ["엔비디아", "LITE", "코위버"]
    sentiment: Literal["bull", "bear", "neutral"]
    summary: str                  # 메시지 핵심 요약
    source_ids: list[int]         # 원본 메시지 참조 ID

# ─── Stage 3 Shuffle 출력 ───

class StockDetail(BaseModel):
    ticker: str                   # 정규화된 티커 "NVDA"
    market: Literal["KR", "US"]
    mention_count: int            # 텔레그램 언급 횟수
    flow_score: float | None      # KR: 외인/기관 수급 점수
    volume_score: float | None    # KR/US 공통: 거래량/등락률 점수
    source: Literal["telegram", "market_data", "both"]
    summaries: list[str]          # 관련 IssueExtract.summary 모음 (Stage 4 촉매 분석용)

class Theme(BaseModel):
    name: str                     # 정규화된 테마명
    narrative: str                # 테마가 왜 주목받는지 한줄 요약 (IssueExtract.summary 집약)
    sentiment: Literal["bull", "bear", "neutral"]
    mention_count: int            # 테마 전체 언급 빈도
    stocks: list[str]             # 정렬된 주도주 티커 ["NVDA", "LITE", "코위버"]

class ShuffleResult(BaseModel):
    themes: list[Theme]
    stock_details: dict[str, StockDetail]  # ticker → 상세 메타데이터 (테마 간 공유)

# ─── Stage 4 Catalyst 출력 ───

class StockCatalyst(BaseModel):
    ticker: str
    themes: list[str]             # 소속 테마들 (복수 가능: NVDA → ["AI 반도체", "CPO/광통신"])
    news: list[str]               # 촉매 뉴스 제목들
    catalyst_summary: str         # "TSMC 실적 발표 → CPO 수요 확대 기대"

# ─── Stage 5 최종 리포트 ───

class DailyReport(BaseModel):
    date: str
    market_pulse: str             # 시장 온도 (10줄 이내)
    narrative_and_themes: str     # 시장 내러티브 + 주목 테마
    featured_analysis: str        # 주도주 분석 (테마별)
```

---

## Stage 상세

### Stage 1: Parallel Ingestion

5개 소스를 `asyncio.gather`로 병렬 수집.

| 소스 | 도구 | 데이터 | 비고 |
|------|------|--------|------|
| 텔레그램 CSV | `telegram_collector` | 전날~당일 메시지 | telegram-collection 설계 활용 |
| 매크로 | `MacroTool` | VIX, F&G, 금리, DXY, WTI | 기존 `macro.py` 활용 |
| 시장 뉴스 | `NewsTool` | 주요 지수 관련 뉴스 | SPY, QQQ, KOSPI 등 키워드 검색 |
| KR 수급 | KIS API | 외인/기관 순매수 Top N | 기존 screener KIS 연동 활용 |
| US 모멘텀 | yfinance | 거래량 폭발 + 등락률 상위 | S&P 500 + NASDAQ 100 구성종목 |

**매크로와 시장 뉴스**는 파이프라인이 직접 수집 → 이후 LLM 컨텍스트로 제공.

**출력**: `IngestResult(telegram_messages, macro_snapshot, market_news, kr_flow, momentum)`

---

### Stage 2: LLM Map

텔레그램 메시지에서 테마/종목/감성을 구조화 추출.

- 메시지를 **50건 단위 청크**로 분할
- 각 청크를 `gpt-4o-mini`로 병렬 처리 (`asyncio.gather`)
- `with_structured_output(list[IssueExtract])` 사용
- 노이즈 메시지(잡담, 광고)는 LLM이 필터링

**프롬프트 핵심 지시:**
```
아래 텔레그램 메시지들에서 투자 관련 이슈를 추출하세요.
각 이슈에 대해:
- theme: 투자 테마명. 아래 기존 테마 목록에 해당하면 그대로 사용하고,
         해당하지 않으면 새 테마명을 자유 생성하세요.
- tickers: 언급된 종목명 (원문 그대로, 정규화하지 않음)
- sentiment: 시장 영향 방향 (bull/bear/neutral)
- summary: 핵심 내용 요약 (1-2문장)
- source_ids: 해당 메시지 ID 목록

기존 테마 목록:
{known_themes}

잡담, 광고, 투자와 무관한 메시지는 무시하세요.
한 메시지가 여러 테마를 다루면 각각 별도 IssueExtract로 분리하세요.
```

**알려진 테마 목록**: `themes.yaml`에서 관리. Map 프롬프트에 주입하여 1차 정규화.

**입력**: `IngestResult.telegram_messages`  
**출력**: `list[IssueExtract]`

---

### Stage 3: Shuffle & Filter (코드 + LLM 경량 호출)

테마 중심 구조화. 대부분 코드로 처리하되, 테마 병합만 LLM 1회 호출.

```
Step 1: 테마 병합 (LLM 경량 호출 1회)
  - Map에서 나온 전체 테마명 목록을 LLM에 전달
  - "유사한 테마를 병합하세요" (예: "CPO" + "광통신" + "co-packaged optics" → "CPO/광통신")
  - gpt-4o-mini로 가볍게 처리
  - 병합 결과를 themes.yaml의 알려진 테마 목록에 자동 추가 (학습 효과)

Step 2: 코드 처리 — 테마/종목 구조화
  - TickerResolver로 종목명 → 티커 변환 (KR/US 구분 없이, 캐시 활용)
  - 병합된 테마명으로 그룹핑: mention_count, sentiment 다수결 집계
  - 테마 내 종목별 언급 빈도 집계
  - Theme.narrative: 해당 테마의 IssueExtract.summary들을 연결하여 생성 (가장 빈번한 요약 기반)
  - ThemeStock.summaries: 해당 종목 관련 IssueExtract.summary 모음 (Stage 4에서 촉매 분석 시 활용)

Step 3: 시장 데이터로 보강
  - KR 종목: KIS 외인/기관 순매수 데이터와 교차 → flow_score 부여
  - US 종목: 거래량 폭발 + 등락률 데이터와 교차 → volume_score 부여
  - 수급/거래량 상위인데 테마에 없는 종목:
    → Step 1의 merge_themes LLM 호출 시 미편입 종목도 함께 전달하여 테마 배정
    → 어떤 테마에도 맞지 않으면 "기타 수급 특징주" 테마 자동 생성

Step 4: 선별
  - 테마 Top N 선별 (mention_count 기준, N=5~7)
  - 테마 내 종목은 mention_count + flow_score/volume_score 가중합으로 정렬
```

**테마 정규화 2단계 전략:**
1. **Map 시점 (1차)**: 프롬프트에 `themes.yaml`의 알려진 테마 목록을 주입 → 대부분 정규화
2. **Shuffle 시점 (2차)**: Map에서 새로 생성된 테마들 중 유사한 것을 LLM 1회 호출로 병합
   - 병합 결과를 `themes.yaml`에 반영 → 다음 실행 시 Map에서 바로 정규화됨 (학습 루프)

**입력**: `list[IssueExtract]` + `IngestResult.kr_flow` + `IngestResult.momentum`  
**출력**: `ShuffleResult(themes, stock_details)`

---

### Stage 4: LLM Catalyst

주도주에 대해 "왜 주목받는지" 촉매 뉴스를 검색.

- 입력: `ShuffleResult` — themes의 테마별 상위 2~3개 종목 + stock_details에서 summaries 참조
- 모델: `gpt-4o` (tool calling 안정성)
- LLM에 제공하는 tools:
  - `NewsTool`: 종목/키워드로 최근 뉴스 검색
  - `TickerResolver`: 종목명 → 정확한 티커 변환
- LLM이 테마 맥락을 이해하고 관련 뉴스를 능동적으로 검색

**프롬프트 핵심 지시:**
```
아래 테마별 주도주 목록이 주어집니다.
각 종목에 대해 NewsTool로 최근 뉴스를 검색하고,
해당 종목이 주목받는 촉매(catalyst)를 파악하세요.

테마당 상위 2-3개 종목에 집중하세요.
뉴스가 없는 종목은 텔레그램 원문 요약을 촉매로 사용하세요.
```

**입력**: `ShuffleResult` (테마당 상위 종목 + stock_details)  
**출력**: `list[StockCatalyst]`

---

### Stage 5: LLM Synthesize

모든 데이터를 통합하여 최종 리포트 3섹션 생성.

- 모델: `claude-sonnet` (내러티브 생성 품질)
- 입력 컨텍스트:
  - `IngestResult.macro_snapshot` — 매크로 지표
  - `IngestResult.market_news` — 시장 주요 뉴스
  - `ShuffleResult` — 테마 + 종목 상세
  - `list[StockCatalyst]` — 촉매 분석 결과

**출력 3섹션:**

#### 시장 온도 (Market Pulse) — 10줄 이내

매크로 수치 해석 + 시장 분위기 판단. 지표 나열이 아닌 의미 해석.
```
VIX 18.2(+1.3) | F&G 62(Greed) | DXY 104.2(-0.3) | US10Y 4.32% | WTI $78.5

리스크온 환경 지속. VIX 소폭 상승했으나 여전히 안정 구간.
Fear&Greed 탐욕 영역 진입으로 단기 과열 경계 필요.
달러 약세 전환 조짐이 신흥국/원자재 관련주에 우호적.
금리 스프레드 축소 지속 — 경기 둔화 시그널 병존.
```

#### 시장 내러티브 & 주목 테마

테마 간 연결고리, 왜 지금 이 테마가 부상하는지 맥락 설명.
```
오늘 시장의 핵심은 AI 인프라 투자 확대입니다.
TSMC 실적 호조가 확인되며 CPO/광통신 테마가 한미 양시장에서 동시 강세...

주목 테마:
1. CPO/광통신 (Bull) — TSMC 실적 → 데이터센터 CAPEX 확대 확인
   관련: 코위버, 옵티시스, LITE, COHR
2. AI 반도체 (Bull) — NVDA 차세대 칩 발표 임박
   관련: SK하이닉스, NVDA, AMD
3. ...
```

#### 주도주 분석

테마별 핵심 종목 + 촉매 + 수급/거래량 근거.
```
[CPO/광통신]
- 코위버 (A058400.KQ): 외인 순매수 +30억, 기관 +15억
  촉매: TSMC CoWoS 증설 발표 → CPO 모듈 수요 증가 수혜
- LITE (LITE): 거래량 3.2x, +5.8%
  촉매: 광트랜시버 분기 매출 가이던스 상향
```

---

## CLI 인터페이스

```bash
# 전체 파이프라인 실행
uv run jarvis report
uv run jarvis report --provider anthropic

# Stage별 독립 실행 (튜닝용)
uv run jarvis report --stage ingest
uv run jarvis report --stage map
uv run jarvis report --stage shuffle
uv run jarvis report --stage catalyst
uv run jarvis report --stage synthesize

# 특정 Stage부터 이어서 실행
uv run jarvis report --from shuffle

# 파일 저장 안함
uv run jarvis report --no-save
```

**V1 대비 변경:**
- `--tickers` 옵션 제거 (파이프라인이 자동 선별)
- `--stage`, `--from`, `--no-save` 옵션 추가

---

## 출력 & 저장

### 터미널 출력
Rich 마크다운 렌더링. 전체 리포트 출력.

### 파일 저장
- 경로: `reports/YYYY-MM/YYYY-MM-DD.md`
- 터미널과 동일 내용의 마크다운 버전
- `reports/` 디렉토리 자동 생성
- `--no-save` 시 저장 생략

---

## 기술 요구사항

| 항목 | 내용 |
|------|------|
| 선행 조건 | Telegram 수집 파이프라인 구현 완료 |
| 기존 활용 | `macro.py`, `news.py`, `kis.py`, `ticker_resolver.py` |
| 신규 모듈 | `src/pipelines/daily_report_v2.py` (오케스트레이터) |
| 신규 모듈 | `src/llm/daily_report_models.py` (Pydantic 모델) |
| 신규 모듈 | `src/llm/daily_report_analyzer.py` (Map/Catalyst/Synthesize) |
| LLM | Map: `gpt-4o-mini`, Catalyst: `gpt-4o`, Synthesize: `claude-sonnet` |
| 중간 결과 | `.cache/report/YYYY-MM-DD/*.json` |
| 최종 출력 | 터미널 Rich + `reports/YYYY-MM/YYYY-MM-DD.md` |

### 파일 구조

```
src/
  pipelines/
    daily_report_v2.py          # 파이프라인 오케스트레이터
    report_stages/
      __init__.py
      ingest.py                 # Stage 1: 병렬 수집
      map_issues.py             # Stage 2: LLM Map
      shuffle_filter.py         # Stage 3: 코드 정규화/필터링
      catalyst.py               # Stage 4: LLM Catalyst
      synthesize.py             # Stage 5: LLM Synthesize
  llm/
    daily_report_models.py      # IssueExtract, Theme, StockCatalyst, DailyReport
    daily_report_analyzer.py    # LLM 호출 함수 (map_chunk, find_catalysts, synthesize_report)
    prompts/
      daily_report.py           # DailyReportPrompts (static methods)
```

각 Stage는 `stages/` 아래 독립 모듈로 분리.
`daily_report_v2.py`가 Stage 간 연결 + 중간 결과 저장/로드 관리.

---

## 튜닝 & 디버깅: LangSmith 연동

### 기본 설정

LangChain 트레이싱을 활성화하여 모든 LLM 호출을 LangSmith에 기록.

```bash
# .env에 추가
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls-...
LANGCHAIN_PROJECT=jarvis-daily-report
```

### Stage별 트레이싱 태깅

각 LLM 호출에 `run_name`과 `metadata`를 부여하여 LangSmith에서 Stage별 필터링 가능.

```python
# Stage 2 Map — 청크별 태깅
llm.invoke(prompt, config={
    "run_name": "map_chunk_3",
    "metadata": {"stage": "map", "chunk_index": 3, "chunk_size": 50}
})

# Stage 4 Catalyst — 테마/종목별 태깅
llm.invoke(prompt, config={
    "run_name": "catalyst_CPO_LITE",
    "metadata": {"stage": "catalyst", "theme": "CPO/광통신", "ticker": "LITE"}
})

# Stage 5 Synthesize
llm.invoke(prompt, config={
    "run_name": "synthesize_final",
    "metadata": {"stage": "synthesize", "theme_count": 5}
})
```

### LangSmith MCP 연동 — Claude Code에서 직접 프롬프트 튜닝

LangSmith MCP 서버를 Claude Code에 연결하면, CLI 실행 후 Claude Code 안에서 바로 트레이스를 조회하고 프롬프트를 개선할 수 있다.

**튜닝 워크플로우:**

```
1. CLI에서 Stage 실행
   $ uv run jarvis report --stage map

2. Claude Code에서 LangSmith MCP로 트레이스 조회
   → "방금 실행한 map stage 트레이스 보여줘"
   → 각 청크의 prompt/response, 토큰 사용량, 응답 품질 확인

3. 문제 발견 시 Claude Code가 직접 프롬프트 수정
   → "map 프롬프트에서 sentiment 추출이 부정확해. bull/bear 판단 기준을 명확히 해줘"
   → 프롬프트 파일 수정 → 재실행 → 트레이스 비교

4. LangSmith Prompt Hub 연동 (선택)
   → 프롬프트 버전 관리
   → A/B 비교
```

**MCP 설정** (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "langsmith": {
      "type": "stdio",
      "command": "npx",
      "args": ["@langchain/langsmith-mcp-server"],
      "env": {
        "LANGSMITH_API_KEY": "${LANGSMITH_API_KEY}"
      }
    }
  }
}
```

**LangSmith MCP로 할 수 있는 것:**
- 최근 트레이스 조회 및 필터링 (stage, run_name, 날짜별)
- 특정 LLM 호출의 정확한 prompt/response 확인
- 런 간 비교 (프롬프트 수정 전/후)
- 토큰 사용량, 레이턴시 분석
- 프롬프트를 LangSmith Prompt Hub에서 가져오기/업데이트

### 프롬프트 관리

LLM 프롬프트는 Python static method로 관리. 변수 바인딩이 명시적이고 IDE 자동완성/타입 힌트 지원.

```python
# src/llm/prompts/daily_report.py

class DailyReportPrompts:
    @staticmethod
    def map_issues(known_themes: str, messages: str) -> str:
        """Stage 2: 텔레그램 메시지에서 테마/종목/감성 추출"""
        return f"""아래 텔레그램 메시지들에서 투자 관련 이슈를 추출하세요.
각 이슈에 대해:
- theme: 투자 테마명. 아래 기존 테마 목록에 해당하면 그대로 사용하고,
         해당하지 않으면 새 테마명을 자유 생성하세요.
- tickers: 언급된 종목명 (원문 그대로, 정규화하지 않음)
- sentiment: 시장 영향 방향 (bull/bear/neutral)
- summary: 핵심 내용 요약 (1-2문장)
- source_ids: 해당 메시지 ID 목록

기존 테마 목록:
{known_themes}

잡담, 광고, 투자와 무관한 메시지는 무시하세요.
한 메시지가 여러 테마를 다루면 각각 별도로 분리하세요.

메시지:
{messages}"""

    @staticmethod
    def merge_themes(known_themes: str, new_themes: str) -> str:
        """Stage 3 Step 1: 유사 테마 병합"""
        return f"""아래에 기존 테마 목록과 새로 추출된 테마 목록이 있습니다.
새 테마 중 기존 테마와 동일하거나 유사한 것은 기존 테마명으로 매핑하고,
완전히 새로운 테마는 그대로 유지하세요.

기존 테마 목록:
{known_themes}

새로 추출된 테마:
{new_themes}

출력: {{"매핑": {{"원래 테마명": "정규화된 테마명", ...}}}}"""

    @staticmethod
    def catalyst(themes_json: str) -> str:
        """Stage 4: 주도주별 촉매 뉴스 검색"""
        return f"""아래 테마별 주도주 목록이 주어집니다.
각 종목에 대해 NewsTool로 최근 뉴스를 검색하고,
해당 종목이 주목받는 촉매(catalyst)를 파악하세요.

테마당 상위 2-3개 종목에 집중하세요.
뉴스가 없는 종목은 텔레그램 원문 요약을 촉매로 사용하세요.

테마 및 주도주:
{themes_json}"""

    @staticmethod
    def synthesize(macro: str, news: str, themes: str, catalysts: str) -> str:
        """Stage 5: 전체 통합 리포트 생성"""
        return f"""아래 데이터를 기반으로 일일 시장 리포트를 작성하세요.

3개 섹션으로 구성:
1. 시장 온도 (10줄 이내): 매크로 수치 해석 + 시장 분위기 판단
2. 시장 내러티브 & 주목 테마: 흐름 스토리 + 테마 간 연결고리
3. 주도주 분석: 테마별 핵심 종목 + 촉매 + 수급/거래량 근거

매크로:
{macro}

시장 뉴스:
{news}

테마 분석:
{themes}

촉매 분석:
{catalysts}"""
```

**장점:**
- 프롬프트 시그니처만 보면 어떤 데이터가 필요한지 파악 가능
- 변수 바인딩이 명시적 — f-string으로 데이터 주입
- IDE 자동완성, 타입 힌트, 리팩토링 지원
- 프롬프트 수정 → Stage 재실행 → LangSmith 트레이스 비교
- 향후 LangSmith Prompt Hub로 마이그레이션 가능
