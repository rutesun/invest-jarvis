# Structure Zone Level Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jarvis analyze`의 지지/저항 표현을 `구조 zone + 실행 line` 구조로 바꾸고, 동일한 계약을 pipeline/LLM/CLI/테스트가 공유하게 만든다.

**Architecture:** 기존 `price_levels.py`는 실행 레벨 수집기로 유지하고, 새 `StructureZoneDetector`가 3년 데이터 기준 구조 zone을 계산한다. `DeepDivePipeline`은 두 결과를 함께 조합해 LLM과 CLI에 전달하고, 회귀 테스트는 고정 CSV fixture와 artifact 저장으로 튜닝 가능하게 만든다.

**Tech Stack:** Python 3.12, pandas, Pydantic, Rich, pytest, uv

---

## 파일 구조

### 기존 코드 재사용
- `src/tools/technical/price_levels.py` - 기존 pivot / ATR / MA / fib / pattern breakout 수집 로직을 그대로 실행 레벨 수집기로 재사용
- `src/pipelines/deep_dive.py` - technical/news/fundamental/disclosure/flow 수집과 LLM 호출 오케스트레이션을 유지
- `src/llm/analyzer.py` - actionable signal prompt와 price level 포맷팅 지점 재사용
- `src/cli/main.py` - `analyze` 최종 렌더링 지점 재사용
- `tests/tools/technical/test_price_levels.py` - 실행 레벨 회귀 테스트의 출발점으로 재사용
- `tests/pipelines/test_deep_dive.py`, `tests/cli/test_analyze_output.py`, `tests/llm/test_analyzer.py` - 통합 계약 검증에 재사용

### 새로 만드는 파일
- `src/tools/technical/structure_zones.py` - swing 후보 추출, zone 폭 계산, clustering, scoring, invalidation 선택
- `src/tools/technical/level_composer.py` - 구조/실행 레벨을 최종 payload로 조합
- `tests/tools/technical/test_structure_zones.py` - detector 단위 테스트
- `tests/tools/technical/test_level_composer.py` - composer 계약 테스트
- `tests/tools/technical/test_structure_zone_regression.py` - CSV fixture 기반 회귀 테스트
- `scripts/export_structure_zone_fixtures.py` - 3년 가격 CSV fixture 생성 스크립트

### 수정하는 파일
- `src/tools/technical/models.py` - `StructureZone`, `StructureZoneSet`, `StructureZoneConfig`, `ZoneTestArtifact` 추가
- `src/tools/technical/price_levels.py` - 실행 레벨 상위 선택 helper 추가
- `src/tools/technical/__init__.py` - 새 detector/composer export 정리
- `src/llm/analyzer.py` - 구조/실행 분리 payload 포맷팅과 actionable signal 입력 변경
- `src/pipelines/deep_dive.py` - detector/composer 호출, 결과 반환, rollout 비교 포인트 추가
- `src/cli/main.py` - 구조 레벨 / 실행 레벨 렌더링 섹션 추가
- `tests/tools/technical/test_price_levels.py` - 실행 레벨 선택 테스트 추가
- `tests/pipelines/test_deep_dive.py` - 새 payload 계약 테스트 추가
- `tests/cli/test_analyze_output.py` - 구조/실행 분리 출력 테스트 추가
- `tests/llm/test_analyzer.py` - 새 prompt 입력 포맷 테스트 추가
- `docs/CLI_USAGE.md` - `analyze` 출력 구조 설명 반영

---

## Task 1: 구조 zone 계약과 데이터 모델 고정

**Files:**
- Modify: `src/tools/technical/models.py`
- Modify: `src/tools/technical/__init__.py`
- Create: `tests/tools/technical/test_structure_zones.py`

- [ ] **Step 1: 새 모델 계약 테스트를 먼저 추가**

