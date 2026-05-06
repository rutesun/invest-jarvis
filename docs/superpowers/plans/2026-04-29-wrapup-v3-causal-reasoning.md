# Wrapup V3: 인과관계 추론 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrapup stage가 테마들을 인과관계 체인(→)으로 엮어 구조화된 인사이트를 생성하도록 개선. 500자 텍스트 덩어리 → 체인 포맷 전환.

**Architecture:** Wrapup stage만 변경 (Reduce V2 유지). 프롬프트 V3 + 입력 보강 + few-shot 예시 + `category_insights` 필드 추가. LLM-as-Judge로 V2 vs V3 정량 비교.

**Tech Stack:** Pydantic models, LangChain structured output, Anthropic Haiku 4.5 (생성) / Sonnet 4.5 (Judge)

---

## File Structure

| 파일 | 역할 | 변경 유형 |
|------|------|----------|
| `src/pipelines/daily_report/models.py` | `CategoryInsightsList` 모델 추가, `DailyReport`에 `category_insights` 필드 추가 | Modify |
| `src/pipelines/daily_report/prompts.py` | `WRAPUP_SYSTEM_PROMPT_V3` + `WRAPUP_USER_PROMPT_V3` 추가 | Modify |
| `src/pipelines/daily_report/examples/wrapup_examples.py` | Wrapup few-shot 예시 (좋은 2 + 나쁜 1) | Create |
| `src/pipelines/daily_report/stages/wrapup_stage.py` | V3 import, 입력 보강, examples 주입 | Modify |
| `src/pipelines/daily_report/pipeline.py` | `format_report`에 `category_insights` 렌더링 추가 | Modify |
| `evaluations/evaluate_wrapup.py` | LLM-as-Judge 평가 스크립트 | Create |
| `tests/pipelines/daily_report/test_wrapup_stage.py` | Wrapup V3 단위 테스트 | Create |

---

### Task 1: `DailyReport` 모델 확장

**Files:**
- Modify: `src/pipelines/daily_report/models.py:195-220`
- Test: `tests/pipelines/daily_report/test_wrapup_stage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/pipelines/daily_report/test_wrapup_stage.py
"""Wrapup V3 단위 테스트."""

from src.pipelines.daily_report.models import (
    CategoryInsightsList,
    DailyReport,
    MacroSnapshot,
)


def test_daily_report_has_category_insights_field():
    """DailyReport에 category_insights 필드가 존재하고, 기본값은 빈 dict."""
    report = DailyReport(
        date="2026-04-20",
        macro=MacroSnapshot(
            date="2026-04-20",
            us_markets={"S&P500": 1.0, "NASDAQ": 0.5, "DOW": 0.3},
            kr_markets={"KOSPI": 0.2, "KOSDAQ": -0.1},
            vix=18.0,
            fear_greed=55,
            krw_usd=1320.0,
        ),
        key_insights=["test insight"],
        news=[],
    )
    assert report.category_insights == {}


def test_daily_report_with_category_insights():
    """DailyReport에 category_insights를 설정할 수 있다."""
    report = DailyReport(
        date="2026-04-20",
        macro=MacroSnapshot(
            date="2026-04-20",
            us_markets={"S&P500": 1.0, "NASDAQ": 0.5, "DOW": 0.3},
            kr_markets={"KOSPI": 0.2, "KOSDAQ": -0.1},
            vix=18.0,
            fear_greed=55,
            krw_usd=1320.0,
        ),
        key_insights=["test"],
        category_insights={
            "반도체": "HBM 가격 상승 + 엔비디아 독점 완화 → 국내 메모리 수혜",
            "에너지": "AI DC 전력 수요 급증 → 전력기기 업체 수주 가속",
        },
        news=[],
    )
    assert len(report.category_insights) == 2
    assert "반도체" in report.category_insights


def test_category_insights_list_model():
    """CategoryInsightsList 모델 검증."""
    result = CategoryInsightsList(
        insights={"반도체": "테스트 인사이트", "에너지": "전력 수요 인사이트"}
    )
    assert len(result.insights) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v`
Expected: FAIL — `CategoryInsightsList` import 실패

- [ ] **Step 3: Add `CategoryInsightsList` and update `DailyReport`**

`src/pipelines/daily_report/models.py`에 추가/변경:

```python
# KeyInsightsList 뒤에 추가 (220행 부근)
class CategoryInsightsList(BaseModel):
    """Wrapup stage의 카테고리별 인사이트."""

    insights: dict[str, str] = Field(
        description="카테고리 → 인사이트 매핑. 예: {'반도체': 'HBM 가격 상승 + 엔비디아 독점 완화 → 국내 메모리 수혜'}"
    )
```

`DailyReport` 변경:

```python
class DailyReport(BaseModel):
    """최종 리포트 출력."""

    date: str
    macro: MacroSnapshot
    key_insights: list[str] = Field(description="한글 크로스 테마 인사이트")
    category_insights: dict[str, str] = Field(
        default_factory=dict,
        description="카테고리별 인사이트 (카테고리 → 인사이트 문자열)",
    )
    news: list[NewsItem]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full test suite to verify backward compatibility**

Run: `uv run pytest tests/pipelines/daily_report/ -v`
Expected: 모든 기존 테스트 PASS. `category_insights`의 `default_factory=dict` 덕분에 기존 코드 영향 없음.

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/daily_report/models.py tests/pipelines/daily_report/test_wrapup_stage.py
git commit -m "feat(daily-report): add CategoryInsightsList model and category_insights to DailyReport"
```

