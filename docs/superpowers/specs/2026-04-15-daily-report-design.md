# Daily Report Pipeline 설계 명세서

**작성일**: 2026-04-15  
**상태**: Design Approved  
**목적**: 텔레그램 메시지 기반 일일 시장 리포트 생성

## 1. 개요

### 1.1 목표

텔레그램 채널 메시지를 분석하여 한글 일일 시장 리포트를 자동 생성하는 파이프라인 구축.

**핵심 문제 해결**:
- V2의 클러스터링 실패 (Bloom Energy가 4개 섹터에 중복 출현)
- 청크별 LLM 분석 시 테마명 불일치
- 섹터 기반 그룹핑의 의미론적 한계

**설계 원칙**:
- **테마 기반 클러스터링**: 섹터 태그 대신 의미론적 테마 사용
- **LLM 기반 테마 정규화**: 청크 간 일관성 확보
- **V1 스타일 포맷팅**: 이모지(🚀📈⚠️), bullet points, Impact 문구
- **V2 아키텍처 계승**: 4단계 파이프라인으로 테스트 용이성 확보
- **확장 가능성**: 향후 screen data 통합 대비

### 1.2 주요 특징

- **Pipeline**: Map → Shuffle → Reduce → Wrapup (4단계)
- **LLM Models**: 
  - Map, Shuffle: gpt-4o (일관성 우선)
  - Reduce, Wrapup: gpt-5.2 (창의성 + 분석력)
- **뉴스 검색**: ddgs (DuckDuckGo Search)
- **출력**: 한글 마크다운 리포트 (이모지, Impact 문구 포함)
- **입력**: Telegram CSV + 매크로 지표 (VIX, Fear & Greed, 시장 변동폭)
- **Location**: `src/pipelines/daily_report/`

## 2. 아키텍처

### 2.1 전체 흐름

```
CSV 로드 + 매크로 수집 (Ingest)
  ↓
청크별 이슈 추출 (Map)
  ↓
테마 정규화 (Shuffle)
  ↓
테마별 분석 (Reduce)
  ↓
크로스 테마 인사이트 (Wrapup)
  ↓
한글 마크다운 리포트
```

### 2.2 Stage별 세부 설계

#### Stage 0: Ingest (데이터 수집)

**입력**: `date: str` (예: "2026-04-14")

**처리**:
1. 매크로 데이터 수집
   - yfinance: ^GSPC, ^IXIC, ^DJI (전날 미국장 종가)
   - yfinance: ^KS11, ^KQ11 (당일 한국장 종가)
   - `src/tools/macro.py`: VIX, Fear & Greed Index
   - 환율: KRW/USD

2. Telegram CSV 로드
   - 경로: `data/YYYY-MM/YYYY-MM-DD-*.csv`
   - 모든 채널 통합
   - 필드: timestamp, channel_id, message_id, text

**출력**: `IngestResult(macro: MacroSnapshot, messages: List[TelegramMessage])`

**에러 핸들링**:
- CSV 없으면 에러 (사용자에게 `jarvis telegram fetch` 실행 안내)
- 매크로 데이터 일부 실패 시 warning 후 계속 진행

---

#### Stage 1: Map (청크별 이슈 추출)

**입력**: `List[TelegramMessage]`

**처리**:
1. 메시지를 청크로 분할 (max_tokens=6000)
2. 각 청크를 LLM(gpt-4o)에 병렬 전송 (asyncio.gather)
3. 유사 주제 메시지를 하나의 이슈로 통합
4. 각 이슈에 2-3개 테마 태그 부여

**출력**: `List[MappedIssue]`

**MappedIssue 모델**:
```python
class MappedIssue(BaseModel):
    title: str              # 한글
    summary: str            # 한글
    themes: List[str]       # 2-3개 테마 (예: ["AI 전력 인프라", "데이터센터"])
    keywords: List[str]     # 종목명, 기술용어
    sentiment: Literal["bull", "bear", "neutral"]
    source_ids: List[str]   # 원본 메시지 ID
```

**프롬프트 핵심**:
- "유사한 주제의 메시지는 하나의 이슈로 통합"
- Few-shot 예시 제공 (Bloom Energy 4개 메시지 → 1개 이슈)
- Temperature: 0.3 (일관성 우선)

**품질 검증**:
- themes 없는 이슈 있으면 에러

---

#### Stage 2: Shuffle (테마 정규화)

