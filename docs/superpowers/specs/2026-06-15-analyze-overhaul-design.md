# Analyze 종합 개편 설계 스펙

- **작성일**: 2026-06-15
- **상태**: Draft v1 (서브에이전트 리뷰 반영)
- **대상**: `analyze`(deep_dive) 파이프라인 — 펀더멘털·기술·플레이북을 구조화된 단일 인사이트로 통합
- **대체 관계**: `2026-06-12-analyze-bull-bear-debate-design.md`의 논쟁 엔진 설계를 흡수·확장한다. 그 문서는 본 스펙으로 대체된다.
- **구현 플랜**: `docs/superpowers/plans/2026-06-15-analyze-output-restructure.md`(플랜 A), `docs/superpowers/plans/2026-06-15-analyze-bull-bear-debate.md`(플랜 B)
- **출처 자료**: `docs/references/trading-playbook.md`, signal-registry-v2 3계층 아이디어

---

## 1. 배경 및 목표

### 1.1 문제: 세 엔진이 따로 논다

현재 `analyze`는 **세 독립 판정 엔진**(팩터 스코어링·플레이북·LLM 종합)이 각자 결론을 내고, 출력에서 따로 섹션으로 찍힌다. 사용자는 여러 섹션을 머릿속에서 합쳐야 한다. 게다가 펀더멘털·RS·수급 신호가 여러 엔진에서 **중복 계산**되고, 엇갈림(예: 팩터=관망 vs 게이트=A등급)은 `apply_playbook_veto`의 조용한 덮어쓰기로 **숨겨진다**.

### 1.2 목표 — 두 축

1. **구조화된 증거 출력**: 모든 지표·사건을 의미 단위 섹션(Summary / CAN SLIM / Stage2 / 모멘텀 / Event / 구조레벨 / 원시)으로 정리하고, 충족·미충족 모두 디테일한 수치와 날짜로 보여준다.
2. **단일 종합 판정**: 투자 판단은 한 곳에서만 나온다. Bull vs Bear 논쟁으로 엔진 간 엇갈림을 숨기지 않고 드러내며, 사실(증거)은 규칙이 만들고 평결만 LLM이 낸다.

두 축은 독립적으로 가치가 있어 **두 플랜으로 분리**한다. 플랜 A(출력)만 완료해도 구조화된 리포트를 얻고, 플랜 B(논쟁)가 그 위에 단일 결론을 얹는다.

---

## 2. 설계 결정 요약

| 항목 | 결정 | 근거 |
|------|------|------|
| 결과물 형태 | 구조화 섹션 + 서술형 종합 판정 | 사용자 결정 |
| 종합 메커니즘 | Bull vs Bear 논쟁 | 엇갈림을 결과물로 |
| 논쟁 엔진 | 규칙이 증거 분류·채점, LLM 판사가 평결 | 사실은 결정적, 평결은 유연 |
| 통합 범위 | 논쟁이 유일한 결론 (기존 결론 제거) | "따로 논다" 정면 해결 |
| 안전 가드레일 | 하드 리스크룰이 판사의 액션 공간 제한 | 투명한 리스크 통제 |
| actionable_signal | 은퇴 | 평결·포지션플랜·시나리오가 대체 |
| LLM 콜 구조 | 2콜 (변론 + 독립 판사) | 판사가 자기 변론 합리화 방지 |
| 지표 구조 | **3계층 레지스트리** (프리미티브→게이트/점수/설명) | 재계산·이중계상 제거 |
| 모멘텀 섹션 | RSI·MACD·거래량·ADX를 독립 섹션으로 | 추세(Stage2)와 다른 축 |
| 보조지표 | cRSI·Fast MACD·Stochastic·CCI는 원시 데이터로 | 핵심 메시지 보호 |
| 퍼포먼스 | 3M·1Y를 Summary에 (6M은 RS와 겹쳐 제외) | 절대수익 ≠ 상대강도 |

### 2.1 리뷰 반영 결정 (서브에이전트 리뷰 후 확정)

