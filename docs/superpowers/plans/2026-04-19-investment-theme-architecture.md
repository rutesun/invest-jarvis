# Investment Theme Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate technical clustering themes from investment insight themes, adding keyword search capability and enhancing Wrapup stage to focus on theme relationships and macro connections.

**Architecture:** Split single `theme` field into `technical_theme` (Shuffle-generated, stable search key) and `investment_theme` (Reduce LLM-generated, investment insights). Add `keywords` field for enhanced search. Modify Reduce prompts to generate investment themes following specific patterns. Enhance Wrapup to synthesize theme relationships with macro data.

**Tech Stack:** Python 3.12, Pydantic, LangChain, Anthropic Claude Haiku 4.5, pytest

---

## File Structure

**Files to modify:**
- `src/pipelines/daily_report/models.py` - Add new fields to ThemeAnalysis and NewsItem
- `src/pipelines/daily_report/prompts.py` - Add V2 prompts for Reduce and Wrapup stages
- `src/pipelines/daily_report/stages/reduce_stage.py` - Modify to use technical_theme and generate investment_theme
- `src/pipelines/daily_report/stages/wrapup_stage.py` - Add macro data formatting and use investment_theme

**Files to create:**
- `tests/pipelines/daily_report/test_investment_themes.py` - Tests for new investment theme generation

**No new files needed** - extending existing pipeline architecture.

---

## Task 1: Extend ThemeAnalysis Model

**Files:**
- Modify: `src/pipelines/daily_report/models.py:110-118`
- Test: `tests/pipelines/daily_report/test_models.py`

- [ ] **Step 1: Write failing test for ThemeAnalysis with new fields**

```python
# tests/pipelines/daily_report/test_models.py
def test_theme_analysis_with_investment_theme():
    """ThemeAnalysis should have investment_theme and keywords fields."""
    data = {
        "investment_theme": "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
        "keywords": ["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩"],
        "emoji": "🚀",
        "summary": "테스트 요약",
        "impact": "테스트 영향",
        "stocks": []
    }
    
    from src.pipelines.daily_report.models import ThemeAnalysis
    analysis = ThemeAnalysis(**data)
    
    assert analysis.investment_theme == "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"
    assert len(analysis.keywords) == 5
    assert "GPU" in analysis.keywords
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipelines/daily_report/test_models.py::test_theme_analysis_with_investment_theme -v`
Expected: FAIL with "ThemeAnalysis.__init__() got an unexpected keyword argument 'investment_theme'"

- [ ] **Step 3: Add new fields to ThemeAnalysis model with validators**

```python
# src/pipelines/daily_report/models.py
from pydantic import BaseModel, Field, field_validator

class ThemeAnalysis(BaseModel):
    """Reduce stage LLM 출력용 (category 제외)."""

    investment_theme: str = Field(
        description="투자 인사이트 테마명 (20-40자). "
        "패턴: [트렌드] + [방향성] + [수혜/리스크]. "
        "예: 'GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜'"
    )
    keywords: list[str] = Field(
        description="검색용 키워드 5-10개 (종목명, 기술용어, 트렌드)"
    )
    emoji: str = Field(description="단일 이모지: 🚀📈⚠️ℹ️📉⚡")
    summary: str = Field(description="한글 bullet points")
    impact: str = Field(description="한글 impact 문구")
    stocks: list[StockDetail] = Field(default_factory=list)
    
    @field_validator("investment_theme")
    def validate_theme_length(cls, v):
        """투자 테마 길이 검증 (20-40자)."""
        length = len(v)
        if not (20 <= length <= 40):
            raise ValueError(
                f"investment_theme 길이는 20-40자여야 합니다 (현재: {length}자, 값: '{v}')"
            )
        return v
    
    @field_validator("keywords")
    def validate_keywords_count(cls, v):
        """키워드 개수 검증 (5-10개)."""
        count = len(v)
        if not (5 <= count <= 10):
            raise ValueError(
                f"keywords는 5-10개여야 합니다 (현재: {count}개)"
            )
        return v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipelines/daily_report/test_models.py::test_theme_analysis_with_investment_theme -v`
Expected: PASS

- [ ] **Step 5: Commit model changes**

```bash
git add src/pipelines/daily_report/models.py tests/pipelines/daily_report/test_models.py
git commit -m "feat(models): add investment_theme and keywords to ThemeAnalysis

- Add investment_theme field with 20-40 char constraint
- Add keywords field with 5-10 items constraint
- Prepare for Reduce stage investment insight generation"
```

---

## Task 1.5: Add ValidationError Retry to LLM Utils

**Files:**
- Modify: `src/pipelines/daily_report/llm_utils.py:57-70`

- [ ] **Step 1: Add ValidationError import**

```python
# src/pipelines/daily_report/llm_utils.py
# Add to imports at top of file (around line 5)
from pydantic import BaseModel, ValidationError
```

- [ ] **Step 2: Modify exception handling to add feedback on ValidationError**

