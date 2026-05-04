# Map Stage 클러스터링 개선 방안

**작성일**: 2026-04-30
**상태**: Draft
**현재 성능**: avg_sources 1.5-1.6 (목표: 1.7-2.0)

---

## 요약

Map stage의 클러스터링 품질을 개선하기 위한 10가지 개선 포인트를 정리한 문서입니다.

**현재 문제:**
- avg_sources 1.5-1.6 수준 (목표 1.7-2.0 미달)
- Temperature 조정만으로는 한계 (0.0: 1.34, 0.2: 1.57, 0.3: 1.45)
- 카테고리 검증 오류로 2-3개 청크 실패
- 테마 다양성 폭발 (206개 고유 테마 / 107개 이슈 = 1.93배)

---

## 개선 포인트

### 1. 다른 날짜 데이터로 검증

**문제:**
- 현재 2026-04-14 하나만 테스트
- 날짜별 메시지 특성 차이 고려 안 됨

**해결책:**
```python
@pytest.mark.parametrize("date", [
    "2026-04-14", "2026-04-15", "2026-04-16", 
    "2026-04-17", "2026-04-20"
])
def test_map_stage_with_real_data(date):
    ingest_result = ingest(date)
    issues = map_stage(ingest_result.messages)
    # 날짜별 avg_sources 분포 파악
```

**기대 효과:**
- 프롬프트 일반화 검증
- 날짜별 avg_sources 분포 파악 (예: 1.4~1.7 범위)
- Edge case 발견 (뉴스 폭발일, 조용한 날)

**트레이드오프:**
- 테스트 시간 5배 증가 (5분 → 25분)
- 신뢰성 크게 향상

**난이도:** 낮음 (1시간)
**우선순위:** 🟡 중간

---

### 2. 카테고리 검증 오류 해결

**문제:**
```
ValidationError: issues.14.category
  Input should be '바이오/제약' (got '의료/제약')
```

LLM이 자연스러운 표현 선호 → 프롬프트 명시했지만 100% 따르지 않음

**해결 방법 A: 카테고리 추가**
```python
IssueCategory = Literal[
    "바이오/제약",
    "의료/제약",  # Alias 추가
    ...
]
```
✅ 장점: 간단, LLM 자유도 유지
❌ 단점: 카테고리 중복, Shuffle에서 정규화 필요

**해결 방법 B: 후처리 매핑 (추천)**
```python
CATEGORY_ALIASES = {
    "의료/제약": "바이오/제약",
    "운송": "운송/물류",
    "엔터테인먼트": "엔터/미디어",
}

def normalize_category(category: str) -> IssueCategory:
    return CATEGORY_ALIASES.get(category, category)
```
✅ 장점: 정규화된 데이터, 명확한 매핑
❌ 단점: 추가 코드, 미리 알 수 없는 alias 문제

**해결 방법 C: Structured Output 강화**
- Anthropic/OpenAI Structured Output 기능 활용
- JSON Schema enum 제약 → LLM 강제 준수

✅ 장점: 100% 검증 성공
❌ 단점: Provider 의존성, 일부 모델만 지원

**난이도:** 낮음 (1시간)
**우선순위:** 🔴 높음 (현재 2-3개 청크 실패 중)

---

### 3. 청크 크기 최적화

**배경:**
```python
MAP_MAX_TOKENS_PER_CHUNK = 80_000  # 약 40,000 한글 글자
```

현재: 250개 메시지 → 3-4개 청크로 분할

**청크 크기의 영향:**

| 크기 | 장점 | 단점 |
|------|------|------|
| 작음 (40k) | 빠른 병렬 처리, 메모리 효율 | 청크 간 통합 불가 |
| 중간 (80k) | 균형 | - |
| 큼 (120k) | 청크 내 통합 증가 | 느린 처리, context window 압박 |

**예시:**
```
청크 40k: [메시지1-60] → 이슈A, [메시지61-120] → 이슈B
         ⚠️ 메시지10(삼성)과 메시지70(SK하이닉스)를 통합 불가

청크 120k: [메시지1-180] → 이슈A+B 통합 가능 ✅
```

**실험 설계:**
```python
for chunk_size in [60_000, 80_000, 100_000, 120_000]:
    MAP_MAX_TOKENS_PER_CHUNK = chunk_size
    issues = map_stage(messages)
    print(f"{chunk_size}: avg_sources={avg_sources}")
```