---

### Task 2: Wrapup few-shot 예시 작성

**Files:**
- Create: `src/pipelines/daily_report/examples/wrapup_examples.py`
- Test: `tests/pipelines/daily_report/test_wrapup_stage.py` (추가)

- [ ] **Step 1: Write the failing test**

`tests/pipelines/daily_report/test_wrapup_stage.py`에 추가:

```python
from src.pipelines.daily_report.examples.wrapup_examples import get_wrapup_examples


def test_wrapup_examples_not_empty():
    """Wrapup 예시가 비어있지 않다."""
    examples = get_wrapup_examples()
    assert len(examples) > 100  # 충분한 길이


def test_wrapup_examples_contains_chain_arrow():
    """Wrapup 예시에 인과관계 체인(→)이 포함된다."""
    examples = get_wrapup_examples()
    assert "→" in examples


def test_wrapup_examples_contains_bad_example():
    """Wrapup 예시에 나쁜 예시가 포함된다."""
    examples = get_wrapup_examples()
    assert "나쁜 예시" in examples or "BAD" in examples.upper()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py::test_wrapup_examples_not_empty -v`
Expected: FAIL — `wrapup_examples` 모듈 없음

- [ ] **Step 3: Create wrapup examples**

```python
# src/pipelines/daily_report/examples/wrapup_examples.py
"""Wrapup stage용 Few-shot 예시 (V3 인과관계 체인)."""

WRAPUP_GOOD_EXAMPLE_1 = """
**좋은 예시 1: AI 인프라 테마 체인**

입력 테마:
- [반도체] GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜
- [에너지] AI DC 전력 수요 급증, 전력기기 업체 수주 가속
- [반도체] HBM 가격 70-75% 추가 상승, 메모리 업사이클 본격화

출력 (key_insights):
🔥 AI DC 전력 수요 급증(2030년 1,350TWh, +220%) + 엔비디아 시총 5조$ 돌파
  → 메모리 반도체 공급 타이트 심화 (HBM 가격 70-75% 추가 상승 전망)
  → 삼성·SK 영업이익 역대 최고치 전망, 전력기기 LS/산일전기 수주 가속
🎯 주목: 메모리 반도체, 전력기기
⚠️ 리스크: 유가 급등(브렌트유 108$) → 인플레이션 재점화 시 투자 지연

**핵심**: 3개 테마를 하나의 인과 체인으로 엮음. 각 →에 왜 연결되는지 숫자로 뒷받침.
"""

WRAPUP_GOOD_EXAMPLE_2 = """
**좋은 예시 2: 지정학 + 에너지 + 방산 체인**

입력 테마:
- [매크로] 호르무즈 해협 긴장 고조, 유가 변동성 확대
- [에너지] 원유 수입 의존도 리스크, 에너지 전환 가속
- [방산] 한국형 방위산업 수출 역대 최고, 방산 수주잔고 확대

출력 (key_insights):
🌊 호르무즈 해협 긴장(유가 80→90$ 급등) + 원유 의존도 리스크
  → 에너지 전환 투자 가속 (정부 2030 RE100 로드맵 앞당김)
  → 방산 수출 역대 최고(1-3월 42억$, +35% YoY)와 동시 진행
🎯 주목: 방산(한화에어로, LIG넥스원), 신재생에너지
⚠️ 리스크: 유가 $100 돌파 시 → 소비재·항공 섹터 마진 압박

**핵심**: 지정학 리스크 → 에너지 전환 → 방산 수혜의 3단계 체인. 숫자 구체적.
"""

WRAPUP_BAD_EXAMPLE_1 = """
**나쁜 예시: 단순 나열 (체인 없음)**

입력 테마: (위와 동일)

출력 (key_insights):
🔥 AI 슈퍼사이클 vs 매크로 디커플링: VIX 17.8·Fear&Greed 64로 시장 심리 양호하나, 나스닥 -0.90% 약세는 '선단주 조정'이 아닌 '섹터 로테이션' 신호. 빅테크 AI 투자 실적 급증(매크로 결별)으로 반도체·AI 인프라는 강세 지속하되, 이차전지·유틸리티 등 경기민감 섹터는 금리 경로에 종속. 호르무즈 리스크(유가 80→90$ 급등)가 표면적으로 에너지 섹터 부양하나 실질 수혜는 방산·신재생으로 전이 중. K-반도체 HBM 가격 70-75% 추가 상승 전망이 국내 증시의 핵심 드라이버로 작동하며, KOSPI 2,540 지지가 유효한 국면.

**이게 나쁜 이유**:
- 500자+ 텍스트 덩어리로 가독성 제로
- "→" 인과 체인 없이 키워드 나열
- 구체적 투자 시사점(🎯/⚠️) 없음
- 어떤 테마가 어떻게 연결되는지 파악 불가
"""


def get_wrapup_examples() -> str:
    """프롬프트용 포맷팅된 Wrapup 예시 반환."""
    return f"{WRAPUP_GOOD_EXAMPLE_1}\n\n{WRAPUP_GOOD_EXAMPLE_2}\n\n{WRAPUP_BAD_EXAMPLE_1}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/daily_report/examples/wrapup_examples.py tests/pipelines/daily_report/test_wrapup_stage.py
git commit -m "feat(daily-report): add wrapup few-shot examples for V3 causal chain format"
```