```python
# src/pipelines/daily_report/llm_utils.py
# Replace lines 57-64 in the except Exception block

        except Exception as e:
            last_exception = e
            
            # ValidationError면 피드백 메시지를 다음 시도에 추가
            if isinstance(e, ValidationError):
                error_details = str(e)
                feedback_message = {
                    "role": "user",
                    "content": f"⚠️ 검증 실패:\n{error_details}\n\n제약 조건을 정확히 지켜주세요."
                }
                # messages 리스트에 피드백 추가 (다음 시도 시 사용됨)
                messages = messages + [feedback_message]
                
                logger.warning(
                    "ValidationError (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    error_details,
                )
            else:
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
```

- [ ] **Step 3: Test ValidationError retry manually**

```python
# Manual test: Create an issue that would trigger ValidationError
# Run reduce stage and check logs for:
# - "ValidationError (attempt 1/3): ..."
# - Retry with feedback message
# - Success on attempt 2 or 3

# Check LangSmith to verify feedback message appears in retry
```

Expected: 
- First attempt fails with ValidationError
- Second attempt includes feedback message
- LLM adjusts output based on feedback

- [ ] **Step 4: Commit ValidationError retry enhancement**

```bash
git add src/pipelines/daily_report/llm_utils.py
git commit -m "feat(llm): add ValidationError retry with feedback

- Detect ValidationError in retry loop
- Add feedback message explaining constraint violation
- LLM sees error details in next retry attempt
- Improves success rate for structured output constraints"
```

---

## Task 2: Extend NewsItem Model

**Files:**
- Modify: `src/pipelines/daily_report/models.py:120-128`
- Test: `tests/pipelines/daily_report/test_models.py`

- [ ] **Step 1: Write failing test for NewsItem with split theme fields**

```python
# tests/pipelines/daily_report/test_models.py
def test_news_item_with_split_themes():
    """NewsItem should have both technical_theme and investment_theme."""
    data = {
        "category": "반도체",
        "technical_theme": "AI 인프라 및 칩 수요",
        "investment_theme": "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
        "keywords": ["GPU", "엔비디아", "AMD"],
        "emoji": "🚀",
        "summary": "테스트 요약",
        "impact": "테스트 영향",
        "stocks": []
    }
    
    from src.pipelines.daily_report.models import NewsItem
    news = NewsItem(**data)
    
    assert news.technical_theme == "AI 인프라 및 칩 수요"
    assert news.investment_theme == "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"
    assert len(news.keywords) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipelines/daily_report/test_models.py::test_news_item_with_split_themes -v`
Expected: FAIL with "NewsItem.__init__() got an unexpected keyword argument 'technical_theme'"

- [ ] **Step 3: Modify NewsItem to use split theme fields**

```python
# src/pipelines/daily_report/models.py
class NewsItem(BaseModel):
    """Reduce stage의 테마별 분석."""

    category: IssueCategory = Field(description="카테고리 (정렬/필터링용)")
    
    # 테마 (2개 필드로 분리)
    technical_theme: str = Field(
        description="Shuffle에서 정규화한 기술적 테마명 (검색 키)"
    )
    investment_theme: str = Field(
        description="투자 인사이트 테마명 (리포트 표시용)"
    )
    
    # 검색
    keywords: list[str] = Field(
        description="검색용 키워드"
    )
    
    emoji: str = Field(description="단일 이모지: 🚀📈⚠️ℹ️📉⚡")
    summary: str = Field(description="한글 bullet points")
    impact: str = Field(description="한글 impact 문구")
    stocks: list[StockDetail] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipelines/daily_report/test_models.py::test_news_item_with_split_themes -v`
Expected: PASS

- [ ] **Step 5: Commit NewsItem changes**

```bash
git add src/pipelines/daily_report/models.py tests/pipelines/daily_report/test_models.py
git commit -m "feat(models): split NewsItem theme into technical and investment

- Add technical_theme field (from Shuffle, stable search key)
- Add investment_theme field (from Reduce LLM, display name)
- Add keywords field for enhanced search
- Remove single theme field"
```

---

## Task 3: Create Reduce Stage V2 Prompts

**Files:**
- Modify: `src/pipelines/daily_report/prompts.py:324-350`
- Test: Manual validation (prompt content check)

- [ ] **Step 1: Add REDUCE_SYSTEM_PROMPT_V2 after existing REDUCE_SYSTEM_PROMPT**

