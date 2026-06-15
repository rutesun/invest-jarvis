# Analyze Bull/Bear 논쟁 종합 판정 Implementation Plan (플랜 B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 펀더멘털·기술·플레이북의 모든 신호를 규칙으로 Bull/Bear 증거 장부에 분류하고, LLM 2콜(변론 + 독립 판사)로 단일 종합 판정을 생성한다. 기존 veto/integrated/actionable 결론은 제거한다.

**Architecture (레이어 경계 — spec §3.0):**
- **Pipeline** = `src/pipelines/debate/` — 증거 장부(ledger, 결정적)와 논쟁 엔진(engine, LLM 조율). deep_dive가 호출.
- **LLM** = `src/llm/models.py`·`analyzer.py` — debate I/O 모델·콜.
- **CLI** = `src/cli/analyze_render.py` — 종합 판정 렌더. 플랜 A가 만든 `format_deep_dive_output`의 debate 삽입 지점을 **한 줄 Edit**으로 채운다(재작성 안 함 → 충돌 없음).
- **전제**: 플랜 A 완료. `momentum_events`(Event 섹션 표시용)와 `analyze_render.py`가 이미 존재한다.

**Tech Stack:** Python 3.12, pydantic v2, langchain (with_structured_output), pytest, uv

**전제 설계:** `docs/superpowers/specs/2026-06-15-analyze-overhaul-design.md` §7-10.

---

## File Structure

| 파일 | 역할 | 신규/수정 |
|------|------|-----------|
| `src/llm/models.py` | Debate I/O 모델 추가, Integrated/Actionable 제거 | 수정 |
| `src/pipelines/debate/__init__.py` | 패키지 | 신규 |
| `src/pipelines/debate/models.py` | Evidence, BullBearLedger, DebateBundle | 신규 |
| `src/pipelines/debate/ledger.py` | build_evidence_ledger, compute_action_space | 신규 |
| `src/pipelines/debate/engine.py` | run_debate (LLM 2콜) | 신규 |
| `src/pipelines/debate/grounding.py` | 변론 grounding 검증 헬퍼 | 신규 |
| `src/llm/analyzer.py` | run_debate_advocacy/judge 추가, integrated/actionable 제거 | 수정 |
| `src/pipelines/deep_dive.py` | debate 배선, veto/integrated/actionable 제거 | 수정 |
| `src/cli/analyze_render.py` | 종합 판정 섹션 (debate 삽입 + ledger fallback) | 수정 |
| `src/cli/main.py` | actionable 패널 제거 | 수정 |
| `src/pipelines/analyze_decision.py` | apply_playbook_veto 삭제 | 수정 |
| `tests/pipelines/debate/*`, `tests/llm/test_debate_analyzer.py` | 테스트 | 신규 |

**중복 제거 (확정 — spec §4.2, §7):**
- `canslim_L` 제외 (entry/holding 모두): gate_C 및 rs_magnitude가 RS 담당
- `canslim_M` **entry만 제외**: gate_A와 동일 시장레짐. holding은 게이트가 없으므로 M 유지(시장레짐 반영)
- `factor_flow` 제외: flow 행과 중복
- `accumulation`은 `canslim_I`로만 라우팅(weight 1). 스펙의 별도 weight-2 행은 두지 않음 — 이중카운트 방지(캘리브레이션 시 재검토)
- `momentum_events`(MACD크로스·RSI다이버전스·RS전환·가격사건)는 **장부 증거에서 제외**. Event 섹션 표시용(플랜 A). 게이트·CAN SLIM·팩터가 같은 기저 신호를 이미 점수화

---

## Task 1: LLM 논쟁 I/O 모델

> ⚠️ 이 task를 **가장 먼저** 실행한다 (debate/models.py가 여기 정의를 import).

**Files:**
- Modify: `src/llm/models.py` (끝에 추가 — `ActionableSignalOutput` 다음)
- Test: `tests/pipelines/debate/test_debate_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/pipelines/debate/__init__.py  (빈 파일)
# tests/pipelines/debate/test_debate_schema.py
def _walk_no_open_dict(schema: dict, path="root"):
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" not in schema:
            raise AssertionError(f"open dict at {path}")
        for k, v in schema.items():
            _walk_no_open_dict(v, f"{path}.{k}")
    elif isinstance(schema, list):
        for i, v in enumerate(schema):
            _walk_no_open_dict(v, f"{path}[{i}]")


def test_debate_output_models_are_strict():
    from src.llm.models import DebateAdvocacyOutput, DebateVerdictOutput
    _walk_no_open_dict(DebateAdvocacyOutput.model_json_schema())
    _walk_no_open_dict(DebateVerdictOutput.model_json_schema())


def test_debate_case_fields():
    from src.llm.models import DebateCase
    case = DebateCase(stance="bull", thesis="강세", points=["근거1", "근거2"])
    assert case.stance == "bull"
    assert len(case.points) == 2
```

- [ ] **Step 2: Run** `uv run pytest tests/pipelines/debate/test_debate_schema.py -v` → FAIL ("cannot import name 'DebateAdvocacyOutput'")

- [ ] **Step 3: Implement** (`src/llm/models.py` 끝에 추가)

```python
class DebateCase(BaseModel):
    """한 진영의 변론."""

    stance: str  # "bull" | "bear"
    thesis: str
    points: list[str]


class DebateAdvocacyInput(BaseModel):
    """변론 콜 입력 — list[dict]는 입력에만 허용."""

    ticker: str
    mode: str  # "entry" | "holding"
    bull_evidence: list[dict]  # [{headline, detail}]
    bear_evidence: list[dict]


class DebateAdvocacyOutput(BaseModel):
    """변론 콜 출력 — 전부 타입 확정 (strict-schema)."""

    bull_case: DebateCase
    bear_case: DebateCase


class DebateJudgeInput(BaseModel):
    """판사 콜 입력."""

    ticker: str
    mode: str
    bull_case: DebateCase
    bear_case: DebateCase
    bull_weight: float
    bear_weight: float
    allowed_actions: list[str]


class DebateVerdictOutput(BaseModel):
    """판사 콜 출력 — 단일 평결."""

    action: str
    confidence: float
    swing_factor: str
    reconciliation: str
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(llm): add debate advocacy/judge I/O models`

---

## Task 2: 장부 모델

