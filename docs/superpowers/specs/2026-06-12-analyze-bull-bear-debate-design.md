# Analyze Bull/Bear 논쟁 종합 엔진 설계 스펙

- **작성일**: 2026-06-12
- **상태**: Draft v1
- **대상**: `analyze`(deep_dive) 파이프라인의 펀더멘털·기술적·플레이북을 단일 종합 인사이트로 통합
- **출처 자료**: `docs/references/trading-playbook.md`, `docs/superpowers/specs/2026-06-10-playbook-engine-design.md`

---

## 1. 배경 및 목표

### 1.1 문제: 세 엔진이 따로 논다

현재 `analyze`(= `deep_dive` 파이프라인)는 **세 개의 독립된 판정 엔진**이 각자 결론을 내고, 출력에서 따로따로 섹션으로 찍힌다. 사용자는 4개 섹션을 읽고 머릿속에서 합쳐야 한다.

| # | 엔진 | 위치 | 출력 | 한계 |
|---|------|------|------|------|
| 1 | 팩터 스코어링 (결정적) | `src/pipelines/analyze_decision.py` | 판단 요약(액션) + 팩터 분류 + 시나리오 | 펀더멘털이 "저평가/적정/고평가" 라벨 하나로 납작해짐 |
| 2 | 플레이북 엔진 | `src/tools/playbook/engine.py` | 게이트 등급·CAN SLIM·포지션플랜(별도 §섹션) | `apply_playbook_veto`로 **거부권만** 1번에 연결 |
| 3 | LLM 종합 인사이트 | `deep_dive._generate_integrated_analysis` | "종합 인사이트 참고" | 이름은 종합인데 입력이 제일 빈약(펀더 라벨 1개), 공시/수급 있을 때만 실행 |
| 4 | actionable_signal | `deep_dive` + `analyzer` | 실행 시그널(액션/타이밍/레벨) | 1·2번과 또 다른 액션을 냄 |

**핵심 문제**: 펀더멘털 신호가 1번(라벨)과 2번(CAN SLIM)에서 **두 번 따로 계산**되고, 네 엔진이 겹치는 데이터로 각자 결론을 낸다. 엇갈림(예: 팩터=관망 vs 게이트=A등급)은 `veto`의 조용한 덮어쓰기로 **숨겨진다**.

### 1.2 목표

1. **단일 결론**: 투자 판단이 한 곳에서 나온다.
2. **서술형 + 근거**: "왜 이 판단인지"를 이야기로 읽히게 하되, 근거(점수·게이트·CAN SLIM·포지션플랜)를 자세히 함께 보여준다.
3. **엇갈림을 결과물로**: 엔진 간 충돌을 숨기지 않고 **Bull vs Bear 논쟁**으로 드러낸다.
4. **재현 가능한 근거**: 사실(증거)은 규칙이 만들어 환각을 차단한다. 평결만 LLM이 내린다.

---

## 2. 설계 결정 요약

| 항목 | 결정 | 근거 |
|------|------|------|
| 결과물 형태 | 서술형 종합 리포트 + 자세한 근거 | 사용자 결정 |
| 메커니즘 | Bull vs Bear 논쟁 | 엇갈림을 결과물로 만드는 가장 직접적 구조 |
| 논쟁 엔진 | **규칙이 증거 분류·채점, LLM 판사가 평결** | 사실은 결정적, 평결은 유연 |
| 통합 범위 | **논쟁이 유일한 결론** (기존 결론 강등/제거) | "따로 논다" 정면 해결 |
| 안전 가드레일 | **하드 리스크룰이 LLM 판사의 액션 범위를 제한** | 투명한 리스크 통제(옛 veto의 조용한 덮어쓰기와 다름) |
| actionable_signal | **은퇴** | 평결·포지션플랜·시나리오가 역할 대체 |
| LLM 콜 구조 | **2콜 (변론 + 독립 판사)** | 판사가 자기 변론을 합리화하지 않게 분리 |

