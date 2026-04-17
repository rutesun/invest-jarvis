# 코드 플로우 정리: Report V1 / V2 / Portfolio Brief

> 작성일: 2026-04-11

---

## 목차

1. [전체 구조 개요](#전체-구조-개요)
2. [Report V1](#report-v1)
3. [Report V2](#report-v2)
4. [Portfolio Brief](#portfolio-brief)
5. [공유 모듈](#공유-모듈)
6. [섹터 분류 체계](#섹터-분류-체계)

---

## 전체 구조 개요

```
src/
├── report.py                          # Report V1 진입점
├── report_v2.py                       # Report V2 진입점
├── llm/
│   ├── models.py                      # 공유 데이터 모델 (DailyReport, NewsItem, KeyTheme)
│   ├── daily_analysis.py              # V1 LLM 분석 엔진 (Map-Reduce)
│   ├── daily_analysis_v2.py           # V2 LLM 분석 엔진 (Map-Filter-Reduce-Wrapup)
│   └── analysis_engine_v2.py         # V2 엔진 구현체 (LLMAnalysisEngine)
└── analysis/
    ├── tools/
    │   ├── base.py                    # BaseAnalysisTool (ABC)
    │   ├── technical/tool.py          # 기술적 분석 도구
    │   ├── news/tool.py               # 뉴스 수집 도구
    │   └── disclosure/                # 공시 수집 도구 (SEC, DART)
    └── portfolio_brief/
        ├── engine.py                  # Portfolio Brief 메인 엔진
        ├── models.py                  # BriefItem, BriefEvent, PortfolioBriefResult
        ├── chart_state.py             # 차트 점수화
        ├── news_disclosure.py         # 뉴스/공시 이벤트 랭킹
        ├── scoring.py                 # 점수 합산
        └── renderer.py                # 마크다운 렌더링
```

---

## Report V1

### 파일

`src/report.py`

### 진입점 함수

| 함수 | 설명 |
|------|------|
| `generate_daily_report(target_date)` | 날짜 기반 일일 리포트 생성 |
| `generate_report_from_file(file_path)` | 파일 경로 기반 리포트 생성 |
| `_generate_markdown_file(date_str)` | 내부 마크다운 생성 함수 |

### 파이프라인

```
CSV 메시지 파일
    │
    ▼
load_messages_for_date() / load_messages_from_file()
    │
    ▼
List[Dict]  ── message_id, channel_name, content, ...
    │
    ▼
analyze_messages()  ── src.llm.daily_analysis
    ├─ _analyze_chunk()  [50개 메시지 단위 청킹]
    │   └─ LLM (gpt-5, temperature=0)
    └─ _merge_reports()  [청크 결과 병합]
    │
    ▼
DailyReport(major_issues, news_items)
    │
    ├─▶ save_daily_summary()  [DB 저장]
    ├─▶ save_news_items()     [DB 저장]
    │
    ▼
_generate_markdown_file()
    ├─ Key Market Themes
    ├─ Macroeconomy News
    └─ Sector Analysis  [8개 섹터별 분류 + 아이콘 매핑]
    │
    ▼
Markdown 파일
    │
    ▼
publish_report_file()  ── Notion 발행
```

### LLM 분석 엔진 V1 (`src/llm/daily_analysis.py`)

- **Map**: `_analyze_chunk(chunk)` — 50개 메시지 청크를 LLM으로 분석
- **Reduce**: `_merge_reports(chunk_results)` — 청크 결과 병합
- **LLM 모델**: `gpt-5`

---

## Report V2

### 파일

`src/report_v2.py`

### 진입점 함수

| 함수 | 설명 |
|------|------|
| `generate_daily_report_v2(target_date)` | 날짜 기반 V2 리포트 생성 |
| `generate_report_from_file_v2(file_path, date_str)` | 파일 경로 기반 V2 리포트 생성 |
| `generate_report_from_messages_v2(messages, date_str, analyzer)` | 메시지 리스트에서 직접 생성 (테스트 가능) |

### 파이프라인

```
CSV 메시지 파일
    │
    ▼
load_messages_for_date() / load_messages_from_file()
    │
    ├──────────────────────────────────────────────┐
    ▼                                              ▼
analyze_messages_v2()                   _build_evidence_lookup()
    │                                              │
    ▼                                              ▼
DailyReport                          ref_lookup  (ID → 원문)
(key_themes,                         id_lookup   (ID → [(channel, content)])
 major_issues,
 news_items)
    │
    └──────────────────────────┬──────────────────┘
                               ▼
                   _generate_markdown_file()
                       ├─ Key Themes (description + impact_points)
                       ├─ Macroeconomy News
                       └─ Sector Analysis  [근거 출처 포함]
                               │
                               ▼
                          Markdown 파일
                               │
                               ▼
                      publish_report_file()  ── Notion 발행
```

### LLM 분석 엔진 V2 (`src/llm/daily_analysis_v2.py`)

**4단계 파이프라인**:

```
messages (List[Dict])
    │
    ▼  [1단계: Map]
_map_phase()
    └─ engine.map_chunk(chunk)  ── LLM (gpt-5-mini)
       └─ List[MappedIssue]
           ├─ sector: str
           ├─ category: Company | Industry | Macroeconomy
           ├─ topic: str
           ├─ context: str
           ├─ keywords: List[str]
           └─ original_message_ids: List[str]
    │
    ▼  [2단계: Filter]
_filter_phase()
    └─ 상위 5개 키워드 추출  ── normalize_keywords()
    │
    ▼  [3단계: Reduce]
_reduce_phase()
    └─ engine.reduce_sector(sector, issues)  ── LLM (gpt-5.2)
       └─ List[NewsItem]
           ├─ category, topic, summary, impact
           ├─ market_view: Bull | Bear | None
           ├─ sector: str
           └─ original_message_ids: List[str]
    │
    ▼  [4단계: Wrapup]
_wrapup_phase()
    └─ engine.wrapup(news_items, top_keywords)  ── LLM (gpt-5-mini)
       ├─ List[KeyTheme]  (title, description, impact_points)
       └─ List[str]  (major_issues)
    │
    ▼
DailyReport
```

### LLMAnalysisEngine (`src/llm/analysis_engine_v2.py`)

| 메서드 | LLM 모델 | 역할 |
|--------|----------|------|
| `map_chunk(messages)` | gpt-5-mini | 청크에서 MappedIssue 추출 |
| `reduce_sector(sector, issues)` | gpt-5.2 | 섹터별 이슈 병합 → NewsItem |
| `wrapup(news_items, top_keywords)` | gpt-5-mini | 키워드 기반 테마/이슈 생성 |

### 정규화 함수 (`src/llm/analysis_engine_v2.py`)

| 함수 | 역할 |
|------|------|
| `normalize_sector(s)` | 8개 표준 섹터로 매핑 |
| `normalize_category(c)` | Company \| Industry \| Macroeconomy |
| `normalize_keywords(kws)` | 키워드 리스트 정규화 |
| `normalize_market_view(v)` | Bull \| Bear \| None |
| `normalize_refs(refs)` | 참조 ID 정규화 |

### 마크다운 생성 헬퍼 함수 (`src/report_v2.py`)

| 함수 | 역할 |
|------|------|
| `_build_evidence_lookup(messages)` | 메시지 ID → 원문 텍스트 룩업 생성 |
| `_resolve_evidence_lines(ids, id_lookup)` | 참조 ID → 근거 텍스트 추출 (최대 2줄) |
| `_extract_impact(item)` | NewsItem의 impact 필드 추출 |
| `_render_company_list(item)` | 중복 제거된 기업 리스트 생성 |

### V1 vs V2 차이점

| 항목 | V1 | V2 |
|------|----|----|
| LLM 단계 | 2단계 (Map-Reduce) | 4단계 (Map-Filter-Reduce-Wrapup) |
| LLM 모델 | gpt-5 단일 | gpt-5-mini / gpt-5.2 용도별 분리 |
| 근거 출처 | 미지원 | 원본 메시지 ID 추적 |
| Key Themes | 없음 | KeyTheme (title + description + impact_points) |
| 뉴스 영향도 | 없음 | impact 필드 별도 분리 |
| DB 저장 | 있음 | 없음 (Notion 발행만) |

---

## Portfolio Brief

### 파일

```
src/analysis/portfolio_brief/
├── engine.py           # 메인 엔진 (run_portfolio_brief)
├── models.py           # 데이터 모델
├── chart_state.py      # 차트 점수화 (0-60점)
├── news_disclosure.py  # 뉴스/공시 이벤트 랭킹 (0-40점)
├── scoring.py          # 점수 합산 (0-100점)
└── renderer.py         # 마크다운 렌더링
```

### 진입점

`async def run_portfolio_brief(mode: str, reference_time: datetime | None) -> PortfolioBriefResult`

- `mode`: `"open"` (장초) | `"close"` (장마감)

### 파이프라인

```
NaverHoldingsAPI.from_env().list_item_codes()
    │
    ▼
보유 종목 리스트 (ticker codes)
    │
    ▼  [Semaphore(6) 병렬 수집]
asyncio.gather(*tasks)
    └─ _guarded_collect()
        └─ _collect_item(ticker)
               │
               ├─ TechnicalAnalysisTool.analyze_async()
               │   └─ AnalysisResult
               │       ├─ assessment (강력매수 ~ 강력매도)
               │       ├─ confidence
               │       ├─ indicators (RSI, MACD, ...)
               │       └─ patterns (VCP, PocketPivot, ...)
               │
               ├─ NewsAnalysisTool.analyze_async()
               │   └─ List[NewsItem]
               │
               ├─ DisclosureAnalysisTool.analyze_async()  [해외: SEC]
               │   └─ List[DisclosureItem]
               │
               ├─ KRDisclosureAnalysisTool.analyze_async()  [국내: DART]
               │   └─ List[DisclosureItem]
               │
               ├─ _fetch_naver_realtime_snapshot_sync()  [KR 종목 시간외 거래가]
               │
               ├─ summarize_chart_state()
               │   └─ (chart_summary, chart_metrics, price_levels, one_line_comment, chart_score)
               │       차트 점수: 0-60점
               │       ├─ _assessment_to_score()  [기본: 16~60]
               │       ├─ confidence bonus         [최대 +12]
               │       ├─ pattern bonus            [최대 +4]
               │       └─ warning penalty          [최대 -4]
               │
               ├─ build_ranked_events()
               │   └─ (List[BriefEvent], news_score)
               │       뉴스 점수: 0-40점
               │       ├─ get_time_window()  [open: 전일 15:30~ / close: 당일 09:00~]
               │       ├─ 뉴스 룩백: 72시간
               │       ├─ _calc_importance()  [기본: News 1.0 / Disclosure 1.4 + 키워드 보너스]
               │       └─ 상위 5개 이벤트 선택
               │
               └─ combine_scores(chart_score, news_score)
                   └─ total_score: 0-100점
    │
    ▼
List[BriefItem]  [total_score 역순 정렬]
    │
    ▼
render_markdown()
    │
    ▼
write_markdown_report()  [파일 저장]
    │
    ├─▶ (선택) _send_telegram_report()  [PORTFOLIO_BRIEF_SEND_TELEGRAM 환경변수]
    │          └─ 3500자 단위로 청킹 송신
    │
    ▼
PortfolioBriefResult(mode, reference_time, report_path, tickers_count, items, errors)
```

### 데이터 모델 (`src/analysis/portfolio_brief/models.py`)

```python
BriefEvent:
    title: str
    source: str
    published_at: datetime
    kind: "news" | "disclosure"
    importance: float          # 최대 4.0
    url: str

BriefItem:
    ticker: str
    company_name: str
    product_type: "domestic" | "overseas"
    chart_summary: str
    chart_metrics: str
    price_levels: str
    one_line_comment: str
    chart_score: float          # 0-60
    news_score: float           # 0-40
    total_score: float          # 0-100
    events: List[BriefEvent]

PortfolioBriefResult:
    mode: str
    reference_time: datetime
    report_path: str | None
    tickers_count: int
    items: List[BriefItem]
    errors: List[str]
```

### 뉴스 중요도 계산 (`src/analysis/portfolio_brief/news_disclosure.py`)

| 조건 | 가중치 |
|------|--------|
| News 기본값 | 1.0 |
| Disclosure 기본값 | 1.4 |
| 키워드 보너스 (실적/가이던스/수주/계약/합병 등) | +0.5씩 |
| 최대값 | 4.0 |

### 마크다운 출력 형식 (`src/analysis/portfolio_brief/renderer.py`)

```markdown
# 보유종목 장초/장마감 브리핑
- 기준시각(KST): YYYY-MM-DD HH:MM
- 종목수: N

## 1. TICKER (회사명) | 종합점수 X.XX (차트 X.XX / 뉴스·공시 X.XX)
- 차트요약: ...
- 차트메트릭: 등락률 | 거래량강도 | 변동폭 | 시간외
- 가격: X.XX | 손절 Y.YY | 지지 Z.ZZ | 슈퍼트렌드 W.WW
- 한줄코멘트: ...
- 주요 뉴스/공시:
  - [kind] title (source, published_at)
  ...
```

---

## 공유 모듈

### LLM 데이터 모델 (`src/llm/models.py`)

Report V1/V2가 공통으로 사용하는 모델:

```python
KeyTheme:
    title: str
    description: str
    impact_points: List[str]

NewsItem:
    category: str              # Company | Industry | Macroeconomy
    topic: str
    summary: str               # 2~4문장
    impact: str                # 한 줄
    market_view: "Bull" | "Bear" | None
    sector: str
    original_message_ids: List[str]

DailyReport:
    key_themes: List[KeyTheme]
    major_issues: List[str]
    news_items: List[NewsItem]
```

### Analysis Tools (`src/analysis/tools/`)

Portfolio Brief가 사용하는 분석 도구:

| 클래스 | 파일 | 역할 |
|--------|------|------|
| `BaseAnalysisTool` (ABC) | `base.py` | 공통 인터페이스 (analyze_async, to_langchain_tool) |
| `TechnicalAnalysisTool` | `technical/tool.py` | 기술적 분석 (KIS, YFinance 데이터) |
| `NewsAnalysisTool` | `news/tool.py` | 뉴스 수집 (Naver KR, YFinance, DuckDuckGo) |
| `DisclosureAnalysisTool` | `disclosure/` | 해외 공시 (SEC 10-K/10-Q/8-K) |
| `KRDisclosureAnalysisTool` | `disclosure/` | 국내 공시 (DART) |

---

## 섹터 분류 체계

Report V1/V2와 Portfolio Brief 분석 모두 동일한 8개 섹터 사용:

| 번호 | 섹터명 | 주요 내용 |
|------|--------|-----------|
| 0 | Macro/Economy | 금리, 환율, 유가, 정책, 무역 |
| 1 | AI & Semiconductor | HBM, 메모리, 장비, NVIDIA, 삼성전자 |
| 2 | Battery & Auto | EV, 배터리, 자율주행, Tesla, LGES |
| 3 | Platform & Fintech | 클라우드, 핀테크, 블록체인 |
| 4 | Bio & Beauty | 제약, 바이오, 미용, GLP-1 |
| 5 | Security & Infra | 사이버보안, 인프라, 국방 |
| 6 | Finance & Holdings | 금융, 지주사, 보험 |
| 7 | Consumer & Retail | 소비, 유통, 패션 |
| - | General | 미분류 |
