# Telegram Daily Report V3: Information Preservation Design

**작성일**: 2026-04-14  
**목적**: 텔레그램 메시지 분석 파이프라인에서 정량 데이터 및 투자 의견 손실 방지

## 1. Overview and Problem Definition

### 현재 문제

기존 V2 파이프라인(`telegram/src/llm/daily_analysis_v2.py`)에서 발생하는 정보 손실:

**입력 (원본 메시지)**:
```
감성코퍼레이션
목표주가 8,000원 >> 7,000원
투자의견 매수-유지
삼성증권
```

**출력 (최종 리포트)**:
```
계약 체결로 매출 확대 기대
```

**손실된 정보**:
- 정량 데이터: 목표주가 8,000원 → 7,000원
- 투자 의견: 매수-유지
- 애널리스트/증권사: 삼성증권

### 근본 원인

1. **다중 LLM 압축 단계**: Map → Reduce → WrapUp 각 단계에서 요약 발생
2. **원문 미보존**: 각 단계마다 텍스트를 전체 전달하며 LLM이 재생성
3. **암묵적 지시**: "요약하라"는 명시적 지시가 없어도 LLM이 압축 경향

### 목표

1. **정량 데이터 보존**: 목표가, PER, 계약 금액, 매출액, 주가 목표 등
2. **투자 의견 보존**: 매수/매도/보유 추천, 신용등급 변경
3. **원문 인용 가능**: 최종 리포트에서 원본 메시지 참조 링크 제공
4. **시장 데이터 통합**: KR 수급, US 모멘텀을 텔레그램 테마에 자연스럽게 매칭

## 2. 6-Stage Pipeline Architecture

### 전체 데이터 흐름

```
Ingest → Map → Shuffle → Catalyst → Synthesize → Render
  ↓       ↓      ↓         ↓           ↓          ↓
ref_     issues themes   catalysts   insights   markdown
lookup   +IDs   +IDs      +IDs       +IDs       +citations
```

### Stage 1: Ingest (수집 및 포인터 생성)

**입력**: 없음  
**출력**: `IngestResult`

**작업**:
1. 텔레그램 메시지 로드 (CSV 파일들)
2. `ref_lookup` 생성: `{msg_id: original_text}` 딕셔너리
3. 시장 뉴스 수집 (SPY, QQQ, KOSPI 등)
4. KR 수급 데이터 수집 (KIS API: 외국인/기관 순매수 상위 30)
5. US 모멘텀 데이터 수집 (KIS API: 등락률/거래량 상위 30)

**핵심 원칙**: 원문 텍스트는 이 단계에서만 로딩, 이후 단계에는 ID만 전달

**출력 모델**:
```python
class IngestResult(BaseModel):
    telegram_messages: list[dict]      # 원본 메시지 (ID 포함)
    ref_lookup: dict[int, str]         # ID → 원문 매핑
    market_news: list[dict]            # 시장 뉴스 (배경 컨텍스트용)
    kr_flow: list[dict]                # 한국 수급 데이터
    momentum: list[dict]               # 미국 모멘텀 데이터
```

### Stage 2: Map (이슈 추출)

**모델**: `gpt-4o` (정확도 중시)  
**입력**: 청크된 텔레그램 메시지  
**출력**: `list[IssueExtract]`

**작업**:
1. 메시지를 50개씩 청크로 분할 (토큰 제한 대응)
2. 각 청크에서 투자 이슈 추출 (병렬 처리)
3. **One-shot 예제 제공**: 숫자가 포함된 summary 예시
4. 광고/잡담 필터링