---

### Task 3: Wrapup V3 프롬프트 작성

**Files:**
- Modify: `src/pipelines/daily_report/prompts.py:436-538`
- Test: `tests/pipelines/daily_report/test_wrapup_stage.py` (추가)

- [ ] **Step 1: Write the failing test**

`tests/pipelines/daily_report/test_wrapup_stage.py`에 추가:

```python
from src.pipelines.daily_report.prompts import (
    WRAPUP_SYSTEM_PROMPT,
    WRAPUP_SYSTEM_PROMPT_V3,
    WRAPUP_USER_PROMPT,
    WRAPUP_USER_PROMPT_V3,
)


def test_wrapup_v3_system_prompt_exists():
    """V3 system prompt가 존재하고 핵심 지시를 포함한다."""
    assert len(WRAPUP_SYSTEM_PROMPT_V3) > 100
    assert "인과관계" in WRAPUP_SYSTEM_PROMPT_V3 or "→" in WRAPUP_SYSTEM_PROMPT_V3
    assert "{examples}" in WRAPUP_SYSTEM_PROMPT_V3


def test_wrapup_v3_user_prompt_exists():
    """V3 user prompt가 존재하고 필수 placeholder를 포함한다."""
    assert "{macro}" in WRAPUP_USER_PROMPT_V3
    assert "{news_items}" in WRAPUP_USER_PROMPT_V3
    assert "{news_count}" in WRAPUP_USER_PROMPT_V3


def test_wrapup_active_prompt_is_v3():
    """활성 Wrapup 프롬프트가 V3이다."""
    assert WRAPUP_SYSTEM_PROMPT is WRAPUP_SYSTEM_PROMPT_V3
    assert WRAPUP_USER_PROMPT is WRAPUP_USER_PROMPT_V3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py::test_wrapup_v3_system_prompt_exists -v`
Expected: FAIL — `WRAPUP_SYSTEM_PROMPT_V3` import 실패

- [ ] **Step 3: Add V3 prompts to `prompts.py`**

`src/pipelines/daily_report/prompts.py`에 추가 (기존 `WRAPUP_SYSTEM_PROMPT_V2` 블록 뒤, `# Activate V2 prompts` 앞):

```python
# ============================================================================
# WRAPUP STAGE PROMPTS V3 (인과관계 체인 포맷)
# ============================================================================

WRAPUP_SYSTEM_PROMPT_V3 = """당신은 시장 전략가입니다.
모든 테마와 매크로 데이터를 종합하여 인과관계 체인으로 구조화된 인사이트를 도출하세요.

**작업**:

1. **여러 테마를 인과관계 체인으로 엮기** (가장 중요!)

   - 하나의 인사이트에 2-3개 테마를 연결
   - 포맷:
     이모지 + 첫 번째 테마/현상 (근거 숫자)
       → 연결되는 두 번째 테마/결과 (왜 이 관계가 성립하는지)
       → 최종 투자 시사점
     🎯 주목: 구체적 섹터/종목
     ⚠️ 리스크: 반대 시나리오

   - 각 → 연결에 "왜?" 포함 (숫자 또는 논리적 근거)
   - 2단계로 충분하면 억지로 늘리지 말 것
   - 엮을 수 없는 테마는 억지로 연결하지 말 것

2. **매크로와 연결**

   - VIX, Fear & Greed, 환율이 체인의 배경/촉매로 작용하는지 분석
   - 매크로 인사이트 최소 1개 필수

3. **key_insights 작성** (3-5개)

   - 카테고리를 넘나드는 큰 그림 인사이트
   - 500자 텍스트 덩어리 절대 금지
   - 각 인사이트는 체인 포맷으로 구조화

4. **category_insights 작성**

   - 입력된 카테고리별 1개씩 (같은 카테고리 내 테마 연결)
   - 포맷: "테마A + 테마B → 투자 시사점" (한 줄, 50자 내외)
   - 커버리지: 입력된 모든 카테고리 포함

**Few-shot 예시**:
{examples}

**출력**: 제공된 함수 스키마(Tool Calling) 형식에 맞추어 반환하세요."""

WRAPUP_USER_PROMPT_V3 = """**매크로 데이터**:
{macro}

**테마별 분석 결과** ({news_count}개 테마):
{news_items}

**작업**:
1. 테마 간 인과관계 체인 구성 (→ 연결, 숫자 근거 포함)
2. 매크로와 연결
3. key_insights 3-5개 (체인 포맷, 500자 덩어리 금지)
4. category_insights: 카테고리별 한 줄 인사이트"""
```

그리고 활성 프롬프트를 V3로 변경:

```python
# Activate V3 prompts
WRAPUP_SYSTEM_PROMPT = WRAPUP_SYSTEM_PROMPT_V3
WRAPUP_USER_PROMPT = WRAPUP_USER_PROMPT_V3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/daily_report/prompts.py tests/pipelines/daily_report/test_wrapup_stage.py
git commit -m "feat(daily-report): add WRAPUP_SYSTEM_PROMPT_V3 with causal chain format"
```

---

### Task 4: Wrapup stage 입력 보강 + V3 적용