**입력**: `List[MappedIssue]`

**처리**:
1. 모든 unique themes 수집 (예: 50개)
2. LLM(gpt-4o)에 테마 리스트 전송
3. 유사 테마 클러스터링 → canonical name 지정
   - 예: ["AI 전력 인프라", "AI DC", "데이터센터 파워"] → "AI 데이터센터 전력 인프라"
4. 각 MappedIssue의 themes를 canonical name으로 교체
5. 테마별로 이슈 그룹핑

**출력**: `ShuffleResult`

**ShuffleResult 모델**:
```python
class ShuffleResult(BaseModel):
    canonical_themes: Dict[str, List[str]]      # {정규화명: [원본 테마들]}
    theme_groups: Dict[str, List[MappedIssue]]  # {정규화명: [이슈들]}
```

**프롬프트 핵심**:
- "의미가 같으면 통합, 너무 광범위하게 묶지 말 것"
- Temperature: 0.1 (일관성 최우선)

**품질 검증**:
- 정규화 후 테마 개수가 원본의 30% 이하면 warning (너무 뭉갬)
- 정규화 후 테마 개수가 원본의 90% 이상이면 warning (거의 안 뭉갬)

---

#### Stage 3: Reduce (테마별 분석)

**입력**: `ShuffleResult`

**처리**: 각 테마 그룹마다
1. 이슈들에서 keywords 수집 (중복 제거)
2. Keywords로 뉴스 검색 (ddgs - DuckDuckGo Search)
3. LLM(gpt-5.2) 분석
   - 입력: theme, issues, news_articles
   - 출력: NewsItem (한글, V1 스타일)
4. 테마별 병렬 처리 (asyncio)

**출력**: `List[NewsItem]`

**NewsItem 모델**:
```python
class NewsItem(BaseModel):
    theme: str              # 한글 정규화 테마명
    emoji: str              # 🚀📈⚠️ℹ️📉⚡
    summary: str            # 한글 bullet points
    impact: str             # 한글 Impact 문구
    stocks: List[StockDetail]  # 관련 종목 (선택)
```

**프롬프트 핵심**:
- "한글로 작성"
- 이모지 사용 지침:
  - 🚀 강세/호재
  - 📈 상승 추세
  - ⚠️ 주의/리스크
  - 📉 약세
  - ℹ️ 중립/정보
  - ⚡ 긴급/중요
- Bullet point 형식
- 마지막에 `**(Impact: ...)** 문구
- Temperature: 0.5 (창의성 필요)

**품질 검증**:
- impact 없으면 warning

**향후 확장**: 
- `_search_news()` 함수에 screen data 쿼리 추가 가능
- 나머지 파이프라인은 변경 불필요

---

#### Stage 4: Wrapup (크로스 테마 인사이트)

**입력**: `List[NewsItem]`

**처리**:
1. 모든 NewsItem을 LLM(gpt-5.2)에 전송
2. 여러 테마를 연결하는 메타 인사이트 3-5개 도출

**출력**: `List[str]` (인사이트 리스트)

**프롬프트 핵심**:
- "여러 테마를 연결하는 메타 인사이트 도출"
- "각 인사이트는 2-3줄로 간결하게"
- "이모지 활용 (🔥💡🌊)"
- Temperature: 0.7 (창의적 연결 필요)

**예시 출력**:
```
[
  "🔥 AI 슈퍼사이클: 데이터센터 전력 인프라 + 반도체 메모리 업사이클 + 전력기기 수주 급증 → 통합 투자 테마 형성",
  "💡 공급망 리쇼어링: 미국 CHIPS Act + 한국 전력기기 수출 + 일본 소재 확대 → 비중국 밸류체인 재편 가속"
]
```

---

#### Stage 5: Render (마크다운 생성)

**입력**: `DailyReport`

**DailyReport 모델**:
```python
class DailyReport(BaseModel):
    date: str
    macro: MacroSnapshot
    insights: List[str]
    news_items: List[NewsItem]
```

**출력**: 마크다운 문자열

**템플릿**:
```markdown
# Daily Report: YYYY-MM-DD

## 📊 시장 스냅샷
- 🇺🇸 미국: S&P500 +1.2%, 나스닥 +1.5%, 다우 +0.8%
- 🇰🇷 한국: KOSPI +2.1%, KOSDAQ +1.8%
- 📉 VIX: 15.3 (-0.5)
- 😨 Fear & Greed: 62 (Greed)
- 💰 원/달러: 1,320원 (-5원)