**예상 결과:**
- 60k: avg_sources 1.3
- 80k: avg_sources 1.5 (현재)
- 100k: avg_sources 1.6-1.7 (최적?)
- 120k: avg_sources 1.7+ but 느림

**트레이드오프:**
- ↑ 청크 크기 → ↑ avg_sources, ↑ 처리시간
- Claude Haiku context window: 200k (여유 있음)

**난이도:** 낮음 (1시간)
**우선순위:** 🟡 중간

---

### 4. Few-shot 예시 최적화

**현재 상태:**
```python
MAP_EXAMPLE_1: 6개 메시지 → 2개 이슈 (avg 3.0)
MAP_EXAMPLE_2: 3개 메시지 → 1개 이슈 (avg 3.0)
MAP_EXAMPLE_3: 4개 메시지 → 1개 이슈 (avg 4.0)
MAP_EXAMPLE_BAD: 3개 메시지 → 3개 이슈 (avg 1.0)
```

**문제:**
- Good 예시 평균 source: 3.0-4.0
- 실제 LLM 출력: 1.5
- **격차가 너무 큼** → LLM이 따라하기 어려움

**개선안:**

**A. 점진적 난이도**
```python
MAP_EXAMPLE_EASY: 2개 메시지 → 1개 (avg 2.0)
MAP_EXAMPLE_MEDIUM: 3-4개 → 1개 (avg 3.5)
MAP_EXAMPLE_HARD: 6-8개 → 1개 (avg 7.0)
```

**B. 도메인 다양화**
```python
# 현재: 반도체/배터리 위주
# 추가: 금융, 에너지, 바이오 등
MAP_EXAMPLE_FINANCE: 은행 3사 실적 → 1개
MAP_EXAMPLE_ENERGY: 유가/환율/정책 → 1개
```

**C. 시간순 통합 예시**
```python
MAP_EXAMPLE_TIMELINE: 
  [월요일] 애플 신제품 루머
  [화요일] 발표회 공지
  [수요일] 실제 발표
  [목요일] 주가 반응
  → 1개 이슈 "애플 신제품 사이클"
```

**D. 나쁜 예시 강화**
```python
MAP_EXAMPLE_BAD_1: 과도한 분절 (10개 → 10개)
MAP_EXAMPLE_BAD_2: 잘못된 통합 (다른 업종 억지로 묶음)
MAP_EXAMPLE_BAD_3: 테마 재사용 안 함
```

**예상 효과:**
- 현재 1.5 → 1.7-1.8 상승 가능

**난이도:** 중간 (3시간)
**우선순위:** 🟢 높음 (Few-shot 효과 입증됨)

---

### 5. 프롬프트 구조 개선

**현재 순서 문제:**
```
MAP_SYSTEM_PROMPT_V6:
1. 데이터 보존 (200 단어)
2. 공격적 클러스터링 (150 단어)
3. 테마 재사용 (100 단어)
4. Takeaway (50 단어)
5. 클러스터링 일관성 (50 단어)
6. 카테고리 선택 (100 단어)
{examples}  ← 맨 끝 (650 단어 후)
```

**인지 과학적 문제:**
- LLM도 **먼저 본 것을 더 중요하게 인식**
- Examples 맨 끝 → 영향력 약화

**개선안 A: Examples First**
```python
MAP_SYSTEM_PROMPT_V7 = """
당신은 한국 금융 시장 전문 애널리스트입니다.

**Few-shot 예시 (먼저 학습하세요)**:
{examples}

이제 위 예시를 참고하여 아래 지침을 따르세요:
1. 공격적 클러스터링 (가장 중요!)
2. 데이터 보존
3. 테마 재사용
"""
```

**개선안 B: 시각적 강조**
```python
"""
========================================
🔥 핵심 목표: 평균 2개 이상 메시지 통합
========================================

{examples}

상세 지침:
1. ...
"""
```

**개선안 C: 체크리스트**
```python
"""
매 이슈 생성 전 체크:
□ 유사 메시지 2개 이상 통합?
□ 같은 테마명 재사용?
□ 숫자 데이터 포함?

{examples}
"""
```