**프롬프트 전략**:
```python
prompt = f"""
아래 텔레그램 메시지에서 투자 관련 이슈를 추출하세요.

**예시**:
메시지: "감성코퍼레이션 목표주가 8,000원→7,000원, 삼성증권 매수 유지"
출력:
{{
  "themes": ["디스플레이", "중소형주"],
  "tickers": ["036620"],
  "sentiment": "neutral",
  "summary": "감성코퍼레이션 목표가 8,000원→7,000원 하향 (삼성증권 매수 유지)",
  "source_ids": [12345]
}}

주의사항:
- summary에 구체적인 숫자 포함 (목표가, PER, 계약 금액 등)
- 투자 의견 명시 (매수/매도/보유)
- 광고/잡담은 무시

메시지:
{messages}
"""
```

**출력 모델**:
```python
class IssueExtract(BaseModel):
    themes: list[str]                  # 여러 테마 가능
    tickers: list[str]                 # 원문 그대로 (정규화 안 함)
    sentiment: Literal["bull", "bear", "neutral"]
    summary: str                       # 숫자 포함 요약
    source_ids: list[int]              # 원문 참조용
```

### Stage 3: Shuffle (테마 병합 및 시장 데이터 매칭)

**모델**: `gpt-4o` (정확도 중시)  
**입력**: `list[IssueExtract]`, KR 수급, US 모멘텀  
**출력**: `ShuffleResult`

**작업**:
1. 유사 테마 병합 (LLM 기반)
2. 티커 정규화 (ticker_resolver)
3. 테마별 종목 그룹핑
4. **시장 데이터 매칭**:
   - KR 수급/US 모멘텀 종목들을 기존 테마에 매칭
   - 매칭 실패한 종목만 "기타 수급 특징주" 테마로

**매칭 로직 예시**:
```python
# NVDA가 모멘텀 상위 → "AI 반도체" 테마에 추가
# TSLA가 모멘텀 상위 → "전기차" 테마에 추가
# 알려지지 않은 종목 → "기타 수급 특징주" 테마

if ticker in telegram_tickers:
    # 이미 텔레그램에서 언급된 종목
    add_to_existing_theme(ticker, flow_score, volume_score)
else:
    # 텔레그램 미언급 종목
    matched_theme = find_semantic_match(ticker, themes)
    if matched_theme:
        add_to_theme(matched_theme, ticker, source="market_data")
    else:
        add_to_fallback_theme("기타 수급 특징주", ticker)
```

**출력 모델**:
```python
class Theme(BaseModel):
    name: str
    narrative: str                     # 대표 서술
    sentiment: Literal["bull", "bear", "neutral"]
    stocks: list[str]                  # 정규화된 티커
    source_ids: list[int]              # 병합된 ID들

class StockDetail(BaseModel):
    ticker: str
    market: Literal["KR", "US"]
    mention_count: int                 # 텔레그램 언급 횟수
    flow_score: float | None           # KR 수급 점수
    volume_score: float | None         # US 모멘텀 점수
    source: Literal["telegram", "market_data", "both"]
    summaries: list[str]               # 해당 종목의 모든 요약

class ShuffleResult(BaseModel):
    themes: list[Theme]
    stock_details: dict[str, StockDetail]
```

### Stage 4: Catalyst (종목별 촉매 검색)

**모델**: `gpt-4o` (정확도 중시, 도구 호출 필요)  
**입력**: `ShuffleResult`  
**출력**: `list[StockCatalyst]`

**작업**:
1. 각 테마의 상위 2-3 종목에 대해 뉴스 검색 (NewsTool)
2. **lookup_message 도구 제공**: LLM이 필요시 원문 메시지 조회
3. 촉매 요약 생성

**도구 정의**:
```python
def lookup_message(message_id: int) -> str:
    """원본 텔레그램 메시지 조회"""
    return ref_lookup.get(message_id, "메시지 없음")
```

**출력 모델**:
```python
class StockCatalyst(BaseModel):
    ticker: str
    themes: list[str]                  # 소속 테마들
    news: list[str]                    # 뉴스 헤드라인
    catalyst_summary: str              # 촉매 요약
    source_ids: list[int]              # 관련 메시지 ID
```

### Stage 5: Synthesize (인사이트 생성)