| # | 항목 | 결정 | 근거 |
|---|------|------|------|
| R1 | `canslim_M` vs `gate_A` 이중카운트 | **entry 모드에서 canslim_M 장부 제외** (holding은 게이트 없으니 유지) | 둘 다 `market_regime.allow_new_buy`에서 파생. `canslim_L`을 gate_C 때문에 뺀 것과 동일 논리 |
| R2 | momentum_events를 논쟁 증거로? | **Event 섹션 표시용으로만. ledger 증거 제외** | 게이트·CAN SLIM·팩터가 이미 같은 기저 신호를 점수화. 사건 재투입은 중복 |
| R3 | accumulation 가중치 | **canslim_I weight 1 유지 + 노트** (캘리브레이션은 운영 후) | 스펙 weight 2와 다르나 이중카운트 방지 우선 |
| R4 | 판단요약(decision_summary) | **플랜 A에서 삭제**(렌더 안 함) | 플랜 A는 평가·판정 배제, 순수 증거 표시. 종합판정(플랜 B)이 유일 결론 |
| R5 | 신규 사건 감지 모듈 위치 | **`src/tools/technical/events.py`** (순수 raw_dataframe 함수) | pipelines는 순수 오케스트레이션. RS 전환만 playbook/relative_strength |
| R6 | 렌더링 위치 | **`src/cli/analyze_render.py`로 분리** | main.py는 Typer 커맨드·오케스트레이션만. 섹션 포맷·조립은 별도 모듈 |
| R7 | 모듈 경계 | Tool=도메인 계산 / Pipeline=조율 / CLI=렌더. 사건감지=Tool | 레이어 책임 명확화 (§3.0) |
| R8 | 가중치·논쟁·평가 | **플랜 A에서 일절 배제** (전부 플랜 B) | 플랜 A는 수집→가공→렌더만 |

---

## 3. 전체 아키텍처 / 데이터 흐름

### 3.0 레이어 책임 경계

| 레이어 | 하는 일 | 규칙 |
|--------|---------|------|
| **Providers** | 외부 원시 데이터 fetch (yfinance, KIS) | 네트워크 호출만 |
| **Tools** | 한 도메인 재료를 결과로 가공 (지표·사건·판정) | 단독 계산·단독 테스트 가능 |
| **Pipelines** | 여러 tool 호출 + result 조립 + LLM 조율 | 도메인 계산 안 함, 조율만 |
| **CLI** | result → 마크다운 렌더 | 표시만. 포맷 로직은 `analyze_render.py`로 분리 |

"수집 → 가공 → 렌더링" 매핑:
- **수집** = Providers(fetch) + Tools(원시→지표)
- **가공** = Tools(단일 도메인: 차트→사건, 게이트 판정) + Pipelines(교차 조립: 여러 결과를 result로)
- **렌더** = CLI

→ 사건 감지(events)는 차트 한 재료의 가공이므로 **Tool**. deep_dive(Pipeline)는 그것을 호출·조립만 하고 계산하지 않는다. 렌더 함수는 main.py가 아니라 `src/cli/analyze_render.py`에 둔다.

### 3.1 데이터 흐름

```text
deep_dive.run(ticker)
  │
  ├─ [기존] technical · fundamental · flow · disclosure · news
  ├─ [기존] playbook_verdict   (PlaybookEngine.evaluate → PlaybookVerdict)
  ├─ [기존] decision_bundle    (build_analyze_decision_bundle → factor_assessments + scenarios)
  │
  ├─ [신규] build_momentum_events(df, vol_sma)        ← tools/technical/events.py (순수)
  │         MACD크로스 · RSI다이버전스 · 신고가/스윙로우 · U/D Volume · 거래량추세
  │         RS 전환은 relative_strength 확장 → playbook_verdict 경유로 주입
  │
  ├─ [신규] build_evidence_ledger(...)                ← pipelines/debate/ledger.py (순수)
  │         playbook_verdict + factor_assessments + snapshot + flow
  │         → BullBearLedger { bull[], bear[], neutral[], weights, action_space }
  │         · momentum_events 는 증거 아님(R2). Event 섹션 표시용
  │
  ├─ [신규] run_debate(ledger, llm, ticker)           ← pipelines/debate/engine.py (LLM 2콜)
  │         ① 변론 콜 ② 독립 판사 콜 → DebateBundle
  │
  └─ 출력: 종합판정 → Summary → CAN SLIM → Stage2 → 모멘텀 → Event → 구조레벨 → 증거상세 → 원시
```