---

## 3. 전체 아키텍처 / 데이터 흐름

```text
deep_dive.run(ticker)
  │
  ├─ [기존] technical · fundamental · flow · disclosure · news
  ├─ [기존] playbook_verdict   (PlaybookEngine.evaluate → PlaybookVerdict)
  ├─ [기존] decision_bundle    (build_analyze_decision_bundle → factor_assessments + scenarios)
  │         · factor_assessments 는 장부 증거로만 사용. decision_summary(액션)는 렌더링·판사 입력 모두 안 함
  │
  ├─ [신규] build_evidence_ledger(...)           ← 결정적(규칙). 새 데이터 안 만듦, 분류만
  │         playbook_verdict + factor_assessments + snapshot + flow
  │         → BullBearLedger { bull[], bear[], neutral[], bull_weight, bear_weight, action_space, mode }
  │
  ├─ [신규] run_debate(ledger, llm)              ← LLM 2콜
  │         ① 변론 콜: bull_case + bear_case (각자 자기 장부 증거만 인용)
  │         ② 판사 콜: 양측 + 가중치 + action_space → DebateVerdict
  │         → DebateBundle { ledger, bull_case, bear_case, verdict }
  │
  └─ 출력: 종합 판정(verdict) → Bull 논거 → Bear 논거 → 판결 사유 → 증거 상세 → 원시 데이터
```

신규 코드는 `src/pipelines/debate/` 패키지에 격리한다(파일 분리 원칙). LLM I/O 모델만 기존 관례대로 `src/llm/models.py`에 둔다.

---

## 4. 증거 장부 (결정적)

### 4.1 모듈: `src/pipelines/debate/ledger.py`

순수 함수. I/O 없음. 기존 판정 결과를 입력받아 bull/bear/neutral로 분류·채점한다.

```python
def build_evidence_ledger(
    *,
    playbook_verdict,          # PlaybookVerdict | None
    factor_assessments,        # list[FactorAssessment]
    snapshot,                  # TechnicalSnapshot (rsi 등)
    flow,                      # InvestorFlow | None
    mode: str,                 # "entry" | "holding"
) -> BullBearLedger: ...
```

### 4.2 라우팅 규칙 — 미보유(entry)

| 증거 key | 출처 필드 | 진영 | 가중치(0~5) |
|----------|-----------|------|-------------|
| `gate_A` | `gate.checklist[A].met` (market_regime) | True→bull / False·None→bear | 필수=4 |
| `gate_B` | `gate.checklist[B]` (Stage2, 미충족 라벨 detail) | True→bull / False→bear | 필수=4 |
| `gate_C` | `gate.checklist[C]` (RS+업종) | True→bull / False→bear | 필수=4 |
| `gate_E` | `gate.checklist[E]` (VCP 돌파) | True→bull / False→bear | 필수=3 |
| `canslim_C..M` | `canslim.{c..m}.met` | True→bull / False→bear / None→neutral | 요소당 1 |
| `accumulation` | `canslim.i` / `AccumulationResult` | 매집→bull / 분산→bear | 2 |
| `flow` | `flow.foreign/institution_direction_5d` | 매수→bull | 2 |
| `rs_magnitude` | `relative_strength.mansfield_rs` | >0→bull / <0→bear | min(abs/10,3) |
| `factor_*` | `factor_assessments[].bias` | bullish→bull / bearish→bear / neutral→neutral | `total_score`/3 (0~5) |
| `rsi_overbought` | `snapshot.rsi >= 80` | bear | 2 |

### 4.3 라우팅 규칙 — 보유(holding)

미보유 규칙 중 게이트 제외 + 아래 추가:

| 증거 key | 출처 | 진영 | 가중치 |
|----------|------|------|--------|
| `exit_{code}` | `exit_verdict.signals[]` (CHARACTER_CHANGE/SMA_SHORT/DISTRIBUTION/RS_WEAKENING/SMA_LONG) | bear | severity: strong=5 / medium=3 / weak=1 |
| `r_cushion` | `exit_verdict.current_r` | >0→bull / <0→bear | min(abs,3) |

