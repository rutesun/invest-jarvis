# 조립: gate·sizing·exit·holdings·engine Implementation Plan (Plan 8/9)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. 체크박스(`- [ ]`)로 추적.

**Goal:** Plan 2~7 부품을 조립해 **`PlaybookVerdict`**를 만든다 — 매수 게이트(veto), 포지션 사이징, 보유 매도 판정, YAML 보유 로더, 그리고 이들을 오케스트레이션하는 `engine`.

**Architecture:** `gate`/`sizing`/`exit_rules`는 순수 함수(부품 결과 주입). `holdings`는 YAML I/O. `engine.evaluate(...)`가 provider fetch(IndexProvider/FmpProvider) + 순수 부품 호출 + 분기(미보유→gate+sizing / 보유→exit_rules)를 조립한다. **연결(deep_dive/analyze_decision/cli)은 Plan 9.**

**Tech Stack:** Python 3.12, pydantic, pyyaml, pytest. `uv run`.

**선행:** Plan 2~7 부품 전부(`market_regime`, `relative_strength`, `sector_strength`, `vcp`, `accumulation`, `canslim`, fundamental EPS, `IndexProvider`, `FmpProvider`).

---

## File Structure
- **Modify:** `src/tools/playbook/models.py` — `GateCheck`, `GateResult`, `PositionPlan`, `ExitSignal`, `ExitVerdict`, `PlaybookVerdict`
- **Create:** `src/tools/playbook/holdings.py` — `playbook.yaml` 로더
- **Create:** `src/tools/playbook/gate.py` — `evaluate_gate(...)`
- **Create:** `src/tools/playbook/sizing.py` — `plan_position(...)`
- **Create:** `src/tools/playbook/exit_rules.py` — `evaluate_exit(...)`
- **Create:** `src/tools/playbook/engine.py` — `PlaybookEngine.evaluate(...)`
- **Test:** `tests/tools/playbook/test_{holdings,gate,sizing,exit_rules,engine}.py`

---

## Task 1: 모델 (§14)
`models.py`에 추가: `GateCheck(name, required, met: bool|None, reason)`, `GateResult(passed, checklist, quality_grade: str|None, veto_reason: str|None)`, `PositionPlan(entry, stop, stop_basis, per_share_risk, shares: int|None, position_value: float|None, weight_pct: float|None, r_targets: dict, capital_mode, error: str|None)`, `ExitSignal(code, severity, detail)`, `ExitVerdict(action, signals: list[ExitSignal], current_r: float|None, trailing_stop: float|None, detail)`, `PlaybookVerdict(ticker, holding: bool, market_regime, relative_strength, sector_strength: SectorStrengthResult|None, canslim, gate: GateResult|None, position_plan: PositionPlan|None, exit_verdict: ExitVerdict|None, headline)`.
- [ ] TDD: 생성 테스트 → 구현 → 커밋 `feat(playbook): gate/sizing/exit/verdict models`

## Task 2: holdings.py (YAML)
`load_holdings(path="playbook.yaml") -> HoldingsConfig`. `account.{krw,usd}.{capital, risk_per_trade_pct}`, `holdings[].{ticker, quantity, avg_price, stop_price?}`. 통화는 `is_korean_ticker`(disclosure.py) 재사용. 파일 없으면 빈 설정(전부 미보유, 비율 모드). `find(ticker)` → holding or None.
- [ ] TDD: 파일 없음/통화 누락/티커 매칭 테스트 → 구현 → 커밋 `feat(playbook): YAML holdings/account loader`

## Task 3: gate.py (★ 종합 + veto)
`evaluate_gate(*, market_regime, is_stage2: float, relative_strength, sector_strength, vcp, canslim, flow) -> GateResult`.
- ★ A=`market_regime.allow_new_buy`; B=`is_stage2 == 1.0`; C=`relative_strength.is_strong AND (sector_strength.is_strong in (True, None) — None이면 종목 RS만, graceful)`; E=`vcp.breakout`.
- ★ 하나라도 False → `passed=False`, `veto_reason`=가장 결정적 미충족 항목. ★ 입력이 None(데이터 결측)이면 보수적 FAIL("데이터 제한: {항목}") — 단 C의 sector_strength None은 종목 RS 살아있으면 통과(§6.3).
- 가점: D=`canslim.score`, I=canslim.i.met, 수급=flow(한국). `quality_grade`(A/B/C, 적격 시 가점 충족 비율).
- checklist에 각 GateCheck.
- [ ] TDD: 적격/★탈락/★None/sector None graceful 케이스 → 구현 → 커밋 `feat(playbook): buy gate with veto`