**레이어 배치 (R5):**
- `src/tools/technical/events.py` — 차트 사건 감지(순수 함수, raw_dataframe만 읽음)
- `src/tools/technical/events_models.py` — 사건 결과 모델
- `src/tools/criteria/relative_strength.py` — RS 전환 감지(index_df 필요, playbook 소속)
- `src/pipelines/debate/` — 증거 장부 + 논쟁 엔진(오케스트레이션)
- `src/llm/models.py`, `src/llm/analyzer.py` — LLM I/O 모델·함수
- `src/cli/analyze_render.py` — analyze 출력 렌더(섹션 함수 + 조립). **main.py에서 분리**
- `src/cli/main.py` — Typer 커맨드·파이프라인 오케스트레이션만 (렌더는 import)

---

## 4. 3계층 지표 레지스트리

**핵심 원칙: 프레임워크는 통째로 보존하되, 역할(계층)을 분리해 이중계상을 막는다. 같은 원천값(프리미티브)은 한 번만 계산하고 여러 프레임워크가 공유한다.**

```text
[프리미티브] 원천값 1회 계산 (single source of truth)
        ├─ [게이트 계층]  Stage2/Minervini Trend Template → 통과/탈락 (점수 0)
        ├─ [점수 계층]    CAN SLIM 7요소 + factor_valuation → 가중합
        └─ [설명·청산]    factor_*(bias 설명) · exit_verdict(보유 청산) · momentum_events(사건 표시)
```

### 4.1 프리미티브

| 프리미티브 | 원천 | 공유 프레임워크 |
|---|---|---|
| 시장레짐 | `market_regime` | 게이트 A, CAN SLIM M, 청산 |
| SMA 체계 | `is_stage2` / SMA20·50·150·200 | 게이트 B, exit_SMA_* |
| 상대강도 | `relative_strength.mansfield_rs` (+sector) | 게이트 C, CAN SLIM L, exit_RS, rs_magnitude |
| VCP 돌파 | `gate.checklist[E]` | 게이트 E |
| EPS 분기/연간 | `canslim.c` / `canslim.a` | CAN SLIM C·A |
| 촉매 | `canslim.n` | CAN SLIM N |
| 거래량 수요 | `canslim.s` / U/D Volume | CAN SLIM S, 모멘텀 거래량 |
| 매집/분산 | `AccumulationResult` | CAN SLIM I, exit_DISTRIBUTION |
| 수급(외인/기관) | `flow.*_direction_5d` | 장부 flow 행 |
| RSI / MACD | `snapshot.rsi` / `snapshot.macd` | 모멘텀, 다이버전스/크로스 사건 |

### 4.2 이중계상 제거 (확정)

| 신호 | 점수 계상 위치 | 제거 대상 |
|---|---|---|
| 상대강도(RS) | `gate_C`(boolean) + `rs_magnitude`(연속값) | `canslim_L` 제거 (gate_C 중복) |
| 시장레짐 | `gate_A` | `canslim_M` entry 제거 (R1) |
| 수급 | `flow` 행 | `factor_flow` 제거 |
| 매집 | `canslim_I` (weight 1) | 별도 accumulation 행 안 둠 (R3) |
| 차트 사건 | 게이트/팩터가 기저 점수화 | momentum_events 증거 제외, 표시만 (R2) |

---

## 5. 출력 레이아웃

```text
# Deep Dive Analysis: TICKER
## 가격: $... (±%)

## 🧭 종합 판정                      ← 유일한 결론 (플랜 B). 없으면 생략
   - 액션 | 확신도 | 결정적 변수
## 🟢 Bull 논거 / 🔴 Bear 논거 / ⚖️ 판결 사유

## 📊 Summary                       ← 게이트 4 pass/fail(부연 1줄) + 핵심수치 + 퍼포먼스(3M·1Y)
## CAN SLIM                         ← 점수 + 미충족 한 줄 + 전 요소 충족·미충족 수치
## Stage 2                          ← SMA 값 + 정배열 + Supertrend(방향/라인/현재가 gap%)
## 모멘텀                            ← RSI(다이버전스) · MACD(크로스) · 거래량(U/D·추세) · ADX
## Event                            ← 신고가 돌파/실패 · 스윙로우 · RS 전환 · 차트패턴(완성 날짜)
## 구조 레벨                         ← 수요/공급/밸런스 존 + Pivot/S1/R1
## 📊 증거 상세                      ← 플레이북 포지션플랜/매도판정 · 팩터 스코어 · 시나리오
## 원시 데이터                       ← cRSI · Fast MACD · Stochastic · CCI · 펀더멘털 · 뉴스/공시/수급
```