```python
# src/pipelines/daily_report/prompts.py
# Insert after line 342 (after existing REDUCE_SYSTEM_PROMPT)

# ============================================================================
# REDUCE STAGE PROMPTS V2 (투자 인사이트 추가)
# ============================================================================

REDUCE_SYSTEM_PROMPT_V2 = """당신은 투자 리포트 작성 전문가입니다.
특정 테마에 대한 분석 리포트를 작성하세요.

**작업**:

1. **투자 인사이트 테마명 생성** (가장 중요!)
   
   입력된 기술적 테마를 투자 인사이트로 변환하세요.
   
   **작성 패턴**:
   - 패턴 1: [트렌드] + [방향성] + [수혜/리스크]
     예: "AI 칩 수요 폭증, GPU 가격 파워 강화"
   
   - 패턴 2: [원인] + [결과] + [투자 액션]
     예: "엔비디아 독점 완화로 대체재 주목"
   
   - 패턴 3: [현상] + [구체적 종목/섹터]
     예: "AI 인프라 투자 가속, AMD·세레브라스 수혜"
   
   **어구 가이드**:
   - Bull: 폭증, 가속화, 본격화, 수혜, 턴어라운드, 주목, 부상
   - Bear: 둔화, 압박, 우려, 리스크, 약화, 부담
   - Neutral: 재편, 전환, 다변화, 가시화
   
   **제약**:
   - 길이: 20-40자 (쉼표 포함)
   - 구조: [전반부 10-15자, 후반부 10-15자]
   - 방향성 명확히 (가속/둔화/전환 등)
   - 가능하면 구체적 종목/섹터 언급

2. **검색 키워드 추출** (5-10개)
   
   - 종목명: 한글/영문 모두
   - 기술용어: GPU, HBM, AI 칩 등
   - 트렌드: 공급망 다변화, 독점 완화 등

3. **테마 분석** (기존 작업)
   
   - 이모지 선택: 🚀📈⚠️📉ℹ️⚡
   - Summary: bullet points (이모지 포함)
   - Impact: 시장 영향 평가
   - Stocks: 관련 종목 (3-5개)

**Few-shot 예시**:

예시 1:
기술적 테마: "AI 인프라 및 칩 수요"
관련 이슈: [오픈AI 세레브라스 200억 계약, 엔비디아 성능 우위, 중국 GPU 임대료 상승]
→ investment_theme: "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"
→ keywords: ["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩", "공급망", "데이터센터"]

예시 2:
기술적 테마: "엔터프라이즈 AI 솔루션"
관련 이슈: [팔란티어 실적 개선, 세일스포스 가격 인상]
→ investment_theme: "엔터프라이즈 AI 채택 본격화, SaaS 가격 파워 회복"
→ keywords: ["팔란티어", "세일스포스", "AI 에이전트", "SaaS", "엔터프라이즈"]

예시 3:
기술적 테마: "콘텐츠 기업 실적 부진"
관련 이슈: [넷플릭스 가이던스 하회, 하이브 목표가 하향]
→ investment_theme: "스트리밍 가이던스 실망, 광고 전환 시급"
→ keywords: ["넷플릭스", "하이브", "스트리밍", "광고", "콘텐츠"]

**출력**: 제공된 함수 스키마(Tool Calling) 형식에 맞추어 반환하세요.

⚠️ 주의:
- investment_theme은 반드시 20-40자 사이
- keywords는 정확히 5-10개
- summary와 impact는 줄바꿈으로 이어진 단일 문자열"""

REDUCE_USER_PROMPT_V2 = """**기술적 테마**: {technical_theme}

**관련 이슈들**:
{issues}

**작업**:
1. 위 기술적 테마를 투자 인사이트로 변환
2. 검색 키워드 추출
3. 테마 분석 작성"""
```

- [ ] **Step 2: Verify prompt length and patterns**

Run manually:
```python
# Count characters in example investment_themes
examples = [
    "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",  # 28 chars
    "엔터프라이즈 AI 채택 본격화, SaaS 가격 파워 회복",  # 29 chars
    "스트리밍 가이던스 실망, 광고 전환 시급"  # 21 chars
]
for ex in examples:
    assert 20 <= len(ex) <= 40, f"Length {len(ex)} not in range: {ex}"
```
Expected: All assertions pass

- [ ] **Step 3: Add prompt to active version (commented out for now)**

```python
# src/pipelines/daily_report/prompts.py
# After REDUCE_USER_PROMPT_V2 definition

# Activate V2 prompts (uncomment when ready to deploy)
# REDUCE_SYSTEM_PROMPT = REDUCE_SYSTEM_PROMPT_V2
# REDUCE_USER_PROMPT = REDUCE_USER_PROMPT_V2
```

- [ ] **Step 4: Commit Reduce V2 prompts**

```bash
git add src/pipelines/daily_report/prompts.py
git commit -m "feat(prompts): add REDUCE_SYSTEM_PROMPT_V2 for investment themes

- Add investment insight generation instructions
- Include 3 writing patterns and word guides
- Add 3 Few-shot examples (bull/bear/neutral)
- Add length constraints (20-40 chars)
- Add keyword extraction (5-10 items)
- Not activated yet (requires reduce_stage.py changes)"
```

---

## Task 4: Create Wrapup Stage V2 Prompts

**Files:**
- Modify: `src/pipelines/daily_report/prompts.py:375-390`

- [ ] **Step 1: Add WRAPUP_SYSTEM_PROMPT_V2 after existing WRAPUP_SYSTEM_PROMPT**

