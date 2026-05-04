# Wrapup V3: 테마 간 인과관계 추론

**Goal:** Daily report의 Wrapup stage가 테마들을 인과관계 체인으로 엮어서 구조화된 인사이트를 생성하도록 개선

**Status:** Approved (brainstorming 완료)

---

## Problem

Wrapup이 10-15개 테마를 종합할 때 500자+ 텍스트 덩어리를 생성함.
"왜 이게 중요한가", "어떤 경로로 주가에 영향 주는가" 구조화되지 않음.
결국 사용자가 원문을 직접 읽고 인과관계를 판단해야 함.

**현재 Wrapup `key_insights` 출력 (V2):**
```
🔥 AI 슈퍼사이클 vs 매크로 디커플링: VIX 17.8·Fear&Greed 64로 시장 심리 양호하나, 
나스닥 -0.90% 약세는 '선단주 조정'이 아닌 '섹터 로테이션' 신호. 빅테크 AI 투자 실적 
급증(매크로 결별)으로 반도체·AI 인프라는 강세 지속하되..." (500자+)
```

**원하는 Wrapup `key_insights` 출력 (V3):**
```
🔥 AI DC 전력 수요 급증 + 엔비디아 시총 5조 돌파
  → 메모리 반도체 공급 타이트 심화 (가격 70-75% 추가 상승 전망)
  → 삼성·SK 영업이익 역대 최고치 전망

🎯 주목: 메모리 반도체, 전력기기
⚠️ 리스크: 유가 급등(브렌트유 108$) → 인플레이션 재점화
```

## Key Decision

**Reduce는 변경하지 않음.** V2 유지.
- Reduce = 개별 테마 분석 (summary + impact). 현재도 잘 동작.
- Wrapup = 여러 테마를 엮어서 인과관계 체인 생성. **여기가 핵심 변경 대상.**
- 인과관계 체인은 "여러 테마를 연결"하는 것이므로 Wrapup의 역할.

## Changes

### 1. Wrapup 입력 보강 (`wrapup_stage.py`)

**현재:** `summary[:100]`만 전달. 인과관계 재료 전부 사라짐.

**변경:** summary 전체 + impact 전체 + stocks 이름 전달.

```python
# Before
f"{item.emoji} {item.summary[:100]}..."

# After
f"[{item.category}] {item.investment_theme}\n"
f"{item.summary}\n"
f"Impact: {item.impact}\n"
f"종목: {', '.join(s.name for s in item.stocks)}" if item.stocks else ""
```

**토큰 리스크:** 현재 reduce fixture 기준 summary 평균 ~200자, impact ~150자, stocks ~50자. 15개 테마 × 400자 = ~6000자 ≈ ~12K tokens. Haiku 4.5 context window 충분. timeout 180초 내 처리 가능.

### 2. `WRAPUP_SYSTEM_PROMPT_V3` (`prompts.py`)

V2 기존 지시 유지 + 인과관계 체인 포맷 요구 추가:

```
**출력 포맷 (V3):**
- 여러 테마를 인과관계 체인으로 엮어서 3-5개 인사이트 도출
- 포맷:
  이모지 + 첫 번째 테마/현상 (근거 숫자)
    → 연결되는 두 번째 테마/결과
    → 최종 투자 시사점
  🎯 주목: 섹터/종목
  ⚠️ 리스크: 반대 시나리오
- 하나의 인사이트에 2-3개 테마를 엮을 것
- 각 → 연결에 왜 이 관계가 성립하는지 포함
- 2단계로 충분하면 억지로 늘리지 말 것
- 500자 텍스트 덩어리 금지
- 엮을 수 없는 테마는 억지로 연결하지 말 것

**커버리지 규칙:**
- 매크로 인사이트 최소 1개 필수 (VIX, Fear&Greed, 환율 등과 테마 연결)
- 입력된 카테고리별 최소 1개 인사이트에 포함되어야 함
- 커버리지 미달 시 해당 카테고리를 단독 인사이트로 추가

{examples}
```

**`{examples}` placeholder 필수.** `wrapup_stage.py`에서 `.format(examples=...)` 으로 주입. `map_stage.py`의 예시 주입 패턴 참고.

### 3. Few-shot 예시 (`wrapup_examples.py`, 생성)

**좋은 예시 2개:** 3개 테마를 체인으로 엮은 것

예시 1: AI 인프라 테마들 엮기
```
입력 테마: [AI DC 전력 수요], [엔비디아 시총 5조], [HBM 가격 상승]
→ 출력:
🔥 AI DC 전력 수요 급증 + 엔비디아 시총 5조 돌파
  → 메모리 반도체 공급 타이트 심화 (가격 70-75% 추가 상승 전망)
  → 삼성·SK 영업이익 역대 최고치 전망
🎯 주목: 메모리 반도체, 전력기기
⚠️ 리스크: 유가 급등 → 인플레이션 재점화
```

예시 2: 지정학 + 에너지 테마 엮기

**나쁜 예시 1개:** 테마 나열만 한 것 (왜 나쁜지 설명 포함)

### 4. LLM-as-Judge 평가 (`evaluations/evaluate_causal.py`, 생성)

