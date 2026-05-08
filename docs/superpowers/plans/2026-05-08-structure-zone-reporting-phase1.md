# Structure Zone Reporting Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jarvis analyze`의 구조 출력이 덜 기계적으로 읽히도록 `V2 structure contract + presentation adapter + no_clear_structure + golden regression`을 도입한다.

**Architecture:** 1차는 내부 엔진 대수술이 아니라 출력 계약과 선택 규칙을 고정하는 단계다. `StructureZoneDetector`는 기존 `StructureZoneSet`을 유지하되 selection trace와 `no_clear_structure` 판단 근거를 함께 반환하고, `level_composer.py`가 유일한 `StructureLevelsPayloadV2` 번역기가 된다. 그 위에 별도 `StructurePresentationAdapter`를 두어 CLI와 LLM이 raw zone 필드를 직접 조립하지 않게 만든다.

**Tech Stack:** Python 3.12, pandas, Pydantic, Rich, pytest, uv

---

## 범위 요약

### 1차에 포함
- `StructureZoneSet` 유지, 단 selection trace / structured reason / no_clear_structure 판단 근거 추가
- `StructureLevelsPayloadV2` 도입
- `StructurePresentationPayload` 및 `StructurePresentationAdapter` 도입
- `level_composer.py`를 유일한 V2 번역기로 고정
- CLI / LLM / pipeline이 presenter 출력만 소비하도록 변경
- fixture acceptance, contract test, golden test, inspector stable JSON artifact 추가

### 2차로 미룸
- `StructureZoneDetector` 반환 타입을 완전 V2-native로 교체
- `src/tools/technical/structure_zones.py`를 `components/structure_zones.py`로 분리
- shared `SwingExtractor` 도입
- `PatternEngine`과 `ZoneEngine`의 실제 코드 분리
- legacy `demand/supply/balance` wrapper 완전 제거

---

## 파일 구조

### 기존 파일 재사용
- `src/tools/technical/structure_zones.py` - 1차는 파일 유지, 내부 단계 함수 분리만 수행
- `src/tools/technical/level_composer.py` - 유일한 V2 번역기
- `src/pipelines/deep_dive.py` - detector/composer/presenter 조합 및 하류 전달
- `src/llm/analyzer.py` - presenter가 만든 `llm_context`만 소비
- `src/cli/main.py` - presenter가 만든 `cli_blocks`만 렌더
- `scripts/inspect_structure_zone.py` - 사람용 출력 + stable JSON artifact 둘 다 담당

### 새로 만드는 파일
- `src/tools/technical/structure_presentation.py` - `StructurePresentationAdapter`, `StructurePresentationPayload`
- `tests/tools/technical/test_structure_levels_payload_v2.py`
- `tests/tools/technical/test_structure_presentation_adapter.py`
- `tests/pipelines/test_deep_dive_structure_contract.py`
- `tests/cli/test_analyze_structure_golden.py`

### 수정하는 파일
- `src/tools/technical/models.py`
- `src/tools/technical/structure_zones.py`
- `src/tools/technical/level_composer.py`
- `src/tools/technical/__init__.py`
- `src/pipelines/deep_dive.py`
- `src/llm/analyzer.py`
- `src/cli/main.py`
- `scripts/inspect_structure_zone.py`
- `tests/tools/technical/test_structure_zones.py`
- `tests/tools/technical/test_structure_zone_regression.py`
- `tests/tools/technical/test_level_composer.py`
- `tests/llm/test_analyzer.py`
- `tests/cli/test_analyze_output.py`

---

## Task 1: 타입 계층과 계약 이름을 먼저 고정

**Files:**
- Modify: `src/tools/technical/models.py`
- Modify: `src/tools/technical/__init__.py`
- Test: `tests/tools/technical/test_structure_levels_payload_v2.py`

- [ ] **Step 1: V2 / presentation 계약 테스트를 먼저 추가**