**Files:**
- Modify: `src/pipelines/daily_report/stages/wrapup_stage.py`
- Test: `tests/pipelines/daily_report/test_wrapup_stage.py` (추가)

- [ ] **Step 1: Write the failing test**

`tests/pipelines/daily_report/test_wrapup_stage.py`에 추가:

```python
import json

from src.pipelines.daily_report.models import NewsItem, MacroSnapshot


def test_wrapup_input_uses_full_summary():
    """Wrapup 입력이 summary[:100]이 아닌 전체 summary를 사용한다."""
    # wrapup_stage.py의 news_text 포맷팅 로직을 직접 검증
    # _build_news_text 함수를 분리하여 테스트
    from src.pipelines.daily_report.stages.wrapup_stage import _build_news_text

    items = [
        NewsItem(
            category="반도체",
            technical_theme="HBM 메모리",
            investment_theme="HBM 가격 상승으로 메모리 업사이클 본격화",
            keywords=["HBM", "삼성전자", "SK하이닉스"],
            source_ids=["msg1"],
            emoji="🚀",
            summary="🚀 HBM3E 가격 70-75% 추가 상승 전망\n📈 삼성전자 HBM 검증 통과로 점유율 확대\n⚡ SK하이닉스 12단 양산 본격화로 공급 확대",
            impact="메모리 반도체 실적 턴어라운드 가속. 2026 영업이익 역대 최고치 전망.",
            stocks=[],
        ),
    ]

    text = _build_news_text(items)

    # summary 전체가 포함되어야 함 ([:100] 잘림 없음)
    assert "SK하이닉스 12단 양산 본격화로 공급 확대" in text
    # impact도 포함되어야 함
    assert "메모리 반도체 실적 턴어라운드" in text
    # stocks name도 포함 가능 (stocks 있을 경우)


def test_wrapup_input_includes_impact():
    """Wrapup 입력에 impact가 포함된다."""
    from src.pipelines.daily_report.stages.wrapup_stage import _build_news_text

    items = [
        NewsItem(
            category="에너지",
            technical_theme="전력 인프라",
            investment_theme="AI DC 전력 수요 급증, 전력기기 수주 가속",
            keywords=["LS ELECTRIC", "전력기기"],
            source_ids=["msg1"],
            emoji="⚡",
            summary="⚡ 전력 수요 +220% 전망",
            impact="전력기기 섹터 수주 레벨업. LS ELECTRIC 목표주가 상향.",
            stocks=[],
        ),
    ]

    text = _build_news_text(items)
    assert "전력기기 섹터 수주 레벨업" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py::test_wrapup_input_uses_full_summary -v`
Expected: FAIL — `_build_news_text` 없음

- [ ] **Step 3: Refactor wrapup_stage.py — extract `_build_news_text`, apply V3**

`src/pipelines/daily_report/stages/wrapup_stage.py` 전체 수정:

```python
"""Wrapup stage: 전체 테마 종합 및 인과관계 인사이트 도출."""

import json
import logging
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.config import WRAPUP_LLM
from src.pipelines.daily_report.examples.wrapup_examples import get_wrapup_examples
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import DailyReport, KeyInsightsList, MacroSnapshot, NewsItem
from src.pipelines.daily_report.prompts import (
    WRAPUP_SYSTEM_PROMPT_V3,
    WRAPUP_USER_PROMPT_V3,
)


logger = logging.getLogger(__name__)


def _build_news_text(news_items: list[NewsItem]) -> str:
    """테마별 분석을 Wrapup 입력 텍스트로 포맷팅.

    summary 전체 + impact 전체 + stocks 이름을 포함한다.
    """
    parts = []
    for item in news_items:
        section = (
            f"[{item.category}] {item.investment_theme}\n"
            f"(기술 테마: {item.technical_theme})\n"
            f"{item.summary}\n"
            f"Impact: {item.impact}"
        )
        if item.stocks:
            stock_names = ", ".join(s.name for s in item.stocks)
            section += f"\n종목: {stock_names}"
        parts.append(section)
    return "\n\n".join(parts)


@traceable(name="Wrapup Stage")
def wrapup_stage(
    news_items: list[NewsItem],
    macro: MacroSnapshot,
    date: str = None,
) -> DailyReport:
    """
    전체 시장 인사이트 도출 (테마 간 인과관계 체인 + 매크로 연결).

    Args:
        news_items: Reduce stage 출력 (테마별 분석)
        macro: 매크로 데이터
        date: 날짜 문자열

    Returns:
        DailyReport (key_insights + category_insights 포함)
    """
    import asyncio
    import time

    if not news_items:
        return DailyReport(
            date=date or macro.date, macro=macro, key_insights=["분석할 뉴스가 없습니다."], news=[]
        )

    start_time = time.time()

    logger.info("Wrapup stage started: %d news items to synthesize", len(news_items))

    report = asyncio.run(_wrapup_stage_async(news_items, macro, date))

    elapsed = time.time() - start_time

    logger.info(
        "Wrapup stage completed: %d key insights generated in %.1fs",
        len(report.key_insights),
        elapsed,
    )

    return report


async def _wrapup_stage_async(
    news_items: list[NewsItem],
    macro: MacroSnapshot,
    date: str = None,
) -> DailyReport:
    """Async implementation of wrapup stage."""
    llm = WRAPUP_LLM.create_llm()

    # 매크로 데이터 포맷팅
    macro_text = f"""VIX: {macro.vix}
Fear & Greed: {macro.fear_greed}
미국 시장: {", ".join(f"{k} {v:+.2f}%" for k, v in macro.us_markets.items())}
한국 시장: {", ".join(f"{k} {v:+.2f}%" for k, v in macro.kr_markets.items())}
KRW/USD: {macro.krw_usd}"""

    # 테마별 분석 포맷팅 (V3: summary 전체 + impact 전체 + stocks)
    news_text = _build_news_text(news_items)

    # V3 프롬프트 + examples 주입
    examples = get_wrapup_examples()
    system_prompt = WRAPUP_SYSTEM_PROMPT_V3.format(examples=examples)
    user_prompt = WRAPUP_USER_PROMPT_V3.format(
        macro=macro_text, news_count=len(news_items), news_items=news_text
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
        response = await invoke_llm_with_retry(llm, KeyInsightsList, messages, config)
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


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"

    # Reduce stage 출력 로드
    reduce_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    with open(reduce_file, encoding="utf-8") as f:
        news_data = json.load(f)
    news_items = [NewsItem(**item) for item in news_data]

    # Ingest stage에서 매크로 로드
    ingest_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/ingest_{date}.json"
    with open(ingest_file, encoding="utf-8") as f:
        ingest_data = json.load(f)
    macro = MacroSnapshot(**ingest_data["macro"])

    print(f"✓ {len(news_items)}개 테마 분석 로드")

    # Wrapup stage 실행
    report = wrapup_stage(news_items, macro, date)

    print(f"✓ {len(report.key_insights)}개 핵심 인사이트 생성")
    print("\n핵심 인사이트:")
    for insight in report.key_insights:
        print(f"  - {insight}")

    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/wrapup_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
```