**모델**: `gpt-5.2` (창의성 중시)  
**입력**: 시장 뉴스, `ShuffleResult`, `list[StockCatalyst]`  
**출력**: `list[Insight]`

**작업**:
1. 시장 온도 해석 (뉴스 기반)
2. **테마 횡단 인사이트** 도출:
   - "AI 반도체 + 전력 인프라 동반 상승"
   - "방산 테마, 계약 뉴스는 많으나 수급 약세"
3. **lookup_message 도구 제공**: 원문 확인 가능

**핵심 원칙**: LLM은 인사이트만 생성, 팩트 나열은 Python이 담당

**출력 모델**:
```python
class Insight(BaseModel):
    title: str                         # 인사이트 제목 (10자 이내)
    content: str                       # 상세 설명 (100-200자)
    related_themes: list[str]          # 관련 테마들
```

### Stage 6: Render (마크다운 조립)

**구현**: Python 코드 (LLM 불필요)  
**입력**: `DailyReport`  
**출력**: 마크다운 문자열

**작업**:
1. 헤더 생성 (날짜, 시장 온도)
2. 인사이트 섹션 렌더링
3. 테마별 섹션:
   - 테마명, narrative, 감성
   - 주도주 목록 (수급/모멘텀 점수 포함)
   - **원문 인용**: `source_ids`로 ref_lookup 조회, 각주 삽입
4. 촉매 분석 섹션
5. 각주 영역 (원본 메시지 전문)

**렌더링 예시**:
```markdown
## 📊 AI 반도체

**분위기**: 상승 (bull)  
**주도주**: NVDA (모멘텀: +15%), 삼성전자 (수급: +50억)

> AI 반도체 수요 급증, 엔비디아 목표가 상향 [^1][^2]

---
[^1]: "엔비디아 목표가 $150 → $180 상향 (골드만삭스)"
[^2]: "삼성전자 HBM3E 공급 확대, 외국인 3일 연속 매수"
```

## 3. Data Models

### 전체 모델 구조

```python
# === Stage 1: Ingest ===
class IngestResult(BaseModel):
    telegram_messages: list[dict]
    ref_lookup: dict[int, str]         # 핵심: 원문 저장소
    market_news: list[dict]
    kr_flow: list[dict]
    momentum: list[dict]

# === Stage 2: Map ===
class IssueExtract(BaseModel):
    themes: list[str]                  # 변경: 단일 → 복수
    tickers: list[str]
    sentiment: Literal["bull", "bear", "neutral"]
    summary: str                       # 숫자 포함 요약
    source_ids: list[int]

# === Stage 3: Shuffle ===
class Theme(BaseModel):
    name: str
    narrative: str
    sentiment: Literal["bull", "bear", "neutral"]
    stocks: list[str]
    source_ids: list[int]              # Map에서 병합됨

class StockDetail(BaseModel):
    ticker: str
    market: Literal["KR", "US"]
    mention_count: int
    flow_score: float | None
    volume_score: float | None
    source: Literal["telegram", "market_data", "both"]
    summaries: list[str]

class ShuffleResult(BaseModel):
    themes: list[Theme]
    stock_details: dict[str, StockDetail]

# === Stage 4: Catalyst ===
class StockCatalyst(BaseModel):
    ticker: str
    themes: list[str]
    news: list[str]
    catalyst_summary: str
    source_ids: list[int]

# === Stage 5: Synthesize ===
class Insight(BaseModel):
    title: str
    content: str
    related_themes: list[str]

# === Stage 6: Render ===
class DailyReport(BaseModel):
    date: str
    insights: list[Insight]
    themes: list[Theme]
    catalysts: list[StockCatalyst]
    stock_details: dict[str, StockDetail]
    ref_lookup: dict[int, str]         # 렌더링용
```

### 주요 변경사항

1. **IssueExtract.themes**: `str` → `list[str]` (다중 테마 지원)
2. **Theme.mention_count** 제거: 불필요 (source_ids 길이로 대체)
3. **Insight 구조화**: `featured_analysis: str` → `insights: list[Insight]`