```python
# src/pipelines/daily_report/prompts.py
# Insert after line 385 (after existing WRAPUP_SYSTEM_PROMPT)

# ============================================================================
# WRAPUP STAGE PROMPTS V2 (전체 시장 인사이트 강화)
# ============================================================================

WRAPUP_SYSTEM_PROMPT_V2 = """당신은 시장 전략가입니다.
모든 테마와 매크로 데이터를 종합하여 전체 시장 인사이트를 도출하세요.

**작업**:

1. **테마 간 관계 파악**
   
   - 연결 관계: 어떤 테마들이 서로 연결되어 있는가?
     예: "AI 인프라 투자 확대 → HBM 수요 증가"
   
   - 대비 관계: 어떤 테마들이 상반되는가?
     예: "AI 섹터 강세 vs 이차전지 약세"
   
   - 선후 관계: 어떤 테마가 다른 테마를 이끄는가?
     예: "엔비디아 독점 완화 → GPU 공급망 재편"

2. **매크로 데이터와 연결**
   
   - VIX, Fear & Greed 지수가 테마들을 어떻게 뒷받침/반박하는가?
   - 미국/한국 시장 차이가 어떤 테마와 관련되는가?
   - 환율이 특정 섹터에 어떤 영향을 주는가?

3. **우선순위 결정**
   
   - 오늘의 핵심 테마는? (이슈 수, 영향력, 시의성 고려)
   - 가장 주목해야 할 섹터는?
   - 어떤 종목/섹터가 수혜/리스크를 받는가?

4. **전체 시장 스토리 구성**
   
   - 한 문장 시장 요약
   - 섹터 로테이션 (어디서 어디로?)
   - 투자 시사점 3-5개

**인사이트 작성 가이드**:
- 단순 요약 금지 (개별 테마 나열 X)
- 메타 관점 필수 (테마 간 관계, 큰 그림)
- 구체적 액션 제시 (어떤 섹터 주목, 어떤 리스크 경계)
- 이모지 활용: 🔥💡🌊⚠️⚡🎯

**출력**: 제공된 함수 스키마(Tool Calling) 형식에 맞추어 반환하세요."""

WRAPUP_USER_PROMPT_V2 = """**매크로 데이터**:
{macro}

**테마별 분석 결과** ({news_count}개 테마):
{news_items}

**작업**:
1. 테마 간 관계 파악 (연결/대비/선후)
2. 매크로와 연결
3. 우선순위 결정
4. 전체 시장 스토리 도출 (3-5개 인사이트)"""
```

- [ ] **Step 2: Add prompt activation (commented out)**

```python
# src/pipelines/daily_report/prompts.py
# After WRAPUP_USER_PROMPT_V2 definition

# Activate V2 prompts (uncomment when ready to deploy)
# WRAPUP_SYSTEM_PROMPT = WRAPUP_SYSTEM_PROMPT_V2
# WRAPUP_USER_PROMPT = WRAPUP_USER_PROMPT_V2
```

- [ ] **Step 3: Commit Wrapup V2 prompts**

```bash
git add src/pipelines/daily_report/prompts.py
git commit -m "feat(prompts): add WRAPUP_SYSTEM_PROMPT_V2 for enhanced insights

- Add theme relationship analysis (connection/contrast/sequence)
- Add macro data connection instructions
- Add priority determination guide
- Add market story construction framework
- Not activated yet (requires wrapup_stage.py changes)"
```

---

## Task 5: Modify Reduce Stage to Generate Investment Themes

**Files:**
- Modify: `src/pipelines/daily_report/stages/reduce_stage.py:67-133`
- Test: `tests/pipelines/daily_report/test_investment_themes.py`

- [ ] **Step 1: Write integration test for investment theme generation**

```python
# tests/pipelines/daily_report/test_investment_themes.py
"""Integration tests for investment theme generation."""

import pytest
from src.pipelines.daily_report.models import MappedIssue, MacroSnapshot, NewsItem
from src.pipelines.daily_report.stages.reduce_stage import reduce_stage


@pytest.fixture
def macro_snapshot():
    """Sample macro data."""
    return MacroSnapshot(
        date="2026-04-19",
        us_markets={"S&P500": 1.2, "NASDAQ": 1.5, "DOW": 0.8},
        kr_markets={"KOSPI": 0.5, "KOSDAQ": 0.3},
        vix=15.2,
        fear_greed=65,
        krw_usd=1320.5
    )


@pytest.fixture
def sample_category_groups():
    """Sample shuffled issues grouped by category and theme."""
    issue1 = MappedIssue(
        category="반도체",
        title="세레브라스 오픈AI 계약",
        summary="오픈AI가 세레브라스와 200억 달러 규모 계약 체결",
        themes=["AI 인프라 및 칩 수요"],
        impact="GPU 공급망 다변화 가속",
        keywords=["세레브라스", "오픈AI", "GPU"],
        sentiment="bull",
        source_ids=["msg1"]
    )
    
    return {
        "반도체": {
            "AI 인프라 및 칩 수요": [issue1]
        }
    }


def test_reduce_generates_investment_theme(sample_category_groups, macro_snapshot):
    """Reduce stage should generate investment_theme and keywords."""
    result = reduce_stage(sample_category_groups, macro_snapshot, date="2026-04-19")
    
    assert len(result) == 1
    news_item = result[0]
    
    # Should have both theme fields
    assert hasattr(news_item, "technical_theme")
    assert hasattr(news_item, "investment_theme")
    assert hasattr(news_item, "keywords")
    
    # technical_theme should match Shuffle output
    assert news_item.technical_theme == "AI 인프라 및 칩 수요"
    
    # investment_theme should be different (LLM-generated insight)
    assert news_item.investment_theme != news_item.technical_theme
    
    # Should have length constraint
    assert 20 <= len(news_item.investment_theme) <= 40
    
    # Should have keywords
    assert 5 <= len(news_item.keywords) <= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipelines/daily_report/test_investment_themes.py::test_reduce_generates_investment_theme -v`
