# Map Stage Prompt Evaluation

Daily report pipeline의 Map stage 프롬프트 품질을 체계적으로 측정하고 개선하기 위한 평가 시스템입니다.

## 개요

### 목적
- 프롬프트 변경사항의 영향을 정량적으로 측정
- 버전 간 비교를 통한 회귀 방지
- 데이터 기반 프롬프트 엔지니어링

### 평가 방식
1. **Rule-based Metrics**: 빠르고 무료, 기본 품질 측정
2. **LLM-as-Judge**: 의미적 유사도 평가 (선택적)

---

## Quick Start

### 1. 로컬 평가 (빠른 테스트)

```bash
# 기본 평가 (규칙 기반만)
uv run python evaluations/evaluate_map.py

# LLM-as-Judge 포함
uv run python evaluations/evaluate_map.py --use-llm-judge

# 특정 프롬프트 버전 평가
uv run python evaluations/evaluate_map.py --prompt-version v3
```

**결과:**
- 콘솔에 요약 출력
- `evaluations/results/` 디렉토리에 JSON 저장

### 2. LangSmith 평가 (실험 추적)

```bash
# 환경 변수 설정
export LANGSMITH_API_KEY=...
export LANGSMITH_PROJECT=invest-jarvis

# 데이터셋 생성 (최초 1회만)
uv run python evaluations/langsmith_eval.py --create-dataset

# 평가 실행
uv run python evaluations/langsmith_eval.py --experiment v4_category_field

# 결과를 LangSmith UI에서 확인
```

**장점:**
- 실험 간 비교 UI
- 시계열 성능 추적
- 팀 공유 가능

---

## 평가 메트릭

### Rule-based Metrics

| 메트릭 | 설명 | 범위 | 목표 |
|--------|------|------|------|
| `split_accuracy` | 예상 이슈 개수 범위 일치 여부 | 0.0~1.0 | ≥ 0.8 |
| `must_split_check` | 분리 필수 메시지 검증 | 0.0/1.0 | 1.0 |
| `number_preservation` | 원문 숫자 보존율 | 0.0~1.0 | ≥ 0.8 |
| `company_preservation` | 기업명 보존율 | 0.0~1.0 | ≥ 0.8 |
| `keyword_coverage` | 키워드 커버리지 | 0.0~1.0 | ≥ 0.8 |
| `theme_relevance` | 테마 적절성 (부분 매칭) | 0.0~1.0 | ≥ 0.7 |
| `category_accuracy` | 카테고리 정확도 (Jaccard) | 0.0~1.0 | ≥ 0.8 |

### LLM-as-Judge Metrics

| 메트릭 | 설명 | 모델 | 비용 |
|--------|------|------|------|
| `theme_relevance_llm` | 테마 의미적 유사도 | Claude Haiku 4.5 | ~$0.01/case |

---

## 테스트 케이스 구조

### 파일 위치
`evaluations/datasets/test_cases.json`

### 필드 설명

```json
{
  "id": "case_001",
  "name": "복합_메시지_테슬라_오라클",
  "input": "텔레그램 메시지 텍스트...",
  "expected": {
    "num_issues_min": 2,           // 최소 이슈 개수
    "num_issues_max": 2,           // 최대 이슈 개수
    "must_split": true,            // 분리 필수 여부
    "must_preserve_numbers": [     // 보존해야 할 숫자들
      "10%", "5.6%"
    ],
    "must_preserve_companies": [   // 보존해야 할 기업명들
      "테슬라", "오라클"
    ],
    "expected_category": "반도체", // 단일 또는 ["반도체", "바이오"]
    "expected_themes": [           // 예상 테마들 (의미적 매칭)
      "전기차 수요 둔화",
      "AI 전력"
    ],
    "expected_keywords": [         // 포함되어야 할 키워드
      "테슬라", "인력 감축", "데이터센터"
    ]
  }
}
```

### 새 테스트 케이스 추가

1. `test_cases.json`에 새 케이스 추가
2. `id`는 고유하게 (`case_XXX` 또는 `case_csv_XXX`)
3. `expected` 필드 모두 명시 (일관성)
4. 로컬 평가로 검증:
   ```bash
   uv run python evaluations/evaluate_map.py
   ```