**예상 효과:**
- Examples First: +0.1~0.2 avg_sources
- 시각적 강조: 주의 집중
- 체크리스트: 단계별 검증

**난이도:** 낮음 (2시간)
**우선순위:** 🟡 중간

---

### 6. 후처리 통합 레이어

**개념:**
```
현재: Map → Shuffle
개선: Map → Post-Map Merge → Shuffle
```

**Post-Map Merge 역할:**
```python
def post_map_merge(issues: list[MappedIssue]) -> list[MappedIssue]:
    """
    Map이 놓친 통합 기회 포착
    
    통합 조건:
    1. 같은 category + 테마 유사도 > 0.8
    2. 같은 기업명 포함
    3. 시간적으로 인접 (1시간 이내)
    """
    # 카테고리별 그룹핑
    by_category = group_by(issues, key=lambda x: x.category)
    
    for category, group in by_category.items():
        # 테마 유사도 계산 (embedding)
        similarity = compute_similarity(group)
        
        # 임계값 이상 → 통합
        for i, j in high_similarity_pairs(similarity, threshold=0.8):
            merged = merge_issues(group[i], group[j])
    
    return merged
```

**장점:**
- Map 보수적 출력 → 후처리로 통합
- 규칙 기반 → 예측 가능
- 추가 LLM 호출 불필요 (빠름, 저렴)

**단점:**
- 복잡도 증가
- 테마 유사도 계산 필요 (embedding model)
- "억지 통합" 리스크

**난이도:** 중간 (2일)
**우선순위:** 🟡 중간

---

### 7. 다른 날짜 성능 비교

**실험 설계:**
```bash
# 1주일 데이터 평가
dates=(2026-04-14 ... 2026-04-20)

for date in "${dates[@]}"; do
  result=$(map_stage $date)
  avg=$(extract_avg_sources "$result")
  echo "$date,$avg" >> results.csv
done

# 통계 분석
python analyze_results.py results.csv
```

**분석 항목:**
```python
df = pd.read_csv("results.csv")
print(f"평균: {df.avg_sources.mean():.2f}")
print(f"표준편차: {df.avg_sources.std():.2f}")
print(f"최소/최대: {df.min():.2f} / {df.max():.2f}")

# 메시지 개수 vs avg_sources 상관관계
corr = df[['message_count', 'avg_sources']].corr()
```

**예상 발견:**
- 메시지 많은 날 → avg_sources 낮음?
- 주말 전후 → 패턴 다름?
- 특정 업종 집중일 → 통합 쉬움?

**난이도:** 낮음 (2시간)
**우선순위:** 🟢 높음

---

### 8. LLM-as-Judge로 클러스터링 품질 평가

**Wrapup 평가 성공 사례 활용:**
```python
# evaluations/evaluate_map.py

def evaluate_map_quality(issues, messages) -> dict:
    """
    평가 차원:
    1. merge_quality (0-10): 통합이 논리적?
    2. separation_quality (0-10): 분리가 적절?
    3. theme_consistency (0-10): 테마 재사용?
    4. data_preservation (0-10): 숫자 보존?
    5. compression_rate (0-10): 압축률 적절?
    """
    
    prompt = f"""
    원본 {len(messages)}개 → {len(issues)}개 이슈
    
    원본 메시지: {messages[:50]}
    생성 이슈: {issues}
    
    위 5개 차원으로 평가하세요.
    """
    
    judge = Sonnet_4_5(temperature=0.1)
    return judge.invoke(prompt)
```

**활용:**
```bash
# V4, V5, V6 비교
python evaluations/evaluate_map.py --baseline V4 --candidate V6
```

**예상 출력:**
```
V4: merge_quality 6.5, theme_consistency 5.0
V6: merge_quality 7.5 (+1.0), theme_consistency 6.5 (+1.5)

Recommendation: V6 shows improvement.
```

**난이도:** 중간 (1일)
**우선순위:** 🟡 중간

---

### 9. Shuffle stage 연계 개선

**현재:**
```
Map: 메시지 → 이슈 (통합)
  └─ 250 messages → 100 issues

Shuffle: 테마 정규화만
  └─ ["AI 메모리", "HBM"] → "AI 메모리 업사이클"
```

**문제:**
- Map 과도 분절
- Shuffle은 **테마명만 정규화**, 이슈 통합 안 함