종합 판정은 최상단(유일한 결론, **플랜 B 전담**). **플랜 A는 판단요약을 렌더하지 않는다** — 결론 없는 구조화 증거 리포트다(R4). 모든 섹션 포맷 함수와 `format_deep_dive_output`은 main.py가 아니라 `src/cli/analyze_render.py`에 둔다(R6). `format_deep_dive_output`은 `result.get("debate")`를 읽어 None이면(플랜 A 단독 상태) 종합 판정 섹션을 건너뛴다 — 이 "빈 자리"를 플랜 A가 미리 만들어 두므로 플랜 B는 충돌 없이 채우기만 한다.

### 5.1 섹션별 내용 규칙

- **CAN SLIM**: `6 / 7 · 미충족: I(기관매집)` 헤더 + 각 요소 `✅/❌ C 분기EPS: +42% (기준 25%)`처럼 충족·미충족 모두 수치.
- **Stage2**: SMA 값 + 정배열 여부 + `Supertrend: 상승 (라인 $140.00, 현재가 대비 +10.9%)`.
- **모멘텀**: RSI 값+상태+다이버전스(날짜), MACD 값/시그널/히스토그램+크로스(날짜), U/D Volume Ratio + 거래량 추세, ADX 강도.
- **Event**: 모든 사건에 발생 날짜. Bull(신고가 돌파·RS 양전환) / Bear(신고가 실패·스윙로우 이탈·RS 음전환·하락 다이버전스) 동일 형식.

---

## 6. 신규 사건 감지 (`src/tools/technical/events.py`)

전부 순수 함수. `raw_dataframe`(이미 모든 지표 컬럼 보유)만 읽는다.

| 함수 | 산출 | 비고 |
|---|---|---|
| `compute_ud_volume_ratio(df, window=50)` | 상승일 거래량 합 ÷ 하락일 거래량 합 | 미너비니·오닐식 매수압력 |
| `compute_volume_trend(vol_sma_20, vol_sma_50)` | "증가"/"감소"/"횡보" | 기존 SMA 비교 |
| `detect_macd_cross(df, lookback=60)` | 골든/데드 크로스 + 날짜 + days_ago | MACD vs Signal 부호 전환 |
| `detect_rsi_divergence(df, window=20)` | 상승/하락 다이버전스 + 날짜 + 수치 | plateau 대응 위해 `>=` 한쪽 허용 |
| `detect_price_events(df)` | 신고가 돌파/실패, 스윙로우 이탈/유지 + 날짜 | High_52w·Swing_Low 컬럼 |
| `build_momentum_events(df, vol_sma_20, vol_sma_50)` | 위를 묶은 `MomentumEvents` | RS 전환은 deep_dive가 주입 |

**RS 전환** (`relative_strength.py` 확장): `compute_relative_strength`가 mansfield 시계열로 음↔양 전환을 감지해 `RelativeStrengthResult.rs_cross_type/date/days_ago`에 담는다. 진짜 부호 전환(−1↔+1)만 잡고, 0(동률)에서의 출발은 제외한다. `playbook_verdict.relative_strength` 경유로 deep_dive에 전달된다.

---

## 7. 증거 장부 (`src/pipelines/debate/ledger.py`)

순수 함수. 기존 판정 결과를 bull/bear/neutral로 분류·채점. **새 데이터 안 만듦.**

### 7.1 라우팅 규칙 — entry (미보유)