```python
# tests/tools/technical/test_structure_levels_payload_v2.py
from src.tools.technical.models import (
    InvalidationLevelView,
    StructureLevelsPayloadV2,
    StructurePresentationPayload,
)


def test_structure_levels_payload_v2_has_summary_fields():
    payload = StructureLevelsPayloadV2(
        summary_label="support_zone",
        headline="최근 지지 존이 우세",
        why="최근 반등 episode가 가장 강함",
        active_box=None,
        support_zones=[],
        resistance_zones=[],
        former_levels=[],
        invalidation=InvalidationLevelView(
            label="18.00~19.00 하향 이탈",
            lower_bound=18.0,
            upper_bound=19.0,
            reference="support_zone",
            reasons=["support_episode"],
        ),
        patterns_reference=[],
    )

    assert payload.summary_label == "support_zone"
    assert payload.headline
    assert payload.why


def test_structure_presentation_payload_keeps_cli_and_llm_views_separate():
    payload = StructurePresentationPayload(
        top_judgment="현재 가장 중요한 구조: support_zone",
        headline="최근 지지 존이 우세",
        why="최근 반등 episode가 가장 강함",
        cli_blocks=["## 구조 레벨", "- **핵심 지지 존**: 18.00~19.00"],
        llm_context="구조 레벨: support_zone 18.00~19.00",
    )

    assert payload.cli_blocks[0] == "## 구조 레벨"
    assert "support_zone" in payload.llm_context
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_structure_levels_payload_v2.py -v`  
Expected: `ImportError` or `AttributeError` for `StructureLevelsPayloadV2` / `StructurePresentationPayload`

- [ ] **Step 3: 모델 이름을 raw / translated / presented 3단계로 정리**

```python
# src/tools/technical/models.py
class StructureZoneSet(BaseModel):
    """Detector raw result."""

    demand_zones: list[StructureZone] = Field(default_factory=list)
    supply_zones: list[StructureZone] = Field(default_factory=list)
    balance_zones: list[StructureZone] = Field(default_factory=list)
    invalidation_candidates: list[StructureZone] = Field(default_factory=list)
    invalidation_zone: StructureZone | None = None
    all_candidates: list[StructureZone] = Field(default_factory=list)
    selection_trace: list[dict] = Field(default_factory=list)
    no_clear_structure: bool = False
    no_clear_structure_reason_codes: list[str] = Field(default_factory=list)


class StructureLevelsPayloadV2(BaseModel):
    """Composer translated payload."""

    summary_label: str
    headline: str
    why: str
    active_box: StructureLevelView | None = None
    support_zones: list[StructureLevelView] = Field(default_factory=list)
    resistance_zones: list[StructureLevelView] = Field(default_factory=list)
    former_levels: list[StructureLevelView] = Field(default_factory=list)
    invalidation: InvalidationLevelView | None = None
    patterns_reference: list[str] = Field(default_factory=list)


class StructurePresentationPayload(BaseModel):
    """Presenter output for CLI/LLM."""

    top_judgment: str
    headline: str
    why: str
    cli_blocks: list[str] = Field(default_factory=list)
    llm_context: str
```

- [ ] **Step 4: 기존 export를 새 이름으로 정리**

```python
# src/tools/technical/__init__.py
from src.tools.technical.models import (
    StructureLevelsPayloadV2,
    StructurePresentationPayload,
    StructureZoneSet,
)
```

- [ ] **Step 5: Task 1 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_structure_levels_payload_v2.py -v`  
Expected: `2 passed`

- [ ] **Step 6: 커밋**

```bash
git add src/tools/technical/models.py src/tools/technical/__init__.py tests/tools/technical/test_structure_levels_payload_v2.py
git commit -m "feat: add phase1 structure contracts" -m "- raw translated presented 타입 계층을 고정함
- structure v2 payload와 presentation payload를 추가함
- phase1 계약 테스트를 추가함"
```

---

## Task 2: detector는 유지하되 내부 단계를 쪼개고 structured reason을 넣기

**Files:**
- Modify: `src/tools/technical/structure_zones.py`
- Modify: `tests/tools/technical/test_structure_zones.py`

- [ ] **Step 1: 내부 단계 함수와 no_clear_structure 테스트를 먼저 추가**

```python
# tests/tools/technical/test_structure_zones.py
import pandas as pd

from src.tools.technical.models import IndicatorSnapshot, StructureZone
from src.tools.technical.structure_zones import StructureZoneDetector