**Files:**
- Create: `src/pipelines/debate/__init__.py`, `src/pipelines/debate/models.py`
- Test: `tests/pipelines/debate/test_models.py`

- [ ] **Step 1: Test**

```python
# tests/pipelines/debate/test_models.py
def test_ledger_weight_sums():
    from src.pipelines.debate.models import BullBearLedger, Evidence

    ledger = BullBearLedger(
        mode="entry",
        bull=[Evidence(side="bull", key="gate_A", weight=4.0, headline="h", detail="d", source="playbook")],
        bear=[Evidence(side="bear", key="gate_E", weight=3.0, headline="h", detail="d", source="playbook")],
        neutral=[], bull_weight=4.0, bear_weight=3.0, action_space=["매수", "관망"],
    )
    assert ledger.bull_weight == 4.0
    assert ledger.action_space == ["매수", "관망"]
```

- [ ] **Step 2: Run** → FAIL ("No module named 'src.pipelines.debate'")

- [ ] **Step 3: Implement**

```python
# src/pipelines/debate/__init__.py  (빈 파일)
```

```python
# src/pipelines/debate/models.py
from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm.models import DebateCase, DebateVerdictOutput


class Evidence(BaseModel):
    side: str  # "bull" | "bear" | "neutral"
    key: str
    weight: float  # 0~5
    headline: str
    detail: str
    source: str  # "playbook" | "factor" | "flow" | "technical"


class BullBearLedger(BaseModel):
    mode: str  # "entry" | "holding"
    bull: list[Evidence] = Field(default_factory=list)
    bear: list[Evidence] = Field(default_factory=list)
    neutral: list[Evidence] = Field(default_factory=list)
    bull_weight: float = 0.0
    bear_weight: float = 0.0
    action_space: list[str] = Field(default_factory=list)


class DebateBundle(BaseModel):
    ledger: BullBearLedger
    bull_case: DebateCase
    bear_case: DebateCase
    verdict: DebateVerdictOutput
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(debate): add ledger and bundle models`

---

## Task 3: 증거 장부 빌더 — entry (canslim_M/L·factor_flow·momentum 제외)

**Files:**
- Create: `src/pipelines/debate/ledger.py`
- Test: `tests/pipelines/debate/test_ledger_entry.py`

- [ ] **Step 1: Test**

```python
# tests/pipelines/debate/test_ledger_entry.py
from src.pipelines.analyze_decision import FactorAssessment
from src.tools.criteria.models import (
    CanslimResult, ElementVerdict, GateCheck, GateResult,
    MarketRegimeResult, PlaybookVerdict, RelativeStrengthResult,
)


def _verdict(mansfield=2.1):
    gate = GateResult(
        passed=True,
        checklist=[
            GateCheck(name="A", required=True, met=True, reason="시장환경=상승"),
            GateCheck(name="B", required=True, met=True, reason="is_stage2=1.0"),
            GateCheck(name="C", required=True, met=True, reason="RS=True, 업종강세=True"),
            GateCheck(name="E", required=True, met=False, reason="breakout=False"),
        ],
        quality_grade="B", veto_reason=None,
    )
    canslim = CanslimResult(
        c=ElementVerdict(met=True, detail="EPS +42%"), a=ElementVerdict(met=True, detail="CAGR +28%"),
        n=ElementVerdict(met=False, detail="촉매 없음"), s=ElementVerdict(met=True, detail="거래량"),
        l=ElementVerdict(met=True, detail="RS 강세"), i=ElementVerdict(met=False, detail="분산 우세"),
        m=ElementVerdict(met=True, detail="상승장"),
    )
    return PlaybookVerdict(
        ticker="TEST", holding=False,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(mansfield_rs=mansfield, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC"),
        sector_strength=None, canslim=canslim, gate=gate, position_plan=None, exit_verdict=None, headline="t",
    )


def test_entry_ledger_routing_and_exclusions():
    from src.pipelines.debate.ledger import build_evidence_ledger

    factors = [
        FactorAssessment(factor_type="flow", role="참고", freshness_score=2, magnitude_score=2,
                         actionability_score=2, total_score=6, summary="s", role_reason="r", evidence=[], bias="bullish"),
        FactorAssessment(factor_type="technical", role="주도", freshness_score=4, magnitude_score=4,
                         actionability_score=4, total_score=12, summary="s", role_reason="r", evidence=[], bias="bullish"),
    ]
    ledger = build_evidence_ledger(
        playbook_verdict=_verdict(), factor_assessments=factors, snapshot=None, flow=None, mode="entry",
    )
    keys = {e.key for e in ledger.bull + ledger.bear + ledger.neutral}
    assert "gate_A" in keys and "gate_E" in keys
    assert "canslim_L" not in keys  # gate_C 중복
    assert "canslim_M" not in keys  # gate_A 중복 (entry)
    assert "factor_flow" not in keys  # flow 행 중복
    assert "factor_technical" in keys
    assert "rs_magnitude" in {e.key for e in ledger.bull}
    assert ledger.bull_weight > ledger.bear_weight
```

- [ ] **Step 2: Run** → FAIL ("No module named 'src.pipelines.debate.ledger'")

- [ ] **Step 3: Implement**