| 증거 key | 출처 | 진영 | 가중치 |
|---|---|---|---|
| `gate_A` | `gate.checklist[A].met` | met→bull / else→bear | 4 |
| `gate_B` | `gate.checklist[B].met` | met→bull / else→bear | 4 |
| `gate_C` | `gate.checklist[C].met` (RS+업종) | met→bull / else→bear | 4 |
| `gate_E` | `gate.checklist[E].met` (VCP) | met→bull / else→bear | 3 |
| `canslim_C·A·N·S·I` | `canslim.{c,a,n,s,i}.met` | met→bull / False→bear / None→neutral | 1 |
| `rs_magnitude` | `relative_strength.mansfield_rs` | >0→bull / <0→bear | min(\|rs\|/10, 3) |
| `flow` | `flow.*_direction_5d` | 매수→bull | 2 |
| `factor_technical·valuation·event` | `factor_assessments[].bias` | bullish→bull / bearish→bear / neutral→neutral | total_score/3 (≤5) |
| `rsi_overbought` | `snapshot.rsi >= 80` | bear | 2 |

**제외 (이중계상):** `canslim_L`(gate_C), `canslim_M`(gate_A, entry만), `factor_flow`(flow 행). `accumulation`은 `canslim_I`로만(weight 1).

### 7.2 라우팅 규칙 — holding (보유)

게이트 제외, `canslim_M` 포함(게이트 없으므로 중복 아님), 추가:

| 증거 key | 출처 | 진영 | 가중치 |
|---|---|---|---|
| `exit_{code}` | `exit_verdict.signals[]` | bear | strong=5 / medium=3 / weak=1 |
| `r_cushion` | `exit_verdict.current_r` | >0→bull / <0→bear | min(\|r\|, 3) |

### 7.3 momentum_events 처리 (R2)

momentum_events(MACD크로스·RSI다이버전스·RS전환·가격사건)는 **장부 증거에 넣지 않는다.** Event 섹션 표시용으로만 사용한다. 게이트·CAN SLIM·팩터가 같은 기저 신호를 이미 점수화하기 때문이다. (후속: RS 전환 등 고유 사건을 선별 투입할 여지는 캘리브레이션 단계에서 재검토)

---

## 8. 논쟁 엔진 (`src/pipelines/debate/engine.py`)

`run_debate(ledger, llm, ticker) -> DebateBundle` — LLM 2콜.

- **① 변론 콜** (`DebateAdvocacyInput` → `DebateAdvocacyOutput`): 각 진영이 **자기 장부 증거만** 인용해 `bull_case`/`bear_case` 작성. 숫자·사실 환각 금지.
- **② 판사 콜** (`DebateJudgeInput` → `DebateVerdictOutput`): 양측 변론 + 가중치 + `allowed_actions` → 단일 평결. `action`은 반드시 `allowed_actions` 중에서 선택.

`ticker`를 두 콜에 전달해 프롬프트 grounding을 확보한다(빈 문자열 금지). LLM 실패 시 `run_debate`가 예외 → deep_dive가 catch, 종합 판정 생략하되 **장부(증거)는 별도로 result에 실어** 증거 상세는 계속 표시한다.

### 8.1 LLM I/O 모델 (`src/llm/models.py`)

strict-schema 가드: 출력 모델(`DebateAdvocacyOutput`/`DebateVerdictOutput`)은 전부 타입 확정. `list[dict]`는 입력(`DebateAdvocacyInput`)에만.

- `DebateCase {stance, thesis, points[]}`
- `DebateAdvocacyInput {ticker, mode, bull_evidence: list[dict], bear_evidence: list[dict]}`
- `DebateAdvocacyOutput {bull_case, bear_case}`
- `DebateJudgeInput {ticker, mode, bull_case, bear_case, bull_weight, bear_weight, allowed_actions}`
- `DebateVerdictOutput {action, confidence, swing_factor, reconciliation}`

---

## 9. 안전 가드레일 (`compute_action_space`)

규칙이 판사의 액션 공간을 제한한다(옛 veto의 조용한 덮어쓰기와 다름 — bull 논거는 그대로 표시·변론되고 제한 이유는 판결문에 명시).

| 모드 | 조건 | 허용 액션 |
|---|---|---|
| entry | `market_regime.allow_new_buy is False` | `["관망"]` |
| entry | 그 외 | `["매수", "관망"]` |
| holding | strong 매도신호 또는 `exit_verdict.action=="liquidate"` | `["청산", "비중축소"]` |
| holding | medium 신호 **≥1** (2개 이상도 동일 버킷) | `["비중축소", "보유"]` |
| holding | 그 외 | `["보유", "비중축소"]` |

> 리뷰 반영: medium 신호 2개 이상이 1개보다 관대해지던 역전을 `>= 1`로 수정. `playbook_verdict is None`이면 무제약(graceful).