**Judge 모델:** Anthropic Sonnet 4.5 (생성 Haiku 4.5와 다른 티어)

**5개 차원 (0-2점, 총 0-10점):**

| 차원 | 0점 | 1점 | 2점 |
|------|-----|-----|-----|
| chain_presence | 체인(→) 없음 | 1단계만 | 2단계+ |
| chain_validity | 논리적 비약 | 일부 연결 약함 | 모든 연결 타당 |
| actionability | 투자 시사점 없음 | 모호한 시사점 | 구체적 섹터/종목 |
| data_grounding | 숫자/팩트 없음 | 일부 포함 | 충분히 포함 |
| conciseness | 500자+ 덩어리 | 구조 있지만 장황 | 구조화 + 간결 |

**평가 격리 (Codex 리뷰 반영):**
- Full pipeline이 아니라 **reduce fixture를 고정 입력으로** 사용
- `tests/pipelines/daily_report/fixtures/stage_outputs/reduce_*.json` 최신으로 1회 갱신 후 고정
- 동일 reduce 출력 → V2 Wrapup / V3 Wrapup → Judge 채점
- 이렇게 해야 map/shuffle/reduce 변동성 없이 Wrapup만 순수 비교 가능

**실행:**
- 3일분 reduce fixture
- 3회 실행 평균
- 목표: V3 평균 7점 이상 (V2 예상 3-4점)

### 5. 롤백 전략

자동 롤백 없음 (개인 도구). 문제 시 `wrapup_stage.py`에서 import를 `_V2`로 수동 변경.

## Codex 리뷰 결과 (2회)

### 1차 리뷰 (Spec 대상, 12개 지적)
- stages가 V2 직접 import → **반영: wrapup_stage.py import 변경**
- summary[:100] 잘림 → **반영: 전체 전달**
- 기존 evaluations/ 재사용 → **반영**

### 2차 리뷰 (설계 대상, Critical 3 + High 5)
- few-shot `.format()` 주입 경로 없음 → **반영: wrapup_stage.py에 examples 주입 코드 추가**
- 자동 롤백 구현 불가 → **반영: 자동 롤백 제거, 수동 변경**
- 평가가 Wrapup 성능 격리 못함 → **반영: reduce fixture 고정 입력 사용**
- 토큰 리스크 → **확인: 15테마 × 400자 ≈ 12K tokens, Haiku context 충분**

## Files Changed

| 파일 | 변경 |
|------|------|
| `src/pipelines/daily_report/prompts.py` | `WRAPUP_SYSTEM_PROMPT_V3` + `WRAPUP_USER_PROMPT_V3` 추가 |
| `src/pipelines/daily_report/stages/wrapup_stage.py` | import V3 + 입력 포맷 보강 + examples 주입 |
| `src/pipelines/daily_report/examples/wrapup_examples.py` | 생성 (좋은 2 + 나쁜 1) |
| `src/pipelines/daily_report/models.py` | `DailyReport`에 `category_insights` 필드 추가 + `CategoryInsightsList` 모델 |
| `evaluations/evaluate_causal.py` | 생성 (Judge 로직, 기존 evaluations/ 확장) |

### 6. 모델 변경: `category_insights` 추가 (`models.py`)

`DailyReport`에 카테고리별 인사이트 필드 추가:

```python
class CategoryInsightsList(BaseModel):
    """Wrapup stage의 카테고리별 인사이트 래퍼."""
    insights: dict[str, str] = Field(
        description="카테고리 → 인사이트 매핑. 예: {'반도체': 'HBM 가격 상승 + 엔비디아 독점 완화 → 국내 메모리 수혜'}"
    )

class DailyReport(BaseModel):
    date: str
    macro: MacroSnapshot
    key_insights: list[str]  # 시장 전체 큰 그림 (테마 간 인과관계)
    category_insights: dict[str, str] = Field(default_factory=dict)  # 카테고리별 인사이트
    news: list[NewsItem]
```

**Wrapup LLM이 2가지를 생성:**
1. `key_insights`: 시장 전체 큰 그림 (3-5개, 카테고리 넘나드는 인과관계)
2. `category_insights`: 입력된 카테고리별 1개씩 (같은 카테고리 내 테마 연결)

**리포트 렌더링:**
```markdown
## Key Insights
🔥 AI DC 전력 → HBM 수요 → 반도체 업사이클
🌊 지정학 리스크 → 유가 급등 → 방산 수혜

## 반도체
> HBM 가격 상승 + 엔비디아 독점 완화 → 국내 메모리 수혜 확대

### 🚀 GPU 공급망 다변화 가속...  (기존 Reduce 출력)
### 🚀 AGI 시대 임박...
```

## Files NOT Changed

- `reduce_stage.py` — Reduce V2 유지
- `config.py` — LLM 설정 변경 없음

## Success Criteria

- V3 Judge 평균 점수 7점 이상 (V2 대비 +3점 이상)
- 500자 텍스트 덩어리 0건
- 인과관계 체인(→) 포함 인사이트 비율 80% 이상
- 기존 테스트 깨지지 않음
- 리포트 3-5일 실전 사용 시 "원문 안 봐도 됨" 체감
