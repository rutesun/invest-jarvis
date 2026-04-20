# Investment Theme Architecture Design

**Date**: 2026-04-19
**Branch**: TBD
**Status**: Draft

---

## 배경 및 목적

현재 `NewsItem.theme`이 두 가지 역할을 동시에 수행한다:

1. **검색 키** (시스템용) — Shuffle stage에서 정규화한 기술적 테마명, 안정적이고 반복적
2. **표시명** (사용자용) — 리포트에 노출되는 투자 인사이트, 구체적이고 맥락 의존적

이 이중 역할로 인해:
- 검색 기능 구현 시 불안정: 기술적 테마명이 매번 바뀌면 키워드 검색 불가
- 투자 인사이트 부족: "AI 인프라 및 칩 수요" 같은 기술적 표현은 투자 방향성을 담지 못함
- Wrapup stage 역할 불명확: 테마명 생성 vs 테마 간 관계 파악

**해결**: 
1. `technical_theme` (Shuffle 생성, 검색 키) + `investment_theme` (Reduce LLM 생성, 표시명) 분리
2. `keywords` 필드 추가로 검색 강화
3. Wrapup은 테마 간 관계 + 매크로 연결에 집중

---

## 데이터 모델 변경

### `ThemeAnalysis` (Reduce LLM 출력)

```python
class ThemeAnalysis(BaseModel):
    """Reduce stage LLM 출력용 (category 제외)."""
    
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
    emoji: str
    summary: str
    impact: str
    stocks: list[StockDetail]
```

### `NewsItem` (Reduce 출력)

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
    
    emoji: str
    summary: str
    impact: str
    stocks: list[StockDetail]
```

---

## 투자 테마 생성 규칙

### 작성 패턴

**패턴 1**: `[트렌드] + [방향성] + [수혜/리스크]`
- 예: "AI 칩 수요 폭증, GPU 가격 파워 강화"
- 예: "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"

**패턴 2**: `[원인] + [결과] + [투자 액션]`
- 예: "엔비디아 독점 완화로 대체재 주목"

**패턴 3**: `[현상] + [구체적 종목/섹터]`
- 예: "AI 인프라 투자 가속, AMD·세레브라스 수혜"

### 어구 가이드

- **Bull**: 폭증, 가속화, 본격화, 수혜, 턴어라운드, 주목, 부상
- **Bear**: 둔화, 압박, 우려, 리스크, 약화, 부담
- **Neutral**: 재편, 전환, 다변화, 가시화

### 제약

- 길이: 20-40자 (쉼표 포함)
- 구조: `[전반부 10-15자, 후반부 10-15자]`
- 방향성 명확히 (가속/둔화/전환 등)
- 가능하면 구체적 종목/섹터 언급

---

## 파이프라인 변경

### Shuffle Stage (변경 없음)

기술적 테마로만 정규화. 투자 인사이트 생성하지 않음.

### Reduce Stage

**입력**: `(category, technical_theme, issues)`  
**출력**: `NewsItem` (technical_theme + investment_theme + keywords)

LLM에게 기술적 테마를 투자 인사이트로 변환 요청.

**Few-shot 예시**:

```
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
```

### Wrapup Stage

**역할 재정의**: 개별 테마명 생성 ❌, 전체 시장 스토리 구성 ✅

**작업**:
1. **테마 간 관계 파악**
   - 연결: "AI 인프라 투자 확대 → HBM 수요 증가"
   - 대비: "AI 섹터 강세 vs 이차전지 약세"
   - 선후: "엔비디아 독점 완화 → GPU 공급망 재편"

2. **매크로 데이터 연결**
   - VIX, Fear & Greed가 테마를 뒷받침/반박?
   - 미국/한국 시장 차이와 테마 관련성?
   - 환율의 섹터별 영향?

3. **우선순위 결정**
   - 핵심 테마 (이슈 수, 영향력, 시의성)
   - 주목 섹터
   - 수혜/리스크 종목

4. **전체 시장 스토리**
   - 한 문장 요약
   - 섹터 로테이션
   - 투자 시사점 3-5개

**입력**: `macro + news_items` (investment_theme 사용)

---

## 검색 기능 설계

### 검색 흐름

1. 사용자 쿼리: "엔비디아"
2. `NewsItem.technical_theme` + `NewsItem.keywords` 검색
3. 매칭된 `NewsItem` 반환
4. UI에는 `investment_theme` 표시

### 예시

```python
# 저장된 데이터
NewsItem(
    technical_theme="AI 인프라 및 칩 수요",  # 검색 키
    investment_theme="GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",  # 표시명
    keywords=["GPU", "엔비디아", "AMD", "세레브라스"]
)