def test_detector_marks_no_clear_structure_when_scores_are_weak():
    dates = pd.date_range("2025-01-01", periods=160, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0] * 160,
            "High": [101.0] * 160,
            "Low": [99.0] * 160,
            "Close": [100.0] * 160,
            "Volume": [100_000] * 160,
        },
        index=dates,
    )
    snapshot = IndicatorSnapshot(price=100.0, change_pct=0.0, atr=1.0, sma_150=100.0)

    zone_set = StructureZoneDetector().detect(df, snapshot)

    assert zone_set.no_clear_structure is True
    assert zone_set.no_clear_structure_reason_codes


def test_detector_selection_trace_is_stable_and_structured():
    detector = StructureZoneDetector()
    zone = StructureZone(
        zone_type="demand",
        lower_bound=18.0,
        upper_bound=19.0,
        mid_price=18.5,
        touch_count=3,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=4.0,
        volume_reaction_score=3.0,
        confluence_score=2.0,
        total_score=13.0,
        strength="core",
        reason_codes=["support_episode_recent"],
        reason_context={"touch_count": 3},
    )

    trace = detector._build_selection_trace(
        selected_label="support_zone",
        selected_zone=zone,
        dropped_duplicates=[],
        no_clear_structure=False,
    )

    assert trace[0]["selected_label"] == "support_zone"
    assert trace[0]["reason_codes"] == ["support_episode_recent"]
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zones.py -k "no_clear_structure or selection_trace" -v`  
Expected: missing field or missing helper failure

- [ ] **Step 3: `StructureZone`에 structured reason 필드를 추가**

```python
# src/tools/technical/models.py
class StructureZone(BaseModel):
    zone_type: str
    lower_bound: float
    upper_bound: float
    mid_price: float
    touch_count: int
    last_touch_date: str | None = None
    touch_score: float
    recency_score: float
    volume_reaction_score: float
    confluence_score: float
    total_score: float
    strength: str
    reasons: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    reason_context: dict[str, float | int | str] = Field(default_factory=dict)
```

- [ ] **Step 4: `detect()`를 단계 함수로 쪼개기**

```python
# src/tools/technical/structure_zones.py
class StructureZoneDetector:
    def detect(self, df: pd.DataFrame, snapshot: IndicatorSnapshot) -> StructureZoneSet:
        candidates = self._build_candidates(df, snapshot)
        selected = self._select_primary_levels(candidates, snapshot)
        invalidation_candidates, invalidation_zone = self.choose_invalidation_zone(
            demand_zones=selected["demand_zones"],
            snapshot=snapshot,
        )
        no_clear_structure, no_clear_codes = self._should_emit_no_clear_structure(selected, snapshot)
        selection_trace = self._build_selection_trace(
            selected_label=selected["summary_label"],
            selected_zone=selected["summary_zone"],
            dropped_duplicates=selected["dropped_duplicates"],
            no_clear_structure=no_clear_structure,
        )
        return StructureZoneSet(
            demand_zones=selected["demand_zones"],
            supply_zones=selected["supply_zones"],
            balance_zones=selected["balance_zones"],
            invalidation_candidates=invalidation_candidates,
            invalidation_zone=invalidation_zone,
            all_candidates=candidates,
            selection_trace=selection_trace,
            no_clear_structure=no_clear_structure,
            no_clear_structure_reason_codes=no_clear_codes,
        )
```

- [ ] **Step 5: 사람이 읽는 `reasons`는 남기되, raw 단계는 `reason_codes`를 기준으로 정렬**

```python
# src/tools/technical/structure_zones.py
StructureZone(
    zone_type=zone_type,
    lower_bound=lower_bound,
    upper_bound=upper_bound,
    mid_price=(lower_bound + upper_bound) / 2,
    touch_count=touch_count,
    last_touch_date=latest_touch.date().isoformat(),
    touch_score=touch_score,
    recency_score=recency_score,
    volume_reaction_score=volume_reaction_score,
    confluence_score=confluence_score,
    total_score=total_score,
    strength="core" if total_score >= self.config.core_zone_threshold else "secondary",
    reasons=["최근 3회 반등이 같은 구간에서 나옴"],
    reason_codes=["support_episode_recent", "support_reaction_strong"],
    reason_context={"touch_count": touch_count, "latest_touch": latest_touch.date().isoformat()},
)
```

- [ ] **Step 6: Task 2 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zones.py -v`  
Expected: all structure zone tests pass