```python
# tests/tools/technical/test_structure_zones.py
from src.tools.technical.models import (
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
    ZoneTestArtifact,
)


def test_structure_zone_set_keeps_invalidation_candidates():
    zone = StructureZone(
        zone_type="demand",
        lower_bound=100.0,
        upper_bound=105.0,
        mid_price=102.5,
        touch_count=3,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=3.0,
        volume_reaction_score=2.0,
        confluence_score=1.0,
        total_score=10.0,
        strength="core",
        reasons=["반복 터치"],
    )

    zone_set = StructureZoneSet(
        demand_zones=[zone],
        supply_zones=[],
        invalidation_candidates=[zone],
        invalidation_zone=zone,
        all_candidates=[zone],
    )

    assert zone_set.invalidation_candidates[0].zone_type == "demand"


def test_zone_test_artifact_has_schema_version():
    artifact = ZoneTestArtifact(
        schema_version="v1",
        symbol="ALAB",
        csv_path="tests/fixtures/technical/structure_zones/ALAB.csv",
        params={"top_n_per_side": 2},
        candidates=[],
        selected_zones=[],
        score_breakdown=[],
    )

    assert artifact.schema_version == "v1"


def test_structure_zone_config_defaults_are_explicit():
    config = StructureZoneConfig()

    assert config.top_n_per_side == 5
    assert config.min_zone_width_pct > 0
```

- [ ] **Step 2: 모델 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zones.py -v`  
Expected: `ImportError` or `AttributeError` for new structure zone models

- [ ] **Step 3: `models.py`에 구조 zone 모델을 추가**

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


class StructureZoneSet(BaseModel):
    demand_zones: list[StructureZone] = Field(default_factory=list)
    supply_zones: list[StructureZone] = Field(default_factory=list)
    invalidation_candidates: list[StructureZone] = Field(default_factory=list)
    invalidation_zone: StructureZone | None = None
    all_candidates: list[StructureZone] = Field(default_factory=list)


class StructureZoneConfig(BaseModel):
    lookback_days: int = 756
    atr_width_multiplier: float = 0.8
    min_zone_width_pct: float = 0.01
    max_zone_width_pct: float = 0.05
    recent_window_days: int = 60
    mid_window_days: int = 180
    volume_baseline_window: int = 20
    top_n_per_side: int = 5
    score_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "touch": 0.35,
            "recency": 0.20,
            "volume": 0.30,
            "confluence": 0.15,
        }
    )


class ZoneTestArtifact(BaseModel):
    schema_version: str
    symbol: str
    csv_path: str
    params: dict
    candidates: list[dict]
    selected_zones: list[dict]
    score_breakdown: list[dict]
```

- [ ] **Step 4: export 정리**

```python
# src/tools/technical/__init__.py
from src.tools.technical.models import (
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
    ZoneTestArtifact,
)
```

- [ ] **Step 5: Task 1 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zones.py -v`  
Expected: `3 passed`

- [ ] **Step 6: 커밋**

```bash
git add src/tools/technical/models.py src/tools/technical/__init__.py tests/tools/technical/test_structure_zones.py
git commit -m "feat(technical): add structure zone contracts" -m "- 구조 zone 데이터 모델을 추가함
- invalidation 후보와 artifact schema version 계약을 고정함
- 구조 zone 기본 모델 테스트를 추가함"
```

---

## Task 2: detector 코어와 점수 계산 구현

**Files:**
- Create: `src/tools/technical/structure_zones.py`
- Modify: `tests/tools/technical/test_structure_zones.py`

- [ ] **Step 1: 폭 계산, clustering, 최근성 점수 테스트 추가**

```python
# tests/tools/technical/test_structure_zones.py
import pandas as pd

from src.tools.technical.models import IndicatorSnapshot, StructureZoneConfig
from src.tools.technical.structure_zones import (
    StructureZoneDetector,
    calculate_zone_half_width,
    cluster_price_candidates,
)


def test_calculate_zone_half_width_respects_pct_floor_and_ceiling():
    width = calculate_zone_half_width(price=100.0, atr=1.0, config=StructureZoneConfig())

    assert width >= 1.0
    assert width <= 5.0


def test_cluster_price_candidates_groups_nearby_swings():
    clusters = cluster_price_candidates([100.0, 101.0, 118.0], half_width=2.0)

    assert clusters == [[100.0, 101.0], [118.0]]


