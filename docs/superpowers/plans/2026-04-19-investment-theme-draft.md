# 구현 계획 및 프롬프트 초안

## 📋 현재 구조 분석

### 1. 데이터 모델 (models.py)

**현재:**
```python
class NewsItem(BaseModel):
    category: IssueCategory
    theme: str              # 하나의 테마 필드
    emoji: str
    summary: str
    impact: str
    stocks: list[StockDetail]
```

**변경 필요:**
```python
class NewsItem(BaseModel):
    category: IssueCategory
    technical_theme: str    # NEW: Shuffle에서 온 기술적 테마
    investment_theme: str   # NEW: Reduce에서 생성한 투자 인사이트
    keywords: list[str]     # NEW: 검색용 키워드
    emoji: str
    summary: str
    impact: str
    stocks: list[StockDetail]
```

---

### 2. Reduce 프롬프트 (prompts.py)

**현재:**
```python
REDUCE_SYSTEM_PROMPT = """당신은 한국 금융 시장 전문 애널리스트입니다.
특정 테마에 대한 분석 리포트를 작성하세요.

**작성 지침**:
1. 한글로 작성
2. 이모지 사용
3. Summary: bullet points
4. Impact: 시장 영향
5. 종목 추출
"""
```

**변경 필요:** 투자 인사이트 테마명 생성 추가

---

### 3. Wrapup 프롬프트 (prompts.py)

**현재:**
```python
WRAPUP_SYSTEM_PROMPT = """당신은 시장 전략가입니다.
여러 테마들을 종합하여 오늘의 핵심 시장 내러티브를 도출하세요.

**작성 지침**:
1. 한글로 작성
2. 메타 인사이트 3-5개 도출
3. 테마 간 연결과 시사점
"""
```

**변경 필요:** 매크로 데이터 연결, 섹터 로테이션, 우선순위 판단 강화

---

## 🔨 구현 계획

### Phase 1: 모델 수정 (models.py)

**파일:** `src/pipelines/daily_report/models.py`

#### 1.1 ThemeAnalysis 수정 (Reduce LLM 출력용)
```python
class ThemeAnalysis(BaseModel):
    """Reduce stage LLM 출력용 (category 제외)."""
    
    # 기존
    theme: str  # → 삭제 또는 deprecated
    
    # 추가
    investment_theme: str = Field(
        description="투자 인사이트 테마명 (20-40자). "
        "패턴: [트렌드] + [방향성] + [수혜/리스크]. "
        "예: 'GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜'"
    )
    keywords: list[str] = Field(
        description="검색용 키워드 5-10개 (종목명, 기술용어, 트렌드)",
        min_length=5,
        max_length=10
    )
    
    # 기존 유지
    emoji: str
    summary: str
    impact: str
    stocks: list[StockDetail]
```

#### 1.2 NewsItem 수정
```python
class NewsItem(BaseModel):
    """Reduce stage의 테마별 분석."""
    
    category: IssueCategory
    
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
    
    # 기존 유지
    emoji: str
    summary: str
    impact: str
    stocks: list[StockDetail]
```

---

### Phase 2: Reduce 프롬프트 수정 (prompts.py)

**파일:** `src/pipelines/daily_report/prompts.py`

#### 2.1 새 버전 추가

```python
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

# 활성 버전 전환
REDUCE_SYSTEM_PROMPT = REDUCE_SYSTEM_PROMPT_V2
REDUCE_USER_PROMPT = REDUCE_USER_PROMPT_V2
```

---

### Phase 3: Wrapup 프롬프트 수정 (prompts.py)

```python
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

# 활성 버전 전환
WRAPUP_SYSTEM_PROMPT = WRAPUP_SYSTEM_PROMPT_V2
WRAPUP_USER_PROMPT = WRAPUP_USER_PROMPT_V2
```

---

### Phase 4: Reduce 스테이지 수정 (reduce_stage.py)

**파일:** `src/pipelines/daily_report/stages/reduce_stage.py`

#### 4.1 _analyze_theme 함수 수정

```python
async def _analyze_theme(
    llm,
    category: str,
    theme: str,  # ← technical_theme
    issues: list[MappedIssue],
    macro: MacroSnapshot,
    date: str,
) -> NewsItem:
    """단일 테마 분석."""
    
    # 이슈 포맷팅
    issues_text = "\n\n".join([
        f"**{issue.title}**\n{issue.summary}\n"
        f"키워드: {', '.join(issue.keywords)}\n"
        f"감성: {issue.sentiment}"
        for issue in issues
    ])
    
    # 프롬프트 (technical_theme 명시)
    system_prompt = REDUCE_SYSTEM_PROMPT
    user_prompt = REDUCE_USER_PROMPT.format(
        technical_theme=theme,  # ← 명시적으로 기술적 테마 전달
        issues=issues_text
    )
    
    messages = REDUCE_LLM.build_messages(system_prompt, user_prompt)
    
    # LLM 호출
    response = await invoke_llm_with_retry(llm, ThemeAnalysis, messages, config)
    
    # NewsItem 생성 (technical_theme + investment_theme)
    return NewsItem(
        category=category,
        technical_theme=theme,              # Shuffle에서 온 것
        investment_theme=response.investment_theme,  # LLM이 생성
        keywords=response.keywords,         # LLM이 추출
        emoji=response.emoji,
        summary=response.summary,
        impact=response.impact,
        stocks=response.stocks,
    )
```