## 4. Stage-by-Stage Verification Strategy

### 검증 원칙

각 단계마다 실제 데이터(2026-04-13)로 검증:
1. **입력 확인**: CSV 파일에서 샘플 메시지 선택
2. **단계별 추적**: 해당 메시지가 각 단계를 거치며 어떻게 변환되는지 추적
3. **정량 데이터 보존 확인**: 숫자가 유실되지 않았는지 검사
4. **원문 인용 확인**: 최종 마크다운에서 원문으로 역추적 가능한지 검사

### Stage 1: Ingest 검증

**검증 포인트**:
- CSV 파일에서 메시지 정상 로드
- ref_lookup에 ID와 원문 정확히 매핑
- KR 수급/US 모멘텀 데이터 정상 수집

**예상 출력 샘플**:
```python
ref_lookup = {
    12345: "감성코퍼레이션 목표주가 8,000원 >> 7,000원 | 투자의견 매수-유지 | 삼성증권",
    12346: "SK하이닉스 HBM3E 공급 확대, 엔비디아 향 출하 본격화",
    ...
}
kr_flow = [
    {"ticker": "005930", "name": "삼성전자", "foreign_net": 5000000000, ...},
    ...
]
```

### Stage 2: Map 검증

**검증 포인트**:
- 메시지 12345가 정확히 추출되었는지
- summary에 "8,000원", "7,000원", "매수-유지" 포함 여부
- source_ids에 12345 포함 여부

**예상 출력 샘플**:
```python
IssueExtract(
    themes=["디스플레이", "중소형주"],
    tickers=["036620"],
    sentiment="neutral",
    summary="감성코퍼레이션 목표가 8,000원→7,000원 하향 (삼성증권 매수 유지)",
    source_ids=[12345]
)
```

**검증 방법**:
```python
# 단계 실행
issues = await map_stage.run(ingest_result.telegram_messages)

# 검증
target_issue = [i for i in issues if 12345 in i.source_ids][0]
assert "8,000원" in target_issue.summary
assert "7,000원" in target_issue.summary
assert "매수" in target_issue.summary
print("✅ Map stage: 정량 데이터 보존 확인")
```

### Stage 3: Shuffle 검증

**검증 포인트**:
- 메시지 12345의 source_ids가 Theme으로 병합되었는지
- "디스플레이" 테마가 생성되었는지
- NVDA가 "AI 반도체" 테마에 추가되었는지 (모멘텀 매칭)
- StockDetail에 flow_score/volume_score 정확히 기록되었는지

**예상 출력 샘플**:
```python
Theme(
    name="디스플레이",
    narrative="감성코퍼레이션 목표가 하향, 실적 우려",
    sentiment="neutral",
    stocks=["036620"],
    source_ids=[12345, 12399]  # 병합됨
)

stock_details["036620"] = StockDetail(
    ticker="036620",
    market="KR",
    mention_count=2,
    flow_score=None,  # 수급 데이터 없음
    volume_score=None,
    source="telegram",
    summaries=[
        "감성코퍼레이션 목표가 8,000원→7,000원 하향 (삼성증권 매수 유지)",
        "...다른 요약..."
    ]
)
```

**검증 방법**:
```python
# 실행
shuffle_result = await shuffle_stage.run(issues, ingest_result.kr_flow, ingest_result.momentum)

# 검증 1: source_ids 보존
display_theme = [t for t in shuffle_result.themes if t.name == "디스플레이"][0]
assert 12345 in display_theme.source_ids

# 검증 2: 모멘텀 매칭
ai_theme = [t for t in shuffle_result.themes if "AI" in t.name][0]
assert "NVDA" in ai_theme.stocks

# 검증 3: summaries 보존
assert any("8,000원" in s for s in shuffle_result.stock_details["036620"].summaries)
print("✅ Shuffle stage: source_ids 병합 및 모멘텀 매칭 확인")
```