def test_detector_sorts_demand_zones_by_total_score():
    dates = pd.date_range("2025-01-01", periods=220, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100 + (i % 5) for i in range(220)],
            "High": [102 + (i % 5) for i in range(220)],
            "Low": [98 + (i % 5) for i in range(220)],
            "Close": [100 + (i % 5) for i in range(220)],
            "Volume": [1_000_000 + i * 1000 for i in range(220)],
        },
        index=dates,
    )
    snapshot = IndicatorSnapshot(price=104.0, change_pct=1.0, atr=3.0, sma_150=95.0)

    result = StructureZoneDetector().detect(df, snapshot)

    assert result.demand_zones == sorted(
        result.demand_zones,
        key=lambda zone: zone.total_score,
        reverse=True,
    )
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zones.py -v`  
Expected: `ModuleNotFoundError: No module named 'src.tools.technical.structure_zones'`

- [ ] **Step 3: detector 골격 구현**

```python
# src/tools/technical/structure_zones.py
from __future__ import annotations

import pandas as pd

from src.tools.technical.models import (
    IndicatorSnapshot,
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
)


def calculate_zone_half_width(price: float, atr: float | None, config: StructureZoneConfig) -> float:
    atr_width = (atr or 0.0) * config.atr_width_multiplier
    min_width = price * config.min_zone_width_pct
    max_width = price * config.max_zone_width_pct
    return min(max(atr_width, min_width), max_width)


def cluster_price_candidates(prices: list[float], half_width: float) -> list[list[float]]:
    if not prices:
        return []
    clusters: list[list[float]] = [[sorted(prices)[0]]]
    for price in sorted(prices)[1:]:
        if abs(price - clusters[-1][-1]) <= half_width:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return clusters


class StructureZoneDetector:
    def __init__(self, config: StructureZoneConfig | None = None):
        self.config = config or StructureZoneConfig()

    def detect(self, df: pd.DataFrame, snapshot: IndicatorSnapshot) -> StructureZoneSet:
        candidates = self._build_candidates(df, snapshot)
        demand = [zone for zone in candidates if zone.zone_type == "demand"]
        supply = [zone for zone in candidates if zone.zone_type == "supply"]
        return StructureZoneSet(
            demand_zones=sorted(demand, key=lambda zone: zone.total_score, reverse=True)[
                : self.config.top_n_per_side
            ],
            supply_zones=sorted(supply, key=lambda zone: zone.total_score, reverse=True)[
                : self.config.top_n_per_side
            ],
            invalidation_candidates=[],
            invalidation_zone=None,
            all_candidates=candidates,
        )
```

- [ ] **Step 4: swing 후보 추출과 점수 계산 최소 구현**

```python
# src/tools/technical/structure_zones.py
    def _build_candidates(self, df: pd.DataFrame, snapshot: IndicatorSnapshot) -> list[StructureZone]:
        recent = df.tail(self.config.lookback_days).copy()
        recent["rolling_low"] = recent["Low"].rolling(window=5, center=True).min()
        recent["rolling_high"] = recent["High"].rolling(window=5, center=True).max()

        low_rows = recent[recent["Low"] == recent["rolling_low"]].tail(12)
        high_rows = recent[recent["High"] == recent["rolling_high"]].tail(12)

        return [
            *self._build_side_zones(low_rows, "demand", snapshot),
            *self._build_side_zones(high_rows, "supply", snapshot),
        ]
```

- [ ] **Step 5: detector 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_structure_zones.py -v`  
Expected: detector 관련 새 테스트 통과, 기존 모델 테스트 유지

- [ ] **Step 6: 커밋**

```bash
git add src/tools/technical/structure_zones.py tests/tools/technical/test_structure_zones.py
git commit -m "feat(technical): add structure zone detector core" -m "- zone 폭 계산과 clustering 로직을 추가함
- swing 기반 구조 zone detector 골격을 구현함
- detector 단위 테스트를 추가함"
```

---

## Task 3: invalidation 규칙과 composer 계약 구현

**Files:**
- Create: `src/tools/technical/level_composer.py`
- Modify: `src/tools/technical/structure_zones.py`
- Modify: `src/tools/technical/price_levels.py`
- Create: `tests/tools/technical/test_level_composer.py`
- Modify: `tests/tools/technical/test_price_levels.py`

- [ ] **Step 1: invalidation과 실행 레벨 선택 테스트부터 추가**

