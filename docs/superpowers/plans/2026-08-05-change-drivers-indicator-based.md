# 지표값 기반 change_drivers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jarvis check`의 "최근 점수 추이" 서술을 점수 델타 기반에서 지표값·이벤트 기반으로 바꿔 crsi Hook 롤오프 같은 유령 신호를 제거하고, 당일 발생 이벤트를 숨김 없이 노출한다.

**Architecture:** 서술(narration) 레이어만 수정한다. `ScoreHistoryPoint`에 `events` 필드를 추가하고, `scorer.py`의 `_top_component_changes`를 재작성해 연속 컴포넌트(crsi·velocity)는 지표값 변화로, 이산 컴포넌트는 점수 델타(순수 롤오프 억제)로 서술한다. 당일 이벤트는 signals 온셋으로 추출한다. 점수·verdict·컴포넌트 스코어링 로직은 불변.

**Tech Stack:** Python 3.13, pandas, pydantic v2, pytest, uv.

## Global Constraints

- 패키지 매니저는 `uv`만 사용한다(`pip` 금지). 테스트: `uv run pytest`.
- 점수·adjusted_score·technical_verdict·컴포넌트 스코어링 파일(aggregator.py, context.py, components/*.py)은 변경 금지. 서술 레이어(models.py 서술 필드, scorer.py 서술 헬퍼, quick_check.py 포맷터)만 수정.
- 코드·주석·변수명은 영어, 사용자 대면 문자열은 기존 관례(한글) 유지.
- 연속 컴포넌트 판정값(verbatim): crsi → metric 키 `crsi`, 임계값 3.0, 라벨 `cRSI`, 소수 1자리, 부호표기 없음. velocity → metric 키 `norm_slope`, 임계값 0.02, 라벨 `SMA20 기울기`, 소수 2자리, 부호표기 있음, 접미사 `%`.
- 롤오프 억제 규칙(verbatim): 이산 컴포넌트의 점수 델타는 `disappeared(전일 signals − 당일 signals)`가 비어있지 않고 `appeared(당일 − 전일)`가 비어있는 "순수 롤오프"일 때 억제한다. 그 외(당일 새 signal 발생, 또는 signal 변화 없는 조용한 점수 이동)는 유지한다.
- 당일 이벤트 정의(verbatim): 컴포넌트별로 당일 `signals` 중 전일 같은 컴포넌트 `signals`에 없던 항목(온셋). 히스토리 첫 포인트(전일 컴포넌트 없음)는 빈 리스트.

---

### Task 1: 당일 이벤트(events) 기능 — 모델 필드 + 추출 헬퍼 + 배선 + 포맷터

**Files:**
- Modify: `src/tools/technical/models.py:98` (ScoreHistoryPoint에 필드 추가)
- Modify: `src/tools/technical/scorer.py` (`_daily_events` 헬퍼 추가, `_build_score_history`에서 배선)
- Modify: `src/pipelines/quick_check.py:236-249, 266-275` (compact/detailed 포맷터에 `이벤트:` 세그먼트)
- Test: `tests/tools/technical/test_scorer.py`, `tests/pipelines/test_quick_check.py`

**Interfaces:**
- Produces: `_daily_events(previous_components: dict[str, dict] | None, current_components: dict[str, dict]) -> list[str]` (scorer.py 모듈 레벨)
- Produces: `ScoreHistoryPoint.events: list[str]` (기본값 빈 리스트)

- [ ] **Step 1: `_daily_events` 실패 테스트 작성**

`tests/tools/technical/test_scorer.py` 상단 import에 `_daily_events`를 추가한다:
```python
from src.tools.technical.scorer import (
    TechnicalScorer,
    _top_component_changes,
    _daily_events,
)
```
파일 하단에 테스트를 추가한다:
```python
def test_daily_events_returns_signal_onsets():
    previous = {
        "crsi": {"score": 10, "signals": []},
        "supertrend": {"score": -25, "signals": ["Supertrend 하락"]},
    }
    current = {
        "crsi": {"score": 20, "signals": ["cRSI Hook Up (매수 시그널)"]},
        "supertrend": {"score": -25, "signals": ["Supertrend 하락"]},
    }

    events = _daily_events(previous, current)

    assert events == ["cRSI Hook Up (매수 시그널)"]


def test_daily_events_empty_for_first_point():
    current = {"crsi": {"score": 20, "signals": ["cRSI Hook Up (매수 시그널)"]}}

    assert _daily_events(None, current) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/tools/technical/test_scorer.py::test_daily_events_returns_signal_onsets tests/tools/technical/test_scorer.py::test_daily_events_empty_for_first_point -v`
Expected: FAIL with `ImportError: cannot import name '_daily_events'`

- [ ] **Step 3: `_daily_events` 구현**

`src/tools/technical/scorer.py`의 `_top_component_changes` 함수 바로 앞(줄 199 부근)에 추가한다:
```python
def _daily_events(
    previous_components: dict[str, dict] | None,
    current_components: dict[str, dict],
) -> list[str]:
    """Signals that newly turned on today (onset vs. the prior day)."""
    if previous_components is None:
        return []
    events: list[str] = []
    for name, component in current_components.items():
        previous = previous_components.get(name, {})
        previous_signals = set(previous.get("signals") or [])
        for signal in component.get("signals") or []:
            if signal not in previous_signals:
                events.append(signal)
    return events
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_scorer.py::test_daily_events_returns_signal_onsets tests/tools/technical/test_scorer.py::test_daily_events_empty_for_first_point -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 모델 필드 추가**

`src/tools/technical/models.py`의 `ScoreHistoryPoint`에서 `change_drivers` 아래에 필드를 추가한다:
```python
    change_drivers: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
```

- [ ] **Step 6: `_build_score_history`에서 events 배선**

`src/tools/technical/scorer.py`의 `ScoreHistoryPoint(...)` 생성 부분(줄 170 부근)에서 `change_drivers=` 아래에 추가한다:
```python
                        change_drivers=_top_component_changes(
                            previous_components, daily.components
                        ),
                        events=_daily_events(previous_components, daily.components),
                        cautions=daily.technical_verdict.cautions[:2],
```

- [ ] **Step 7: compact 포맷터에 `이벤트:` 세그먼트 실패 테스트 작성**

`tests/pipelines/test_quick_check.py`에 추가한다(import 확인: `from src.pipelines.quick_check import _format_compact_history_point`):
```python
from src.pipelines.quick_check import _format_compact_history_point


def test_compact_history_shows_events_before_changes():
    point = {
        "date": "2026-07-31",
        "close": 311.23,
        "component_raw_total": -55,
        "adjusted_score": -55,
        "verdict_action": "avoid",
        "one_line_reason": "조정 점수가 -25점 미만으로 리스크 우위",
        "new_entry_allowed": False,
        "events": ["cRSI Hook Up (매수 시그널)"],
        "change_drivers": ["cRSI 32.7→38.1 상승"],
    }

    line = _format_compact_history_point(point, None)

    assert "이벤트: cRSI Hook Up (매수 시그널)" in line
    assert line.index("이벤트:") < line.index("변화:")


def test_compact_history_omits_events_segment_when_empty():
    point = {
        "date": "2026-08-03",
        "close": 321.05,
        "component_raw_total": -75,
        "adjusted_score": -75,
        "verdict_action": "avoid",
        "one_line_reason": "조정 점수가 -25점 미만으로 리스크 우위",
        "new_entry_allowed": False,
        "events": [],
        "change_drivers": ["cRSI 38.1→44.1 상승"],
    }

    line = _format_compact_history_point(point, None)

    assert "이벤트:" not in line
```

- [ ] **Step 8: 테스트 실패 확인**

Run: `uv run pytest tests/pipelines/test_quick_check.py::test_compact_history_shows_events_before_changes -v`
Expected: FAIL (`이벤트:` 문자열 없음)

- [ ] **Step 9: compact/detailed 포맷터 구현**

`src/pipelines/quick_check.py`의 `_format_compact_history_point`에서 `details = []` 아래, `changes = ...` 위에 추가한다:
```python
    details = []
    events = point.get("events") or []
    if events:
        details.append(f"이벤트: {', '.join(events)}")
    changes = point.get("change_drivers") or []
    if changes:
        details.append(f"변화: {', '.join(changes)}")
```
`_format_detailed_history_point`에서 `changes = point.get("change_drivers") or []` 위에 추가한다:
```python
    events = point.get("events") or []
    if events:
        lines.append(f"  - 이벤트: {', '.join(events)}")
    changes = point.get("change_drivers") or []
    if changes:
        lines.append(f"  - 변화: {', '.join(changes)}")
```

- [ ] **Step 10: 테스트 통과 확인**

Run: `uv run pytest tests/pipelines/test_quick_check.py -k history -v && uv run pytest tests/tools/technical/test_scorer.py -k daily_events -v`
Expected: PASS (전부)

- [ ] **Step 11: Commit**

```bash
git add src/tools/technical/models.py src/tools/technical/scorer.py src/pipelines/quick_check.py tests/tools/technical/test_scorer.py tests/pipelines/test_quick_check.py
git commit -m "feat(technical): score history에 당일 이벤트(events) 노출" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `_top_component_changes` 재작성 — 연속 지표 서술 + 롤오프 억제

**Files:**
- Modify: `src/tools/technical/scorer.py:199-233` (`_top_component_changes` 재작성, 헬퍼·레지스트리 추가)
- Test: `tests/tools/technical/test_scorer.py`

**Interfaces:**
- Consumes: 없음(모듈 내부)
- Produces: `_top_component_changes(previous_components, current_components, limit=2) -> list[str]` — 반환 형식: 이산 드라이버(`"{name} {delta:+d} {개선/악화}"` 상위 `limit`개 + 필요 시 `"기타 {delta:+d} {개선/악화}"`)를 앞에, 연속 드라이버 문자열을 뒤에 이어붙인 리스트.
- Produces 헬퍼(모듈 레벨): `_continuous_value(name, component) -> float | None`, `_format_continuous(name, prev_val, cur_val) -> str | None`, `_is_pure_rolloff(previous, current) -> bool`, 상수 `_CONTINUOUS_COMPONENTS: dict[str, dict]`.

- [ ] **Step 1: 연속 지표 서술 실패 테스트 작성**

`tests/tools/technical/test_scorer.py`에 추가한다:
```python
def test_change_drivers_narrate_crsi_value_not_score_delta():
    previous = {
        "crsi": {
            "score": 20,
            "signals": ["cRSI Hook Up (매수 시그널)"],
            "metrics": {"crsi": 38.1},
        },
        "supertrend": {"score": -25, "signals": ["Supertrend 하락"]},
    }
    current = {
        "crsi": {"score": 0, "signals": [], "metrics": {"crsi": 44.1}},
        "supertrend": {"score": -25, "signals": ["Supertrend 하락"]},
    }

    changes = _top_component_changes(previous, current)

    assert "cRSI 38.1→44.1 상승" in changes
    assert not any("crsi" in c and "악화" in c for c in changes)


def test_change_drivers_crsi_below_threshold_is_silent():
    previous = {"crsi": {"score": 0, "signals": [], "metrics": {"crsi": 40.0}}}
    current = {"crsi": {"score": 0, "signals": [], "metrics": {"crsi": 41.5}}}

    assert _top_component_changes(previous, current) == []


def test_change_drivers_velocity_sign_flip():
    previous = {"velocity": {"score": -10, "signals": [], "metrics": {"norm_slope": -0.10}}}
    current = {"velocity": {"score": 15, "signals": ["상승 전환점"], "metrics": {"norm_slope": 0.05}}}

    changes = _top_component_changes(previous, current)

    assert "SMA20 기울기 -0.10%→+0.05% 상승전환" in changes


def test_change_drivers_suppress_pure_rolloff():
    previous = {
        "supertrend": {
            "score": 35,
            "signals": ["Supertrend 상승", "Supertrend 매수 전환"],
        }
    }
    current = {"supertrend": {"score": 20, "signals": ["Supertrend 상승"]}}

    assert _top_component_changes(previous, current) == []


def test_change_drivers_keep_delta_on_new_signal():
    previous = {"supertrend": {"score": 20, "signals": ["Supertrend 상승"]}}
    current = {
        "supertrend": {
            "score": 35,
            "signals": ["Supertrend 상승", "Supertrend 매수 전환"],
        }
    }

    changes = _top_component_changes(previous, current)

    assert changes == ["supertrend +15 개선"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/tools/technical/test_scorer.py -k "narrate_crsi or below_threshold or velocity_sign or pure_rolloff or new_signal" -v`
Expected: FAIL (연속 서술/억제 미구현)

- [ ] **Step 3: 레지스트리·헬퍼·재작성 구현**

`src/tools/technical/scorer.py`에서 기존 `_top_component_changes`(줄 199-221)를 아래로 교체하고, 그 앞에 상수·헬퍼를 추가한다:
```python
# Components whose score is driven by a continuous indicator value.
# Narrate the actual indicator move instead of the score delta so that
# one-time event bonuses (e.g. cRSI Hook) don't create phantom "악화/개선".
_CONTINUOUS_COMPONENTS: dict[str, dict] = {
    "crsi": {
        "metric": "crsi",
        "label": "cRSI",
        "threshold": 3.0,
        "decimals": 1,
        "signed": False,
        "suffix": "",
    },
    "velocity": {
        "metric": "norm_slope",
        "label": "SMA20 기울기",
        "threshold": 0.02,
        "decimals": 2,
        "signed": True,
        "suffix": "%",
    },
}


def _continuous_value(name: str, component: dict) -> float | None:
    spec = _CONTINUOUS_COMPONENTS.get(name)
    if spec is None:
        return None
    metrics = component.get("metrics") or {}
    value = metrics.get(spec["metric"])
    return float(value) if value is not None else None


def _format_continuous(name: str, prev_val: float, cur_val: float) -> str | None:
    spec = _CONTINUOUS_COMPONENTS[name]
    delta = cur_val - prev_val
    sign_flip = (prev_val < 0 < cur_val) or (prev_val > 0 > cur_val)
    if abs(delta) < spec["threshold"] and not sign_flip:
        return None
    if sign_flip:
        direction = "상승전환" if cur_val > prev_val else "하락전환"
    else:
        direction = "상승" if delta > 0 else "하락"
    decimals = spec["decimals"]
    fmt = f"{{:+.{decimals}f}}" if spec["signed"] else f"{{:.{decimals}f}}"
    suffix = spec["suffix"]
    prev_text = fmt.format(prev_val) + suffix
    cur_text = fmt.format(cur_val) + suffix
    return f"{spec['label']} {prev_text}→{cur_text} {direction}"


def _is_pure_rolloff(previous: dict, current: dict) -> bool:
    previous_signals = set(previous.get("signals") or [])
    current_signals = set(current.get("signals") or [])
    disappeared = previous_signals - current_signals
    appeared = current_signals - previous_signals
    return bool(disappeared) and not appeared


def _top_component_changes(
    previous_components: dict[str, dict] | None,
    current_components: dict[str, dict],
    limit: int = 2,
) -> list[str]:
    if previous_components is None:
        return []
    previous_scores = _component_scores(previous_components)
    current_scores = _component_scores(current_components)
    component_names = set(previous_scores) | set(current_scores)

    continuous: list[str] = []
    discrete_changes: list[tuple[str, int]] = []

    for name in component_names:
        previous = previous_components.get(name, {})
        current = current_components.get(name, {})

        if name in _CONTINUOUS_COMPONENTS:
            prev_val = _continuous_value(name, previous)
            cur_val = _continuous_value(name, current)
            if prev_val is not None and cur_val is not None:
                driver = _format_continuous(name, prev_val, cur_val)
                if driver is not None:
                    continuous.append(driver)
                continue  # metrics present → continuous track owns this component

        delta = current_scores.get(name, 0) - previous_scores.get(name, 0)
        if delta == 0:
            continue
        if _is_pure_rolloff(previous, current):
            continue
        discrete_changes.append((name, delta))

    discrete_changes.sort(key=lambda item: (-abs(item[1]), item[0]))
    selected = discrete_changes[:limit]
    remaining_delta = sum(delta for _, delta in discrete_changes[limit:])
    formatted = [f"{name} {delta:+d} {_change_label(delta)}" for name, delta in selected]
    if remaining_delta:
        formatted.append(f"기타 {remaining_delta:+d} {_change_label(remaining_delta)}")
    formatted.extend(continuous)
    return formatted
```

- [ ] **Step 4: 새 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_scorer.py -k "narrate_crsi or below_threshold or velocity_sign or pure_rolloff or new_signal" -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 기존 테스트 회귀 확인**

Run: `uv run pytest tests/tools/technical/test_scorer.py -v`
Expected: PASS (기존 `test_score_history_change_drivers_use_component_delta`, `..._deterministic_for_ties` 포함 전부 통과 — 두 테스트 모두 이산 컴포넌트만 쓰고 metrics 없어 fallback으로 기존 동작 유지)

- [ ] **Step 6: Commit**

```bash
git add src/tools/technical/scorer.py tests/tools/technical/test_scorer.py
git commit -m "feat(technical): change_drivers를 지표값 기반 서술 + 롤오프 억제로 재작성" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 시나리오 통합 테스트 + 실제 실행 검증

**Files:**
- Test: `tests/tools/technical/test_scorer.py`

**Interfaces:**
- Consumes: `_top_component_changes`, `_daily_events` (Task 1·2 산출물)

- [ ] **Step 1: ALAB 시나리오 통합 테스트 작성**

`tests/tools/technical/test_scorer.py`에 추가한다. 실측(point-in-time) 값을 손으로 고정해 3일 서술을 검증한다:
```python
def test_alab_scenario_removes_crsi_phantom_and_shows_events():
    # 7/31: cRSI Hook Up 발생, cRSI 32.7→38.1
    d0731_prev = {
        "crsi": {"score": 10, "signals": [], "metrics": {"crsi": 32.7}},
        "supertrend": {"score": -25, "signals": ["Supertrend 하락"]},
        "minervini": {"score": -20, "signals": []},
    }
    d0731 = {
        "crsi": {
            "score": 20,
            "signals": ["cRSI Hook Up (매수 시그널)"],
            "metrics": {"crsi": 38.1},
        },
        "supertrend": {"score": -25, "signals": ["Supertrend 하락"]},
        "minervini": {"score": -20, "signals": []},
    }
    # 8/03: Hook Up 롤오프(점수 20→0), cRSI 38.1→44.1 계속 상승
    d0803 = {
        "crsi": {"score": 0, "signals": [], "metrics": {"crsi": 44.1}},
        "supertrend": {"score": -25, "signals": ["Supertrend 하락"]},
        "minervini": {"score": -20, "signals": []},
    }
    # 8/04: Supertrend 매수 전환, minervini 강세 전환
    d0804 = {
        "crsi": {"score": 0, "signals": [], "metrics": {"crsi": 52.9}},
        "supertrend": {
            "score": 40,
            "signals": ["Supertrend 상승", "Supertrend 매수 전환"],
        },
        "minervini": {"score": 25, "signals": []},
    }

    # 7/31: 이벤트 Hook Up, 변화 cRSI 상승, crsi 악화 없음
    ev_0731 = _daily_events(d0731_prev, d0731)
    ch_0731 = _top_component_changes(d0731_prev, d0731)
    assert ev_0731 == ["cRSI Hook Up (매수 시그널)"]
    assert "cRSI 32.7→38.1 상승" in ch_0731
    assert not any("악화" in c for c in ch_0731)

    # 8/03: 이벤트 없음, 롤오프 억제, 지표 상승만
    ev_0803 = _daily_events(d0731, d0803)
    ch_0803 = _top_component_changes(d0731, d0803)
    assert ev_0803 == []
    assert ch_0803 == ["cRSI 38.1→44.1 상승"]

    # 8/04: 이벤트 Supertrend 매수 전환, 이산 개선 서술
    ev_0804 = _daily_events(d0803, d0804)
    ch_0804 = _top_component_changes(d0803, d0804)
    assert ev_0804 == ["Supertrend 상승", "Supertrend 매수 전환"]
    assert "supertrend +65 개선" in ch_0804
    assert "minervini +45 개선" in ch_0804
```

- [ ] **Step 2: 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/test_scorer.py::test_alab_scenario_removes_crsi_phantom_and_shows_events -v`
Expected: PASS

- [ ] **Step 3: 전체 기술 테스트 회귀 확인**

Run: `uv run pytest tests/tools/technical/ tests/pipelines/test_quick_check.py -q`
Expected: PASS (전부)

- [ ] **Step 4: 실제 CLI 실행 검증**

Run: `uv run jarvis check ALAB`
Expected: "최근 점수 추이"에서 (a) 8/3 줄에 `crsi ... 악화`가 사라지고 지표 상승 서술이 나오며, (b) 이벤트가 있는 날 `이벤트:` 세그먼트가 표시됨. 실제 출력 몇 줄을 확인하고, 값은 데이터 최신성에 따라 달라질 수 있으므로 "악화 유령 제거 + 이벤트 노출" 여부만 판정한다.

- [ ] **Step 5: Commit**

```bash
git add tests/tools/technical/test_scorer.py
git commit -m "test(technical): ALAB 시나리오로 crsi 유령 제거·이벤트 노출 고정" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- 트랙 1(당일 이벤트) → Task 1 (`_daily_events`, `events` 필드, `이벤트:` 포맷터). ✓
- 트랙 2(연속 지표 crsi·velocity) → Task 2 (`_CONTINUOUS_COMPONENTS`, `_format_continuous`). ✓
- 트랙 3(이산 롤오프 억제) → Task 2 (`_is_pure_rolloff`). ✓
- 출력 예시(7/31·8/3·8/4) → Task 3 시나리오 테스트. ✓
- 변경 범위(models/scorer/quick_check만, 스코어링 불변) → Global Constraints + 각 Task Files. ✓
- 테스트(단위·시나리오) → Task 1·2·3. 골든은 네트워크 의존 대신 point-in-time 실측값을 손으로 고정한 hermetic 시나리오 테스트로 대체(내부 서술 로직이라 외부 API 계약 골든 불필요; CLAUDE.md 테스트 원칙은 외부 금융 API 대상). ✓

**2. Placeholder scan:** "TBD/TODO/적절히" 등 없음. 모든 코드 스텝에 완전한 코드 포함. ✓

**3. Type consistency:** `_daily_events`/`_top_component_changes`/`_continuous_value`/`_format_continuous`/`_is_pure_rolloff` 시그니처가 Task 간 일치. `ScoreHistoryPoint.events: list[str]`가 모델·배선·포맷터·테스트에서 동일. `_component_scores`·`_change_label`은 기존 함수 재사용(정의 존재 확인 완료). ✓