### Stage 4: Catalyst 검증

**검증 포인트**:
- "036620" 종목에 대한 촉매가 생성되었는지
- lookup_message 도구가 정상 작동하는지
- source_ids 보존되었는지

**예상 출력 샘플**:
```python
StockCatalyst(
    ticker="036620",
    themes=["디스플레이"],
    news=["감성코퍼레이션, 2Q 실적 가이던스 발표 예정"],
    catalyst_summary="목표가 하향에도 불구, 신규 계약 기대감 (삼성증권 매수 유지)",
    source_ids=[12345]
)
```

### Stage 5: Synthesize 검증

**검증 포인트**:
- Insight가 여러 테마를 연결하는지
- lookup_message 도구로 원문 참조했는지
- 과도한 압축 없이 핵심만 추출했는지

**예상 출력 샘플**:
```python
Insight(
    title="디스플레이",
    content="중소형 디스플레이 업체 목표가 하향 움직임. 실적 압박 속 신규 계약이 변곡점이 될 전망. 삼성증권은 매수 의견 유지.",
    related_themes=["디스플레이", "중소형주"]
)
```

### Stage 6: Render 검증

**검증 포인트**:
- 최종 마크다운에서 각주 `[^1]` 클릭 시 원문 확인 가능
- 숫자가 정확히 표시되는지
- source_ids로 ref_lookup 역추적 성공

**예상 출력 샘플**:
```markdown
## 📊 디스플레이

**분위기**: 중립 (neutral)  
**주도주**: 감성코퍼레이션 (036620)

> 감성코퍼레이션 목표가 8,000원→7,000원 하향, 삼성증권 매수 유지 [^1]

---
### 각주
[^1]: 감성코퍼레이션 목표주가 8,000원 >> 7,000원 | 투자의견 매수-유지 | 삼성증권
```

**검증 방법**:
```python
# 실행
report = DailyReport(
    date="2026-04-13",
    insights=insights,
    themes=shuffle_result.themes,
    catalysts=catalysts,
    stock_details=shuffle_result.stock_details,
    ref_lookup=ingest_result.ref_lookup
)
markdown = render_report(report)

# 검증: 각주 역추적
assert "[^1]" in markdown
assert "8,000원 >> 7,000원" in markdown  # 각주 내용
assert "매수-유지" in markdown
print("✅ Render stage: 원문 인용 확인")
```

### 통합 검증: End-to-End Tracing

**전체 추적 스크립트**:
```python
# 1. CSV에서 샘플 메시지 선택
sample_msg_id = 12345
sample_text = "감성코퍼레이션 목표주가 8,000원 >> 7,000원 | 투자의견 매수-유지 | 삼성증권"

# 2. Ingest
ingest_result = await ingest_stage.run()
assert ingest_result.ref_lookup[sample_msg_id] == sample_text
print(f"✅ Ingest: {sample_msg_id} → ref_lookup")

# 3. Map
issues = await map_stage.run(ingest_result.telegram_messages)
target_issue = [i for i in issues if sample_msg_id in i.source_ids][0]
assert "8,000원" in target_issue.summary
print(f"✅ Map: {sample_msg_id} → IssueExtract (숫자 보존)")

# 4. Shuffle
shuffle_result = await shuffle_stage.run(issues, ...)
theme = [t for t in shuffle_result.themes if sample_msg_id in t.source_ids][0]
print(f"✅ Shuffle: {sample_msg_id} → Theme '{theme.name}'")

# 5. Catalyst
catalysts = await catalyst_stage.run(shuffle_result, ingest_result.ref_lookup)
catalyst = [c for c in catalysts if sample_msg_id in c.source_ids][0]
print(f"✅ Catalyst: {sample_msg_id} → StockCatalyst")

# 6. Synthesize
insights = await synthesize_stage.run(...)
print(f"✅ Synthesize: {len(insights)}개 인사이트 생성")

# 7. Render
report = DailyReport(..., ref_lookup=ingest_result.ref_lookup)
markdown = render_report(report)
assert sample_text in markdown  # 각주에 원문 포함
print(f"✅ Render: {sample_msg_id} → 마크다운 각주")

print("\n🎉 End-to-End 검증 완료: 메시지 12345의 숫자가 최종 출력까지 보존됨")
```