## 🔥 오늘의 핵심 인사이트
{insights}

## 📰 테마별 분석

### 🚀 AI 데이터센터 전력 인프라
- 🔋 Oracle-Bloom Energy 2.8GW 연료전지 계약
- 📈 LS ELECTRIC 북미 배전반 1,700억원 수주
- ⚡ 2030년 DC 전력 수요 1,350TWh 전망 (+220%)

**(Impact: 전력 인프라 병목 해소로 AI 투자 가속화. 한국 전력기기 3사 수주 레벨업 기대)**

**관련 종목**:
- LS ELECTRIC (010120.KS): 북미 AI DC 배전반 1,700억원 공급 계약
```

**저장 경로**: `reports/YYYY-MM/YYYY-MM-DD_daily_report.md`

## 3. 데이터 모델

### 3.1 핵심 모델

```python
class MacroSnapshot(BaseModel):
    date: str
    us_markets: Dict[str, float]  # {"S&P500": 5234.5, "NASDAQ": 16789.2, "DOW": 38456.7}
    kr_markets: Dict[str, float]  # {"KOSPI": 2678.3, "KOSDAQ": 875.4}
    vix: float
    fear_greed: int  # 0-100
    krw_usd: float

class TelegramMessage(BaseModel):
    channel_id: str
    message_id: str
    timestamp: datetime
    text: str

class IngestResult(BaseModel):
    date: str
    macro: MacroSnapshot
    messages: List[TelegramMessage]

class MappedIssue(BaseModel):
    title: str              # 한글
    summary: str            # 한글
    themes: List[str]       # V2의 sector(str)에서 변경
    keywords: List[str]
    sentiment: Literal["bull", "bear", "neutral"]
    source_ids: List[str]

class ShuffleResult(BaseModel):
    canonical_themes: Dict[str, List[str]]
    theme_groups: Dict[str, List[MappedIssue]]

class StockDetail(BaseModel):
    name: str
    ticker: str
    catalyst: str  # 한글

class NewsItem(BaseModel):
    theme: str              # 한글
    emoji: str
    summary: str            # 한글
    impact: str             # 한글
    stocks: List[StockDetail]

class DailyReport(BaseModel):
    date: str
    macro: MacroSnapshot
    insights: List[str]     # 한글
    news_items: List[NewsItem]
```

### 3.2 V2 대비 변경사항

| 항목 | V2 | V3 (daily_report) |
|------|----|--------------------|
| 이슈 그룹핑 | `sector: str` | `themes: List[str]` |
| 정규화 Stage | 없음 | Shuffle 추가 |
| 출력 언어 | 영어 | 한글 |
| 매크로 지표 | 없음 | MacroSnapshot 추가 |
| 이모지 | 제한적 | V1 스타일 (6종) |

## 4. 파일 구조

```
src/pipelines/daily_report/
├── __init__.py
│   └── export: run_daily_report(date: str) -> DailyReport
│
├── pipeline.py
│   └── 전체 파이프라인 오케스트레이션
│   └── run_daily_report() 구현
│
├── stages/
│   ├── __init__.py
│   ├── ingest_stage.py
│   │   └── ingest(date: str) -> IngestResult
│   │   └── _fetch_macro() -> MacroSnapshot
│   │   └── _load_telegram_csvs(date: str) -> List[TelegramMessage]
│   │
│   ├── map_stage.py
│   │   └── map_stage(messages: List[TelegramMessage]) -> List[MappedIssue]
│   │   └── _chunk_messages() -> List[List[TelegramMessage]]
│   │   └── _analyze_chunk(chunk, llm) -> List[MappedIssue]
│   │
│   ├── shuffle_stage.py
│   │   └── shuffle_stage(issues: List[MappedIssue]) -> ShuffleResult
│   │   └── _collect_unique_themes() -> Set[str]
│   │   └── _normalize_themes(themes, llm) -> Dict[str, List[str]]
│   │
│   ├── reduce_stage.py
│   │   └── reduce_stage(shuffle_result: ShuffleResult) -> List[NewsItem]
│   │   └── _search_news(keywords: List[str]) -> List[NewsArticle]
│   │   └── _analyze_theme(theme, issues, news, llm) -> NewsItem
│   │
│   └── wrapup_stage.py
│       └── wrapup_stage(news_items: List[NewsItem]) -> List[str]
│       └── _synthesize_insights(news_items, llm) -> List[str]
│
├── models.py
│   └── 모든 Pydantic 모델 정의
│
├── prompts.py
│   └── MAP_PROMPT
│   └── SHUFFLE_PROMPT
│   └── REDUCE_PROMPT
│   └── WRAPUP_PROMPT
│
└── renderer.py
    └── render_to_markdown(report: DailyReport) -> str
    └── save_report(report: DailyReport, output_dir: str)