```python
# src/pipelines/debate/ledger.py
from __future__ import annotations

from src.pipelines.debate.models import BullBearLedger, Evidence

_GATE_WEIGHTS = {"A": 4.0, "B": 4.0, "C": 4.0, "E": 3.0}
_CANSLIM_ENTRY = {"c": "분기 EPS", "a": "연간 CAGR", "n": "신요소", "s": "수급", "i": "기관매집"}  # L, M 제외
_CANSLIM_HOLDING = {**_CANSLIM_ENTRY, "m": "시장"}  # 게이트 없으니 M 포함 (L은 rs_magnitude 중복으로 제외)
_FACTOR_LABELS = {"technical": "기술", "valuation": "밸류", "event": "이벤트"}  # flow 제외


def _add(buckets: dict, ev: Evidence) -> None:
    buckets[ev.side].append(ev)


def build_evidence_ledger(*, playbook_verdict, factor_assessments, snapshot, flow, mode: str) -> BullBearLedger:
    """기존 판정 결과를 bull/bear/neutral 로 분류·채점. 순수 함수, 새 데이터 안 만듦.
    momentum_events 는 증거가 아니다(Event 섹션 표시용)."""
    buckets: dict[str, list[Evidence]] = {"bull": [], "bear": [], "neutral": []}

    # 게이트 (entry 전용)
    if mode == "entry" and playbook_verdict is not None and playbook_verdict.gate is not None:
        for check in playbook_verdict.gate.checklist:
            if check.name not in _GATE_WEIGHTS:
                continue
            _add(buckets, Evidence(
                side="bull" if check.met is True else "bear", key=f"gate_{check.name}",
                weight=_GATE_WEIGHTS[check.name], headline=f"게이트 {check.name}",
                detail=check.reason, source="playbook",
            ))

    # CAN SLIM (mode 별 라벨셋 — L 항상 제외, M은 holding 만)
    if playbook_verdict is not None and playbook_verdict.canslim is not None:
        labels = _CANSLIM_ENTRY if mode == "entry" else _CANSLIM_HOLDING
        cs = playbook_verdict.canslim
        for attr, label in labels.items():
            v = getattr(cs, attr)
            side = "bull" if v.met is True else "bear" if v.met is False else "neutral"
            _add(buckets, Evidence(side=side, key=f"canslim_{attr.upper()}", weight=1.0,
                                   headline=f"CAN SLIM {attr.upper()} {label}", detail=v.detail or "—", source="playbook"))

    # rs_magnitude (연속값)
    if playbook_verdict is not None and playbook_verdict.relative_strength is not None:
        rs = playbook_verdict.relative_strength.mansfield_rs
        if rs != 0:
            _add(buckets, Evidence(side="bull" if rs > 0 else "bear", key="rs_magnitude",
                                   weight=min(abs(rs) / 10.0, 3.0), headline="상대강도 크기",
                                   detail=f"Mansfield RS={rs:+.2f}", source="playbook"))

    # flow (factor_flow 제외, 이 행만)
    if flow is not None:
        foreign = getattr(flow, "foreign_direction_5d", "N/A")
        inst = getattr(flow, "institution_direction_5d", "N/A")
        if foreign == "매수" or inst == "매수":
            _add(buckets, Evidence(side="bull", key="flow", weight=2.0, headline="수급",
                                   detail=f"외인 5일 {foreign} / 기관 5일 {inst}", source="flow"))

    # factor_assessments (flow 제외)
    for fa in factor_assessments or []:
        if fa.factor_type not in _FACTOR_LABELS:
            continue
        side = "bull" if fa.bias == "bullish" else "bear" if fa.bias == "bearish" else "neutral"
        _add(buckets, Evidence(side=side, key=f"factor_{fa.factor_type}", weight=min(fa.total_score / 3.0, 5.0),
                               headline=fa.headline or f"{_FACTOR_LABELS[fa.factor_type]} 팩터",
                               detail=fa.summary, source="factor"))

    # rsi_overbought (단방향 하드 신호)
    if snapshot is not None:
        rsi = getattr(snapshot, "rsi", None)
        if rsi is not None and rsi >= 80:
            _add(buckets, Evidence(side="bear", key="rsi_overbought", weight=2.0,
                                   headline="RSI 과매수", detail=f"RSI={rsi:.1f} ≥ 80", source="technical"))

    # holding: exit signals + r_cushion
    if mode == "holding" and playbook_verdict is not None:
        ev = getattr(playbook_verdict, "exit_verdict", None)
        if ev is not None:
            sw = {"strong": 5.0, "medium": 3.0, "weak": 1.0}
            for sig in ev.signals:
                _add(buckets, Evidence(side="bear", key=f"exit_{sig.code}", weight=sw.get(sig.severity, 1.0),
                                       headline=f"매도신호 {sig.code}", detail=sig.detail, source="playbook"))
            if ev.current_r is not None and ev.current_r != 0:
                _add(buckets, Evidence(side="bull" if ev.current_r > 0 else "bear", key="r_cushion",
                                       weight=min(abs(ev.current_r), 3.0), headline="R 쿠션",
                                       detail=f"current_r={ev.current_r:.2f}", source="playbook"))

    return BullBearLedger(
        mode=mode, bull=buckets["bull"], bear=buckets["bear"], neutral=buckets["neutral"],
        bull_weight=round(sum(e.weight for e in buckets["bull"]), 2),
        bear_weight=round(sum(e.weight for e in buckets["bear"]), 2),
        action_space=compute_action_space(playbook_verdict, mode),
    )


def compute_action_space(playbook_verdict, mode: str) -> list[str]:
    """하드 리스크 가드레일 — 판사의 허용 액션 제한."""
    if playbook_verdict is None:
        return ["매수", "관망"] if mode == "entry" else ["보유", "비중축소", "청산"]
    if mode == "entry":
        regime = getattr(playbook_verdict, "market_regime", None)
        if regime is not None and regime.allow_new_buy is False:
            return ["관망"]
        return ["매수", "관망"]
    ev = getattr(playbook_verdict, "exit_verdict", None)
    if ev is not None:
        if any(s.severity == "strong" for s in ev.signals) or ev.action == "liquidate":
            return ["청산", "비중축소"]
        if sum(1 for s in ev.signals if s.severity == "medium") >= 1:  # 1개 이상은 같은 버킷
            return ["비중축소", "보유"]
    return ["보유", "비중축소"]
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(debate): entry ledger with dedup (canslim_M/L, factor_flow, momentum excluded)`

---

## Task 4: 장부 holding + action_space 테스트

**Files:**
- Test: `tests/pipelines/debate/test_ledger_holding.py`, `tests/pipelines/debate/test_action_space.py`

- [ ] **Step 1: Test**