- [ ] **Step 7: 커밋**

```bash
git add src/tools/technical/models.py src/tools/technical/structure_zones.py tests/tools/technical/test_structure_zones.py
git commit -m "refactor: stage structure detector internals" -m "- detector 내부를 단계 함수로 분리함
- structured reason과 selection trace를 추가함
- no_clear_structure 경로를 테스트로 고정함"
```

---

## Task 3: `level_composer.py`를 유일한 V2 번역기로 만들기

**Files:**
- Modify: `src/tools/technical/level_composer.py`
- Modify: `tests/tools/technical/test_level_composer.py`

- [ ] **Step 1: V2 번역과 execution dedupe 테스트 추가**

```python
# tests/tools/technical/test_level_composer.py
from src.tools.technical.models import PriceLevel, PriceLevels, StructureZone, StructureZoneSet
from src.tools.technical.level_composer import compose_level_payload


def test_compose_level_payload_builds_v2_support_summary():
    zone = StructureZone(
        zone_type="demand",
        lower_bound=18.0,
        upper_bound=19.0,
        mid_price=18.5,
        touch_count=3,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=4.0,
        volume_reaction_score=3.0,
        confluence_score=2.0,
        total_score=13.0,
        strength="core",
        reasons=["최근 반등"],
        reason_codes=["support_episode_recent"],
    )
    zone_set = StructureZoneSet(
        demand_zones=[zone],
        supply_zones=[],
        invalidation_candidates=[zone],
        invalidation_zone=zone,
        all_candidates=[zone],
        selection_trace=[],
        no_clear_structure=False,
    )
    levels = PriceLevels(
        current_price=20.0,
        support_levels=[PriceLevel(price=18.5, type="pivot_s1", distance_pct=-7.5, description="피봇 S1")],
        resistance_levels=[],
    )

    payload = compose_level_payload(zone_set, levels)

    assert payload.structure_levels.summary_label == "support_zone"
    assert payload.structure_levels.support_zones[0].lower_bound == 18.0
    assert payload.execution_levels == []


def test_compose_level_payload_emits_no_clear_structure():
    zone_set = StructureZoneSet(no_clear_structure=True, no_clear_structure_reason_codes=["weak_signal"])
    levels = PriceLevels(current_price=20.0)

    payload = compose_level_payload(zone_set, levels)

    assert payload.structure_levels.summary_label == "no_clear_structure"
    assert "뚜렷한 박스" in payload.structure_levels.headline
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_level_composer.py -v`  
Expected: attribute mismatch for V2 fields

- [ ] **Step 3: `compose_level_payload()`가 `StructureLevelsPayloadV2`만 만들도록 변경**

```python
# src/tools/technical/level_composer.py
def compose_level_payload(
    zone_set: StructureZoneSet,
    price_levels: PriceLevels,
    atr: float | None = None,
) -> LevelPayload:
    structure_levels = _build_structure_levels_v2(zone_set)
    execution_levels = _build_execution_levels(
        price_levels=price_levels,
        protected_ranges=_protected_ranges_from_structure(structure_levels),
    )
    return LevelPayload(
        structure_levels=structure_levels,
        execution_levels=execution_levels,
        structure_summary=structure_levels.headline,
        execution_summary=_build_execution_summary(execution_levels),
    )
```

- [ ] **Step 4: execution block dedupe 규칙 반영**

```python
# src/tools/technical/level_composer.py
def _protected_ranges_from_structure(structure_levels: StructureLevelsPayloadV2) -> list[tuple[float, float]]:
    ranges = []
    if structure_levels.active_box:
        ranges.append((structure_levels.active_box.lower_bound, structure_levels.active_box.upper_bound))
    for zone in structure_levels.support_zones + structure_levels.resistance_zones:
        ranges.append((zone.lower_bound, zone.upper_bound))
    return ranges
```