```python
# tests/tools/technical/test_level_composer.py
from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.models import PriceLevel, PriceLevels, StructureZone, StructureZoneSet


def test_compose_level_payload_prefers_structure_then_execution():
    demand = StructureZone(
        zone_type="demand",
        lower_bound=200.0,
        upper_bound=205.0,
        mid_price=202.5,
        touch_count=4,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=4.0,
        volume_reaction_score=3.0,
        confluence_score=2.0,
        total_score=13.0,
        strength="core",
        reasons=["반복 지지"],
    )
    zone_set = StructureZoneSet(
        demand_zones=[demand],
        supply_zones=[],
        invalidation_candidates=[demand],
        invalidation_zone=demand,
        all_candidates=[demand],
    )
    price_levels = PriceLevels(
        current_price=210.0,
        support_levels=[
            PriceLevel(price=205.0, type="pivot_s1", distance_pct=-2.3, description="피봇 지지1"),
            PriceLevel(price=198.0, type="sma_50", distance_pct=-5.7, description="50일선"),
        ],
        resistance_levels=[
            PriceLevel(price=218.0, type="pivot_r1", distance_pct=3.8, description="피봇 저항1"),
        ],
    )

    payload = compose_level_payload(zone_set, price_levels)

    assert payload["structure_levels"]["demand_zones"][0] == "200.00~205.00"
    assert payload["execution_levels"][0]["type"] == "pivot_s1"
    assert payload["structure_levels"]["invalidation"] == "200.00 하향 이탈"
```

```python
# tests/tools/technical/test_price_levels.py
from src.tools.technical.price_levels import select_execution_levels


def test_select_execution_levels_prefers_nearest_priority_levels():
    levels = PriceLevels(
        current_price=200.0,
        support_levels=[
            PriceLevel(price=198.0, type="pivot_s1", distance_pct=-1.0, description="피봇"),
            PriceLevel(price=195.0, type="atr_support_1x", distance_pct=-2.5, description="ATR"),
        ],
        resistance_levels=[
            PriceLevel(price=203.0, type="sma_20", distance_pct=1.5, description="20일선"),
            PriceLevel(price=205.0, type="fib_0.382", distance_pct=2.5, description="피보나치"),
        ],
    )

    selected = select_execution_levels(levels, max_count=3)

    assert [item.type for item in selected] == ["pivot_s1", "sma_20", "atr_support_1x"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/tools/technical/test_level_composer.py tests/tools/technical/test_price_levels.py -v`  
Expected: `ModuleNotFoundError` for composer and `AttributeError` for `select_execution_levels`

- [ ] **Step 3: invalidation 선택 규칙 구현**

```python
# src/tools/technical/structure_zones.py
    def choose_invalidation_zone(
        self,
        demand_zones: list[StructureZone],
        snapshot: IndicatorSnapshot,
    ) -> tuple[list[StructureZone], StructureZone | None]:
        candidates: list[StructureZone] = []
        if demand_zones:
            candidates.append(demand_zones[0])
        if snapshot.sma_150:
            candidates.append(
                StructureZone(
                    zone_type="invalidation",
                    lower_bound=snapshot.sma_150,
                    upper_bound=snapshot.sma_150,
                    mid_price=snapshot.sma_150,
                    touch_count=0,
                    last_touch_date=None,
                    touch_score=0.0,
                    recency_score=0.0,
                    volume_reaction_score=0.0,
                    confluence_score=1.0,
                    total_score=1.0,
                    strength="secondary",
                    reasons=["150일선 fallback"],
                )
            )
        selected = candidates[0] if candidates else None
        return candidates, selected
```

- [ ] **Step 4: composer와 실행 레벨 helper 추가**

```python
# src/tools/technical/price_levels.py
def select_execution_levels(levels: PriceLevels, max_count: int = 3) -> list[PriceLevel]:
    priority_order = {"pivot": 0, "sma": 1, "atr": 2, "fib": 3, "pattern": 4, "swing": 5}
    all_levels = [*levels.support_levels, *levels.resistance_levels]
    return sorted(
        all_levels,
        key=lambda level: (
            abs(level.distance_pct),
            priority_order.get(level.type.split("_")[0], 9),
        ),
    )[:max_count]
```