## 5. Implementation Considerations

### 프로젝트 구조

```
src/pipelines/
  telegram_v3/
    __init__.py
    pipeline.py              # DailyReportV3Pipeline
    stages/
      __init__.py
      ingest.py              # IngestStage
      map_issues.py          # MapStage
      shuffle_filter.py      # ShuffleStage
      catalyst.py            # CatalystStage
      synthesize.py          # SynthesizeStage
    models.py                # Pydantic 모델들
    prompts.py               # 프롬프트 템플릿
    renderer.py              # Markdown 렌더링
    tools.py                 # lookup_message 도구
```

### 기술 스택

- **LangChain**: AgentExecutor, ChatOpenAI, tool calling
- **Pydantic**: 모델 검증
- **asyncio**: 병렬 처리
- **Telethon**: 텔레그램 수집 (기존 유지)

### 모델 선택 전략

| Stage | Model | 이유 |
|-------|-------|------|
| Map | gpt-4o | 정확도 중시 (정량 데이터 추출) |
| Shuffle | gpt-4o | 정확도 중시 (테마 병합, 티커 매칭) |
| Catalyst | gpt-4o | 정확도 + 도구 호출 |
| Synthesize | gpt-5.2 | 창의성 중시 (인사이트 도출) |

### 프롬프트 엔지니어링

#### Map Stage One-Shot 예제

```python
ONE_SHOT_EXAMPLES = """
**예시 1**:
메시지: "감성코퍼레이션 목표주가 8,000원→7,000원, 삼성증권 매수 유지"
출력:
{
  "themes": ["디스플레이", "중소형주"],
  "tickers": ["036620"],
  "sentiment": "neutral",
  "summary": "감성코퍼레이션 목표가 8,000원→7,000원 하향 (삼성증권 매수 유지)",
  "source_ids": [12345]
}

**예시 2**:
메시지: "SK하이닉스 HBM 매출 2Q 15조원 예상, 모건스탠리 목표가 $220 상향"
출력:
{
  "themes": ["AI 반도체", "메모리"],
  "tickers": ["000660"],
  "sentiment": "bull",
  "summary": "SK하이닉스 HBM 매출 2Q 15조원 예상, 모건스탠리 목표가 $220 상향",
  "source_ids": [12346]
}
"""
```

### 도구 호출 구현

```python
from langchain.tools import tool
from langchain.agents import AgentExecutor

@tool
def lookup_message(message_id: int) -> str:
    """
    텔레그램 원본 메시지 조회
    
    Args:
        message_id: 메시지 ID
        
    Returns:
        원본 메시지 텍스트
    """
    global ref_lookup
    return ref_lookup.get(message_id, "메시지 없음")

# Catalyst/Synthesize Stage에서 사용
agent = AgentExecutor(
    agent=agent_chain,
    tools=[lookup_message, news_tool],
    ...
)
```

### 토큰 최적화

**기존 V2 (전체 텍스트 전달)**:
```
Ingest: 10,000 tokens
Map: 50,000 tokens (청크 10개 × 5,000)
Reduce: 30,000 tokens
WrapUp: 20,000 tokens
-----------------
Total: 110,000 tokens
```

**V3 (ID만 전달)**:
```
Ingest: 10,000 tokens (ref_lookup 생성만)
Map: 50,000 tokens (변화 없음)
Shuffle: 5,000 tokens (IssueExtract 리스트만)
Catalyst: 3,000 tokens (Theme 리스트만)
Synthesize: 2,000 tokens (요약만)
-----------------
Total: 70,000 tokens (36% 절감)
```