## Task 4: sizing.py
`plan_position(*, entry, atr_stop: float|None, invalidation_low: float|None, capital: float|None, risk_pct: float) -> PositionPlan`.
- 손절 후보: ①`entry*0.92` ②`atr_stop`(2×ATR) ③`invalidation_low`(zone lower). 가장 타이트(entry와 가까운) 채택, 단 손절폭 <3%면 다음 후보. **상한 가드**: 모두 −8% 초과면 `error="risk_too_wide"`.
- `per_share_risk=entry-stop`; `if <=0: error="invalid_stop", shares=None`. `shares=floor(capital*risk_pct/per_share_risk)`(capital 있으면). r_targets `+2R/+3R`. capital 없으면 `capital_mode="ratio"`(shares=None, 비율만).
- [ ] TDD: 골든(자본 1000만·위험1%·진입5만/손절4.75만→40주) + per_share_risk≤0 + 상한가드 → 구현 → 커밋 `feat(playbook): position sizing`

## Task 5: exit_rules.py (보유 매도 5단계)
`evaluate_exit(*, df, snapshot, relative_strength, accumulation, holding) -> ExitVerdict`.
- 신호(종가 기준): 1 성격변화(신고가 실패/스윙로우 이탈) 2 단기이평 이탈(종가<SMA20/50) 3 분산(accumulation 분산 우세) 4 RS 음전환 5 장기이평 이탈(종가<SMA150/200+기울기 꺾임).
- 매핑: 강(5)→청산; 중(2/3)→비중축소; 약(1·4)→경고+보유; 중 2개↑→청산.
- `current_r`: holding.stop_price 있으면 `(close-avg)/(avg-stop_price)`, 없으면 None + "평단 대비 ±X%". 트레일링: SMA50.
- [ ] TDD: 청산/비중축소/보유 케이스 → 구현 → 커밋 `feat(playbook): exit rules (5 signals)`

## Task 6: engine.py (오케스트레이션)
`PlaybookEngine(index_provider, fmp_provider, kis_provider).evaluate(ticker, technical_result, fundamental, flow, zone_set, holding) -> PlaybookVerdict`.
- fetch: `index_provider.get_index_history(ticker)` → (sym, index_df). 종목 stock_df = `technical_result.raw_dataframe`.
- 순수 부품: `assess_market_regime`, `compute_relative_strength`, `sector_strength`(미국=`FmpSectorStrength(fmp_provider)`, 한국=`KisSectorStrength(kis_provider)` — **Plan 5 우려1: provider 인터페이스를 여기서 올바르게 주입**), `detect_vcp_breakout`, `analyze_accumulation`, `compute_canslim`.
- `is_stage2 = technical_result.components["minervini"]["metrics"].get("is_stage2", 0.0)`.
- 분기: 미보유→`evaluate_gate` (PASS면 `plan_position`); 보유→`evaluate_exit`.
- `headline` 구성. `PlaybookVerdict` 반환.
- **KIS 동시 호출 주의**(순차). 실데이터: `engine.evaluate("AAPL"...)`, `("005930.KS"...)` 통합 — gate/canslim/sizing 또는 exit 채워지는지.
- [ ] TDD: mock 부품으로 미보유/보유 분기 + 실데이터 → 구현 → 커밋 `feat(playbook): engine orchestration -> PlaybookVerdict`

---

## Self-Review
**1. 스펙 커버리지:** §6(gate·veto·graceful)→T3; §10(sizing 상한가드·per_share_risk≤0)→T4; §11(exit 5신호)→T5; §13(holdings YAML)→T2; §4.2(engine 순서)→T6; §14 모델→T1. R23/D2(C★=종목RS+업종, sector None graceful)→T3. Plan5 우려1(sector provider 인터페이스)→T6.
**2. Placeholder:** 없음(부품 인터페이스 Plan 2~7 확정).
**3. 타입 일관성:** `PlaybookVerdict` 필드가 부품 result 타입과 일치; gate/sizing/exit 시그니처 명시.

> veto의 **최종 표면(decision_summary 덮어쓰기)**과 CLI 출력은 **Plan 9(연결)**에서. 이 Plan은 `PlaybookVerdict` 생성까지.

---

## 다음 단계
Plan 9(마지막): `deep_dive`가 `PlaybookEngine` 호출 + `zone_set` 전달, `analyze_decision`에 `apply_playbook_veto`, `main.py`에 "📋 플레이북 평가" 섹션 렌더.