```python
# src/tools/technical/level_composer.py
from src.tools.technical.models import PriceLevels, StructureZoneSet
from src.tools.technical.price_levels import select_execution_levels


def _format_zone(zone) -> str:
    return f"{zone.lower_bound:.2f}~{zone.upper_bound:.2f}"


def compose_level_payload(zone_set: StructureZoneSet, price_levels: PriceLevels) -> dict:
    execution_levels = select_execution_levels(price_levels, max_count=3)
    invalidation = None
    if zone_set.invalidation_zone:
        invalidation = f"{zone_set.invalidation_zone.lower_bound:.2f} 하향 이탈"

    return {
        "structure_levels": {
            "demand_zones": [_format_zone(zone) for zone in zone_set.demand_zones[:2]],
            "supply_zones": [_format_zone(zone) for zone in zone_set.supply_zones[:2]],
            "invalidation": invalidation,
        },
        "execution_levels": [
            {
                "type": level.type,
                "description": level.description,
                "price": level.price,
                "distance_pct": level.distance_pct,
            }
            for level in execution_levels
        ],
    }
```

- [ ] **Step 5: Task 3 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_level_composer.py tests/tools/technical/test_price_levels.py -v`  
Expected: 새 composer/selection 테스트 통과, 기존 `test_price_levels.py` 유지

- [ ] **Step 6: 커밋**

```bash
git add src/tools/technical/structure_zones.py src/tools/technical/level_composer.py src/tools/technical/price_levels.py tests/tools/technical/test_level_composer.py tests/tools/technical/test_price_levels.py
git commit -m "feat(technical): compose structure and execution levels" -m "- 구조 무효화 선택 규칙을 추가함
- 실행 레벨 상위 선택 helper를 구현함
- 구조/실행 payload 조합 로직과 테스트를 추가함"
```

---

## Task 4: pipeline, LLM, CLI를 새 계약으로 연결

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Modify: `src/llm/analyzer.py`
- Modify: `src/cli/main.py`
- Modify: `tests/pipelines/test_deep_dive.py`
- Modify: `tests/llm/test_analyzer.py`
- Modify: `tests/cli/test_analyze_output.py`

- [ ] **Step 1: pipeline과 analyzer 계약 테스트 추가**

```python
# tests/pipelines/test_deep_dive.py
@pytest.mark.asyncio
async def test_deep_dive_pipeline_returns_structure_and_execution_levels(
    mock_technical_tool, mock_news_tool, mock_llm
):
    with (
        patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
        patch("src.pipelines.deep_dive.StructureZoneDetector") as mock_detector_cls,
        patch("src.pipelines.deep_dive.compose_level_payload") as mock_compose,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["상승 추세"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.8,
            key_themes=["AI 수요"],
            summary="긍정적",
            impact_assessment="우호적",
        )
        mock_signal.return_value = ActionableSignalOutput(
            action="관망",
            timing="조정_대기",
            signal_strength=7,
            headline="구조는 상방, 추격은 보류",
            primary_reason="구조 수요 구간은 유효하지만 단기 저항 근접",
            supporting_reasons=[],
            risks=[],
            confidence=0.7,
        )
        mock_detector_cls.return_value.detect.return_value = StructureZoneSet(
            demand_zones=[],
            supply_zones=[],
            invalidation_candidates=[],
            invalidation_zone=None,
            all_candidates=[],
        )
        mock_compose.return_value = {
            "structure_levels": {"demand_zones": ["200.00~205.00"], "supply_zones": [], "invalidation": None},
            "execution_levels": [{"type": "pivot_s1", "description": "피봇 지지1", "price": 205.0, "distance_pct": -1.0}],
        }

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )

    result = await pipeline.run("AAPL")

    assert "structure_levels" in result
    assert "execution_levels" in result
    assert result["structure_levels"]["demand_zones"] == ["200.00~205.00"]
```

```python
# tests/llm/test_analyzer.py
from src.llm.analyzer import format_structure_context_for_llm