```python
# tests/pipelines/debate/test_ledger_holding.py
from src.tools.criteria.models import (
    CanslimResult, ElementVerdict, ExitSignal, ExitVerdict,
    MarketRegimeResult, PlaybookVerdict, RelativeStrengthResult,
)


def _holding(signals, action="hold", current_r=None):
    cs = CanslimResult(c=ElementVerdict(met=True), a=ElementVerdict(met=True), n=ElementVerdict(met=True),
                       s=ElementVerdict(met=True), l=ElementVerdict(met=True), i=ElementVerdict(met=True),
                       m=ElementVerdict(met=True))
    return PlaybookVerdict(
        ticker="T", holding=True,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(mansfield_rs=1.0, outperform_6m=5.0, rp_slope_4w=0.1, index_symbol="^GSPC"),
        sector_strength=None, canslim=cs, gate=None, position_plan=None,
        exit_verdict=ExitVerdict(action=action, signals=signals, current_r=current_r, trailing_stop=None, detail="d"),
        headline="t",
    )


def test_holding_routes_exit_and_keeps_canslim_m():
    from src.pipelines.debate.ledger import build_evidence_ledger

    signals = [ExitSignal(code="SMA_LONG", severity="strong", detail="종가<SMA200")]
    ledger = build_evidence_ledger(playbook_verdict=_holding(signals, action="liquidate"),
                                   factor_assessments=[], snapshot=None, flow=None, mode="holding")
    keys = {e.key for e in ledger.bull + ledger.bear}
    assert "exit_SMA_LONG" in keys
    assert "canslim_M" in keys  # holding 은 게이트 없으니 M 유지
    assert "canslim_L" not in keys  # L 은 항상 제외
    assert not any(k.startswith("gate_") for k in keys)
    assert next(e for e in ledger.bear if e.key == "exit_SMA_LONG").weight == 5.0
```

```python
# tests/pipelines/debate/test_action_space.py
from src.tools.criteria.models import (
    ExitSignal, ExitVerdict, MarketRegimeResult, PlaybookVerdict, RelativeStrengthResult,
)
from src.pipelines.debate.ledger import compute_action_space


def _v(regime_allow=True, exit_signals=None, exit_action="hold", holding=False):
    return PlaybookVerdict(
        ticker="T", holding=holding,
        market_regime=MarketRegimeResult(regime="상승" if regime_allow else "하락", allow_new_buy=regime_allow, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(mansfield_rs=1.0, outperform_6m=5.0, rp_slope_4w=0.1, index_symbol="^GSPC"),
        sector_strength=None, canslim=None, gate=None, position_plan=None,
        exit_verdict=(ExitVerdict(action=exit_action, signals=exit_signals or [], current_r=None, trailing_stop=None, detail="d") if holding else None),
        headline="t",
    )


def test_bear_market_entry_only_watch():
    assert compute_action_space(_v(regime_allow=False), "entry") == ["관망"]


def test_two_medium_not_more_permissive_than_one():
    two = [ExitSignal(code="SMA_SHORT", severity="medium", detail="d"),
           ExitSignal(code="DISTRIBUTION", severity="medium", detail="d")]
    assert compute_action_space(_v(exit_signals=two, holding=True), "holding") == ["비중축소", "보유"]


def test_strong_exit_no_add():
    s = [ExitSignal(code="SMA_LONG", severity="strong", detail="d")]
    assert compute_action_space(_v(exit_signals=s, exit_action="liquidate", holding=True), "holding") == ["청산", "비중축소"]


def test_none_verdict_graceful():
    assert compute_action_space(None, "entry") == ["매수", "관망"]
```

- [ ] **Step 2: Run** `uv run pytest tests/pipelines/debate/test_ledger_holding.py tests/pipelines/debate/test_action_space.py -v` → PASS (Task 3 구현이 holding·med&gt;=1 처리)

- [ ] **Step 3: Fix if needed** (실패 시 Task 3의 `_CANSLIM_HOLDING`·`medium >= 1` 확인)

- [ ] **Step 4: Re-run** → PASS  **Step 5: Commit** `test(debate): holding routing and action space guardrails`

---

## Task 5: 변론 + 판사 LLM 함수

**Files:**
- Modify: `src/llm/analyzer.py`
- Test: `tests/llm/test_debate_analyzer.py`

- [ ] **Step 1: Test**

```python
# tests/llm/test_debate_analyzer.py
import pytest

from src.llm.models import (
    DebateAdvocacyInput, DebateAdvocacyOutput, DebateCase, DebateJudgeInput, DebateVerdictOutput,
)


class _Chain:
    def __init__(self, out): self._out = out
    async def ainvoke(self, _): return self._out


class _Pipe:
    def __init__(self, out): self._out = out
    def __ror__(self, _prompt): return _Chain(self._out)


class _LLM:
    def __init__(self, adv, ver): self._adv, self._ver = adv, ver
    def with_structured_output(self, model):
        return _Pipe(self._adv if model is DebateAdvocacyOutput else self._ver)


@pytest.mark.asyncio
async def test_run_debate_advocacy():
    from src.llm.analyzer import run_debate_advocacy
    adv = DebateAdvocacyOutput(bull_case=DebateCase(stance="bull", thesis="강세", points=["p"]),
                               bear_case=DebateCase(stance="bear", thesis="약세", points=["q"]))
    out = await run_debate_advocacy(
        DebateAdvocacyInput(ticker="T", mode="entry", bull_evidence=[{"headline": "게이트 A", "detail": "상승장"}], bear_evidence=[]),
        _LLM(adv, None))
    assert out.bull_case.thesis == "강세"


@pytest.mark.asyncio
async def test_run_debate_judge():
    from src.llm.analyzer import run_debate_judge
    ver = DebateVerdictOutput(action="매수", confidence=0.72, swing_factor="VCP", reconciliation="bull 우세")
    out = await run_debate_judge(
        DebateJudgeInput(ticker="T", mode="entry", bull_case=DebateCase(stance="bull", thesis="t", points=["p"]),
                         bear_case=DebateCase(stance="bear", thesis="t", points=["q"]),
                         bull_weight=12.0, bear_weight=4.0, allowed_actions=["매수", "관망"]),
        _LLM(None, ver))
    assert out.action in ["매수", "관망"]
```

- [ ] **Step 2: Run** → FAIL ("cannot import name 'run_debate_advocacy'")

- [ ] **Step 3: Implement** (`src/llm/analyzer.py` 끝에 추가; import 블록에 debate 모델 추가)