Expected: FAIL (reduce_stage doesn't pass technical_theme yet, NewsItem creation will fail)

- [ ] **Step 3: Modify _analyze_theme to pass technical_theme and use V2 prompt**

```python
# src/pipelines/daily_report/stages/reduce_stage.py
# Replace _analyze_theme function (lines 67-133)

async def _analyze_theme(
    llm,
    category: str,
    theme: str,  # technical_theme from Shuffle
    issues: list[MappedIssue],
    macro: MacroSnapshot,
    date: str,
) -> NewsItem:
    """단일 테마 분석 (투자 인사이트 생성)."""

    issues_text = "\n\n".join(
        [
            f"**{issue.title}**\n{issue.summary}\n"
            f"키워드: {', '.join(issue.keywords)}\n"
            f"감성: {issue.sentiment}"
            for issue in issues
        ]
    )

    # V2 prompt 사용 (투자 인사이트 생성)
    from src.pipelines.daily_report.prompts import (
        REDUCE_SYSTEM_PROMPT_V2,
        REDUCE_USER_PROMPT_V2
    )
    
    system_prompt = REDUCE_SYSTEM_PROMPT_V2
    user_prompt = REDUCE_USER_PROMPT_V2.format(
        technical_theme=theme,  # 명시적으로 기술적 테마 전달
        issues=issues_text
    )

    run_name = f"Reduce Stage - {date} - {category}/{theme[:20]}"
    config = {
        "run_name": run_name,
        "tags": [
            "daily_report",
            "reduce_stage",
            f"date:{date}",
            f"category:{category}",
            f"theme:{theme}",
        ],
        "metadata": {
            "stage": "reduce",
            "date": date,
            "category": category,
            "theme": theme,
            "issue_count": len(issues),
        },
    }

    messages = REDUCE_LLM.build_messages(system_prompt, user_prompt)

    try:
        response = await invoke_llm_with_retry(llm, ThemeAnalysis, messages, config)

        return NewsItem(
            category=category,
            technical_theme=theme,  # Shuffle에서 온 것
            investment_theme=response.investment_theme,  # LLM이 생성
            keywords=response.keywords,  # LLM이 추출
            emoji=response.emoji,
            summary=response.summary,
            impact=response.impact,
            stocks=response.stocks,
        )
    except Exception as e:
        logger.error(
            "테마 분석 실패 - [%s] %s: %s (%s)",
            category,
            theme,
            type(e).__name__,
            str(e),
            exc_info=True
        )
        # Fallback 없이 예외 전파 (실패율 체크에서 처리)
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipelines/daily_report/test_investment_themes.py::test_reduce_generates_investment_theme -v`
Expected: PASS (may take time due to LLM call)

- [ ] **Step 5: Commit reduce stage changes**

```bash
git add src/pipelines/daily_report/stages/reduce_stage.py tests/pipelines/daily_report/test_investment_themes.py
git commit -m "feat(reduce): generate investment themes from technical themes

- Modify _analyze_theme to use REDUCE_SYSTEM_PROMPT_V2
- Pass technical_theme explicitly to LLM
- Create NewsItem with both technical_theme and investment_theme
- Remove fallback logic (let exceptions propagate)
- Add integration test for investment theme generation"
```

---

## Task 5.5: Add Failure Rate Check to Reduce Stage

**Files:**
- Modify: `src/pipelines/daily_report/stages/reduce_stage.py:53-64`

- [ ] **Step 1: Modify _analyze_themes_parallel to track and handle failures**

```python
# src/pipelines/daily_report/stages/reduce_stage.py
# Replace _analyze_themes_parallel function (lines 53-64)

async def _analyze_themes_parallel(
    category_groups: dict[str, dict[str, list[MappedIssue]]],
    macro: MacroSnapshot,
    date: str,
) -> list[NewsItem]:
    """카테고리/테마별 병렬 분석 (실패율 체크 포함)."""
    llm = REDUCE_LLM.create_llm()
    
    # 테마명과 함께 태스크 저장
    theme_tasks = []
    for category, theme_map in category_groups.items():
        for theme, issues in theme_map.items():
            task = _analyze_theme(llm, category, theme, issues, macro, date)
            theme_tasks.append((category, theme, task))
    
    # 병렬 실행 (예외 수집)
    results = await asyncio.gather(
        *[task for _, _, task in theme_tasks],
        return_exceptions=True
    )
    
    # 성공/실패 분류
    success = []
    failed_info = []
    
    for (category, theme, _), result in zip(theme_tasks, results):
        if isinstance(result, Exception):
            failed_info.append({
                "category": category,
                "theme": theme,
                "error_type": type(result).__name__,
                "error_message": str(result)
            })
        else:
            success.append(result)
    
    # 실패 정보 로깅
    for fail in failed_info:
        logger.error(
            "❌ 테마 분석 실패 - [%s] %s: %s (%s)",
            fail["category"],
            fail["theme"],
            fail["error_type"],
            fail["error_message"]
        )
    
    # 실패율 체크
    failure_rate = len(failed_info) / len(results) if results else 0
    
    if failure_rate > 0.2:
        logger.error(
            "🛑 테마 분석 실패율 %.1f%% 초과 (%d/%d), 파이프라인 중단",
            failure_rate * 100,
            len(failed_info),
            len(results)
        )
        raise RuntimeError(
            f"Theme analysis failure rate too high: {len(failed_info)}/{len(results)} "
            f"({failure_rate:.1%})"
        )
    
    if failed_info:
        logger.warning(
            "⚠️ %d개 테마 분석 실패 (성공률: %.1f%%)",
            len(failed_info),
            (1 - failure_rate) * 100
        )
    
    return success
```

- [ ] **Step 2: Test failure rate check with mock failures**

```python
# Manual test: Temporarily make some themes fail
# Verify:
# - Failed themes are logged with error type and message
# - Success rate is calculated correctly
# - Pipeline stops if > 20% fail
# - Pipeline continues if < 20% fail
```

Expected:
- 2/18 failures (11%): Continues with 16 items, warning logged
- 5/18 failures (28%): Stops with RuntimeError

- [ ] **Step 3: Commit failure rate check**

```bash
git add src/pipelines/daily_report/stages/reduce_stage.py
git commit -m "feat(reduce): add failure rate check for theme analysis

- Track category and theme with each task
- Collect exceptions with return_exceptions=True
- Log detailed failure information (category, theme, error type)
- Calculate failure rate and stop if > 20%
- Allow partial failures (< 20%) with warning
- No fallback NewsItems (failed themes excluded from report)"
```

---

## Task 6: Modify Wrapup Stage to Use Macro Data and Investment Themes

**Files:**
- Modify: `src/pipelines/daily_report/stages/wrapup_stage.py:20-78`
- Test: Manual testing with 2026-04-17 data

- [ ] **Step 1: Read current wrapup_stage.py to understand structure**

```bash
cat src/pipelines/daily_report/stages/wrapup_stage.py
```

- [ ] **Step 2: Modify wrapup_stage to format macro data and use investment_theme**

```python
# src/pipelines/daily_report/stages/wrapup_stage.py
# Replace wrapup_stage function (lines 23-49)

@traceable(name="Wrapup Stage")
def wrapup_stage(
    news_items: list[NewsItem],
    macro: MacroSnapshot,
    date: str = None,
) -> DailyReport:
    """
    전체 시장 인사이트 도출 (테마 간 관계 + 매크로 연결).

    Args:
        news_items: Reduce stage 출력 (테마별 분석)
        macro: 매크로 데이터
        date: 날짜 문자열

    Returns:
        DailyReport (key_insights 포함)
    """
    if not news_items:
        return DailyReport(
            date=date or macro.date,
            macro=macro,
            key_insights=["분석할 뉴스가 없습니다."],
            news=[]
        )

    llm = WRAPUP_LLM.create_llm()

    # 매크로 데이터 포맷팅
    macro_text = f"""VIX: {macro.vix}
Fear & Greed: {macro.fear_greed}
미국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.us_markets.items())}
한국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.kr_markets.items())}
KRW/USD: {macro.krw_usd}"""

    # 테마별 분석 포맷팅 (investment_theme 사용)
    news_text = "\n\n".join(
        [
            f"[{item.category}] {item.investment_theme}\n"  # investment_theme 사용
            f"(기술 테마: {item.technical_theme})\n"
            f"{item.emoji} {item.summary[:100]}..."  # 요약 일부만
            for item in news_items
        ]
    )

    # V2 프롬프트 사용
    from src.pipelines.daily_report.prompts import (
        WRAPUP_SYSTEM_PROMPT_V2,
        WRAPUP_USER_PROMPT_V2
    )
    
    system_prompt = WRAPUP_SYSTEM_PROMPT_V2
    user_prompt = WRAPUP_USER_PROMPT_V2.format(
        macro=macro_text,
        news_count=len(news_items),
        news_items=news_text
    )

    run_name = f"Wrapup Stage - {date}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "wrapup_stage", f"date:{date}"],
        "metadata": {
            "stage": "wrapup",
            "date": date,
            "theme_count": len(news_items),
        },
    }

    messages = WRAPUP_LLM.build_messages(system_prompt, user_prompt)

    try:
        response = invoke_llm_with_retry(llm, KeyInsightsList, messages, config)
        key_insights = response.insights
    except Exception as e:
        logger.error("Wrapup stage failed: %s", e, exc_info=True)
        key_insights = ["전체 인사이트 도출 실패"]

    return DailyReport(
        date=date or macro.date,
        macro=macro,
        key_insights=key_insights,
        news=news_items,
    )
```

- [ ] **Step 3: Test with 2026-04-17 data**

```bash
# Run wrapup stage manually with existing data
uv run python -m src.pipelines.daily_report.stages.wrapup_stage 2026-04-17
```
Expected: Should load reduce output, format macro data, and generate insights using V2 prompt

- [ ] **Step 4: Verify macro data appears in prompt**

Check LangSmith logs to confirm:
- Macro data (VIX, Fear & Greed, markets) appears in user prompt
- Investment themes (not technical themes) appear in prompt
- Key insights reference both themes and macro conditions

- [ ] **Step 5: Commit wrapup stage changes**

```bash
git add src/pipelines/daily_report/stages/wrapup_stage.py
git commit -m "feat(wrapup): add macro data and use investment themes

- Format macro data (VIX, Fear & Greed, markets, KRW/USD)
- Use investment_theme instead of theme in prompt
- Switch to WRAPUP_SYSTEM_PROMPT_V2
- Include technical_theme as reference for debugging"
```

---

## Task 7: Activate V2 Prompts

**Files:**
- Modify: `src/pipelines/daily_report/prompts.py`

- [ ] **Step 1: Uncomment V2 prompt activation**

```python
# src/pipelines/daily_report/prompts.py
# Find and uncomment these lines (added in Task 3 and 4)

# Activate Reduce V2 prompts
REDUCE_SYSTEM_PROMPT = REDUCE_SYSTEM_PROMPT_V2
REDUCE_USER_PROMPT = REDUCE_USER_PROMPT_V2

# Activate Wrapup V2 prompts
WRAPUP_SYSTEM_PROMPT = WRAPUP_SYSTEM_PROMPT_V2
WRAPUP_USER_PROMPT = WRAPUP_USER_PROMPT_V2
```

- [ ] **Step 2: Run full pipeline test with 2026-04-17**

```bash
# Test full pipeline from ingest to wrapup
./scripts/test_daily_report_stages.sh 2026-04-17
```
Expected: All stages pass, reduce output contains investment_theme, wrapup references macro

- [ ] **Step 3: Verify output quality**

Check `tests/pipelines/daily_report/fixtures/stage_outputs/reduce_2026-04-17.json`:
- Each NewsItem has technical_theme, investment_theme, keywords
- investment_theme length is 20-40 chars
- keywords array has 5-10 items

- [ ] **Step 4: Commit prompt activation**

```bash
git add src/pipelines/daily_report/prompts.py
git commit -m "feat(prompts): activate V2 prompts for Reduce and Wrapup

- Enable REDUCE_SYSTEM_PROMPT_V2 and REDUCE_USER_PROMPT_V2
- Enable WRAPUP_SYSTEM_PROMPT_V2 and WRAPUP_USER_PROMPT_V2
- Full pipeline tested with 2026-04-17 data"
```

---

## Task 8: Update Documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CLI_USAGE.md`

- [ ] **Step 1: Update ARCHITECTURE.md Daily Report section**

```markdown
# docs/ARCHITECTURE.md
# Find the "Daily Report 파이프라인" section and update:

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
```

- [ ] **Step 2: Commit ARCHITECTURE.md update**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: update ARCHITECTURE.md with investment theme system

- Add dual theme architecture explanation
- Add search flow diagram
- Add investment theme patterns
- Link to design specs"
```

- [ ] **Step 3: Update CLI_USAGE.md report daily section**

```markdown
# docs/CLI_USAGE.md
# Find "#### 3-2. report daily" section and update output format:

**출력 파일:**
- `reports/2026-04/daily_2026-04-17.md`

**리포트 구조:**
- 매크로 데이터 (VIX, Fear & Greed, 시장 지수, 환율)
- 핵심 인사이트 3-5개 (테마 간 관계 + 매크로 연결)
- 카테고리별 테마 분석
  - 투자 인사이트 테마명 (20-40자, 방향성 명확)
  - 이모지 + 요약 + 영향 + 관련 종목
  - 검색 키워드 (종목명, 기술용어, 트렌드)

**예시:**
```markdown
## 매크로 데이터
VIX: 15.2 | Fear & Greed: 65 (Greed)
미국: S&P500 +1.2%, NASDAQ +1.5% | 한국: KOSPI +0.5%

## 핵심 인사이트
💡 AI 인프라 투자 확대가 HBM 수요 증가로 이어지며 국내 반도체 업사이클 기대
🌊 미국 금리 인하 기대감 속 성장주 중심 랠리, 한국은 실적 검증 단계
⚠️ 중국 경기 둔화 우려가 이차전지·조선 섹터 리스크로 작용

## 반도체
### 🚀 GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜
...
```
```

- [ ] **Step 4: Commit CLI_USAGE.md update**

```bash
git add docs/CLI_USAGE.md
git commit -m "docs: update CLI_USAGE.md with new report format

- Add macro data section explanation
- Add investment theme example (20-40 chars)
- Add search keyword explanation
- Show theme relationship examples"
```

---

## Task 9: Clean Up and Final Testing

**Files:**
- Delete: `/tmp/implementation_plan.md` (obsolete draft)
- Test: Full pipeline with 2026-04-17

- [ ] **Step 1: Remove obsolete draft plan**

```bash
rm /tmp/implementation_plan.md
```

- [ ] **Step 2: Run full integration test**

```bash
# Full pipeline from Telegram data to final report
uv run python -m src.pipelines.daily_report.pipeline 2026-04-17
```
Expected: 
- Ingest: Load messages and macro
- Map: Extract issues with categories
- Shuffle: Group by category, normalize technical themes
- Reduce: Generate investment themes (20-40 chars) and keywords (5-10 items)
- Wrapup: Connect themes with macro data, output key insights

- [ ] **Step 3: Validate reduce output manually**

```python
# Load and inspect reduce output
import json
with open("tests/pipelines/daily_report/fixtures/stage_outputs/reduce_2026-04-17.json") as f:
    items = json.load(f)

for item in items:
    # Check fields exist
    assert "technical_theme" in item
    assert "investment_theme" in item
    assert "keywords" in item
    
    # Check length constraints
    inv_theme = item["investment_theme"]
    assert 20 <= len(inv_theme) <= 40, f"Length {len(inv_theme)}: {inv_theme}"
    
    # Check keywords count
    keywords = item["keywords"]
    assert 5 <= len(keywords) <= 10, f"Keywords {len(keywords)}: {keywords}"
    
    print(f"✓ [{item['category']}]")
    print(f"  Technical: {item['technical_theme']}")
    print(f"  Investment: {item['investment_theme']}")
    print(f"  Keywords: {keywords}")
```

- [ ] **Step 4: Validate wrapup output**

```python
# Check wrapup references macro
with open("tests/pipelines/daily_report/fixtures/stage_outputs/wrapup_2026-04-17.json") as f:
    report = json.load(f)

insights = report["key_insights"]
assert len(insights) >= 3, "Should have at least 3 insights"

# Check insights reference macro concepts
macro_terms = ["VIX", "Fear", "Greed", "시장", "환율", "금리"]
has_macro_ref = any(
    any(term in insight for term in macro_terms)
    for insight in insights
)
assert has_macro_ref, "Insights should reference macro data"

print("✓ Wrapup insights:")
for insight in insights:
    print(f"  - {insight}")
```

- [ ] **Step 5: Run pytest suite**

```bash
# Run all daily report tests
pytest tests/pipelines/daily_report/ -v
```
Expected: All tests pass (including new test_investment_themes.py)

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete investment theme architecture implementation

Summary:
- Split theme field into technical_theme (search key) and investment_theme (display)
- Add keywords field for enhanced search (5-10 items)
- Implement investment theme generation in Reduce stage (20-40 chars)
- Enhance Wrapup to connect themes with macro data
- Update all documentation

Breaking changes:
- NewsItem.theme removed, replaced with technical_theme + investment_theme
- ThemeAnalysis.theme removed, replaced with investment_theme
- Reduce stage now requires V2 prompts
- Wrapup stage now requires macro data formatting

Tested with 2026-04-17 data, all stages pass."
```

---

## Self-Review Checklist

**Spec Coverage:**
- [x] ThemeAnalysis has investment_theme and keywords fields (Task 1)
- [x] NewsItem has technical_theme, investment_theme, keywords fields (Task 2)
- [x] REDUCE_SYSTEM_PROMPT_V2 with 3 patterns and Few-shot examples (Task 3)
- [x] WRAPUP_SYSTEM_PROMPT_V2 with theme relationships and macro connection (Task 4)
- [x] reduce_stage.py generates investment themes (Task 5)
- [x] wrapup_stage.py formats macro data and uses investment_theme (Task 6)
- [x] Prompts activated (Task 7)
- [x] Documentation updated (Task 8)
- [x] Full integration testing (Task 9)

**Placeholder Scan:**
- [x] No "TBD" or "TODO" in any step
- [x] All code blocks are complete and runnable
- [x] No "similar to Task N" references
- [x] All test commands have expected outputs
- [x] All commit messages are complete

**Type Consistency:**
- [x] `technical_theme` used consistently across reduce_stage.py and models.py
- [x] `investment_theme` used consistently across all files
- [x] `keywords` is `list[str]` in all model definitions
- [x] ThemeAnalysis matches NewsItem field types
- [x] Prompt variable names match function parameters

**Additional Checks:**
- [x] All tasks are 2-5 minute actions
- [x] TDD approach: test → fail → implement → pass → commit
- [x] Each task is self-contained and produces working software
- [x] File paths are exact (not "src/pipelines/..." but full paths)
- [x] No breaking changes to existing Ingest, Map, Shuffle stages

---

## Plan Complete

Plan saved to `docs/superpowers/plans/2026-04-19-investment-theme-architecture.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