def test_format_structure_context_for_llm_lists_structure_then_execution():
    context = format_structure_context_for_llm(
        structure_levels={
            "demand_zones": ["200.00~205.00"],
            "supply_zones": ["220.00~224.00"],
            "invalidation": "200.00 하향 이탈",
        },
        execution_levels=[
            {"type": "pivot_s1", "description": "피봇 지지1", "price": 205.0, "distance_pct": -1.0},
            {"type": "sma_50", "description": "50일선", "price": 198.0, "distance_pct": -4.0},
        ],
    )

    assert "구조 레벨" in context
    assert "실행 레벨" in context
    assert "200.00~205.00" in context
    assert "피봇 지지1" in context
```

```python
# tests/cli/test_analyze_output.py
def test_format_deep_dive_output_shows_structure_and_execution_sections():
    snapshot = IndicatorSnapshot(price=210.0, change_pct=1.5, rsi=61.0)
    technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=88,
        strategies=[],
        overall_assessment="중립",
        confidence_score=0.7,
        key_insights=[],
        warnings=[],
    )
    result = {
        "ticker": "AAPL",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {"summary": "강세", "key_insights": [], "recommendation": "매수", "confidence": 0.7, "rationale": "좋음"},
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="technical",
            core_variables=["구조 수요 구간 유지"],
            action="관망",
            timing="조정_대기",
            action_sentence="지금 추격보다 눌림 확인이 유리",
        ),
        "factor_assessments": [],
        "scenarios": [],
        "structure_levels": {"demand_zones": ["200.00~205.00"], "supply_zones": ["220.00~224.00"], "invalidation": "200.00 하향 이탈"},
        "execution_levels": [{"type": "pivot_s1", "description": "피봇 지지1", "price": 205.0, "distance_pct": -1.0}],
    }

    output = format_deep_dive_output(result)

    assert "## 구조 레벨" in output
    assert "## 실행 레벨" in output
    assert "200.00~205.00" in output
    assert "피봇 지지1" in output
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/pipelines/test_deep_dive.py tests/llm/test_analyzer.py tests/cli/test_analyze_output.py -v`  
Expected: 새 키/시그니처/렌더링 섹션 부재로 실패

- [ ] **Step 3: pipeline 통합**

```python
# src/pipelines/deep_dive.py
from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.structure_zones import StructureZoneDetector

zone_detector = StructureZoneDetector()
zone_set = zone_detector.detect(df, technical_data.snapshot)
level_payload = compose_level_payload(zone_set, price_levels)

actionable_signal = await analyzer.generate_actionable_signal(
    ticker=ticker,
    technical_summary=f"{technical_summary.summary}\n\n{technical_summary.rationale}",
    chart_patterns=chart_patterns,
    price_levels=price_levels,
    structure_levels=level_payload["structure_levels"],
    execution_levels=level_payload["execution_levels"],
    llm=self.llm,
)

return {
    "ticker": ticker,
    "technical": technical_data,
    "technical_summary": technical_summary,
    "decision_summary": decision_bundle.summary,
    "factor_assessments": decision_bundle.factor_assessments,
    "scenarios": decision_bundle.scenarios,
    "structure_levels": level_payload["structure_levels"],
    "execution_levels": level_payload["execution_levels"],
    "actionable_signal": actionable_signal,
}
```

- [ ] **Step 4: analyzer와 CLI 포맷터 수정**

```python
# src/llm/analyzer.py
def format_structure_context_for_llm(structure_levels: dict, execution_levels: list[dict]) -> str:
    lines = ["구조 레벨:"]
    for zone in structure_levels.get("demand_zones", []):
        lines.append(f"- 수요 구간: {zone}")
    for zone in structure_levels.get("supply_zones", []):
        lines.append(f"- 공급 구간: {zone}")
    if structure_levels.get("invalidation"):
        lines.append(f"- 구조 무효화: {structure_levels['invalidation']}")
    lines.append("")
    lines.append("실행 레벨:")
    for level in execution_levels:
        lines.append(
            f"- {level['description']}: ${level['price']:.2f} ({level['distance_pct']:+.1f}%)"
        )
    return "\n".join(lines)


async def generate_actionable_signal(
    ticker: str,
    technical_summary: str,
    chart_patterns: dict[str, ChartPatternResult],
    price_levels: PriceLevels,
    structure_levels: dict,
    execution_levels: list[dict],
    news_analysis: str | None = None,
    fundamental_summary: str | None = None,
    llm: BaseChatModel | None = None,
) -> ActionableSignalOutput:
    structure_context = format_structure_context_for_llm(structure_levels, execution_levels)