### 4.4 산출 모델: `src/pipelines/debate/models.py`

```python
class Evidence(BaseModel):
    side: str       # "bull" | "bear" | "neutral"
    key: str        # "gate_A" | "canslim_C" | "factor_technical" | "exit_SMA_LONG" ...
    weight: float   # 0~5
    headline: str   # 한 줄 라벨 (예: "게이트 A: 시장환경=상승")
    detail: str     # 근거 상세 (reason/detail 원문)
    source: str     # "playbook" | "factor" | "technical" | "flow"

class BullBearLedger(BaseModel):
    mode: str               # "entry" | "holding"
    bull: list[Evidence]
    bear: list[Evidence]
    neutral: list[Evidence]
    bull_weight: float      # sum(bull.weight)
    bear_weight: float      # sum(bear.weight)
    action_space: list[str] # 가드레일이 허용한 액션 (§6)
```

---

## 5. 논쟁 엔진 (LLM)

### 5.1 모듈: `src/pipelines/debate/engine.py`

```python
async def run_debate(ledger: BullBearLedger, llm) -> DebateBundle: ...
```

- **① 변론 콜** (`DebateAdvocacyInput` → `DebateAdvocacyOutput`)
  - 입력: bull/bear 증거 목록(headline+detail)
  - 제약(프롬프트): 각 측은 **자기 장부 증거만 인용**, neutral·상대 증거 인용 금지, 숫자/사실을 지어내지 말 것
  - 출력: `bull_case`, `bear_case` (각 `DebateCase {stance, thesis, points[]}`)
- **② 판사 콜** (`DebateJudgeInput` → `DebateVerdictOutput`)
  - 입력: 두 변론 + `bull_weight`/`bear_weight` + **`allowed_actions`(가드레일)**
  - 제약: `action`은 반드시 `allowed_actions` 중에서 선택
  - 출력: `DebateVerdict {action, confidence, swing_factor, reconciliation}`

### 5.2 LLM I/O 모델: `src/llm/models.py` 추가

```python
class DebateCase(BaseModel):
    stance: str         # "bull" | "bear"
    thesis: str         # 한 줄 핵심 주장
    points: list[str]   # 근거 (각 항목 장부 증거 기반)

class DebateAdvocacyInput(BaseModel):
    ticker: str
    mode: str                    # "entry" | "holding"
    bull_evidence: list[dict]    # [{headline, detail}]
    bear_evidence: list[dict]

class DebateAdvocacyOutput(BaseModel):
    bull_case: DebateCase
    bear_case: DebateCase

class DebateJudgeInput(BaseModel):
    ticker: str
    mode: str
    bull_case: DebateCase
    bear_case: DebateCase
    bull_weight: float
    bear_weight: float
    allowed_actions: list[str]

class DebateVerdictOutput(BaseModel):
    action: str          # allowed_actions 중 하나
    confidence: float    # 0.0~1.0
    swing_factor: str    # 결정적 변수 한 줄
    reconciliation: str  # 판결 사유 서술
```

`src/pipelines/debate/models.py`:

```python
class DebateBundle(BaseModel):
    ledger: BullBearLedger
    bull_case: DebateCase
    bear_case: DebateCase
    verdict: DebateVerdictOutput
```

> ⚠️ strict-schema 가드: 위 모델은 `dict` 필드(`list[dict]`)를 LLM **출력** 모델에 두지 않는다. `list[dict]`는 변론 **입력**(`DebateAdvocacyInput`)에만 존재. 출력 모델(`DebateAdvocacyOutput`/`DebateVerdictOutput`)은 전부 타입 확정. (참고: openai-strict-schema-guard)

---

## 6. 안전 가드레일