```

## 5. CLI 통합

**명령어**: `uv run jarvis report [date]`

**구현** (`src/cli/main.py`):
```python
@app.command()
def report(
    date: str = typer.Option(None, help="날짜 (YYYY-MM-DD), 기본값: 어제"),
    save: bool = typer.Option(True, help="파일 저장 여부")
):
    """일일 시장 리포트 생성 (텔레그램 분석)"""
    from src.pipelines.daily_report import run_daily_report
    
    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    report = run_daily_report(date)
    
    # 콘솔 출력 (rich)
    console.print(Panel("📊 시장 스냅샷"))
    # ...
    console.print(Panel("🔥 오늘의 핵심 인사이트"))
    for insight in report.insights:
        console.print(f"  {insight}")
    
    # 파일 저장
    if save:
        output_path = f"reports/{date[:7]}/{date}_daily_report.md"
        save_report(report, output_path)
        console.print(f"✅ 저장: {output_path}")
```

**실행 예시**:
```bash
$ uv run jarvis report

🔄 Daily Report 생성 중...
  ✓ Ingest: 324 messages, macro data collected
  ✓ Map: 45 issues extracted from 7 chunks
  ✓ Shuffle: 45 themes → 12 canonical themes
  ✓ Reduce: 12 news items generated
  ✓ Wrapup: 4 cross-theme insights

📊 시장 스냅샷
...

✅ 저장: reports/2026-04/2026-04-14_daily_report.md
```

## 6. 테스트 전략

### 6.1 Unit Tests

각 Stage별 독립 테스트:

```python
def test_map_stage():
    messages = load_fixture("sample_messages.json")
    issues = map_stage(messages)
    assert len(issues) > 0
    assert all(issue.themes for issue in issues)
    assert all(len(issue.themes) <= 3 for issue in issues)

def test_shuffle_stage():
    issues = [
        MappedIssue(themes=["AI 전력", "DC 파워"]),
        MappedIssue(themes=["AI 데이터센터"]),
    ]
    result = shuffle_stage(issues)
    # 정규화 확인
    assert len(result.canonical_themes) <= len(set(
        theme for issue in issues for theme in issue.themes
    ))

def test_reduce_stage():
    shuffle_result = ShuffleResult(theme_groups={...})
    news_items = reduce_stage(shuffle_result)
    assert all(item.impact for item in news_items)  # Impact 필수
    assert all(item.emoji for item in news_items)   # 이모지 필수
    assert all(item.emoji in "🚀📈⚠️ℹ️📉⚡" for item in news_items)
```

### 6.2 Integration Tests

```python
def test_full_pipeline():
    # 실제 과거 데이터로 end-to-end 테스트
    report = run_daily_report("2026-04-14")
    assert report.macro.vix > 0
    assert len(report.insights) >= 3
    assert len(report.news_items) > 0
    assert all("Impact:" in item.impact for item in report.news_items)
```

### 6.3 프롬프트 튜닝

각 Stage를 독립 실행하여 프롬프트 개선:

```bash
# Map Stage만 테스트
python -m src.pipelines.daily_report.stages.map_stage --date 2026-04-14

