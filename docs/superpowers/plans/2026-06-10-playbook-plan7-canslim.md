# CAN SLIM 종합 Implementation Plan (Plan 7/8)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. 체크박스(`- [ ]`)로 추적.

**Goal:** `canslim.py` — 부품 결과를 종합해 CAN SLIM 7요소를 정량 판정한다(C·A·I 신규 계산, N·S·L·M은 다른 모듈 결과 참조). 그리고 Plan 2에서 미뤘던 **분기 EPS 시계열 병합**을 정리한다(C의 가속 판정에 필요).

**Architecture:** `compute_canslim(...)`는 **순수 함수** — 이미 계산된 부품 결과(`FundamentalSnapshot`, `AccumulationResult`, `SectorStrengthResult`, `RelativeStrengthResult`, `MarketRegimeResult`)와 technical `snapshot`/`components`를 주입받아 `CanslimResult`를 반환. fetch 없음. 데이터 없으면 해당 요소 `met=None`(이중 계산 금지: N·S·L·M은 참조만).

**Tech Stack:** Python 3.12, pandas, pydantic, pytest. `uv run`.

**선행:** Plan 2~6 (fundamental EPS, accumulation, RS, sector_strength, market_regime, minervini is_stage2).

**CAN SLIM 매핑(스펙 §7):** C=분기EPS, A=연간EPS+ROE, N=52주 신고가 근접, S=거래량+유통주식, L=업종+종목 RS, I=매집(거래량), M=시장환경.

---

## File Structure
- **Modify:** `src/tools/playbook/models.py` — `ElementVerdict`, `CanslimResult`
- **Modify:** `src/tools/fundamental.py` — 분기 EPS 시계열 병합 정리(quarterly_data를 profit-ratio 분기 EPS 기준으로, 연간 행 혼입 제거)
- **Create:** `src/tools/playbook/canslim.py` — `compute_canslim(...)`
- **Test:** `tests/tools/playbook/test_canslim.py`, `tests/tools/test_fundamental_eps.py`(병합 보강)

---

## Task 1: ElementVerdict + CanslimResult 모델

- [ ] **Step 1: 실패 테스트** (`tests/tools/playbook/test_canslim.py`)

```python
from src.tools.playbook.models import ElementVerdict, CanslimResult

def test_canslim_score_counts_met():
    e = lambda m: ElementVerdict(met=m, detail="")
    r = CanslimResult(c=e(True), a=e(True), n=e(False), s=e(None),
                      l=e(True), i=e(True), m=e(True))
    assert r.score == 5            # met True 개수 (None 제외)
    assert "C✅" in r.summary and "S—" in r.summary
```

- [ ] **Step 2~3: 구현** — `models.py`:

```python
class ElementVerdict(BaseModel):
    met: bool | None
    detail: str = ""

class CanslimResult(BaseModel):
    c: ElementVerdict; a: ElementVerdict; n: ElementVerdict; s: ElementVerdict
    l: ElementVerdict; i: ElementVerdict; m: ElementVerdict

    @computed_field
    @property
    def score(self) -> int:
        return sum(1 for e in (self.c,self.a,self.n,self.s,self.l,self.i,self.m) if e.met is True)

    @computed_field
    @property
    def summary(self) -> str:
        order = [("C",self.c),("A",self.a),("N",self.n),("S",self.s),("L",self.l),("I",self.i),("M",self.m)]
        sym = {True:"✅", False:"❌", None:"—"}
        graded = sum(1 for _,e in order if e.met is not None)
        return " ".join(f"{k}{sym[e.met]}" for k,e in order) + f" ({self.score}/{graded})"
```

- [ ] **Step 4~5: 통과 + 커밋** `git commit -m "feat(playbook): ElementVerdict + CanslimResult model"`

---

## Task 2: 분기 EPS 시계열 병합 정리 (Plan 2 잔여)

현재 `_normalize_kis_snapshot`의 `quarterly_data`에 연간 행이 섞여(eps=None) 분기 EPS 시계열이 온전치 않다. **`quarterly_data`를 profit-ratio 분기 EPS(`_build_quarterly_eps`) 기준으로** 구성하고, balance-sheet 매출/순이익은 같은 `period`만 병합한다.

- [ ] **Step 1: 실패 테스트** — `_normalize_kis_snapshot`(또는 헬퍼) 결과 `quarterly_data`가 분기 period(`YYYY-03/06/09/12`)만 갖고, eps가 4개 분기 모두 채워지는지(연간 행 없음). mock profit_ratio_q(분기 5+개) + balance(분기) 입력.

- [ ] **Step 2~3: 구현** — `fundamental.py`: `quarterly_data` 빌드를 "profit-ratio 분기 EPS 시계열을 기준 리스트로 두고, balance-sheet 분기 매출/순이익을 period 매칭해 병합. 매칭 안 되는 balance 연간 행은 quarterly에 넣지 않음." (현재의 balance 기준 병합 → EPS 기준 병합으로 전환)

```python
# 개념: eps_rows = _build_quarterly_eps(profit_ratio_q)  # 분기 EPS 시계열
#       balance_by_period = {period: (revenue, earnings)} from valid_balance_sheet (분기만)
#       for q in eps_rows: q.revenue/earnings = balance_by_period.get(q.period)
#       quarterly_data = eps_rows   (연간은 annual_data로 분리, 이미 Plan 2)
```