```python
async def run_debate_advocacy(input_data: DebateAdvocacyInput, llm) -> DebateAdvocacyOutput:
    """① 변론 콜: bull/bear 각자 자기 장부 증거만 인용."""

    def _fmt(ev: list[dict]) -> str:
        return "\n".join(f"- {e['headline']}: {e['detail']}" for e in ev) if ev else "(증거 없음)"

    prompt = ChatPromptTemplate.from_messages([
        ("system", "너는 주식 분석 토론의 변론가다. Bull/Bear 각 진영 변론을 작성한다.\n"
                   "규칙: 각 진영은 자기 측 증거만 인용. 상대/중립 증거 인용 금지. 숫자·사실 환각 금지. 한국어로 간결히."),
        ("human", "종목: {ticker} (모드: {mode})\n\n[Bull 증거]\n{bull_evidence}\n\n[Bear 증거]\n{bear_evidence}\n\n"
                  "각 진영 thesis(한 줄)와 points(근거)를 작성. 증거 없는 진영은 thesis='해당 없음', points=[]."),
    ])
    chain = prompt | llm.with_structured_output(DebateAdvocacyOutput)
    return await chain.ainvoke({
        "ticker": input_data.ticker, "mode": input_data.mode,
        "bull_evidence": _fmt(input_data.bull_evidence), "bear_evidence": _fmt(input_data.bear_evidence),
    })


async def run_debate_judge(input_data: DebateJudgeInput, llm) -> DebateVerdictOutput:
    """② 판사 콜: 양측 변론 + 가중치 + 허용 액션 → 단일 평결."""

    def _fmt_case(c) -> str:
        pts = "\n".join(f"  - {p}" for p in c.points) or "  (없음)"
        return f"thesis: {c.thesis}\n{pts}"

    prompt = ChatPromptTemplate.from_messages([
        ("system", "너는 중립적 주식 분석 판사다. 변론과 증거 가중치를 읽고 단일 평결을 내린다.\n"
                   "규칙: action 은 반드시 allowed_actions 중에서만 선택(리스크 가드레일). 변론 합리화 말고 증거 우위로 판단. "
                   "reconciliation 에 결론 근거와, 가드레일이 액션을 제한했다면 그 이유도 적어라. 한국어로."),
        ("human", "종목: {ticker} (모드: {mode})\n\n[Bull 변론] (가중치 {bull_weight})\n{bull_case}\n\n"
                  "[Bear 변론] (가중치 {bear_weight})\n{bear_case}\n\n허용 액션: {allowed_actions}\n\n"
                  "action, confidence(0~1), swing_factor(한 줄), reconciliation 을 산출하라."),
    ])
    chain = prompt | llm.with_structured_output(DebateVerdictOutput)
    return await chain.ainvoke({
        "ticker": input_data.ticker, "mode": input_data.mode,
        "bull_case": _fmt_case(input_data.bull_case), "bear_case": _fmt_case(input_data.bear_case),
        "bull_weight": input_data.bull_weight, "bear_weight": input_data.bear_weight,
        "allowed_actions": ", ".join(input_data.allowed_actions),
    })
```

import 추가 (기존 `from src.llm.models import (...)` 블록에 병합):

```python
    DebateAdvocacyInput,
    DebateAdvocacyOutput,
    DebateJudgeInput,
    DebateVerdictOutput,
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(llm): add debate advocacy and judge calls`

---

## Task 6: 논쟁 엔진 (ticker 전달)

**Files:**
- Create: `src/pipelines/debate/engine.py`
- Test: `tests/pipelines/debate/test_debate_engine.py`

- [ ] **Step 1: Test**

```python
# tests/pipelines/debate/test_debate_engine.py
import pytest

from src.llm.models import DebateAdvocacyOutput, DebateCase, DebateVerdictOutput
from src.pipelines.debate.models import BullBearLedger, Evidence


class _Chain:
    def __init__(self, out): self._out = out
    async def ainvoke(self, _): return self._out


class _Pipe:
    def __init__(self, out): self._out = out
    def __ror__(self, _p): return _Chain(self._out)


class _LLM:
    def __init__(self, adv, ver): self._adv, self._ver = adv, ver
    def with_structured_output(self, model):
        return _Pipe(self._adv if model is DebateAdvocacyOutput else self._ver)


@pytest.mark.asyncio
async def test_run_debate_bundle():
    from src.pipelines.debate.engine import run_debate

    ledger = BullBearLedger(
        mode="entry",
        bull=[Evidence(side="bull", key="gate_A", weight=4.0, headline="게이트 A", detail="상승장", source="playbook")],
        bear=[Evidence(side="bear", key="gate_E", weight=3.0, headline="게이트 E", detail="미돌파", source="playbook")],
        neutral=[], bull_weight=4.0, bear_weight=3.0, action_space=["매수", "관망"],
    )
    adv = DebateAdvocacyOutput(bull_case=DebateCase(stance="bull", thesis="강세", points=["게이트 A 통과"]),
                               bear_case=DebateCase(stance="bear", thesis="약세", points=["VCP 미돌파"]))
    ver = DebateVerdictOutput(action="매수", confidence=0.7, swing_factor="시장환경", reconciliation="bull 우세")
    bundle = await run_debate(ledger, _LLM(adv, ver), ticker="TEST")
    assert bundle.verdict.action in ledger.action_space
    assert bundle.bull_case.thesis == "강세"
    assert bundle.ledger is ledger
```

- [ ] **Step 2: Run** → FAIL ("No module named 'src.pipelines.debate.engine'")

- [ ] **Step 3: Implement**

```python
# src/pipelines/debate/engine.py
from __future__ import annotations

from src.llm.analyzer import run_debate_advocacy, run_debate_judge
from src.llm.models import DebateAdvocacyInput, DebateJudgeInput
from src.pipelines.debate.models import BullBearLedger, DebateBundle


async def run_debate(ledger: BullBearLedger, llm, *, ticker: str = "") -> DebateBundle:
    """① 변론 콜 → ② 독립 판사 콜 → DebateBundle."""
    advocacy = await run_debate_advocacy(
        DebateAdvocacyInput(
            ticker=ticker, mode=ledger.mode,
            bull_evidence=[{"headline": e.headline, "detail": e.detail} for e in ledger.bull],
            bear_evidence=[{"headline": e.headline, "detail": e.detail} for e in ledger.bear],
        ), llm)
    verdict = await run_debate_judge(
        DebateJudgeInput(
            ticker=ticker, mode=ledger.mode, bull_case=advocacy.bull_case, bear_case=advocacy.bear_case,
            bull_weight=ledger.bull_weight, bear_weight=ledger.bear_weight, allowed_actions=ledger.action_space,
        ), llm)
    return DebateBundle(ledger=ledger, bull_case=advocacy.bull_case, bear_case=advocacy.bear_case, verdict=verdict)
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(debate): two-call debate engine with ticker`

---

## Task 7: 변론 grounding 헬퍼

**Files:**
- Create: `src/pipelines/debate/grounding.py`
- Test: `tests/pipelines/debate/test_grounding.py`