---

## 프롬프트 버전 관리

### 프롬프트 위치
`src/pipelines/daily_report/prompts.py`

### 버전 명명 규칙
```python
MAP_SYSTEM_PROMPT_V1 = """..."""  # 기본 클러스터링
MAP_SYSTEM_PROMPT_V2 = """..."""  # 데이터 보존 강조
MAP_SYSTEM_PROMPT_V3 = """..."""  # 테마 작명법 개선
MAP_SYSTEM_PROMPT_V4 = """..."""  # 카테고리 필드 추가

MAP_SYSTEM_PROMPT = MAP_SYSTEM_PROMPT_V4  # 현재 활성 버전
```

### 프롬프트 변경 워크플로우

1. **새 버전 작성**
   ```python
   MAP_SYSTEM_PROMPT_V5 = """새 프롬프트..."""
   ```

2. **평가 실행**
   ```bash
   # V4 baseline
   uv run python evaluations/langsmith_eval.py --experiment v4_baseline
   
   # V5 테스트 (코드에서 MAP_SYSTEM_PROMPT = V5로 변경 후)
   uv run python evaluations/langsmith_eval.py --experiment v5_test
   ```

3. **결과 비교**
   - LangSmith UI에서 두 실험 비교
   - 모든 메트릭이 ≥ baseline이면 승인

4. **커밋**
   ```bash
   git add src/pipelines/daily_report/prompts.py
   git add evaluations/results/v5_test_*.json
   git commit -m "feat(prompt): MAP_SYSTEM_PROMPT V5 - 성능 개선"
   ```

---

## 고급 사용법

### 특정 테스트 케이스만 실행

```python
# evaluate_map.py 수정
test_cases = load_test_cases()
filtered = [tc for tc in test_cases if tc["id"] == "case_001"]
```

### 커스텀 메트릭 추가

1. `evaluations/metrics.py`에 함수 작성:
   ```python
   def my_metric(issues: List[MappedIssue], expected: Dict[str, Any]) -> float:
       # 로직 구현
       return score  # 0.0 ~ 1.0
   ```

2. `RULE_BASED_METRICS`에 등록:
   ```python
   RULE_BASED_METRICS = {
       # ...
       "my_metric": my_metric,
   }
   ```

3. 테스트 케이스에 예상값 추가 (필요시)

### LangSmith 실험 태그 활용

```python
# langsmith_eval.py
client.create_project(
    project_name="invest-jarvis",
    tags=["prompt-v5", "category-field", "production"]
)
```

---

## 문제 해결

### "LANGSMITH_API_KEY not found"
```bash
export LANGSMITH_API_KEY=your_key
export LANGSMITH_PROJECT=invest-jarvis
```

### 테스트 케이스 검증 실패
```bash
# JSON 문법 확인
python -c "import json; json.load(open('evaluations/datasets/test_cases.json'))"

# 스키마 검증 (TODO: 스크립트 추가 예정)
```

### LLM-as-Judge 비용 우려
- 로컬 평가 시 `--use-llm-judge` 생략 (규칙 기반만 사용)
- 또는 테스트 케이스 수를 줄임

---

## 아키텍처

```
evaluations/
├── metrics.py               # 메트릭 함수 (규칙 기반 + LLM)
├── evaluate_map.py          # 로컬 평가 스크립트
├── langsmith_eval.py        # LangSmith 연동 스크립트
├── datasets/
│   └── test_cases.json      # 평가 케이스
└── results/                 # 평가 결과 JSON (git에 포함)
    └── v4_baseline_*.json
```

**설계 원칙:**
- `metrics.py`: 순수 함수, 의존성 최소화
- 평가 스크립트: 오케스트레이션 + I/O만
- 테스트 케이스: JSON (비개발자도 기여 가능)

---

## 참고 자료

- [LangSmith 문서](https://docs.smith.langchain.com/)
- [프롬프트 엔지니어링 가이드](https://www.promptingguide.ai/)
- 설계 스펙: `docs/superpowers/specs/2026-04-17-category-field-design.md`