```

```python
# src/cli/main.py
def _format_structure_levels(result: dict) -> str:
    structure = result.get("structure_levels") or {}
    lines = ["## 구조 레벨", ""]
    for label in structure.get("demand_zones", []):
        lines.append(f"- **수요 구간**: {label}")
    for label in structure.get("supply_zones", []):
        lines.append(f"- **공급 구간**: {label}")
    if structure.get("invalidation"):
        lines.append(f"- **구조 무효화**: {structure['invalidation']}")
    lines.append("")
    return "\n".join(lines)


def _format_execution_levels(result: dict) -> str:
    execution_levels = result.get("execution_levels") or []
    lines = ["## 실행 레벨", ""]
    for item in execution_levels:
        lines.append(
            f"- **{item['description']}**: ${item['price']:.2f} ({item['distance_pct']:+.1f}%)"
        )
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 5: 통합 테스트 재실행**

Run: `uv run pytest tests/pipelines/test_deep_dive.py tests/llm/test_analyzer.py tests/cli/test_analyze_output.py -v`  
Expected: 새 계약 테스트 통과, 기존 judgment-first 테스트 유지

- [ ] **Step 6: 커밋**

```bash
git add src/pipelines/deep_dive.py src/llm/analyzer.py src/cli/main.py tests/pipelines/test_deep_dive.py tests/llm/test_analyzer.py tests/cli/test_analyze_output.py
git commit -m "feat(analyze): wire structure zone output into pipeline" -m "- deep_dive에 구조/실행 레벨 payload를 연결함
- actionable signal 입력을 구조 zone 기준으로 확장함
- CLI 출력에 구조 레벨과 실행 레벨 섹션을 추가함"
```

---

## Task 5: CSV fixture 회귀 테스트와 artifact 저장 경로 추가

**Files:**
- Create: `scripts/export_structure_zone_fixtures.py`
- Create: `tests/tools/technical/test_structure_zone_regression.py`
- Create: `tests/fixtures/technical/structure_zones/033100.KQ.csv`
- Create: `tests/fixtures/technical/structure_zones/066970.KQ.csv`
- Create: `tests/fixtures/technical/structure_zones/ALAB.csv`
- Modify: `docs/CLI_USAGE.md`

- [ ] **Step 1: fixture export 스크립트 테스트 요구사항을 먼저 적기**

```python
# tests/tools/technical/test_structure_zone_regression.py
from pathlib import Path

import pandas as pd

from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.models import IndicatorSnapshot
from src.tools.technical.price_levels import identify_key_levels
from src.tools.technical.structure_zones import StructureZoneDetector


def test_structure_zone_regression_from_csv_fixture(tmp_path: Path):
    csv_path = Path("tests/fixtures/technical/structure_zones/ALAB.csv")
    df = pd.read_csv(csv_path, index_col="Date", parse_dates=["Date"])
    snapshot = IndicatorSnapshot(price=float(df["Close"].iloc[-1]), change_pct=0.0, atr=5.0, sma_150=180.0)

    zone_set = StructureZoneDetector().detect(df, snapshot)
    price_levels = identify_key_levels(snapshot=snapshot, pattern_results={}, lookback_high=df["High"].max(), lookback_low=df["Low"].min())
    payload = compose_level_payload(zone_set, price_levels)

    assert len(payload["structure_levels"]["demand_zones"]) <= 2
    assert len(payload["structure_levels"]["supply_zones"]) <= 2
```

- [ ] **Step 2: export 스크립트 구현**

```python
# scripts/export_structure_zone_fixtures.py
from __future__ import annotations

import asyncio
from pathlib import Path

from src.providers.yfinance_provider import YFinanceProvider


TICKERS = {
    "033100.KQ": "tests/fixtures/technical/structure_zones/033100.KQ.csv",
    "066970.KQ": "tests/fixtures/technical/structure_zones/066970.KQ.csv",
    "ALAB": "tests/fixtures/technical/structure_zones/ALAB.csv",
}


async def main() -> None:
    provider = YFinanceProvider()
    for ticker, out_path in TICKERS.items():
        df = await provider.get_price_history(ticker, period="3y")
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: fixture CSV 생성**

Run: `uv run python scripts/export_structure_zone_fixtures.py`  
Expected: `tests/fixtures/technical/structure_zones/033100.KQ.csv`, `066970.KQ.csv`, `ALAB.csv` 생성

- [ ] **Step 4: artifact 저장 규칙 추가**

```python
# tests/tools/technical/test_structure_zone_regression.py
import json
from pathlib import Path

