# Analyze 판단 우선 출력 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jarvis analyze` 출력을 원시 데이터 나열형에서 판단 우선형으로 재구성해, 사용자가 먼저 `주도 팩터 / 핵심 변수 / 액션`을 보고 그 뒤에 근거와 원시 데이터를 읽도록 만든다.

**Architecture:** 기존 `DeepDivePipeline`의 데이터 수집 흐름은 유지하고, 그 위에 가산형 `analyze_decision` 레이어를 얹어 `technical / flow / event / valuation`을 점수화한다. 최종 액션은 새 canonical decision artifact만이 결정하고, 기존 LLM 요약과 추천 값은 근거 데이터로만 남긴다.

**Tech Stack:** Python 3.12, Pydantic, Typer, Rich Markdown/Panel, pytest, uv

---

## 파일 구조

### 새로 만드는 파일
- `src/pipelines/analyze_decision.py` - 판단 우선 모델, 점수 계약, 팩터 우선순위화, 저증거 fallback, 시나리오 생성
- `tests/pipelines/test_analyze_decision.py` - 팩터 점수, stale pattern 가드레일, 혼합/판단 보류, invalidation 테스트
- `tests/cli/test_analyze_output.py` - 상단 3줄 요약, 팩터 이유, 판단 보류 이유, canonical action 렌더링 테스트

### 수정하는 파일
- `src/pipelines/deep_dive.py` - 기존 기술/뉴스/펀더멘털/공시/수급 데이터를 이용해 decision bundle 생성
- `src/cli/main.py` - 추천 중심 렌더링을 판단 중심 렌더링으로 교체
- `tests/pipelines/test_deep_dive.py` - pipeline이 decision summary, factor assessments, scenarios를 반환하는지 검증
- `docs/CLI_USAGE.md` - `analyze` 출력 구조와 이유 필드 문서화

---

## 한눈에 보는 작업 흐름

### Task 1
- 판단 모델과 점수 계약의 뼈대를 만든다.

### Task 2
- stale pattern, event 범위, 판단 보류 같은 실제 판단 규칙을 넣는다.

### Task 3
- `DeepDivePipeline`이 새 판단 결과를 함께 반환하도록 연결한다.

### Task 4
- CLI를 `판단 → 팩터 분류 → 시나리오 → 원시 데이터` 순서로 다시 그린다.

### Task 5
- 문서와 acceptance 성격 테스트를 마무리한다.

---

### Task 1: 판단 모델과 점수 계약 추가

**Files:**
- Create: `src/pipelines/analyze_decision.py`
- Test: `tests/pipelines/test_analyze_decision.py`

- [ ] **Step 1: 모델 테스트부터 실패하게 작성**

```python
# tests/pipelines/test_analyze_decision.py
from src.pipelines.analyze_decision import (
    AnalyzeDecisionSummary,
    AnalyzeScenario,
    FactorAssessment,
)


def test_factor_assessment_keeps_role_reason():
    assessment = FactorAssessment(
        factor_type="event",
        role="참고",
        freshness_score=4,
        magnitude_score=2,
        actionability_score=1,
        total_score=7,
        summary="반복 보도 중심",
        role_reason="신규 정보가 부족해 actionability가 낮음",
        evidence=["증권사 해설 기사 3건"],
    )

    assert assessment.factor_type == "event"
    assert assessment.role == "참고"
    assert assessment.role_reason == "신규 정보가 부족해 actionability가 낮음"


def test_decision_summary_accepts_defer_reason():
    summary = AnalyzeDecisionSummary(
        leader="판단 보류",
        core_variables=["수급 데이터 부재", "event 신호 약함"],
        action="관망",
        timing="보류",
        action_sentence="지금은 강한 단정보다 관망이 낫다",
        defer_reason="계산 가능한 팩터가 1개뿐임",
    )

    assert summary.leader == "판단 보류"
    assert summary.defer_reason == "계산 가능한 팩터가 1개뿐임"


def test_scenario_requires_invalidation_conditions():
    scenario = AnalyzeScenario(
        name="기본 시나리오",
        trigger_price_levels=["20일선 유지"],
        confirming_factors=["외인 순매수 지속"],
        invalidation_conditions=["20일선 종가 이탈", "거래량 둔화"],
        expected_path="눌림 후 재상승",
        recommended_action="조정 구간 분할 접근",
    )

    assert scenario.invalidation_conditions == ["20일선 종가 이탈", "거래량 둔화"]
```