**개선안: Shuffle V2 (테마 정규화 + 이슈 통합)**
```python
def shuffle_stage(issues) -> ShuffleResult:
    # 기존: 테마 정규화
    theme_mapping = normalize_themes(issues)
    
    # 신규: 같은 정규화 테마 → 이슈 통합
    merged_issues = merge_by_normalized_theme(
        issues, theme_mapping
    )
    
    return ShuffleResult(
        theme_mapping=theme_mapping,
        merged_issues=merged_issues,  # 새 필드
    )
```

**예시:**
```
Map 출력:
- Issue 1: "삼성 HBM" (themes: ["AI 메모리"])
- Issue 2: "SK하이닉스 HBM" (themes: ["HBM 업사이클"])

Shuffle 정규화:
- "AI 메모리" + "HBM 업사이클" → "AI 메모리 업사이클"

Shuffle 통합:
- Issue 1 + 2 → "HBM 시장 공급 부족"
  (source_ids 합침)
```

**장점:**
- Map 과도 분절 보완
- 테마 정규화 결과 활용 (일석이조)
- avg_sources 크게 향상 (1.5 → 2.5+)

**단점:**
- Shuffle 복잡도 증가
- 잘못된 통합 리스크
- Reduce 입력 변경 (하위 호환성)

**난이도:** 중상 (3-4일)
**우선순위:** 🔴 높음 (근본적 해결책)

---

### 10. 카테고리 Validation 완화

**현재 동작:**
```python
# LLM: "의료/제약" → ValidationError
# → Retry 3회
# → 실패 → 청크 전체 버림
```

**문제:**
- 2-3개 청크 validation 실패 → 데이터 손실
- Retry 3회 = 추가 비용/시간

**해결 방법:**

**A. Fuzzy Matching**
```python
from difflib import get_close_matches

def validate_category(value: str) -> str:
    if value in VALID_CATEGORIES:
        return value
    
    # 유사도 매칭
    matches = get_close_matches(
        value, VALID_CATEGORIES, n=1, cutoff=0.6
    )
    if matches:
        logger.warning(f"Fuzzy: {value} → {matches[0]}")
        return matches[0]
    
    # 실패 → 기타
    return "기타"
```

**B. Alias 사전 (추천)**
```python
CATEGORY_ALIASES = {
    "의료/제약": "바이오/제약",
    "제약": "바이오/제약",
    "운송": "운송/물류",
    "항공": "운송/물류",
    "엔터테인먼트": "엔터/미디어",
    "게임": "엔터/미디어",
}

def normalize_category(value: str) -> str:
    return CATEGORY_ALIASES.get(value, value)
```

**C. LLM 자체 수정 요청**
```python
if validation_error:
    prompt += f"""
    이전 category 오류: '{wrong_value}'
    허용 값: {VALID_CATEGORIES}
    가장 유사한 것으로 선택하세요.
    """
```

**장점:**
- 데이터 손실 방지 (100% 성공)
- Retry 감소 → 빠름, 저렴
- 사용자 경험 개선

**추천:** A + B 조합

**난이도:** 낮음 (1시간)
**우선순위:** 🔴 높음

---

## 우선순위 및 로드맵

### 우선순위 매트릭스

| 순위 | 항목 | 난이도 | 영향도 | 시간 | 우선순위 |
|------|------|--------|--------|------|----------|
| 1 | #10 카테고리 Validation 완화 | 낮음 | 높음 | 1h | 🔴 |
| 2 | #2 카테고리 오류 해결 | 낮음 | 높음 | 1h | 🔴 |
| 3 | #4 Few-shot 예시 최적화 | 중간 | 높음 | 3h | 🟢 |
| 4 | #7 다른 날짜 성능 비교 | 낮음 | 중간 | 2h | 🟢 |
| 5 | #3 청크 크기 최적화 | 낮음 | 중간 | 1h | 🟡 |
| 6 | #5 프롬프트 구조 개선 | 낮음 | 중간 | 2h | 🟡 |
| 7 | #9 Shuffle stage 연계 | 높음 | 높음 | 4일 | 🟡 |
| 8 | #8 LLM-as-Judge 평가 | 중간 | 낮음 | 1일 | 🟡 |
| 9 | #6 후처리 통합 레이어 | 중간 | 중간 | 2일 | 🟡 |
| 10 | #1 다른 날짜 검증 | 낮음 | 낮음 | 1h | 🟡 |