import pandas as pd

from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.models import IndicatorSnapshot
from src.tools.technical.price_levels import identify_key_levels
from src.tools.technical.structure_zones import StructureZoneDetector


def test_structure_zone_regression_writes_artifact(tmp_path: Path):
    csv_path = Path("tests/fixtures/technical/structure_zones/ALAB.csv")
    df = pd.read_csv(csv_path, index_col="Date", parse_dates=["Date"])
    snapshot = IndicatorSnapshot(price=float(df["Close"].iloc[-1]), change_pct=0.0, atr=5.0, sma_150=180.0)
    zone_set = StructureZoneDetector().detect(df, snapshot)
    price_levels = identify_key_levels(
        snapshot=snapshot,
        pattern_results={},
        lookback_high=df["High"].max(),
        lookback_low=df["Low"].min(),
    )
    payload = compose_level_payload(zone_set, price_levels)

    artifact_dir = Path("artifacts/structure_zones")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "ALAB-regression.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "symbol": "ALAB",
                "params": {"top_n_per_side": 2},
                "selected_zones": payload["structure_levels"],
                "execution_levels": payload["execution_levels"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    assert artifact_path.exists()
```

- [ ] **Step 5: 회귀 테스트와 문서 업데이트**

```markdown
<!-- docs/CLI_USAGE.md -->
### `jarvis analyze`

출력 순서:
1. 판단 요약
2. 구조 레벨
3. 실행 레벨
4. 팩터 분류 / 시나리오 / 원시 데이터

구조 레벨은 장기 구조 구간이고, 실행 레벨은 pivot / MA / ATR / fib 기반 단기 실행 보조선이다.
```

- [ ] **Step 6: 회귀 테스트 실행**

Run: `uv run pytest tests/tools/technical/test_structure_zone_regression.py -v`  
Expected: fixture 기반 회귀 테스트 통과, `artifacts/structure_zones/*.json` 생성

- [ ] **Step 7: 커밋**

```bash
git add scripts/export_structure_zone_fixtures.py tests/tools/technical/test_structure_zone_regression.py tests/fixtures/technical/structure_zones/033100.KQ.csv tests/fixtures/technical/structure_zones/066970.KQ.csv tests/fixtures/technical/structure_zones/ALAB.csv docs/CLI_USAGE.md
git commit -m "test(technical): add structure zone regression fixtures" -m "- 3년 가격 CSV fixture 생성 스크립트를 추가함
- 구조 zone 회귀 테스트와 artifact 저장 경로를 추가함
- analyze 출력 구조 문서를 업데이트함"
```

---

## 최종 검증

- [ ] `uv run pytest tests/tools/technical/test_structure_zones.py tests/tools/technical/test_level_composer.py tests/tools/technical/test_price_levels.py -v`
- [ ] `uv run pytest tests/pipelines/test_deep_dive.py tests/llm/test_analyzer.py tests/cli/test_analyze_output.py -v`
- [ ] `uv run pytest tests/tools/technical/test_structure_zone_regression.py -v`
- [ ] `uv run jarvis analyze ALAB` 실행 후 `구조 레벨` / `실행 레벨` / `구조 무효화` 출력 확인

## 플랜 자가 점검

- spec의 4개 보강점이 모두 plan task에 매핑된다.
  - 제품 성공 기준: Task 4, Task 5
  - 출력 계약: Task 1, Task 3, Task 4
  - invalidation / conflict handling: Task 3
  - rollout / artifact / latency: Task 5 + 최종 검증
- placeholder 문구 없이 실제 파일과 명령으로 작성했다.
- 구현 순서는 `계약 → detector → composer → 통합 → fixture`라서 중간마다 테스트 가능한 상태를 만든다.