- [ ] **Step 5: Task 3 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_level_composer.py -v`  
Expected: all tests pass

- [ ] **Step 6: 커밋**

```bash
git add src/tools/technical/level_composer.py tests/tools/technical/test_level_composer.py
git commit -m "feat: translate structure zones into v2 payload" -m "- level composer를 유일한 v2 번역기로 고정함
- no_clear_structure와 execution dedupe를 반영함
- v2 contract 테스트를 추가함"
```

---

## Task 4: presenter를 도입하고 CLI / LLM이 raw zone을 직접 읽지 못하게 막기

**Files:**
- Create: `src/tools/technical/structure_presentation.py`
- Modify: `src/llm/analyzer.py`
- Modify: `src/cli/main.py`
- Test: `tests/tools/technical/test_structure_presentation_adapter.py`
- Test: `tests/llm/test_analyzer.py`
- Test: `tests/cli/test_analyze_output.py`

- [ ] **Step 1: presenter 단위 테스트부터 추가**

```python
# tests/tools/technical/test_structure_presentation_adapter.py
from src.tools.technical.models import StructureLevelsPayloadV2
from src.tools.technical.structure_presentation import StructurePresentationAdapter


def test_presentation_adapter_builds_top_judgment_and_cli_blocks():
    payload = StructureLevelsPayloadV2(
        summary_label="former_supply_box",
        headline="20.00~25.00 박스 하단 이탈 이후 전환 저항이 우세",
        why="최근 반등이 같은 상단에서 거절됨",
        active_box=None,
        support_zones=[],
        resistance_zones=[],
        former_levels=[],
        invalidation=None,
        patterns_reference=[],
    )

    presented = StructurePresentationAdapter().build(payload, execution_levels=[])

    assert "현재 가장 중요한 구조" in presented.top_judgment
    assert presented.cli_blocks[0] == "## 구조 레벨"
    assert "former_supply_box" in presented.llm_context
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_structure_presentation_adapter.py -v`  
Expected: module import failure

- [ ] **Step 3: presenter 구현**

```python
# src/tools/technical/structure_presentation.py
from src.tools.technical.models import (
    ExecutionLevelView,
    StructureLevelsPayloadV2,
    StructurePresentationPayload,
)


class StructurePresentationAdapter:
    def build(
        self,
        structure_levels: StructureLevelsPayloadV2,
        execution_levels: list[ExecutionLevelView],
    ) -> StructurePresentationPayload:
        cli_blocks = [
            "## 구조 레벨",
            f"- **현재 가장 중요한 구조**: {structure_levels.summary_label}",
            f"- **headline**: {structure_levels.headline}",
            f"- **why**: {structure_levels.why}",
        ]
        if execution_levels:
            cli_blocks.extend(
                [
                    "",
                    "## 실행 레벨",
                    *[
                        f"- **{level.description}**: ${level.price:.2f} ({level.distance_pct:+.1f}%)"
                        for level in execution_levels
                    ],
                ]
            )
        llm_context = "\n".join(
            [
                f"summary_label: {structure_levels.summary_label}",
                f"headline: {structure_levels.headline}",
                f"why: {structure_levels.why}",
            ]
        )
        return StructurePresentationPayload(
            top_judgment=f"현재 가장 중요한 구조: {structure_levels.summary_label}",
            headline=structure_levels.headline,
            why=structure_levels.why,
            cli_blocks=cli_blocks,
            llm_context=llm_context,
        )
```

- [ ] **Step 4: `deep_dive.py`가 presenter를 주입받고 결과를 함께 반환하게 변경**

```python
# src/pipelines/deep_dive.py
from src.tools.technical.structure_presentation import StructurePresentationAdapter

class DeepDivePipeline:
    def __init__(
        self,
        technical_tool,
        news_tool,
        llm,
        fundamental_tool=None,
        disclosure_tool=None,
        flow_tool=None,
        structure_zone_detector=None,
        level_payload_composer=None,
        structure_presenter: StructurePresentationAdapter | None = None,
    ):
        self.structure_presenter = structure_presenter or StructurePresentationAdapter()

    async def run(self, ticker: str) -> dict:
        level_payload = self.level_payload_composer(zone_set, price_levels, atr=technical_data.snapshot.atr)
        presented_structure = self.structure_presenter.build(
            structure_levels=level_payload.structure_levels,
            execution_levels=level_payload.execution_levels,
        )
        return {
            "ticker": ticker,
            "structure_levels": level_payload.structure_levels,
            "execution_levels": level_payload.execution_levels,
            "presented_structure": presented_structure,
        }