---

### Phase 5: Wrapup 스테이지 수정 (wrapup_stage.py)

**파일:** `src/pipelines/daily_report/stages/wrapup_stage.py`

#### 5.1 프롬프트에 매크로 데이터 추가

```python
def wrapup_stage(
    news_items: list[NewsItem],
    macro: MacroSnapshot,  # ← 추가
    date: str = None,
) -> DailyReport:
    """전체 시장 인사이트 도출."""
    
    # 매크로 데이터 포맷팅
    macro_text = f"""
VIX: {macro.vix}
Fear & Greed: {macro.fear_greed}
미국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.us_markets.items())}
한국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.kr_markets.items())}
KRW/USD: {macro.krw_usd}
"""
    
    # 테마별 분석 포맷팅 (investment_theme 사용)
    news_text = "\n\n".join([
        f"[{item.category}] {item.investment_theme}\n"  # ← investment_theme
        f"기술 테마: {item.technical_theme}\n"
        f"{item.summary}"
        for item in news_items
    ])
    
    # 프롬프트
    user_prompt = WRAPUP_USER_PROMPT.format(
        macro=macro_text,
        news_count=len(news_items),
        news_items=news_text
    )
    
    # LLM 호출
    ...
```

---

## 🧪 프롬프트 검증 및 개선 방법

### 1. Few-shot 예시 품질 검증

**체크리스트:**
- [ ] 다양한 감성 커버 (bull, bear, neutral)
- [ ] 다양한 패턴 커버 (패턴 1, 2, 3)
- [ ] 길이 제약 준수 (20-40자)
- [ ] 실제 사용할 테마와 유사

**개선 방법:**
```python
# tests/pipelines/daily_report/test_reduce_prompt.py

def test_reduce_prompt_examples():
    """Reduce 프롬프트 예시가 충분한지 검증"""
    
    examples = [
        {
            "tech": "AI 인프라 및 칩 수요",
            "investment": "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
            "pattern": 1,
            "sentiment": "bull"
        },
        {
            "tech": "콘텐츠 기업 실적 부진",
            "investment": "스트리밍 가이던스 실망, 광고 전환 시급",
            "pattern": 1,
            "sentiment": "bear"
        },
    ]
    
    # 패턴 커버리지
    patterns = {ex["pattern"] for ex in examples}
    assert patterns == {1, 2, 3}, "모든 패턴 커버 필요"
    
    # 감성 커버리지
    sentiments = {ex["sentiment"] for ex in examples}
    assert sentiments == {"bull", "bear", "neutral"}, "모든 감성 커버 필요"
```

---

### 2. 출력 품질 평가 (LLM-as-Judge)

**평가 기준:**
1. 길이: 20-40자?
2. 패턴: 지정된 패턴 따름?
3. 방향성: 명확한가? (가속/둔화/전환)
4. 구체성: 섹터/종목 언급?
5. 키워드: 5-10개?

**평가 프롬프트:**
```python
INVESTMENT_THEME_JUDGE_PROMPT = """당신은 투자 테마명 품질 평가자입니다.

**평가 대상**:
기술 테마: {technical_theme}
투자 테마: {investment_theme}
키워드: {keywords}

**평가 기준**:
1. 길이 (0-10점): 20-40자 사이인가?
2. 패턴 (0-10점): [트렌드 + 방향성 + 수혜/리스크] 패턴을 따르는가?
3. 방향성 (0-10점): 가속/둔화/전환 등 방향성이 명확한가?
4. 구체성 (0-10점): 구체적 섹터/종목을 언급하는가?
5. 키워드 (0-10점): 5-10개의 적절한 키워드인가?

**출력**:
{{
  "scores": {{
    "length": X,
    "pattern": X,
    "direction": X,
    "specificity": X,
    "keywords": X
  }},
  "total": XX,
  "feedback": "구체적 개선 제안..."
}}
"""
```

---

### 3. A/B 테스트

**비교 항목:**
- 프롬프트 V1 vs V2
- Few-shot 3개 vs 5개
- 길이 제약 있음 vs 없음

**측정 지표:**
- 평균 길이
- 패턴 준수율
- 사용자 만족도 (수동 평가)