- [ ] **Step 2: 새 테스트가 실제로 실패하는지 확인**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py -v`  
Expected: `ModuleNotFoundError: No module named 'src.pipelines.analyze_decision'`

- [ ] **Step 3: 판단 우선용 기본 모델 추가**

```python
# src/pipelines/analyze_decision.py
from pydantic import BaseModel, Field


class FactorAssessment(BaseModel):
    factor_type: str
    role: str
    freshness_score: int = Field(ge=0, le=5)
    magnitude_score: int = Field(ge=0, le=5)
    actionability_score: int = Field(ge=0, le=5)
    total_score: int = Field(ge=0, le=15)
    summary: str
    role_reason: str
    evidence: list[str]


class AnalyzeDecisionSummary(BaseModel):
    leader: str
    core_variables: list[str]
    action: str
    timing: str
    action_sentence: str
    defer_reason: str | None = None


class AnalyzeScenario(BaseModel):
    name: str
    trigger_price_levels: list[str]
    confirming_factors: list[str]
    invalidation_conditions: list[str]
    expected_path: str
    recommended_action: str


class AnalyzeDecisionBundle(BaseModel):
    summary: AnalyzeDecisionSummary
    factor_assessments: list[FactorAssessment]
    scenarios: list[AnalyzeScenario]
```

- [ ] **Step 4: 모델 테스트가 통과하는지 확인**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py -v`  
Expected: `3 passed`

- [ ] **Step 5: 점수 계약 테스트를 추가**

```python
# tests/pipelines/test_analyze_decision.py
from src.pipelines.analyze_decision import classify_leader_label


def test_classify_leader_label_returns_mixed_when_margin_is_small():
    factor_scores = [
        {"factor_type": "technical", "total_score": 11},
        {"factor_type": "flow", "total_score": 10},
    ]

    assert classify_leader_label(factor_scores) == "혼합"


def test_classify_leader_label_returns_defer_when_only_one_factor_exists():
    factor_scores = [
        {"factor_type": "technical", "total_score": 6},
    ]

    assert classify_leader_label(factor_scores) == "판단 보류"
```

- [ ] **Step 6: 점수 계약 테스트가 실패하는지 확인**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py::test_classify_leader_label_returns_mixed_when_margin_is_small -v`  
Expected: `ImportError` or `AttributeError` for `classify_leader_label`

- [ ] **Step 7: 주도/혼합/판단 보류 판정 헬퍼 구현**

```python
# src/pipelines/analyze_decision.py
def classify_leader_label(factor_scores: list[dict[str, int]]) -> str:
    ranked = sorted(factor_scores, key=lambda item: item["total_score"], reverse=True)

    if len(ranked) < 2:
        return "판단 보류"

    first = ranked[0]["total_score"]
    second = ranked[1]["total_score"]

    if first < 7:
        return "판단 보류"

    if first - second < 2:
        return "혼합"

    return ranked[0]["factor_type"]
```

- [ ] **Step 8: Task 1 전체 테스트 재실행**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py -v`  
Expected: `5 passed`

- [ ] **Step 9: 커밋**

```bash
git add src/pipelines/analyze_decision.py tests/pipelines/test_analyze_decision.py
git commit -m "feat(pipelines): add judgment-first decision models" -m "- 판단 요약 모델과 시나리오 구조를 추가함
- 주도/혼합/판단 보류 판정 헬퍼를 정의함
- 이유 필드를 포함한 기본 단위 테스트를 추가함"
```