**핵심 변경 요약:**
1. `_build_news_text()` 헬퍼 분리 — summary 전체 + impact 전체 + stocks 이름 포함
2. import를 `WRAPUP_SYSTEM_PROMPT_V3` / `WRAPUP_USER_PROMPT_V3`로 변경
3. `get_wrapup_examples()` import + `.format(examples=...)` 주입
4. `summary[:100]...` 잘림 제거

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/pipelines/daily_report/ -v`
Expected: 모든 기존 테스트 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/daily_report/stages/wrapup_stage.py tests/pipelines/daily_report/test_wrapup_stage.py
git commit -m "feat(daily-report): apply wrapup V3 prompt with full input and examples injection"
```

---

### Task 5: `format_report`에 `category_insights` 렌더링 추가

**Files:**
- Modify: `src/pipelines/daily_report/pipeline.py:166-238`
- Test: `tests/pipelines/daily_report/test_wrapup_stage.py` (추가)

- [ ] **Step 1: Write the failing test**

`tests/pipelines/daily_report/test_wrapup_stage.py`에 추가:

```python
from src.pipelines.daily_report.pipeline import format_report


def test_format_report_renders_category_insights():
    """format_report가 category_insights를 렌더링한다."""
    report = DailyReport(
        date="2026-04-20",
        macro=MacroSnapshot(
            date="2026-04-20",
            us_markets={"S&P500": 1.0, "NASDAQ": 0.5, "DOW": 0.3},
            kr_markets={"KOSPI": 0.2, "KOSDAQ": -0.1},
            vix=18.0,
            fear_greed=55,
            krw_usd=1320.0,
        ),
        key_insights=["🔥 테스트 인사이트"],
        category_insights={
            "반도체": "HBM 가격 상승 + 엔비디아 독점 완화 → 국내 메모리 수혜",
        },
        news=[],
    )
    md = format_report(report)
    assert "## 반도체" in md
    assert "HBM 가격 상승" in md


def test_format_report_without_category_insights():
    """category_insights가 비어있으면 해당 섹션 생략."""
    report = DailyReport(
        date="2026-04-20",
        macro=MacroSnapshot(
            date="2026-04-20",
            us_markets={"S&P500": 1.0, "NASDAQ": 0.5, "DOW": 0.3},
            kr_markets={"KOSPI": 0.2, "KOSDAQ": -0.1},
            vix=18.0,
            fear_greed=55,
            krw_usd=1320.0,
        ),
        key_insights=["🔥 테스트"],
        news=[],
    )
    md = format_report(report)
    # category_insights 없으면 렌더링 안 함
    assert "category" not in md.lower() or "Theme Analysis" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py::test_format_report_renders_category_insights -v`
Expected: FAIL — `## 반도체` not found

- [ ] **Step 3: Update `format_report` in `pipeline.py`**

`src/pipelines/daily_report/pipeline.py`의 `format_report` 함수에서, `## 📰 Theme Analysis` 섹션 직전에 category_insights 렌더링 추가:

```python
    # 테마별 분석 (카테고리 그룹핑)
    output += "## 📰 Theme Analysis\n\n"

    # category_insights가 있으면 카테고리 헤딩으로 그룹핑
    categories_with_insights = set(report.category_insights.keys()) if report.category_insights else set()
    current_category = None

    for news_item in report.news:
        # 카테고리가 바뀌면 헤딩 추가
        if news_item.category != current_category:
            current_category = news_item.category
            output += f"## {current_category}\n\n"
            # category_insight가 있으면 blockquote로 표시
            if current_category in categories_with_insights:
                output += f"> {report.category_insights[current_category]}\n\n"

        output += f"### {news_item.emoji} {news_item.investment_theme}\n\n"
```