```

- [ ] **Step 5: `analyzer.py`와 `main.py`가 presenter 출력만 읽도록 변경**

```python
# src/llm/analyzer.py
def format_structure_context_for_llm(presented_structure) -> str:
    if presented_structure is None:
        return "구조 레벨 데이터 없음"
    structure_dict = _as_dict(presented_structure)
    return structure_dict["llm_context"]
```

```python
# src/cli/main.py
def _format_structure_levels(presented_structure) -> str:
    if not presented_structure:
        return ""
    structure_dict = _to_payload_dict(presented_structure)
    return "\n".join(structure_dict["cli_blocks"]) + "\n"
```

- [ ] **Step 6: analyzer / CLI 계약 테스트 추가**

```python
# tests/llm/test_analyzer.py
def test_format_structure_context_for_llm_uses_presenter_context():
    presented = {
        "llm_context": "summary_label: support_zone\nheadline: 최근 지지 존이 우세"
    }
    assert "summary_label" in format_structure_context_for_llm(presented)
    assert "demand_zones" not in format_structure_context_for_llm(presented)
```

```python
# tests/cli/test_analyze_output.py
from datetime import datetime

from src.cli.main import format_deep_dive_output
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


def test_format_deep_dive_output_uses_presented_structure_blocks():
    snapshot = IndicatorSnapshot(price=20.0, change_pct=1.2)
    technical = TechnicalResult(
        ticker="PGY",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=100,
        strategies=[],
        overall_assessment="관망",
        confidence_score=60.0,
        key_insights=[],
        warnings=[],
    )
    result = {
        "ticker": "PGY",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {
                "summary": "중립",
                "key_insights": [],
                "recommendation": "관망",
                "confidence": 0.6,
                "rationale": "구조 확인 필요",
            },
        )(),
        "decision_summary": None,
        "factor_assessments": [],
        "scenarios": [],
        "structure_levels": None,
        "execution_levels": [],
        "presented_structure": {
            "cli_blocks": [
                "## 구조 레벨",
                "- **현재 가장 중요한 구조**: support_zone",
                "- **headline**: 최근 지지 존이 우세",
            ]
        },
    }
    output = format_deep_dive_output(result)
    assert "현재 가장 중요한 구조" in output
    assert "수요 존" not in output
```

- [ ] **Step 7: Task 4 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_structure_presentation_adapter.py tests/llm/test_analyzer.py tests/cli/test_analyze_output.py -v`  
Expected: all tests pass

- [ ] **Step 8: 커밋**

```bash
git add src/tools/technical/structure_presentation.py src/pipelines/deep_dive.py src/llm/analyzer.py src/cli/main.py tests/tools/technical/test_structure_presentation_adapter.py tests/llm/test_analyzer.py tests/cli/test_analyze_output.py
git commit -m "feat: present structure output through adapter" -m "- structure presentation adapter를 추가함
- llm과 cli가 raw zone 필드를 직접 읽지 않게 변경함
- 구조 표현 계약 테스트를 추가함"
```

---

## Task 5: regression, golden, inspector를 stable artifact 기준으로 고정

**Files:**
- Modify: `scripts/inspect_structure_zone.py`
- Modify: `src/tools/technical/structure_zone_inspector.py`
- Modify: `tests/tools/technical/test_structure_zone_regression.py`
- Create: `tests/pipelines/test_deep_dive_structure_contract.py`
- Create: `tests/cli/test_analyze_structure_golden.py`

- [ ] **Step 1: fixture acceptance와 inspector JSON 테스트를 먼저 추가**

```python
# tests/tools/technical/test_structure_zone_regression.py
def test_alab_fixture_acceptance():
    _, payload = _build_payload("ALAB")
    assert payload.structure_levels.summary_label in {"support_zone", "no_clear_structure"}
    assert payload.structure_levels.headline


def test_inspector_stable_json_has_selection_trace(tmp_path):
    artifact = build_structure_zone_artifact("ALAB")
    assert artifact["selection_trace"]
    assert "selected_label" in artifact["selection_trace"][0]
    assert "reason_codes" in artifact["selection_trace"][0]
```

```python
# tests/pipelines/test_deep_dive_structure_contract.py
import pytest


@pytest.mark.asyncio
async def test_deep_dive_returns_v2_and_presented_structure(pipeline):
    result = await pipeline.run("ALAB")
    assert result["structure_levels"].summary_label
    assert result["presented_structure"].cli_blocks
```