---

### Task 2: 실제 판단 규칙 추가

**Files:**
- Modify: `src/pipelines/analyze_decision.py`
- Test: `tests/pipelines/test_analyze_decision.py`

- [ ] **Step 1: stale pattern 강등과 event 범위 테스트를 먼저 작성**

```python
# tests/pipelines/test_analyze_decision.py
from src.pipelines.analyze_decision import (
    build_event_assessment,
    build_technical_assessment,
)


def test_technical_assessment_downgrades_stale_pattern_to_reference():
    assessment = build_technical_assessment(
        total_score=140,
        rsi=78.0,
        chart_patterns=[
            {
                "pattern_name": "Double Bottom",
                "detected": True,
                "days_ago": 145,
            }
        ],
    )

    assert assessment.role == "참고"
    assert "145일 전" in assessment.role_reason


def test_event_assessment_uses_news_and_disclosure_metadata_only():
    assessment = build_event_assessment(
        news_titles=["제룡전기, 480억원 공급계약 체결"],
        disclosure_items=[{"form_type": "공시", "description": "공급계약 체결"}],
    )

    assert assessment.factor_type == "event"
    assert "공급계약" in assessment.summary
    assert assessment.total_score >= 10
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py::test_technical_assessment_downgrades_stale_pattern_to_reference -v`  
Expected: `ImportError` or `AttributeError` for `build_technical_assessment`

- [ ] **Step 3: 점수 계산과 최소 가드레일 구현**

```python
# src/pipelines/analyze_decision.py
def build_technical_assessment(total_score: int, rsi: float | None, chart_patterns: list[dict]) -> FactorAssessment:
    stale_pattern = next(
        (pattern for pattern in chart_patterns if pattern.get("detected") and pattern.get("days_ago", 0) > 120),
        None,
    )

    if stale_pattern:
        return FactorAssessment(
            factor_type="technical",
            role="참고",
            freshness_score=1,
            magnitude_score=4,
            actionability_score=1,
            total_score=6,
            summary="기술 신호는 존재하지만 오래된 패턴 중심",
            role_reason=f"{stale_pattern['days_ago']}일 전 완성된 패턴이라 현재 액션과 거리 있음",
            evidence=[stale_pattern["pattern_name"], f"RSI {rsi:.1f}" if rsi is not None else "RSI 없음"],
        )

    score = 11 if total_score >= 100 else 8
    role = "주도" if score >= 10 else "보조"
    return FactorAssessment(
        factor_type="technical",
        role=role,
        freshness_score=4,
        magnitude_score=4,
        actionability_score=3,
        total_score=score,
        summary="가격과 모멘텀이 현재 흐름을 직접 설명함",
        role_reason="신고가/거래량/추세 지표가 현재 액션과 직접 연결됨",
        evidence=[f"technical total_score={total_score}", f"RSI {rsi:.1f}" if rsi is not None else "RSI 없음"],
    )


def build_event_assessment(news_titles: list[str], disclosure_items: list[dict] | None) -> FactorAssessment:
    has_contract = any("계약" in title for title in news_titles)
    has_disclosure = bool(disclosure_items)

    total_score = 10 if has_contract and has_disclosure else 7 if news_titles else 0
    role = "주도" if total_score >= 10 else "보조" if total_score >= 7 else "참고"
    reason = "뉴스와 공시 메타데이터가 같은 방향으로 확인됨" if has_disclosure else "뉴스는 있으나 신규 공시 확인은 제한적임"

    return FactorAssessment(
        factor_type="event",
        role=role,
        freshness_score=5 if news_titles else 0,
        magnitude_score=4 if has_contract else 2,
        actionability_score=4 if has_disclosure else 2,
        total_score=total_score,
        summary=news_titles[0] if news_titles else "유의미한 이벤트 부재",
        role_reason=reason,
        evidence=news_titles[:2] + [item["description"] for item in (disclosure_items or [])[:1]],
    )
```