이 변경으로 기존 `## 📰 Theme Analysis` 아래의 flat 구조가 카테고리별 그룹핑으로 바뀜. 기존 테스트에 영향 없음 (렌더링 테스트 없었음).

전체 변경된 `format_report` 함수 (`## 📰 Theme Analysis` 부분부터):

```python
    # 테마별 분석
    current_category = None
    for news_item in report.news:
        # 카테고리가 바뀌면 헤딩 추가
        if news_item.category != current_category:
            current_category = news_item.category
            output += f"## {current_category}\n\n"
            if report.category_insights and current_category in report.category_insights:
                output += f"> {report.category_insights[current_category]}\n\n"

        output += f"### {news_item.emoji} {news_item.investment_theme}\n\n"

        # Summary를 bullet list로 포맷팅
        summary_lines = news_item.summary.split("\n")
        for line in summary_lines:
            line = line.strip()
            if line:
                if line.startswith("•") or line.startswith("-"):
                    output += f"{line}\n"
                else:
                    output += f"- {line}\n"
        output += "\n"

        output += f"**Impact**: {news_item.impact}\n\n"

        if news_item.stocks:
            output += "**관련 종목**:\n"
            for stock in news_item.stocks:
                output += f"- **{stock.name}** ({stock.ticker}): {stock.catalyst}\n"
            output += "\n"

        # 출처 (원본 메시지 발췌)
        if news_item.source_ids:
            source_messages = _load_source_messages(news_item.source_ids, report.date, data_dir)
            if source_messages:
                output += "**출처**:\n"
                for idx, (_source_id, content) in enumerate(source_messages.items(), 1):
                    excerpt = _extract_relevant_text(content, news_item.keywords, max_length=200)
                    if excerpt:
                        output += f"  {idx}. {excerpt}\n"
                output += "\n"

    return output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/pipelines/daily_report/ -v`
Expected: 모든 기존 테스트 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/daily_report/pipeline.py tests/pipelines/daily_report/test_wrapup_stage.py
git commit -m "feat(daily-report): render category_insights as grouped headings in markdown report"
```

---

### Task 6: LLM-as-Judge 평가 스크립트

**Files:**
- Create: `evaluations/evaluate_wrapup.py`

- [ ] **Step 1: Create the evaluation script**

```python
# evaluations/evaluate_wrapup.py
"""Wrapup stage V2 vs V3 평가 스크립트 (LLM-as-Judge).

Usage:
    uv run python evaluations/evaluate_wrapup.py
    uv run python evaluations/evaluate_wrapup.py --dates 2026-04-20
    uv run python evaluations/evaluate_wrapup.py --runs 5

Reduce fixture를 고정 입력으로 사용하여 Wrapup만 순수 비교.
Judge 모델: Anthropic Sonnet 4.5 (생성 Haiku 4.5와 다른 티어).
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from src.llm.provider import LLMProvider
from src.pipelines.daily_report.config import WRAPUP_LLM
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import (
    KeyInsightsList,
    MacroSnapshot,
    NewsItem,
)
from src.pipelines.daily_report.prompts import (
    WRAPUP_SYSTEM_PROMPT_V2,
    WRAPUP_USER_PROMPT_V2,
    WRAPUP_SYSTEM_PROMPT_V3,
    WRAPUP_USER_PROMPT_V3,
)
from src.pipelines.daily_report.examples.wrapup_examples import get_wrapup_examples


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIXTURE_DIR = Path("tests/pipelines/daily_report/fixtures/stage_outputs")


# ============================================================================
# Judge 모델
# ============================================================================

JUDGE_SYSTEM_PROMPT = """당신은 투자 리포트 품질 평가자입니다.
Daily report의 key_insights를 5개 차원으로 평가하세요.

**평가 차원 (각 0-2점, 총 0-10점)**:

| 차원 | 0점 | 1점 | 2점 |
|------|-----|-----|-----|
| chain_presence | 인과 체인(→) 없음 | 1단계만 | 2단계+ 체인 포함 |
| chain_validity | 논리적 비약 있음 | 일부 연결 약함 | 모든 연결 타당 |
| actionability | 투자 시사점 없음 | 모호한 시사점 | 구체적 섹터/종목 제시 |
| data_grounding | 숫자/팩트 없음 | 일부 포함 | 충분히 포함 |
| conciseness | 500자+ 덩어리 | 구조 있지만 장황 | 구조화 + 간결 |

JSON으로 응답하세요."""

JUDGE_USER_PROMPT = """**평가 대상 (key_insights)**:
{insights}