- [ ] **Step 1: Test**

```python
# tests/pipelines/debate/test_grounding.py
def test_points_grounding_ratio():
    from src.pipelines.debate.grounding import points_grounding_ratio
    ratio = points_grounding_ratio(["게이트 A 통과로 시장환경 양호", "관련 없는 환각 주장"],
                                   ["게이트 A: 시장환경=상승", "CAN SLIM C 분기 EPS"])
    assert ratio == 0.5
```

- [ ] **Step 2: Run** → FAIL  **Step 3: Implement**

```python
# src/pipelines/debate/grounding.py
from __future__ import annotations

import re


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[\s:=,()/]+", text) if len(t) >= 2}


def points_grounding_ratio(points: list[str], evidence_headlines: list[str]) -> float:
    """각 point 가 증거 headline 토큰을 1개 이상 포함하는 비율 (환각 검출)."""
    if not points:
        return 1.0
    ev: set[str] = set()
    for h in evidence_headlines:
        ev |= _tokens(h)
    grounded = sum(1 for p in points if _tokens(p) & ev)
    return round(grounded / len(points), 4)
```

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(debate): add grounding ratio helper`

---

## Task 8: deep_dive 배선 (ledger 항상 result, ticker, graceful)

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Test: `tests/pipelines/test_deep_dive_debate.py`

- [ ] **Step 1: Test**

```python
# tests/pipelines/test_deep_dive_debate.py
import pytest


@pytest.mark.asyncio
async def test_build_debate_returns_bundle_and_ledger(monkeypatch):
    from src.pipelines import deep_dive
    from src.llm.models import DebateAdvocacyOutput, DebateCase, DebateVerdictOutput

    async def _adv(_i, _l):
        return DebateAdvocacyOutput(bull_case=DebateCase(stance="bull", thesis="강세", points=["p"]),
                                    bear_case=DebateCase(stance="bear", thesis="약세", points=["q"]))

    async def _judge(_i, _l):
        return DebateVerdictOutput(action="관망", confidence=0.5, swing_factor="x", reconciliation="y")

    monkeypatch.setattr(deep_dive, "run_debate_advocacy", _adv, raising=False)
    monkeypatch.setattr(deep_dive, "run_debate_judge", _judge, raising=False)

    bundle, ledger = await deep_dive._build_debate(
        playbook_verdict=None, factor_assessments=[], snapshot=None, flow=None,
        holding=False, llm=object(), ticker="TEST")
    assert ledger is not None
    assert bundle is not None
    assert bundle.verdict.action in ledger.action_space


@pytest.mark.asyncio
async def test_build_debate_graceful_on_llm_failure(monkeypatch):
    from src.pipelines import deep_dive

    async def _boom(_i, _l):
        raise RuntimeError("llm down")

    monkeypatch.setattr(deep_dive, "run_debate_advocacy", _boom, raising=False)
    bundle, ledger = await deep_dive._build_debate(
        playbook_verdict=None, factor_assessments=[], snapshot=None, flow=None,
        holding=False, llm=object(), ticker="TEST")
    assert bundle is None
    assert ledger is not None  # 실패해도 증거 장부는 표시 가능
```

- [ ] **Step 2: Run** → FAIL ("has no attribute '_build_debate'")

- [ ] **Step 3: Implement**

deep_dive.py import 추가:

```python
from src.pipelines.debate.engine import run_debate
from src.pipelines.debate.ledger import build_evidence_ledger
from src.llm.analyzer import run_debate_advocacy, run_debate_judge  # monkeypatch 대상
```

모듈 헬퍼:

```python
async def _build_debate(*, playbook_verdict, factor_assessments, snapshot, flow, holding, llm, ticker):
    """증거 장부 생성 후 논쟁 실행. (bundle|None, ledger) 반환 — 실패해도 ledger 는 보존."""
    mode = "holding" if holding else "entry"
    ledger = build_evidence_ledger(playbook_verdict=playbook_verdict, factor_assessments=factor_assessments,
                                   snapshot=snapshot, flow=flow, mode=mode)
    try:
        bundle = await run_debate(ledger, llm, ticker=ticker)
        return bundle, ledger
    except Exception as e:
        logger.warning("Debate engine failed: %s", e)
        return None, ledger
```

`run()` 내부 — momentum_events 생성(플랜 A Task 8) 이후. **playbook_verdict 계산 시 이미 구한 `holding`을 재사용**한다(중복 `load_holdings()` 금지):

```python
        debate_bundle, debate_ledger = await _build_debate(
            playbook_verdict=playbook_verdict,
            factor_assessments=decision_bundle.factor_assessments,
            snapshot=technical_data.snapshot, flow=flow_data,
            holding=holding is not None, llm=self.llm, ticker=ticker,
        )
```

> 라인 주의(리뷰 C2): deep_dive.py 라인 번호는 플랜 A 적용 후 시프트되어 있다. 삽입 지점은 **내용**으로 찾는다 — `momentum_events.rs_event = ...` 다음 줄.

return dict에 키 추가:

```python
            "debate": debate_bundle,
            "debate_ledger": debate_ledger,
```

> `holding` 변수: playbook_verdict 계산 블록(`holding = load_holdings().find(ticker)`)을 try 밖으로 끌어올려 재사용한다.

- [ ] **Step 4: Run** → PASS  **Step 5: Commit** `feat(deep_dive): wire debate, preserve ledger on failure`

---

## Task 9: 종합 판정 렌더 (analyze_render.py — 삽입 방식)

플랜 A가 만든 `format_deep_dive_output`의 debate 주석 자리를 **한 줄 Edit**으로 채운다(재작성 안 함 → 충돌 없음).

**Files:**
- Modify: `src/cli/analyze_render.py`
- Test: `tests/cli/test_debate_format.py`

- [ ] **Step 1: Test**

```python
# tests/cli/test_debate_format.py
from src.llm.models import DebateCase, DebateVerdictOutput
from src.pipelines.debate.models import BullBearLedger, DebateBundle, Evidence