```python
def ab_test_reduce_prompts(date: str, sample_size: int = 10):
    """Reduce 프롬프트 A/B 테스트"""
    
    # 샘플 테마 추출
    themes = load_sample_themes(date, sample_size)
    
    results_v1 = []
    results_v2 = []
    
    for theme in themes:
        # V1 실행
        result_v1 = run_reduce_stage(theme, prompt_version="v1")
        results_v1.append(result_v1)
        
        # V2 실행
        result_v2 = run_reduce_stage(theme, prompt_version="v2")
        results_v2.append(result_v2)
    
    # 평가
    scores_v1 = evaluate_results(results_v1)
    scores_v2 = evaluate_results(results_v2)
    
    print(f"V1 평균 점수: {scores_v1.mean()}")
    print(f"V2 평균 점수: {scores_v2.mean()}")
    
    # 통계적 유의성 검정
    from scipy.stats import ttest_rel
    statistic, pvalue = ttest_rel(scores_v1, scores_v2)
    print(f"p-value: {pvalue}")
```

---

### 4. 프롬프트 버전 관리

```python
# prompts.py

REDUCE_PROMPT_VERSIONS = {
    "v1": {
        "system": REDUCE_SYSTEM_PROMPT_V1,
        "user": REDUCE_USER_PROMPT_V1,
        "date": "2026-04-17",
        "notes": "초기 버전, 투자 인사이트 없음"
    },
    "v2": {
        "system": REDUCE_SYSTEM_PROMPT_V2,
        "user": REDUCE_USER_PROMPT_V2,
        "date": "2026-04-18",
        "notes": "투자 인사이트 + 키워드 추가, Few-shot 3개"
    },
    "v3": {  # 미래 버전
        "system": REDUCE_SYSTEM_PROMPT_V3,
        "user": REDUCE_USER_PROMPT_V3,
        "date": "2026-04-20",
        "notes": "Few-shot 5개로 증가, 길이 제약 강화"
    }
}

# 활성 버전
ACTIVE_REDUCE_VERSION = "v2"
REDUCE_SYSTEM_PROMPT = REDUCE_PROMPT_VERSIONS[ACTIVE_REDUCE_VERSION]["system"]
REDUCE_USER_PROMPT = REDUCE_PROMPT_VERSIONS[ACTIVE_REDUCE_VERSION]["user"]
```

---

## 📊 테스트 계획

### 1. 유닛 테스트
```bash
# 모델 검증
pytest tests/pipelines/daily_report/test_models.py::test_news_item_fields

# 프롬프트 검증
pytest tests/pipelines/daily_report/test_prompts.py::test_reduce_prompt_examples
```

### 2. 통합 테스트
```bash
# 전체 파이프라인 (2026-04-17 데이터)
uv run python -m src.pipelines.daily_report.stages.reduce_stage 2026-04-17

# 결과 검증
pytest tests/pipelines/daily_report/test_integration.py::test_reduce_investment_themes
```

### 3. 품질 검증
```bash
# LLM-as-Judge
uv run python scripts/evaluate_investment_themes.py 2026-04-17

# A/B 테스트
uv run python scripts/ab_test_prompts.py 2026-04-17 --sample-size 10
```

---

## 🎯 체크리스트

### Phase 1: 모델
- [ ] ThemeAnalysis에 investment_theme, keywords 추가
- [ ] NewsItem에 technical_theme, investment_theme, keywords 추가
- [ ] 기존 코드 호환성 확인

### Phase 2: Reduce 프롬프트
- [ ] REDUCE_SYSTEM_PROMPT_V2 작성
- [ ] Few-shot 예시 3개 추가
- [ ] 길이/패턴 제약 명시

### Phase 3: Wrapup 프롬프트
- [ ] WRAPUP_SYSTEM_PROMPT_V2 작성
- [ ] 매크로 연결 지침 추가
- [ ] 테마 간 관계 파악 지침 추가

### Phase 4: Reduce 스테이지
- [ ] _analyze_theme 함수 수정
- [ ] technical_theme → investment_theme 변환
- [ ] NewsItem 생성 로직 수정

### Phase 5: Wrapup 스테이지
- [ ] 매크로 데이터 포맷팅
- [ ] investment_theme 사용
- [ ] 프롬프트 전달 수정

### Phase 6: 테스트
- [ ] 유닛 테스트 작성
- [ ] 2026-04-17 데이터로 통합 테스트
- [ ] 품질 평가 (LLM-as-Judge)
- [ ] A/B 테스트 (V1 vs V2)

### Phase 7: 문서화
- [ ] ARCHITECTURE.md 업데이트
- [ ] CLI_USAGE.md 업데이트
- [ ] 변경사항 CHANGELOG 작성

---

## 다음 단계

구현을 시작할까요? 어떤 Phase부터 시작하고 싶으신가요?