### 에러 처리

```python
class PipelineStage:
    async def run(self, *args, **kwargs):
        try:
            result = await self._execute(*args, **kwargs)
            self._validate_output(result)
            return result
        except ValidationError as e:
            logger.error(f"{self.__class__.__name__} validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"{self.__class__.__name__} failed: {e}")
            # Fallback: 이전 단계 결과 반환 또는 기본값
            return self._get_fallback_result()
```

## 6. Implementation Order and Milestones

### Phase 1: 모델 정의 (1-2시간)

**파일**: `src/pipelines/telegram_v3/models.py`

**작업**:
- [ ] `IngestResult` 정의
- [ ] `IssueExtract` 정의 (themes를 list[str]로)
- [ ] `Theme`, `StockDetail`, `ShuffleResult` 정의
- [ ] `StockCatalyst` 정의
- [ ] `Insight`, `DailyReport` 정의

**검증**: Pydantic 모델 유닛 테스트

### Phase 2: Ingest Stage (1-2시간)

**파일**: `src/pipelines/telegram_v3/stages/ingest.py`

**작업**:
- [ ] 텔레그램 CSV 로더 (기존 코드 재사용)
- [ ] ref_lookup 생성 로직
- [ ] 시장 뉴스 수집 (MacroTool, NewsTool)
- [ ] KR 수급 수집 (KIS API)
- [ ] US 모멘텀 수집 (KIS API)

**검증**: 
```python
result = await ingest_stage.run()
assert len(result.ref_lookup) > 0
assert len(result.kr_flow) == 30
assert len(result.momentum) == 60
```

### Phase 3: Map Stage (2-3시간) ⚠️ 가장 중요

**파일**: 
- `src/pipelines/telegram_v3/stages/map_issues.py`
- `src/pipelines/telegram_v3/prompts.py`

**작업**:
- [ ] 청크 분할 로직 (50개씩)
- [ ] One-shot 예제 프롬프트 작성
- [ ] LLM 호출 (gpt-4o)
- [ ] 병렬 처리 (asyncio.gather)
- [ ] 결과 병합

**검증**:
```python
issues = await map_stage.run(ingest_result.telegram_messages)
sample_issue = [i for i in issues if 12345 in i.source_ids][0]
assert "8,000원" in sample_issue.summary  # 핵심 검증
assert "7,000원" in sample_issue.summary
assert "매수" in sample_issue.summary or "유지" in sample_issue.summary
```

### Phase 4: Shuffle Stage (2-3시간)

**파일**: `src/pipelines/telegram_v3/stages/shuffle_filter.py`

**작업**:
- [ ] 테마 병합 LLM 호출
- [ ] 티커 정규화 (ticker_resolver)
- [ ] Theme 객체 생성 (source_ids 병합)
- [ ] 모멘텀 종목 매칭 로직
- [ ] StockDetail 생성 (flow_score, volume_score)

**검증**:
```python
shuffle_result = await shuffle_stage.run(issues, kr_flow, momentum)
# 검증 1: 모멘텀 매칭
ai_theme = [t for t in shuffle_result.themes if "AI" in t.name][0]
assert "NVDA" in ai_theme.stocks

# 검증 2: summaries 보존
assert "8,000원" in shuffle_result.stock_details["036620"].summaries[0]
```

### Phase 5: Catalyst Stage (1-2시간)

**파일**: 
- `src/pipelines/telegram_v3/stages/catalyst.py`
- `src/pipelines/telegram_v3/tools.py`

**작업**:
- [ ] lookup_message 도구 구현
- [ ] AgentExecutor 설정 (gpt-4o)
- [ ] 상위 종목 선별 로직
- [ ] 뉴스 검색 및 촉매 요약