- [ ] **Step 4: stale/event 테스트 통과 확인**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py -v`  
Expected: `7 passed`

- [ ] **Step 5: 저증거 fallback 테스트 추가**

```python
# tests/pipelines/test_analyze_decision.py
from src.pipelines.analyze_decision import build_decision_summary


def test_build_decision_summary_uses_defer_reason_when_signal_is_weak():
    summary = build_decision_summary(
        leader_label="판단 보류",
        assessments=[],
    )

    assert summary.leader == "판단 보류"
    assert "계산 가능한 팩터" in summary.defer_reason
    assert summary.action == "관망"
    assert summary.timing == "보류"
```

- [ ] **Step 6: fallback 테스트가 실패하는지 확인**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py::test_build_decision_summary_uses_defer_reason_when_signal_is_weak -v`  
Expected: `ImportError` or `AttributeError` for `build_decision_summary`

- [ ] **Step 7: 판단 보류 요약 생성기 추가**

```python
# src/pipelines/analyze_decision.py
def build_decision_summary(leader_label: str, assessments: list[FactorAssessment]) -> AnalyzeDecisionSummary:
    if leader_label == "판단 보류":
        return AnalyzeDecisionSummary(
            leader="판단 보류",
            core_variables=["계산 가능한 팩터 부족"],
            action="관망",
            timing="보류",
            action_sentence="지금은 강한 단정보다 관망이 낫다",
            defer_reason="계산 가능한 팩터가 부족하거나 점수 우위가 없음",
        )

    core_variables = [assessment.summary for assessment in assessments[:2]]
    action = "관망" if leader_label == "혼합" else "매수"
    timing = "조정_대기" if leader_label in {"technical", "flow", "혼합"} else "지금"

    return AnalyzeDecisionSummary(
        leader=leader_label,
        core_variables=core_variables,
        action=action,
        timing=timing,
        action_sentence="지금 추격보다 핵심 레벨 확인 후 접근이 유리" if action == "관망" else "현재 주도 팩터를 따라 대응 가능",
        defer_reason=None,
    )
```

- [ ] **Step 8: Task 2 전체 테스트 재실행**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py -v`  
Expected: `8 passed`

- [ ] **Step 9: 커밋**

```bash
git add src/pipelines/analyze_decision.py tests/pipelines/test_analyze_decision.py
git commit -m "feat(pipelines): add factor scoring guardrails" -m "- event 범위를 뉴스와 공시 메타데이터로 제한함
- stale pattern 강등 규칙과 판단 보류 fallback을 추가함
- 점수 계약 관련 테스트를 보강함"
```

---

### Task 3: DeepDivePipeline에 판단 결과 연결

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Modify: `tests/pipelines/test_deep_dive.py`

- [ ] **Step 1: pipeline이 decision bundle을 반환하는지 실패 테스트 작성**

```python
# tests/pipelines/test_deep_dive.py
from src.pipelines.analyze_decision import AnalyzeDecisionBundle, AnalyzeDecisionSummary, AnalyzeScenario, FactorAssessment