def _bundle(action="매수"):
    ledger = BullBearLedger(
        mode="entry",
        bull=[Evidence(side="bull", key="gate_A", weight=4.0, headline="게이트 A", detail="상승장", source="playbook")],
        bear=[Evidence(side="bear", key="gate_E", weight=3.0, headline="게이트 E", detail="미돌파", source="playbook")],
        neutral=[], bull_weight=4.0, bear_weight=3.0, action_space=["매수", "관망"],
    )
    return DebateBundle(
        ledger=ledger,
        bull_case=DebateCase(stance="bull", thesis="강세 우위", points=["게이트 A 통과"]),
        bear_case=DebateCase(stance="bear", thesis="VCP 미돌파", points=["E 미충족"]),
        verdict=DebateVerdictOutput(action=action, confidence=0.72, swing_factor="시장환경", reconciliation="bull 우위."),
    )


def test_format_debate_section():
    from src.cli.analyze_render import _format_debate_section
    out = _format_debate_section(_bundle())
    assert "종합 판정" in out and "매수" in out and "72%" in out
    assert "Bull 논거" in out and "Bear 논거" in out and "판결 사유" in out


def test_format_ledger_fallback():
    from src.cli.analyze_render import _format_ledger_fallback
    out = _format_ledger_fallback(_bundle().ledger)
    assert "증거" in out and "게이트 A" in out


def test_deep_dive_output_includes_verdict():
    """플랜 A 출력에 debate 가 있으면 종합 판정이 최상단에 들어간다."""
    from src.cli.analyze_render import format_deep_dive_output
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult
    from src.tools.technical.events_models import MomentumEvents
    from datetime import datetime

    snap = IndicatorSnapshot(price=155.3, change_pct=1.2)
    tech = TechnicalResult(ticker="T", timestamp=datetime(2026, 6, 15), snapshot=snap, components={}, total_score=0)

    class _Sum:
        summary = "s"; recommendation = "보유"; confidence = 0.5; rationale = "r"; key_insights = []

    result = {"ticker": "T", "technical": tech, "technical_summary": _Sum(),
              "momentum_events": MomentumEvents(), "playbook_verdict": None,
              "chart_patterns": {}, "factor_assessments": [], "scenarios": [],
              "debate": _bundle(), "debate_ledger": _bundle().ledger}
    out = format_deep_dive_output(result)
    assert "## 🧭 종합 판정" in out
    assert out.index("종합 판정") < out.index("## 📊 Summary")
```

- [ ] **Step 2: Run** → FAIL ("cannot import name '_format_debate_section'")

- [ ] **Step 3: Implement**

`src/cli/analyze_render.py`에 추가:

```python
def _format_debate_section(bundle) -> str:
    """Bull/Bear 논쟁 종합 판정 — 유일한 결론."""
    if bundle is None:
        return ""
    v = bundle.verdict
    lines = ["## 🧭 종합 판정", "",
             f"- **액션**: {v.action} | **확신도**: {v.confidence * 100:.0f}%",
             f"- **결정적 변수**: {v.swing_factor}", "",
             "## 🟢 Bull 논거", f"_{bundle.bull_case.thesis}_"]
    lines += [f"- {p}" for p in bundle.bull_case.points]
    lines += ["", "## 🔴 Bear 논거", f"_{bundle.bear_case.thesis}_"]
    lines += [f"- {p}" for p in bundle.bear_case.points]
    lines += ["", "## ⚖️ 판결 사유", v.reconciliation, ""]
    return "\n".join(lines) + "\n"


def _format_ledger_fallback(ledger) -> str:
    """LLM 실패 시 — 결정적 증거 장부만 표시 (spec §10)."""
    if ledger is None:
        return ""
    lines = ["## 🧭 종합 판정 (LLM 미생성 — 증거 요약)", "",
             f"- Bull 가중치 {ledger.bull_weight} vs Bear 가중치 {ledger.bear_weight}", "",
             "**Bull 증거**"]
    lines += [f"- {e.headline}: {e.detail} (가중치 {e.weight})" for e in ledger.bull] or ["- 없음"]
    lines += ["", "**Bear 증거**"]
    lines += [f"- {e.headline}: {e.detail} (가중치 {e.weight})" for e in ledger.bear] or ["- 없음"]
    lines.append("")
    return "\n".join(lines) + "\n"
```

`format_deep_dive_output`의 가격 줄 다음 주석 자리를 Edit로 교체:

```python
    output += f"## 가격: ${snapshot.price:.2f} ({snapshot.change_pct:+.2f}%)\n\n"

    # 종합 판정 (유일한 결론) — debate 있으면 평결, 없으면 ledger 요약
    debate_bundle = result.get("debate")
    if debate_bundle is not None:
        output += _format_debate_section(debate_bundle)
    elif result.get("debate_ledger") is not None:
        output += _format_ledger_fallback(result["debate_ledger"])
```

(플랜 A가 남긴 `# [플랜 B가 여기에 종합 판정(debate) 섹션을 삽입한다 ...]` 주석 줄을 위 블록으로 교체.)

- [ ] **Step 4: Run** `uv run pytest tests/cli/test_debate_format.py -v` → PASS

- [ ] **Step 5: Commit** `feat(cli): render verdict section with ledger fallback`

---

## Task 10: 죽은 코드 제거 + 테스트 마이그레이션

**Files:**
- Modify: `analyze_decision.py`, `llm/models.py`, `llm/analyzer.py`, `deep_dive.py`, `cli/main.py`, `cli/analyze_render.py`
- Delete/Modify: 7개 테스트 파일

- [ ] **Step 1: Grep 사용처**

Run:
```bash
grep -rn "apply_playbook_veto\|generate_integrated_analysis\|generate_actionable_signal\|IntegratedAnalysis\|ActionableSignalOutput\|_format_top_summary\|display_actionable_signal\|veto_applied\|action_original\|integrated_analysis\|actionable_signal" src/ tests/
```

- [ ] **Step 2: Remove source**

1. `analyze_decision.py` — `apply_playbook_veto` 삭제; `AnalyzeDecisionSummary.veto_applied`/`action_original` 필드 삭제(grep 확인 후).
2. `llm/models.py` — `IntegratedAnalysisInput/Output`, `ActionableSignalOutput` 삭제.
3. `llm/analyzer.py` — `generate_integrated_analysis`, `generate_actionable_signal` 삭제 + 이제 안 쓰는 import 정리.
4. `deep_dive.py` — `_generate_integrated_analysis`/`_format_flow_for_llm`(integrated 전용이면) 삭제; integrated/actionable/veto 호출 블록 삭제(**내용으로 찾기** — 플랜 A 후 라인 시프트); `IntegratedAnalysis*`/`apply_playbook_veto` import 제거. return dict의 `integrated_analysis`/`actionable_signal` 키 제거.
5. `cli/analyze_render.py` — `_format_raw_analysis_sections` 안의 `integrated = result.get("integrated_analysis")` 렌더 블록 삭제(리뷰 C2: 플랜 A 이동분에 잔존).
6. `cli/main.py` — `display_actionable_signal` 삭제; `analyze` 커맨드의 actionable 패널 출력 블록 삭제; `ActionableSignalOutput` import 제거.