# 검색
query = "엔비디아"
# → technical_theme에서 "AI 인프라 및 칩 수요" 매칭
# → keywords에서 "엔비디아" 매칭
# → investment_theme "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜" 표시
```

---

## 프롬프트 변경

### REDUCE_SYSTEM_PROMPT_V2

**추가 작업**:
- 투자 인사이트 테마명 생성 (3가지 패턴, 어구 가이드, 길이 제약)
- 검색 키워드 추출 (5-10개)
- Few-shot 예시 3개

### WRAPUP_SYSTEM_PROMPT_V2

**역할 강화**:
- 테마 간 관계 파악 (연결/대비/선후)
- 매크로 데이터 연결
- 우선순위 결정
- 전체 시장 스토리 구성

**입력 추가**:
- 매크로 데이터 (VIX, Fear & Greed, 시장 지수, 환율)

---

## 검증 방법

### 1. Few-shot 품질 체크

- [ ] 다양한 감성 커버 (bull, bear, neutral)
- [ ] 다양한 패턴 커버 (패턴 1, 2, 3)
- [ ] 길이 제약 준수 (20-40자)
- [ ] 실제 테마와 유사성

### 2. LLM-as-Judge 평가

**평가 기준**:
1. 길이: 20-40자?
2. 패턴: 지정 패턴 준수?
3. 방향성: 명확한가?
4. 구체성: 섹터/종목 언급?
5. 키워드: 5-10개?

### 3. A/B 테스트

- 프롬프트 V1 vs V2
- Few-shot 3개 vs 5개
- 길이 제약 있음 vs 없음

**측정 지표**:
- 평균 길이
- 패턴 준수율
- 사용자 만족도

### 4. 프롬프트 버전 관리

```python
REDUCE_PROMPT_VERSIONS = {
    "v1": {...},
    "v2": {...},
}
ACTIVE_REDUCE_VERSION = "v2"
```

---

## 영향 받는 파일

| 파일 | 변경 유형 |
|------|-----------|
| `src/pipelines/daily_report/models.py` | `ThemeAnalysis`: `investment_theme`, `keywords` 추가<br>`NewsItem`: `technical_theme`, `investment_theme`, `keywords` 추가 |
| `src/pipelines/daily_report/prompts.py` | `REDUCE_SYSTEM_PROMPT_V2` 추가<br>`REDUCE_USER_PROMPT_V2` 추가<br>`WRAPUP_SYSTEM_PROMPT_V2` 추가<br>`WRAPUP_USER_PROMPT_V2` 추가 |
| `src/pipelines/daily_report/stages/reduce_stage.py` | `_analyze_theme`: technical_theme → investment_theme 변환<br>`NewsItem` 생성 로직 수정 |
| `src/pipelines/daily_report/stages/wrapup_stage.py` | 매크로 데이터 포맷팅 추가<br>`investment_theme` 사용 |
| `tests/pipelines/daily_report/test_models.py` | 새 필드 테스트 |
| `tests/pipelines/daily_report/test_reduce_stage.py` | investment_theme 생성 테스트 |
| `tests/pipelines/daily_report/test_wrapup_stage.py` | 매크로 연결 테스트 |

---

## 마이그레이션

- 기존 `NewsItem` 객체는 `technical_theme`, `investment_theme` 필드가 없음
- 신규 필드는 optional로 추가하거나, 기존 `theme`을 `technical_theme`으로 복사
- 점진적 마이그레이션: 신규 리포트만 새 구조 사용