`veto 제거`는 "충돌을 숨기는 조용한 덮어쓰기를 없앤다"는 뜻이지, 하드 리스크룰을 푼다는 게 아니다. 규칙이 **판사의 액션 공간(`action_space`)을 제한**하고, 판사는 그 안에서만 고른다. bull 논거는 그대로 표시·변론되며, 제한 이유는 판결문(`reconciliation`)에 명시된다.

`src/pipelines/debate/ledger.py`의 순수 함수 `compute_action_space`:

```python
def compute_action_space(playbook_verdict, mode: str) -> list[str]: ...
```

| 모드 | 조건 | 허용 액션 |
|------|------|-----------|
| entry | `market_regime.allow_new_buy is False` (하락장) | `["관망"]` (매수 불가) |
| entry | 그 외 | `["매수", "관망"]` |
| holding | strong 매도신호 존재 (예: SMA_LONG) 또는 `exit_verdict.action=="liquidate"` | `["청산", "비중축소"]` (보유강화 불가) |
| holding | medium 신호 1개 | `["비중축소", "보유"]` |
| holding | 그 외 | `["보유", "비중축소"]` |

`playbook_verdict is None`(엔진 미주입/실패) → entry는 `["매수","관망"]`, holding은 `["보유","비중축소","청산"]` (제약 없음, graceful).

---

## 7. 출력 레이아웃

`format_deep_dive_output` 재구성:

```text
# Deep Dive Analysis: TICKER
## 가격: $... (±%)

## 🧭 종합 판정                       ← 유일한 결론
- 액션: 매수 | 확신도: 72%
- 결정적 변수: <swing_factor>
- 판단: <reconciliation 요약 첫 문장>

## 🟢 Bull 논거
<bull_case.thesis>
- <point 1> ... (자기 장부 증거 기반)

## 🔴 Bear 논거
<bear_case.thesis>
- <point 1> ...

## ⚖️ 판결 사유
<reconciliation 전문>

## 📊 증거 상세                       ← "근거 자세히"
- 플레이북: 게이트 체크리스트 / CAN SLIM 7요소 / RS·업종 / 포지션 플랜(or 매도 판정)
- 팩터 스코어: technical/event/flow/valuation (기존 _format_factor_section 재사용)
- 시나리오: 가격 레벨/무효화 조건 (기존 _format_scenario_section 재사용)

## 원시 데이터 (기술적 지표 / 펀더멘털) — 기존 유지
```

기존 `_format_playbook_section`은 "증거 상세" 하위로 이동. `_format_top_summary`(판단 요약)는 제거(종합 판정이 대체).

---

## 8. 제거 / 강등 (마이그레이션)

| 대상 | 파일 | 조치 |
|------|------|------|
| `apply_playbook_veto` 호출 | `deep_dive.py:259-263` | 제거 |
| `apply_playbook_veto` 함수 | `analyze_decision.py:734-773` | 삭제(죽은 코드) + 테스트 제거 |
| `_generate_integrated_analysis` | `deep_dive.py:182-191,471-502` | 제거 |
| integrated_analysis 출력/포맷 | `deep_dive.py` return, `main.py:817-830` | 제거 |
| `IntegratedAnalysisInput/Output` | `src/llm/models.py:105-122` | 사용처 제거 후 모델 삭제 |
| `generate_integrated_analysis` | `src/llm/analyzer.py` | 삭제 |
| actionable_signal 생성/표시 | `deep_dive.py:219-230`, `main.py:952-,1040-` | 제거(은퇴) |
| `generate_actionable_signal`·`ActionableSignalOutput` | `analyzer.py`, `models.py:125-` | 사용처 제거 후 삭제 |
| `_format_top_summary` | `main.py:399-411` | 제거 |
| `build_analyze_decision_bundle` | `analyze_decision.py:637` | **유지** — factor_assessments·scenarios 산출. `decision_summary`는 렌더·판사 입력 모두 안 함 |