**검증**:
```python
catalysts = await catalyst_stage.run(shuffle_result, ref_lookup)
target_catalyst = [c for c in catalysts if c.ticker == "036620"][0]
assert len(target_catalyst.news) > 0
assert len(target_catalyst.catalyst_summary) > 10
```

### Phase 6: Synthesize Stage (1-2시간)

**파일**: `src/pipelines/telegram_v3/stages/synthesize.py`

**작업**:
- [ ] lookup_message 도구 제공
- [ ] AgentExecutor 설정 (gpt-5.2)
- [ ] 시장 온도 프롬프트
- [ ] 인사이트 리스트 생성

**검증**:
```python
insights = await synthesize_stage.run(market_news, shuffle_result, catalysts, ref_lookup)
assert len(insights) >= 3
assert any("AI" in i.title or "반도체" in i.title for i in insights)
```

### Phase 7: Render Stage (1시간)

**파일**: `src/pipelines/telegram_v3/renderer.py`

**작업**:
- [ ] 마크다운 템플릿 작성
- [ ] source_ids → ref_lookup 각주 변환
- [ ] 테마별 섹션 렌더링
- [ ] 촉매 섹션 렌더링

**검증**:
```python
markdown = render_report(report)
assert "[^1]" in markdown
assert "8,000원 >> 7,000원" in markdown
assert "매수-유지" in markdown
```

### Phase 8: 통합 및 End-to-End 테스트 (1-2시간)

**파일**: `src/pipelines/telegram_v3/pipeline.py`

**작업**:
- [ ] DailyReportV3Pipeline 클래스 구현
- [ ] 6개 Stage 순차 실행
- [ ] 에러 핸들링
- [ ] End-to-End 추적 스크립트 (위 검증 섹션 참조)

**검증**:
```bash
# 실제 데이터로 전체 파이프라인 실행
uv run python -m src.pipelines.telegram_v3.pipeline --date 2026-04-13

# 출력 확인
cat output/2026-04-13-daily-report.md
# → "8,000원 >> 7,000원" 문자열 검색
```

### 성공 기준

1. ✅ **정량 데이터 보존**: 샘플 메시지의 숫자가 최종 마크다운에 정확히 포함
2. ✅ **원문 인용**: 각주 클릭 시 원본 메시지 확인 가능
3. ✅ **모멘텀 매칭**: NVDA가 "AI 반도체" 테마에 포함
4. ✅ **투자 의견 보존**: "매수", "매도", "보유" 문자열 유실 없음
5. ✅ **토큰 절감**: 기존 대비 30% 이상 절감

### 예상 소요 시간

| Phase | 시간 | 누적 |
|-------|------|------|
| 1. 모델 정의 | 1-2h | 2h |
| 2. Ingest | 1-2h | 4h |
| 3. Map ⚠️ | 2-3h | 7h |
| 4. Shuffle | 2-3h | 10h |
| 5. Catalyst | 1-2h | 12h |
| 6. Synthesize | 1-2h | 14h |
| 7. Render | 1h | 15h |
| 8. 통합 테스트 | 1-2h | 17h |

**총 예상 시간**: 8-12시간 (단계별 검증 포함)

## 7. References

- **기존 파이프라인**: `/Users/user/Develop/My/telegram/src/llm/daily_analysis_v2.py`
- **참고 아키텍처**: `/Users/user/Develop/My/invest-jarvis/.worktrees/daily-report-v2/`
- **실제 데이터**: `/Users/user/Develop/My/telegram/data/2026-04/2026-04-13-*.csv`

---

**최종 검증 체크리스트**:
- [ ] 메시지 12345의 "8,000원" 숫자가 최종 마크다운에 포함
- [ ] 각주 `[^1]` 클릭 시 원문 "감성코퍼레이션 목표주가 8,000원 >> 7,000원..." 확인 가능
- [ ] NVDA가 "기타 수급 특징주"가 아닌 "AI 반도체" 테마에 포함
- [ ] "매수-유지" 문자열 유실 없음
- [ ] 토큰 사용량 30% 절감 달성