# Shuffle Stage만 테스트
python -m src.pipelines.daily_report.stages.shuffle_stage --input map_output.json
```

## 7. 성능 & 에러 핸들링

### 7.1 성능 최적화

- **Map Stage**: 청크별 병렬 처리 (asyncio.gather)
- **Reduce Stage**: 테마별 병렬 처리 (asyncio.gather)
- **예상 실행 시간**: 2-5분 (메시지 수에 따라)

### 7.2 에러 핸들링

| 에러 유형 | 처리 방식 |
|-----------|-----------|
| CSV 없음 | 즉시 에러, 사용자에게 `jarvis telegram fetch` 안내 |
| 매크로 데이터 실패 | warning 출력, 해당 필드 None으로 계속 진행 |
| LLM API 실패 | 재시도 3회, 실패 시 에러 |
| Stage 실패 | 부분 결과라도 저장 (디버깅용) |

### 7.3 의존성

**기존 모듈 재사용**:
- `src/llm/`: OpenAI/Anthropic 클라이언트
- `src/tools/macro.py`: VIX, Fear & Greed 수집

**새로운 의존성**: 
- `duckduckgo-search` (ddgs): 뉴스 검색용

## 8. 향후 확장

### 8.1 Screen Data 통합

**현재 설계**:
```python
# reduce_stage.py
def _search_news(keywords: List[str]) -> List[NewsArticle]:
    return search_from_ddgs(keywords)
```

**Screen Data 추가 시**:
```python
def _search_news(keywords: List[str]) -> List[NewsArticle]:
    ddgs_news = search_from_ddgs(keywords)
    screen_news = search_from_screen_db(keywords)  # ← 추가
    return ddgs_news + screen_news
```

**통합 포인트**:
- Reduce Stage의 `_search_news()` 함수 하나만 수정
- 나머지 파이프라인은 변경 불필요
- Screen data가 다른 형식이면 adapter 패턴 적용

### 8.2 추가 가능 기능

- **Stage별 캐싱**: Map/Shuffle 결과를 캐싱하여 Reduce 재실행 속도 향상
- **다중 LLM 지원**: gpt-4o 외 claude-3.5-sonnet 옵션 추가
- **테마 우선순위**: Shuffle 후 중요도 scoring으로 상위 N개 테마만 분석
- **실시간 업데이트**: WebSocket으로 텔레그램 실시간 수신 → 리포트 자동 재생성

## 9. 문서 업데이트 계획

구현 완료 후 다음 문서들을 업데이트해야 함:

1. **README.md**
   - Features 섹션: "Daily Report V2 (테마 기반 텔레그램 분석)" 추가
   - Commands 섹션: `jarvis report` 커맨드 설명 업데이트

2. **docs/CLI_USAGE.md**
   - Section 3: "report - 일일 시장 리포트" 전체 재작성
   - 기존 V1 내용 대체
   - 출력 예시 추가 (매크로 + 인사이트 + 테마별 분석)

3. **CLAUDE.md**
   - Architecture 섹션: `src/pipelines/daily_report/` 추가
   - Common Commands: `jarvis report` 설명 업데이트

## 10. 마일스톤

**Phase 1: 기본 파이프라인** (우선순위 높음)
- [ ] 모델 정의 (models.py)
- [ ] Ingest Stage
- [ ] Map Stage + 프롬프트
- [ ] Shuffle Stage + 프롬프트
- [ ] Reduce Stage + 프롬프트
- [ ] Wrapup Stage + 프롬프트
- [ ] Renderer
- [ ] CLI 통합

**Phase 2: 테스트 & 튜닝**
- [ ] Unit tests (각 Stage)
- [ ] Integration test (전체 파이프라인)
- [ ] 프롬프트 튜닝 (실제 데이터로)
- [ ] 품질 검증 로직

**Phase 3: 문서화**
- [ ] README.md 업데이트
- [ ] docs/CLI_USAGE.md 업데이트
- [ ] CLAUDE.md 업데이트

**Phase 4: 향후 확장** (선택)
- [ ] Screen data 통합
- [ ] 다중 LLM 지원
- [ ] Stage별 캐싱

## 11. 참고 자료

**기존 코드베이스**:
- V1 참고: `/Users/user/Develop/My/telegram/src/llm/daily_analysis.py`
- V2 참고: `/Users/user/Develop/My/telegram/src/llm/daily_analysis_v2.py`
- V1 리포트 예시: `.worktrees/daily-report-v2/reports/2026-04/2026-04-14_daily_report_v1.md`

**V1 vs V2 비교**:
| 측면 | V1 | V2 |
|------|----|----|
| 클러스터링 | ✅ 우수 | ❌ 실패 (중복 출현) |
| 이모지 활용 | ✅ 우수 | ⚠️ 제한적 |
| 가독성 | ✅ 우수 | ⚠️ 보통 |
| 테스트 용이성 | ❌ 어려움 | ✅ 우수 |
| 확장성 | ❌ 어려움 | ✅ 우수 |

**V3 (daily_report) 목표**: V1의 품질 + V2의 구조