`build_analyze_decision_bundle`을 유지하는 이유: `factor_assessments`(장부 증거)와 `scenarios`(가격 레벨 상세)가 계속 필요하다. `decision_summary.action`은 factor_assessments에서 파생된 값이라 장부의 `factor_*` 증거와 중복된다 → 판사에 따로 넘기지 않고 **화면·판사 입력 모두에서 뺀다**(경쟁 결론 재유입 방지). 내부 계산은 scenarios 생성에만 쓰인다.

---

## 9. 테스트 전략

기존 컨벤션 준수: 실 DB/실 LLM 없이, 합성 입력 + mock. (참고: stock-report-tests-fake-conn)

| 테스트 | 대상 | 방식 |
|--------|------|------|
| `test_ledger_entry.py` | `build_evidence_ledger` (entry) | 합성 `PlaybookVerdict`+`FactorAssessment` → bull/bear 분류·가중치 단언 |
| `test_ledger_holding.py` | `build_evidence_ledger` (holding) | 합성 `ExitVerdict` 신호 → bear 라우팅·severity 가중치 단언 |
| `test_action_space.py` | `compute_action_space` | 하락장→`["관망"]`, strong 매도→보유강화 불가 단언 |
| `test_debate_engine.py` | `run_debate` | mock LLM, 프롬프트에 장부 증거 포함 단언, 평결 `action ∈ allowed_actions` 단언 |
| `test_debate_schema.py` | LLM 출력 모델 | strict-schema 회귀가드(`model_json_schema()` 워킹) |
| `test_grounding.py` | 변론 grounding | mock 변론 출력의 points가 장부 headline 집합 내인지 검증 헬퍼 |

---

## 10. 엣지 케이스 / 결측 처리

| 상황 | 처리 |
|------|------|
| `playbook_verdict is None` (엔진 실패/미주입) | 장부는 factor_assessments+flow+rsi만으로 구성, action_space 무제약 graceful |
| 장부 한쪽이 빔 (bull 또는 bear 0개) | 변론 콜은 빈 측 `points=[]` 허용, thesis="해당 없음". 판사는 가중치로 판단 |
| 양쪽 모두 빈약 (bull_weight+bear_weight 낮음) | 판사 confidence 낮게 유도 + action 보수적(관망/보유) |
| LLM 변론/판사 실패 | `run_debate` 예외 → deep_dive에서 catch, 종합 판정 섹션 생략 + 증거 상세만 표시(기존 플레이북 섹션 graceful 패턴) |
| 보유 종목인데 holding 정보 없음 | `load_holdings().find(ticker)` None → entry 모드 |

---

## 11. 영향 받는 파일

**신규**
- `src/pipelines/debate/__init__.py`
- `src/pipelines/debate/models.py` (Evidence, BullBearLedger, DebateBundle)
- `src/pipelines/debate/ledger.py` (build_evidence_ledger, compute_action_space)
- `src/pipelines/debate/engine.py` (run_debate)
- `src/llm/prompts/debate_advocacy.*`, `debate_judge.*` (프롬프트)
- `tests/pipelines/debate/` (위 §9)

**수정**
- `src/pipelines/deep_dive.py` (논쟁 배선, veto·integrated·actionable 제거)
- `src/llm/models.py` (Debate 모델 추가, Integrated/Actionable 제거)
- `src/llm/analyzer.py` (debate 함수 추가, integrated/actionable 제거)
- `src/cli/main.py` (출력 레이아웃 재구성)
- `src/pipelines/analyze_decision.py` (`apply_playbook_veto` 삭제)
- `docs/FEATURES.md` (src 변경 동반 — push 전 필수)

**삭제(테스트)**
- `apply_playbook_veto` / integrated / actionable 관련 테스트

---

## 12. 미해결/후속

- 프롬프트 튜닝(변론 길이·판사 confidence 캘리브레이션)은 구현 후 실제 출력 보고 조정.
- 다중 종목(`report ticker`)·`quick_check` 파이프라인 적용 여부는 본 스펙 범위 밖(analyze/deep_dive 우선).