@pytest.mark.asyncio
async def test_deep_dive_pipeline_returns_decision_bundle(mock_technical_tool, mock_news_tool, mock_llm):
    with (
        patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
        patch("src.pipelines.deep_dive.build_analyze_decision_bundle") as mock_bundle,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=["신제품"],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_signal.return_value = ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=8,
            headline="매수",
            primary_reason="골든크로스",
            supporting_reasons=[],
            risks=[],
            confidence=0.75,
        )
        mock_bundle.return_value = AnalyzeDecisionBundle(
            summary=AnalyzeDecisionSummary(
                leader="technical",
                core_variables=["가격 모멘텀"],
                action="관망",
                timing="조정_대기",
                action_sentence="눌림 확인 후 접근",
            ),
            factor_assessments=[
                FactorAssessment(
                    factor_type="technical",
                    role="주도",
                    freshness_score=4,
                    magnitude_score=4,
                    actionability_score=3,
                    total_score=11,
                    summary="가격 모멘텀",
                    role_reason="추세가 현재 액션과 직접 연결됨",
                    evidence=["technical total_score=75"],
                )
            ],
            scenarios=[
                AnalyzeScenario(
                    name="기본 시나리오",
                    trigger_price_levels=["20일선 유지"],
                    confirming_factors=["거래량 유지"],
                    invalidation_conditions=["20일선 종가 이탈"],
                    expected_path="눌림 후 재상승",
                    recommended_action="조정 구간 접근",
                )
            ],
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

        assert result["decision_summary"].leader == "technical"
        assert result["factor_assessments"][0].role == "주도"
        assert result["scenarios"][0].name == "기본 시나리오"
```

- [ ] **Step 2: 새 pipeline 테스트가 실패하는지 확인**

Run: `uv run pytest tests/pipelines/test_deep_dive.py::test_deep_dive_pipeline_returns_decision_bundle -v`  
Expected: `ImportError` for `build_analyze_decision_bundle` or missing keys in `result`

- [ ] **Step 3: bundle 생성 함수를 만들고 pipeline에 연결**

```python
# src/pipelines/analyze_decision.py
def build_analyze_decision_bundle(
    *,
    technical_data,
    technical_summary,
    news_articles,
    news_analysis,
    fundamental_summary,
    disclosure_items,
    flow_data,
    chart_patterns,
    price_levels,
) -> AnalyzeDecisionBundle:
    assessments = [
        build_technical_assessment(
            total_score=technical_data.total_score,
            rsi=technical_data.snapshot.rsi,
            chart_patterns=[
                {
                    "pattern_name": result.pattern_name,
                    "detected": result.detected,
                    "days_ago": result.days_ago or 0,
                }
                for result in chart_patterns.values()
            ],
        ),
        build_event_assessment(
            news_titles=[article.title for article in news_articles],
            disclosure_items=[
                {"form_type": item.form_type, "description": item.description}
                for item in disclosure_items or []
            ],
        ),
    ]
    leader_label = classify_leader_label(
        [{"factor_type": a.factor_type, "total_score": a.total_score} for a in assessments]
    )
    summary = build_decision_summary(leader_label, assessments)
    scenarios = build_default_scenarios(summary, price_levels, assessments)
    return AnalyzeDecisionBundle(summary=summary, factor_assessments=assessments, scenarios=scenarios)
```

```python
# src/pipelines/deep_dive.py
from src.pipelines.analyze_decision import build_analyze_decision_bundle

# inside run(), after price_levels/actionable_signal creation
decision_bundle = build_analyze_decision_bundle(
    technical_data=technical_data,
    technical_summary=technical_summary,
    news_articles=news_articles,
    news_analysis=news_analysis,
    fundamental_summary=fundamental_summary,
    disclosure_items=disclosure_items,
    flow_data=flow_data,
    chart_patterns=chart_patterns,
    price_levels=price_levels,
)

return {
    # existing keys...
    "decision_summary": decision_bundle.summary,
    "factor_assessments": decision_bundle.factor_assessments,
    "scenarios": decision_bundle.scenarios,
}
```

- [ ] **Step 4: pipeline 테스트 전체 통과 확인**

Run: `uv run pytest tests/pipelines/test_deep_dive.py -v`  
Expected: all tests in `tests/pipelines/test_deep_dive.py` pass

- [ ] **Step 5: 저증거 상태 테스트 추가**

```python
# tests/pipelines/test_deep_dive.py
@pytest.mark.asyncio
async def test_deep_dive_pipeline_uses_defer_state_when_news_and_flow_are_missing(mock_technical_tool, mock_llm):
    empty_news_tool = AsyncMock()
    empty_news_tool.execute.return_value = ToolResult(success=True, data=[])

    with (
        patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech_summary,
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_signal.return_value = ActionableSignalOutput(
            action="관망",
            timing="보류",
            signal_strength=5,
            headline="관망",
            primary_reason="근거 부족",
            supporting_reasons=[],
            risks=[],
            confidence=0.45,
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=empty_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

        assert result["decision_summary"].action == "관망"
        assert result["decision_summary"].timing in {"조정_대기", "보류"}
```

- [ ] **Step 6: 저증거 테스트 단독 실행**

Run: `uv run pytest tests/pipelines/test_deep_dive.py::test_deep_dive_pipeline_uses_defer_state_when_news_and_flow_are_missing -v`  
Expected: `1 passed`

- [ ] **Step 7: 커밋**

```bash
git add src/pipelines/deep_dive.py src/pipelines/analyze_decision.py tests/pipelines/test_deep_dive.py tests/pipelines/test_analyze_decision.py
git commit -m "feat(pipelines): wire decision bundle into analyze" -m "- DeepDivePipeline에 판단 레이어 결과를 추가함
- 기존 broad dict 위에 additive wrapper를 얹음
- 저증거 상태와 시나리오 반환 테스트를 보강함"
```

---

### Task 4: CLI를 판단 우선 구조로 재구성

**Files:**
- Modify: `src/cli/main.py`
- Create: `tests/cli/test_analyze_output.py`

- [ ] **Step 1: 상단 요약과 이유 노출 테스트를 먼저 작성**

```python
# tests/cli/test_analyze_output.py
from datetime import datetime

from src.cli.main import format_deep_dive_output
from src.pipelines.analyze_decision import AnalyzeDecisionSummary, AnalyzeScenario, FactorAssessment
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


def test_format_deep_dive_output_shows_top_summary_and_factor_reasons():
    snapshot = IndicatorSnapshot(price=91500.0, change_pct=29.97, rsi=89.1)
    technical = TechnicalResult(
        ticker="033100.KQ",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=140,
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=[],
        warnings=[],
    )

    result = {
        "ticker": "033100.KQ",
        "technical": technical,
        "technical_summary": type("TechSummary", (), {
            "summary": "강세",
            "key_insights": [],
            "recommendation": "매수",
            "confidence": 0.75,
            "rationale": "기술적 강세",
        })(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="혼합",
            core_variables=["신고가 구간", "RSI 과열"],
            action="관망",
            timing="조정_대기",
            action_sentence="지금 추격보다 눌림 확인이 유리",
        ),
        "factor_assessments": [
            FactorAssessment(
                factor_type="technical",
                role="보조",
                freshness_score=4,
                magnitude_score=4,
                actionability_score=3,
                total_score=11,
                summary="신고가 돌파",
                role_reason="RSI 과열로 추격 부담",
                evidence=["RSI 89.1"],
            ),
            FactorAssessment(
                factor_type="event",
                role="참고",
                freshness_score=3,
                magnitude_score=2,
                actionability_score=1,
                total_score=6,
                summary="반복 기대 기사",
                role_reason="신규 정보가 부족해 actionability가 낮음",
                evidence=["반복 기사 2건"],
            ),
        ],
        "scenarios": [
            AnalyzeScenario(
                name="기본 시나리오",
                trigger_price_levels=["20일선 유지"],
                confirming_factors=["외인 순매수"],
                invalidation_conditions=["20일선 종가 이탈"],
                expected_path="눌림 후 재상승",
                recommended_action="조정 구간 접근",
            )
        ],
    }

    output = format_deep_dive_output(result)

    assert "주도 팩터" in output
    assert "핵심 변수" in output
    assert "액션" in output
    assert "RSI 과열로 추격 부담" in output
    assert "신규 정보가 부족해 actionability가 낮음" in output
```

- [ ] **Step 2: 현재 출력이 실패하는지 확인**

Run: `uv run pytest tests/cli/test_analyze_output.py -v`  
Expected: assertion failure because current output does not contain judgment-first sections

- [ ] **Step 3: canonical summary 렌더링 헬퍼 추가**

```python
# src/cli/main.py
def _format_factor_section(factor_assessments: list) -> str:
    lines = ["## 팩터 분류", ""]
    for role in ("주도", "보조", "참고"):
        filtered = [item for item in factor_assessments if item.role == role]
        if not filtered:
            continue
        lines.append(f"### {role}")
        lines.append("")
        for item in filtered:
            lines.append(f"- **{item.factor_type}**: {item.summary}")
            lines.append(f"  이유: {item.role_reason}")
        lines.append("")
    return "\n".join(lines)


def _format_top_summary(decision_summary) -> str:
    lines = [
        "## 판단 요약",
        "",
        f"- **주도 팩터**: {decision_summary.leader}",
        f"- **핵심 변수**: {', '.join(decision_summary.core_variables)}",
        f"- **액션**: {decision_summary.action} | {decision_summary.timing}",
        f"  {decision_summary.action_sentence}",
    ]
    if decision_summary.defer_reason:
        lines.append(f"  이유: {decision_summary.defer_reason}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: `format_deep_dive_output()`를 판단 우선 순서로 재배치**

```python
# src/cli/main.py
def format_deep_dive_output(result: dict) -> str:
    ticker = result["ticker"]
    technical = result["technical"]
    snapshot = technical.indicators or technical.snapshot
    decision_summary = result.get("decision_summary")
    factor_assessments = result.get("factor_assessments", [])
    scenarios = result.get("scenarios", [])

    output = f"# Deep Dive Analysis: {ticker}\n\n"
    output += f"## 가격: ${snapshot.price:.2f} ({snapshot.change_pct:+.2f}%)\n\n"

    if decision_summary:
        output += _format_top_summary(decision_summary)
    if factor_assessments:
        output += _format_factor_section(factor_assessments) + "\n"
    if scenarios:
        output += _format_scenario_section(scenarios) + "\n"

    # 기존 기술/펀더멘털/뉴스/공시/수급 원시 섹션은 아래에 유지
    output += _format_raw_analysis_sections(result)
    return output
```

- [ ] **Step 5: 상단 요약 렌더링 테스트 통과 확인**

Run: `uv run pytest tests/cli/test_analyze_output.py -v`  
Expected: `1 passed`

- [ ] **Step 6: 판단 보류 이유 노출 테스트 추가**

```python
# tests/cli/test_analyze_output.py
def test_format_deep_dive_output_shows_defer_reason():
    summary = AnalyzeDecisionSummary(
        leader="판단 보류",
        core_variables=["계산 가능한 팩터 부족"],
        action="관망",
        timing="보류",
        action_sentence="지금은 관망이 낫다",
        defer_reason="수급 데이터 부재 + event 신호 약함",
    )

    output = _format_top_summary(summary)

    assert "판단 보류" in output
    assert "수급 데이터 부재 + event 신호 약함" in output
```

- [ ] **Step 7: 판단 보류 테스트와 CLI 스위트 실행**

Run: `uv run pytest tests/cli/test_analyze_output.py tests/cli/test_cli.py -v`  
Expected: all tests pass

- [ ] **Step 8: 커밋**

```bash
git add src/cli/main.py tests/cli/test_analyze_output.py tests/cli/test_cli.py
git commit -m "feat(cli): render analyze output from canonical judgment" -m "- 상단 3줄 요약과 팩터 이유 섹션을 추가함
- 판단 보류 이유와 시나리오 출력을 렌더링함
- 기존 최종 판단 충돌을 canonical summary 기준으로 정리함"
```

---

### Task 5: 문서와 acceptance 검증 마무리

**Files:**
- Modify: `docs/CLI_USAGE.md`
- Modify: `tests/cli/test_analyze_output.py`

- [ ] **Step 1: event가 참고로 내려가는 케이스를 acceptance 스타일로 테스트**

```python
# tests/cli/test_analyze_output.py
def test_format_deep_dive_output_marks_event_as_reference_with_reason():
    assessment = FactorAssessment(
        factor_type="event",
        role="참고",
        freshness_score=4,
        magnitude_score=2,
        actionability_score=1,
        total_score=7,
        summary="AI 전력 수요 기대 기사",
        role_reason="기대감 반복 보도 위주라 현재 액션 설명력이 약함",
        evidence=["관련 기사 2건"],
    )

    output = _format_factor_section([assessment])

    assert "참고" in output
    assert "기대감 반복 보도 위주라 현재 액션 설명력이 약함" in output
```

- [ ] **Step 2: helper가 덜 구현됐으면 실패하는지 확인**

Run: `uv run pytest tests/cli/test_analyze_output.py::test_format_deep_dive_output_marks_event_as_reference_with_reason -v`  
Expected: failure if `참고` or reason text is missing from the factor section

- [ ] **Step 3: `docs/CLI_USAGE.md`의 analyze 설명 확정**

```md
### 2. analyze - 심층 분석 (LLM)

**출력 내용:**
- 상단 판단 요약
  - `주도 팩터`
  - `핵심 변수`
  - `액션`
- 팩터 분류
  - `주도 / 보조 / 참고`
  - `참고`는 강등 이유를 함께 표시
- 액션 시나리오
  - `기본 시나리오`
  - `반대 시나리오`
  - 판단이 약하면 `판단 보류`와 이유 표시
- 원시 데이터
  - 기술 지표, 펀더멘털, 뉴스, 공시, 수급, 차트
```

- [ ] **Step 4: 문서 + 핵심 테스트 묶음 검증**

Run: `uv run pytest tests/cli/test_analyze_output.py tests/pipelines/test_analyze_decision.py tests/pipelines/test_deep_dive.py -v`  
Expected: all targeted tests pass

- [ ] **Step 5: 전체 테스트 스위트 실행**

Run: `uv run pytest`  
Expected: full suite passes

- [ ] **Step 6: 커밋**

```bash
git add docs/CLI_USAGE.md tests/cli/test_analyze_output.py tests/pipelines/test_analyze_decision.py tests/pipelines/test_deep_dive.py
git commit -m "docs: document judgment-first analyze output" -m "- analyze 출력 구조와 판단 보류 규칙을 문서화함
- acceptance 성격의 출력 테스트를 보강함
- 전체 회귀 테스트 통과를 확인함"
```

---

## Self-Review Notes

### Spec Coverage

- `주도 / 보조 / 참고` 분류: Task 1, Task 2
- `혼합` / `판단 보류` 상태: Task 1, Task 2, Task 4
- `event` 범위 축소: Task 2
- stale pattern 최소 가드레일: Task 2
- canonical judgment artifact: Task 4
- scenario + invalidation: Task 3, Task 4
- additive wrapper only: Task 3
- docs update: Task 5
- golden-set 성격의 acceptance coverage: Task 5

### Placeholder Scan

- `TODO`, `TBD`, “적절히 처리” 같은 placeholder는 남기지 않았다.
- 코드가 바뀌는 단계에는 모두 구체 코드 블록을 넣었다.
- 테스트 단계에는 실행 명령과 기대 결과를 모두 적었다.

### Type Consistency

- `FactorAssessment.role_reason`은 점수 계산, 렌더링, 테스트에서 같은 이름으로 사용한다.
- `AnalyzeDecisionSummary.defer_reason`은 fallback과 상단 요약 렌더링에서 같은 이름으로 사용한다.
- `AnalyzeScenario.invalidation_conditions`는 모델 정의 후 pipeline과 CLI에서 동일하게 사용한다.