- [ ] **Step 4~5: 통과 + 실데이터** — `fundamental.execute("005930.KS")`의 `quarterly_data`가 분기 4개 + eps/eps_yoy 모두 채워지는지(연간 혼입 없음). KIS 순차 호출(rate limit 주의).
- [ ] **Step 6: 커밋** `git commit -m "fix(fundamental): quarterly_data uses profit-ratio EPS series (no annual rows)"`

---

## Task 3: canslim.py 종합

- [ ] **Step 1: 실패 테스트** — 부품 결과 주입 → 7요소 판정. 예: 강한 종목(C/A 성장↑, N 신고가, L 강세, I 매집, M 상승) → score 높음.

```python
# tests/tools/playbook/test_canslim.py
from src.tools.playbook.canslim import compute_canslim
# mock inputs (snapshot, components, fundamental, accumulation, sector, rs, regime)
# assert result.c.met / a.met / ... 기대대로, score 합산
```

- [ ] **Step 2~3: 구현** — `src/tools/playbook/canslim.py`:

```python
from src.tools.playbook.models import CanslimResult, ElementVerdict

_GROWTH = 0.25

def _v(met, detail=""):
    return ElementVerdict(met=met, detail=detail)

def compute_canslim(*, snapshot, components, fundamental, accumulation,
                    sector_strength, relative_strength, market_regime) -> CanslimResult:
    # C: 최근 분기 EPS YoY >= 25% (+ 가속: 최근 > 직전)
    q = (fundamental.quarterly_data or []) if fundamental else []
    if q and q[0].eps_yoy is not None:
        accel = len(q) > 1 and q[1].eps_yoy is not None and q[0].eps_yoy > q[1].eps_yoy
        c = _v(q[0].eps_yoy >= _GROWTH, f"분기EPS YoY {q[0].eps_yoy:.1%}{' 가속' if accel else ''}")
    else:
        c = _v(None, "분기 EPS 없음")
    # A: 연간 EPS 성장 + ROE
    a_data = (fundamental.annual_data or []) if fundamental else []
    if len(a_data) >= 2 and a_data[0].eps and a_data[1].eps:
        g = (a_data[0].eps - a_data[1].eps) / abs(a_data[1].eps)
        roe_ok = (fundamental.roe or 0) >= 0.15
        a = _v(g >= _GROWTH and roe_ok, f"연EPS {g:.1%}, ROE {fundamental.roe}")
    else:
        a = _v(None, "연간 EPS 부족")
    # N: 52주 신고가 -25% 이내 (참조 — snapshot)
    if snapshot and snapshot.high_52w:
        near = snapshot.price >= snapshot.high_52w * 0.75
        n = _v(near, f"52주고점 대비 {(snapshot.price/snapshot.high_52w-1)*100:.1f}%")
    else:
        n = _v(None, "52주 데이터 없음")
    # S: 거래량 신호(volume score>0) + 유통주식(있으면 가점)
    vol = (components or {}).get("volume", {})
    s_ok = vol.get("score", 0) > 0
    s = _v(s_ok, f"volume score {vol.get('score')}")
    # L: 업종 강세 AND 종목 RS 강세 (참조)
    l_strong = bool(getattr(sector_strength, "is_strong", None)) and bool(getattr(relative_strength, "is_strong", None))
    l_none = sector_strength is None and relative_strength is None
    l = _v(None if l_none else l_strong, "업종+RS")
    # I: 매집 우세 or Pocket Pivot (참조)
    pp = any("Pocket Pivot" in sig for sig in vol.get("signals", []))
    i_met = (getattr(accumulation, "is_accumulating", None) is True) or pp
    i = _v(i_met if accumulation or vol else None, f"매집 {getattr(accumulation,'accumulation_ratio',None)}, PP={pp}")
    # M: 시장환경 (참조)
    m = _v(getattr(market_regime, "allow_new_buy", None), getattr(market_regime, "regime", ""))
    return CanslimResult(c=c, a=a, n=n, s=s, l=l, i=i, m=m)
```

- [ ] **Step 4~6: 통과 + 실데이터(AAPL·005930 — 부품 조립해 compute_canslim 호출, score/summary 출력) + 커밋** `git commit -m "feat(playbook): CAN SLIM aggregation (C/A/I compute + N/S/L/M reference)"`

---

## Self-Review
**1. 스펙 커버리지:** §7 7요소 매핑(C·A·I 계산, N·S·L·M 참조) → T3 ✅; 분기 EPS 가속용 시계열 정리 → T2 ✅; 이중 계산 방지(N·S·L·M은 기존 결과 참조) ✅.
**2. Placeholder:** 없음(부품 결과 인터페이스는 Plan 2~6에서 정의됨).
**3. 타입 일관성:** `compute_canslim` 키워드 인자명이 부품 result 타입과 일치; `CanslimResult.score/summary` computed.

> 한국은 `sector_strength`가 KIS로 채워지고, `float_shares`는 None일 수 있음(S는 거래량 위주). 데이터 없는 요소는 `met=None` → score 분모에서 제외(summary의 `/graded`).

---

## 다음 단계
Plan 8(마지막): `gate`(★ 종합 + veto) · `sizing` · `exit_rules` · `holdings`(YAML) · `engine`(부품 오케스트레이션) · `deep_dive`/`analyze_decision`(veto)/`main.py` 연결.