```python
# tests/cli/test_analyze_structure_golden.py
def test_golden_pgy_top_summary():
    result = _load_golden_fixture("PGY")
    output = format_deep_dive_output(result)
    assert "former_supply_box" in output
    assert "headline" in output
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zone_regression.py tests/pipelines/test_deep_dive_structure_contract.py tests/cli/test_analyze_structure_golden.py -v`  
Expected: missing helper / missing field failures

- [ ] **Step 3: inspector가 human-readable output과 stable JSON artifact를 둘 다 내도록 수정**

```python
# scripts/inspect_structure_zone.py
artifact = inspector.inspect(symbol=args.symbol, format="json")
if args.json_out:
    Path(args.json_out).write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
print(inspector.render_human_summary(artifact))
```

```python
# src/tools/technical/structure_zone_inspector.py
def inspect(self, symbol: str, format: str = "json") -> dict:
    df, snapshot, price_levels = self._load_fixture_inputs(symbol)
    zone_set = self.detector.detect(df, snapshot)
    payload = self.level_payload_composer(zone_set, price_levels, atr=snapshot.atr)
    return {
        "schema_version": "v2",
        "symbol": symbol,
        "summary_label": payload.structure_levels.summary_label,
        "headline": payload.structure_levels.headline,
        "selection_trace": zone_set.selection_trace,
        "selected_structure": payload.structure_levels.model_dump(),
        "execution_levels": [level.model_dump() for level in payload.execution_levels],
    }
```

- [ ] **Step 4: fixture helper를 공통화해 regression / golden / inspector가 같은 준비 코드를 쓰게 변경**

```python
# tests/tools/technical/test_structure_zone_regression.py
def build_fixture_inputs(symbol: str):
    df = _load_fixture(symbol)
    snapshot = _build_snapshot(df)
    price_levels = identify_key_levels(
        snapshot=snapshot,
        pattern_results={},
        lookback_high=float(df["High"].max()),
        lookback_low=float(df["Low"].min()),
    )
    return df, snapshot, price_levels
```

- [ ] **Step 5: 대표 fixture acceptance를 명시적으로 고정**

```python
# tests/cli/test_analyze_structure_golden.py
EXPECTED_SUMMARY = {
    "PGY": "former_supply_box",
    "NVTS": "support_zone",
    "ALAB": {"support_zone", "no_clear_structure"},
    "066970.KQ": {"active_box", "former_supply_box", "support_zone"},
}
```

- [ ] **Step 6: Task 5 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zone_regression.py tests/pipelines/test_deep_dive_structure_contract.py tests/cli/test_analyze_structure_golden.py -v`  
Expected: all tests pass

- [ ] **Step 7: 전체 phase1 회귀 실행**

Run: `uv run pytest tests/tools/technical/test_structure_zones.py tests/tools/technical/test_structure_levels_payload_v2.py tests/tools/technical/test_structure_presentation_adapter.py tests/tools/technical/test_structure_zone_regression.py tests/tools/technical/test_level_composer.py tests/pipelines/test_deep_dive_structure_contract.py tests/llm/test_analyzer.py tests/cli/test_analyze_output.py tests/cli/test_analyze_structure_golden.py -v`

Expected: full pass, no legacy `demand_zones`/`balance_zones` wording in presenter-facing tests

- [ ] **Step 8: 커밋**

```bash
git add scripts/inspect_structure_zone.py src/tools/technical/structure_zone_inspector.py tests/tools/technical/test_structure_zone_regression.py tests/pipelines/test_deep_dive_structure_contract.py tests/cli/test_analyze_structure_golden.py
git commit -m "test: lock structure reporting regression wall" -m "- inspector stable json artifact를 추가함
- fixture acceptance와 golden 테스트를 고정함
- phase1 구조 출력 회귀 기준을 정리함"
```

---

## Task 6: 문서와 2차 이관 메모 정리

**Files:**
- Modify: `docs/changes/structure-zone-reporting.md`
- Modify: `docs/adr/0006-separate-zone-pattern-and-v2-structure-payload.md`

- [ ] **Step 1: 1차 완료 시점 상태를 change record에 반영**

```markdown
## Phase 1 Delivered