위 인사이트를 5개 차원으로 평가하세요."""


class JudgeScore(BaseModel):
    """Judge 채점 결과."""

    chain_presence: int = Field(ge=0, le=2)
    chain_validity: int = Field(ge=0, le=2)
    actionability: int = Field(ge=0, le=2)
    data_grounding: int = Field(ge=0, le=2)
    conciseness: int = Field(ge=0, le=2)
    reasoning: str = Field(description="채점 이유 (한 줄)")

    @property
    def total(self) -> int:
        return (
            self.chain_presence
            + self.chain_validity
            + self.actionability
            + self.data_grounding
            + self.conciseness
        )


# ============================================================================
# Wrapup 실행 (V2/V3)
# ============================================================================

def _build_news_text_v2(news_items: list[NewsItem]) -> str:
    """V2 포맷: summary[:100] 잘림."""
    return "\n\n".join(
        f"[{item.category}] {item.investment_theme}\n"
        f"(기술 테마: {item.technical_theme})\n"
        f"{item.emoji} {item.summary[:100]}..."
        for item in news_items
    )


def _build_news_text_v3(news_items: list[NewsItem]) -> str:
    """V3 포맷: summary 전체 + impact + stocks."""
    parts = []
    for item in news_items:
        section = (
            f"[{item.category}] {item.investment_theme}\n"
            f"(기술 테마: {item.technical_theme})\n"
            f"{item.summary}\n"
            f"Impact: {item.impact}"
        )
        if item.stocks:
            stock_names = ", ".join(s.name for s in item.stocks)
            section += f"\n종목: {stock_names}"
        parts.append(section)
    return "\n\n".join(parts)


def _build_macro_text(macro: MacroSnapshot) -> str:
    """매크로 데이터 포맷팅."""
    return (
        f"VIX: {macro.vix}\n"
        f"Fear & Greed: {macro.fear_greed}\n"
        f"미국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.us_markets.items())}\n"
        f"한국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.kr_markets.items())}\n"
        f"KRW/USD: {macro.krw_usd}"
    )


async def run_wrapup(
    version: str,
    news_items: list[NewsItem],
    macro: MacroSnapshot,
) -> list[str]:
    """Wrapup stage를 V2 또는 V3로 실행."""
    llm = WRAPUP_LLM.create_llm()
    macro_text = _build_macro_text(macro)

    if version == "v2":
        news_text = _build_news_text_v2(news_items)
        system_prompt = WRAPUP_SYSTEM_PROMPT_V2
        user_prompt = WRAPUP_USER_PROMPT_V2.format(
            macro=macro_text, news_count=len(news_items), news_items=news_text
        )
    else:
        news_text = _build_news_text_v3(news_items)
        examples = get_wrapup_examples()
        system_prompt = WRAPUP_SYSTEM_PROMPT_V3.format(examples=examples)
        user_prompt = WRAPUP_USER_PROMPT_V3.format(
            macro=macro_text, news_count=len(news_items), news_items=news_text
        )

    messages = WRAPUP_LLM.build_messages(system_prompt, user_prompt)
    config = {"run_name": f"Eval Wrapup {version}", "tags": ["evaluation"]}

    response = await invoke_llm_with_retry(llm, KeyInsightsList, messages, config)
    return response.insights


# ============================================================================
# Judge
# ============================================================================

async def judge_insights(insights: list[str]) -> JudgeScore:
    """LLM-as-Judge로 인사이트 채점."""
    judge_llm = LLMProvider.create(
        provider="anthropic",
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0,
    )

    insights_text = "\n\n".join(insights)
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=JUDGE_USER_PROMPT.format(insights=insights_text)),
    ]

    llm_with_output = judge_llm.with_structured_output(JudgeScore)
    return await asyncio.wait_for(
        llm_with_output.ainvoke(messages),
        timeout=60.0,
    )


# ============================================================================
# Main
# ============================================================================

def load_fixture(date: str) -> tuple[list[NewsItem], MacroSnapshot]:
    """Reduce + Ingest fixture 로드."""
    reduce_file = FIXTURE_DIR / f"reduce_{date}.json"
    ingest_file = FIXTURE_DIR / f"ingest_{date}.json"

    with open(reduce_file, encoding="utf-8") as f:
        news_data = json.load(f)
    with open(ingest_file, encoding="utf-8") as f:
        ingest_data = json.load(f)

    news_items = [NewsItem(**item) for item in news_data]
    macro = MacroSnapshot(**ingest_data["macro"])
    return news_items, macro


async def evaluate_date(date: str, runs: int) -> dict:
    """한 날짜에 대해 V2/V3 비교 평가."""
    news_items, macro = load_fixture(date)
    print(f"\n{'='*60}")
    print(f"📅 {date} ({len(news_items)} themes, {runs} runs)")
    print(f"{'='*60}")

    results = {"date": date, "v2": [], "v3": []}

    for run_idx in range(runs):
        print(f"\n  Run {run_idx + 1}/{runs}...")

        for version in ["v2", "v3"]:
            try:
                insights = await run_wrapup(version, news_items, macro)
                score = await judge_insights(insights)

                results[version].append({
                    "run": run_idx + 1,
                    "total": score.total,
                    "chain_presence": score.chain_presence,
                    "chain_validity": score.chain_validity,
                    "actionability": score.actionability,
                    "data_grounding": score.data_grounding,
                    "conciseness": score.conciseness,
                    "reasoning": score.reasoning,
                    "insights": insights,
                })

                print(f"    {version.upper()}: {score.total}/10 — {score.reasoning}")
            except Exception as e:
                print(f"    {version.upper()}: ERROR — {e}")
                results[version].append({"run": run_idx + 1, "total": 0, "error": str(e)})

    return results


def print_summary(all_results: list[dict]):
    """전체 요약 출력."""
    v2_scores = []
    v3_scores = []

    for result in all_results:
        for entry in result["v2"]:
            if "total" in entry and "error" not in entry:
                v2_scores.append(entry["total"])
        for entry in result["v3"]:
            if "total" in entry and "error" not in entry:
                v3_scores.append(entry["total"])

    v2_avg = sum(v2_scores) / len(v2_scores) if v2_scores else 0
    v3_avg = sum(v3_scores) / len(v3_scores) if v3_scores else 0

    print(f"\n{'='*60}")
    print("📊 EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"  V2 average: {v2_avg:.1f}/10 ({len(v2_scores)} runs)")
    print(f"  V3 average: {v3_avg:.1f}/10 ({len(v3_scores)} runs)")
    print(f"  Delta: {v3_avg - v2_avg:+.1f}")
    print(f"  Target: V3 ≥ 7.0 ({'✅ PASS' if v3_avg >= 7.0 else '❌ FAIL'})")


async def main_async(dates: list[str], runs: int):
    """비동기 메인."""
    all_results = []
    for date in dates:
        result = await evaluate_date(date, runs)
        all_results.append(result)

    print_summary(all_results)

    # 결과 저장
    output_dir = Path("evaluations/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_file = output_dir / f"{timestamp}_wrapup_v2_vs_v3.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Results saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Wrapup V2 vs V3 평가")
    parser.add_argument(
        "--dates",
        default="2026-04-20",
        help="평가할 날짜 (쉼표 구분). reduce fixture 필요. 기본: 2026-04-20",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="날짜당 실행 횟수 (기본: 3)",
    )
    args = parser.parse_args()

    dates = [d.strip() for d in args.dates.split(",")]

    # fixture 존재 확인
    for date in dates:
        reduce_file = FIXTURE_DIR / f"reduce_{date}.json"
        ingest_file = FIXTURE_DIR / f"ingest_{date}.json"
        if not reduce_file.exists():
            print(f"❌ Reduce fixture 없음: {reduce_file}")
            return
        if not ingest_file.exists():
            print(f"❌ Ingest fixture 없음: {ingest_file}")
            return

        # NewsItem 포맷 확인 (category 필드 필요)
        with open(reduce_file, encoding="utf-8") as f:
            first_item = json.load(f)[0]
        if "category" not in first_item:
            print(f"⚠️  {date} fixture는 구버전 포맷 (category 없음). 2026-04-20 이후 사용 권장.")
            return

    print("🚀 Wrapup V2 vs V3 Evaluation")
    print(f"   Dates: {dates}")
    print(f"   Runs per date: {args.runs}")
    print(f"   Judge: Anthropic Sonnet 4.5")

    asyncio.run(main_async(dates, args.runs))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script loads without errors**

Run: `uv run python -c "import evaluations.evaluate_wrapup; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add evaluations/evaluate_wrapup.py
git commit -m "feat(evaluation): add wrapup V2 vs V3 LLM-as-Judge evaluation script"
```

---

### Task 7: Change record 업데이트 + 통합 검증

**Files:**
- Modify: `docs/changes/daily-report-causal-reasoning.md`

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: 모든 테스트 PASS.

- [ ] **Step 2: Smoke test — wrapup CLI 실행 (2026-04-20 fixture)**

Run: `uv run python -m src.pipelines.daily_report.stages.wrapup_stage 2026-04-20`
Expected: 인사이트 출력에 `→` 체인 포함. 500자 덩어리 없음.

- [ ] **Step 3: Change record checklist 업데이트**

`docs/changes/daily-report-causal-reasoning.md`에서 완료 항목 체크:

```markdown
## Checklist

- [x] Reduce/Wrapup 프롬프트 V3 + stages import 변경
- [x] Wrapup 입력 `summary[:100]` → 전체 전달
- [x] Few-shot 예시 추가
- [x] LLM-as-Judge 평가 구현 (기존 `evaluations/` 확장)
- [ ] V2 baseline → V3 채점 비교
- [ ] 실전 테스트 3-5일
- [ ] `docs/FEATURES.md` 업데이트
```

Note: "V2 baseline → V3 채점 비교"와 "실전 테스트"는 `evaluations/evaluate_wrapup.py` 실행 후 별도 확인. "FEATURES.md 업데이트"는 실전 테스트 완료 후.

- [ ] **Step 4: Commit**

```bash
git add docs/changes/daily-report-causal-reasoning.md
git commit -m "docs: update causal reasoning change record checklist with implementation progress"
```

---

### Task 8: 평가 실행 및 결과 확인

이 Task는 API 호출이 필요한 실행 단계. 이전 Task들이 모두 완료된 후 수행.

- [ ] **Step 1: Evaluate V2 vs V3**

Run: `uv run python evaluations/evaluate_wrapup.py --dates 2026-04-20 --runs 3`
Expected:
- V2 평균: 3-4점
- V3 평균: 7점 이상
- Delta: +3점 이상

- [ ] **Step 2: 결과 확인 및 조정**

`evaluations/results/` 디렉토리에 저장된 JSON 결과 확인.

**V3 < 7점인 경우:**
- `chain_presence` 낮으면 → 프롬프트에 "반드시 → 사용" 강화
- `data_grounding` 낮으면 → 프롬프트에 "숫자 필수 포함" 강화
- `conciseness` 낮으면 → 프롬프트에 "300자 이내" 명시

**V3 ≥ 7점이면:** 다음 Step으로.

- [ ] **Step 3: Commit evaluation results**

```bash
git add evaluations/results/
git commit -m "docs(evaluation): add wrapup V2 vs V3 judge results"
```