- [ ] **Step 3: Migrate tests** (리뷰 C3 — 7개 파일)

- `tests/pipelines/test_apply_playbook_veto.py` → 파일 삭제
- `tests/llm/test_analyzer.py` → `generate_actionable_signal`/`generate_integrated_analysis` import·테스트 삭제
- `tests/llm/test_models.py` → `ActionableSignalOutput` import·테스트 삭제
- `tests/pipelines/test_deep_dive.py` → actionable mock 7곳: `run_debate_advocacy`/`run_debate_judge` mock으로 재배선하거나 해당 단언 삭제. result dict 단언에서 `actionable_signal`/`integrated_analysis` 제거, `debate`/`debate_ledger` 추가
- `tests/pipelines/test_deep_dive_structure_contract.py` → 동일 패턴 정리
- `tests/cli/test_cli.py` → `ActionableSignalOutput` import·구성 삭제
- `tests/cli/test_analyze_output.py` → 플랜 A Task 18에서 이미 마이그레이션(추가 작업 없으면 통과 확인)

- [ ] **Step 4: Verify**

Run: `grep -rn "apply_playbook_veto\|generate_integrated_analysis\|generate_actionable_signal\|IntegratedAnalysis\|ActionableSignalOutput\|_format_top_summary\|display_actionable_signal\|integrated_analysis" src/ tests/`
Expected: 빈 결과

Run: `uv run pytest -q`
Expected: PASS (green)

- [ ] **Step 5: Commit** `refactor(analyze): remove veto/integrated/actionable, migrate tests`

---

## Task 11: 엣지 케이스

**Files:**
- Test: `tests/pipelines/debate/test_ledger_edge.py`

- [ ] **Step 1: Test**

```python
# tests/pipelines/debate/test_ledger_edge.py
def test_ledger_no_playbook_factors_only():
    from src.pipelines.debate.ledger import build_evidence_ledger
    from src.pipelines.analyze_decision import FactorAssessment

    factors = [FactorAssessment(factor_type="technical", role="주도", freshness_score=4, magnitude_score=4,
                                actionability_score=4, total_score=12, summary="강세", role_reason="r", evidence=[], bias="bullish")]
    ledger = build_evidence_ledger(playbook_verdict=None, factor_assessments=factors,
                                   snapshot=None, flow=None, mode="entry")
    assert ledger.action_space == ["매수", "관망"]
    assert any(e.key == "factor_technical" for e in ledger.bull)
    assert not any(e.key.startswith("gate_") for e in ledger.bull + ledger.bear)


def test_empty_ledger():
    from src.pipelines.debate.ledger import build_evidence_ledger
    ledger = build_evidence_ledger(playbook_verdict=None, factor_assessments=[],
                                   snapshot=None, flow=None, mode="entry")
    assert ledger.bull == [] and ledger.bull_weight == 0.0
```

- [ ] **Step 2-4: Run** → PASS (Task 3 None 가드)  **Step 5: Commit** `test(debate): edge cases`

---

## Task 12: 전체 회귀 + FEATURES.md

- [ ] **Step 1: Full suite** `uv run pytest -q` → PASS
- [ ] **Step 2: Lint** `uv run ruff check src/pipelines/debate/ src/llm/ src/cli/ src/pipelines/deep_dive.py src/pipelines/analyze_decision.py` → clean
- [ ] **Step 3: FEATURES.md** (analyze 섹션)

```markdown
- **Bull/Bear 논쟁 종합 판정** (`src/pipelines/debate/`): 모든 신호를 규칙으로 Bull/Bear 증거 장부에 분류(3계층) → LLM 변론 → 독립 LLM 판사가 단일 평결. 유일한 결론.
- **액션 가드레일**: 하락장→신규매수 차단, 강한 매도신호→보유강화 차단. 판사 허용 액션을 규칙이 제한.
- **중복 제거**: RS=gate_C+rs_magnitude, canslim_L 제외(항상)·canslim_M 제외(entry)·factor_flow 제외·momentum은 표시용.
- **제거**: veto/integrated/actionable 결론 일원화. LLM 실패 시 증거 장부 fallback 표시.
```

- [ ] **Step 4: Commit** `docs: document Bull/Bear debate verdict engine`

---

## Self-Review

**Spec 반영 (§2.1 결정):** R1 canslim_M entry 제외(T3) / R2 momentum 증거 제외(T3, 인자에서 빠짐) / R3 accumulation=canslim_I weight 1 + 노트(중복제거 표) / R4 판단요약은 플랜 A에서 삭제(본 플랜 무관) / R5 events=tool(플랜 A) / R6 렌더=analyze_render(T9) / R7 debate=pipeline / R8 가중치·논쟁=플랜 B(본 플랜).

**리뷰 반영:** C1 플랜충돌 → format_deep_dive_output Edit 삽입(T9, 재작성 안 함) / C2 라인시프트 "내용으로 찾기" 명시 + integrated 렌더 제거(T10) / C3 7개 테스트 마이그레이션(T10) / M1 canslim_M(T3) / M2 accumulation 노트 / M4 action_space medium≥1(T3) / M5 ticker 전달(T6,T8) / M6 ledger fallback(T8,T9) / Task1↔4 순서 → Task 1을 LLM 모델로 최우선.

**레이어:** debate=Pipeline(T2-8) / 렌더=CLI analyze_render(T9) / LLM=llm(T1,T5). ✅

**Type consistency:** `Evidence`/`BullBearLedger`/`DebateBundle`(debate/models) + `DebateCase`/`DebateAdvocacy*`/`DebateJudgeInput`/`DebateVerdictOutput`(llm/models) 필드명이 정의·사용처에서 일치. `build_evidence_ledger` 시그니처에서 momentum_events 인자 제거됨(T3) — 호출처(T8)와 일치.