1. `StructureLevelsPayloadV2` 도입
2. `StructurePresentationAdapter` 도입
3. `no_clear_structure` / selection trace / golden regression 추가

## Phase 2 Deferred

1. detector 반환 타입 V2-native 전환
2. `components/structure_zones.py` 분리
3. shared `SwingExtractor`
4. pattern/zone 엔진 실제 분리
```

- [ ] **Step 2: ADR에 1차/2차 분리 결정 추가**

```markdown
## Phase Boundary

- Phase 1: output quality fix
- Phase 2: architecture cleanup
```

- [ ] **Step 3: 문서 diff 확인**

Run: `git diff -- docs/changes/structure-zone-reporting.md docs/adr/0006-separate-zone-pattern-and-v2-structure-payload.md`

Expected: 1차 완료 범위와 2차 deferred 항목이 명확히 보임

- [ ] **Step 4: 커밋**

```bash
git add docs/changes/structure-zone-reporting.md docs/adr/0006-separate-zone-pattern-and-v2-structure-payload.md
git commit -m "docs: record phase1 structure reporting boundary" -m "- 1차와 2차 범위를 문서에 명시함
- output quality fix와 architecture cleanup 경계를 남김"
```

---

## 구현 순서 요약

1. 타입과 계약 이름부터 고정
2. detector 내부 단계 함수 분리와 structured reason 추가
3. composer를 유일한 V2 번역기로 전환
4. presenter 도입 후 CLI / LLM 연결
5. regression / golden / inspector wall 세우기
6. 문서에 1차/2차 경계 기록

---

## Self-Review

### Spec coverage
- `V2 contract`: Task 1, Task 3
- `presentation adapter`: Task 4
- `no_clear_structure`: Task 2, Task 3, Task 5
- `dedupe / selection priority`: Task 2, Task 3
- `golden / contract / inspector`: Task 5
- `2차 deferred 기록`: Task 6

### Placeholder scan
- 빈칸 표기 없음
- 각 테스트 단계에 실제 파일 경로와 명령 포함
- 각 코드 단계에 실제 클래스/함수 시그니처 포함

---

## Phase 2 Progress Update

아래 체크리스트는 Phase 1 완료 이후 실제 진행된 Phase 2 구조 개선 작업을 반영한다.

- [x] `components/structure_zones.py`로 구조 zone 구현을 분리하고 기존 `structure_zones.py`는 호환 wrapper로 유지
- [x] shared `SwingExtractor`를 추가하고 zone engine이 공통 swing 입력층을 사용하도록 연결
- [x] `PatternEngine` 경계를 추가하고 `deep_dive.py`가 직접 pattern 함수를 호출하지 않도록 정리
- [x] `touch episode` 메타데이터를 `StructureZoneSet`/inspect payload에 추가
- [x] raw touch count 중심 점수를 `episode` 기반 touch score로 전환
- [x] primary zone 선택 시 `proximity + episode recency` 우선순위를 반영
- [x] `selection_priority_trace`를 추가하고 inspector에서 읽기 쉬운 섹션으로 노출
- [x] volume profile(`POC/HVN`) overlap을 confluence score 보조 근거로 반영
- [ ] detector 반환 타입을 완전 `V2-native`로 전환하고 legacy `demand/supply/balance` 표현 제거
- [ ] `PatternEngine`이 실제로 shared swing extractor 출력을 내부 로직에서 직접 사용하도록 리팩터링
- [x] volume profile overlap 근거를 inspector 출력에 직접 표시
- [ ] fixture 기반 파라미터 스윕 / compare report 자동화로 tuning loop 완성

### Type consistency
- raw: `StructureZoneSet`
- translated: `StructureLevelsPayloadV2`
- presented: `StructurePresentationPayload`
- presenter: `StructurePresentationAdapter`

---

## 실행 후 기대 상태

- `level_composer.py`만 V2를 만든다.
- CLI / LLM은 raw zone 필드를 직접 읽지 않는다.
- `no_clear_structure`가 fixture와 golden test로 보호된다.
- inspector는 사람용 출력과 machine-stable JSON artifact를 함께 만든다.
- 2차 엔진룸 정리 항목은 문서에 남고, 1차 PR 범위에는 들어오지 않는다.