---

## 10. 제거 / 마이그레이션

| 대상 | 위치 | 조치 |
|---|---|---|
| `apply_playbook_veto` | `analyze_decision.py` | 삭제 + `veto_applied`/`action_original` 필드 제거 |
| `_generate_integrated_analysis` | `deep_dive.py` | 제거 |
| integrated_analysis 렌더 | `main.py:817-830` | **삭제** (리뷰 지적 — 죽은 코드) |
| `IntegratedAnalysisInput/Output` | `llm/models.py` | 삭제 |
| `generate_integrated_analysis` | `llm/analyzer.py` | 삭제 |
| `actionable_signal` 생성/표시 | `deep_dive.py`, `main.py` | 은퇴 |
| `generate_actionable_signal`·`ActionableSignalOutput` | `analyzer.py`, `models.py` | 삭제 |
| `_format_top_summary` | `main.py` | **플랜 A에서 제거** (판단요약 삭제, R4). analyze_render로 옮기지 않음 |
| `display_actionable_signal` | `main.py` | 삭제 |
| deep_dive 렌더 함수 전체 | `main.py` → `analyze_render.py` | **플랜 A에서 이동** (R6): `_format_*`, `format_deep_dive_output` |

**테스트 마이그레이션 (리뷰 지적):** 제거 심볼을 import/mock 하는 테스트 파일(`test_apply_playbook_veto.py`, `test_analyzer.py`, `test_models.py`, `test_deep_dive.py`, `test_deep_dive_structure_contract.py`, `test_cli.py`, `test_analyze_output.py`)을 각각 삭제 또는 새 debate 함수로 재배선한다. `build_analyze_decision_bundle`은 **유지**(factor_assessments·scenarios 산출).

---

## 11. 영향 받는 파일

**신규**
- `src/tools/technical/events.py`, `events_models.py` (사건 감지 — Tool)
- `src/cli/analyze_render.py` (deep_dive 출력 렌더 — main.py에서 분리)
- `src/pipelines/debate/__init__.py`, `models.py`, `ledger.py`, `engine.py`, `grounding.py` (플랜 B)
- `tests/tools/technical/test_events.py`, `tests/cli/test_analyze_render.py`, `tests/pipelines/debate/*`

**수정**
- `src/tools/criteria/relative_strength.py`, `models.py` (RS 전환 필드)
- `src/pipelines/deep_dive.py` (사건 tool 호출·조립; 플랜 B에서 논쟁 배선·제거)
- `src/cli/main.py` (렌더를 analyze_render로 분리·import; 판단요약/actionable 제거)
- `src/llm/models.py`, `analyzer.py` (플랜 B: debate 추가, integrated/actionable 제거)
- `src/pipelines/analyze_decision.py` (플랜 B: veto 삭제)
- `docs/FEATURES.md`

---

## 12. 테스트 전략

실 DB/실 LLM 없이 합성 입력 + mock. 핵심:
- 사건 감지: 합성 df로 U/D ratio(상승 3·하락 2 → 3.0), MACD 크로스 날짜, 신고가/스윙로우, RSI 다이버전스, **진짜 부호 전환을 만드는** RS 전환.
- 장부: entry/holding 라우팅, `canslim_L`/`canslim_M`(entry)/`factor_flow` 제외 단언, 가중치.
- action_space: 하락장→관망, strong→보유강화 불가, medium≥2 버킷.
- 엔진: mock LLM, `action ∈ allowed_actions`.
- 스키마: 출력 모델 strict 회귀가드.
- **통합 렌더**: 최소 result dict로 `format_deep_dive_output` 섹션 순서 + 종합판정 포함 검증(리뷰 지적 — 격리 테스트만으론 배선 누락 못 잡음).

---

## 13. 미해결 / 후속

- 가중치 캘리브레이션(accumulation weight, momentum 사건 선별 투입, 변론 길이·판사 confidence)은 실제 출력 보고 조정.
- SMA 기울기(%/주) 표기는 후속 — 현재는 값+정배열+Supertrend gap에 집중. FEATURES.md에 기울기를 명시하지 않는다.
- 다중 종목(`report`)·`quick_check` 적용은 본 스펙 범위 밖.