### Phase 1: Quick Wins (1일)

**목표**: avg_sources 1.5 → 1.6-1.7

```
Day 1 오전:
- #10 카테고리 Validation 완화 (1h)
- #2 카테고리 오류 해결 (1h)

Day 1 오후:
- #3 청크 크기 실험 (1h)
- #5 프롬프트 구조 개선 (2h)

검증:
- 테스트 실행 → avg_sources 확인
```

### Phase 2: 중기 개선 (1주)

**목표**: avg_sources 1.7-1.8, 안정성 확보

```
Week 1:
- #4 Few-shot 예시 최적화 (3h)
- #7 다른 날짜 성능 비교 (2h)
- #8 LLM-as-Judge 평가 구현 (1일)

검증:
- 5개 날짜로 테스트
- V4 → V6 → V7 성능 비교
```

### Phase 3: 구조적 개선 (2주)

**목표**: avg_sources 1.8-2.0

```
Week 2-3:
- #9 Shuffle stage 연계 (4일)
- #6 후처리 통합 레이어 (2일)

검증:
- 전체 파이프라인 영향 평가
- Reduce/Wrapup 품질 확인
```

---

## Temperature 실험 결과

### 실험 방법
- 2026-04-14 데이터로 각 Temperature 3회 실행
- avg_sources, 이슈 개수, 일관성 측정

### 결과

| Temperature | avg_sources (평균) | 범위 | Issues 범위 | 일관성 | 평가 |
|-------------|-------------------|------|-------------|--------|------|
| 0.0 | 1.34 | 1.23~1.41 | 100~141 | 나쁨 | ❌ |
| 0.1 | (측정 중) | - | - | - | ⏳ |
| 0.2 | **1.57** | 1.52~1.62 | 78~118 | 중간 | ✅ **최적** |
| 0.3 | 1.45 | 1.4~1.5 | 119~133 | 좋음 | ⚠️ |

### 분석

**Temperature 0의 역효과:**
- 보수적 동작 → "확신 없으면 분리" 전략
- 93%가 1:1 매핑 (클러스터링 거의 실패)
- 프롬프트 "공격적 클러스터링" 지침 무시

**Temperature 0.2가 최적:**
- 창의적 통합 가능
- avg_sources 최고 달성 (1.57)
- 적절한 변동성

**Temperature 0.3:**
- 일관성 좋지만 성능 5% 낮음

### 권장 설정

```python
# config.py
MAP_LLM = StageLLMConfig(
    provider="anthropic",
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    temperature=0.2,  # 최적값
)
```

---

## 참고 자료

### 관련 문서
- `docs/ARCHITECTURE.md` - Daily Report 파이프라인 구조
- `docs/spec/daily-report-causal-reasoning.md` - Wrapup V3 개선 사례
- `src/pipelines/daily_report/prompts.py` - 현재 프롬프트 (V6)
- `src/pipelines/daily_report/examples/map_examples.py` - Few-shot 예시

### 코드 위치
- Map stage: `src/pipelines/daily_report/stages/map_stage.py`
- Config: `src/pipelines/daily_report/config.py`
- Models: `src/pipelines/daily_report/models.py`
- Tests: `tests/pipelines/daily_report/test_map_stage.py`

### 평가 스크립트
- Wrapup 평가: `evaluations/evaluate_wrapup.py` (참고용)
- Map 평가 (예정): `evaluations/evaluate_map.py`

---

## 다음 단계

### 즉시 실행
1. ✅ Temperature 0.1 실험 완료 대기
2. ⏳ 결과 분석 후 최종 Temperature 결정
3. ⏳ Phase 1 Quick Wins 실행

### 검토 필요
- Shuffle stage 통합 기능 추가 여부
- 후처리 레이어 vs 프롬프트 개선 우선순위
- 날짜별 평가 범위 (일주일 vs 한 달)

### 추적 메트릭
- avg_sources (목표: ≥1.7)
- 테마 다양성 (목표: 고유 테마 ≤ 이슈 × 1.5)
- 카테고리 검증 성공률 (목표: 100%)
- 처리 시간 (목표: <5분/250메시지)
