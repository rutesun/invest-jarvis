# CAN SLIM 데이터: fundamental EPS·연간 Implementation Plan (Plan 2/8)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 superpowers:executing-plans로 task별 실행. 체크박스(`- [ ]`)로 추적.

**Goal:** `fundamental.py`가 **분기 EPS YoY**(CAN SLIM C)와 **연간 EPS 시계열**(A)을 한국·미국 모두에서 제공하도록 확장한다.

**Architecture:** 한국은 **`financial-ratio`(tr=FHKST66430300)의 `eps`**를 div=1(분기)·div=0(연간)으로 받아 YoY를 직접 계산한다(2026-06 실호출 확정 — `profit-ratio`는 `eps=None`이라 쓰지 않음). 미국은 yfinance에서 분기/연간 EPS를 받는다(필드명은 Task 1 spike로 확정). 결과는 `QuarterlyData.eps/eps_yoy`와 새 `FundamentalSnapshot.annual_data`에 담는다.

**Tech Stack:** Python 3.12, yfinance, KIS OpenAPI, pydantic, pytest. `uv run`.

**선행:** Plan 1 완료(`get_financial_ratio(ticker, div_cls_code)` 존재). worktree `.env`에 KIS/OpenAI 키 있음.

**Scope:** 데이터 레이어(EPS 값 + YoY)까지. CAN SLIM의 C·A "판정"(≥25% 등)과 I·N·S·L·M 종합은 Plan 7(canslim)에서 이 데이터를 소비한다.

---

## File Structure

- **Create:** `scripts/verify_yf_eps.py` — yfinance EPS 필드 spike(1회용)
- **Modify:** `src/tools/fundamental.py`
  - `QuarterlyData` — `eps`, `eps_yoy` 필드 추가
  - `AnnualData` — 신규 모델
  - `FundamentalSnapshot` — `annual_data: list[AnnualData] | None`
  - `_normalize_kis_snapshot` / `_fetch_kis_fundamentals` — financial-ratio 분기·연간 EPS 파싱
  - `_fetch_yfinance_fundamentals` — 분기/연간 EPS 파싱
- **Modify:** `src/llm/models.py` — `FundamentalSummaryInput`에 연간 성장 요약 필드(R6)
- **Modify:** `src/cli/main.py` — 펀더멘털 출력에 연간 EPS 추세 렌더(R6)
- **Test:** `tests/tools/test_fundamental_eps.py`

---

## Task 1: yfinance EPS 필드 spike

미국 분기/연간 EPS를 yfinance 어디서 얻는지 실호출로 확정한다(`info["trailingEps"]`는 TTM 단일값이라 분기 YoY엔 부족).

**Files:** Create `scripts/verify_yf_eps.py`

- [ ] **Step 1: spike 스크립트 작성**

```python
# scripts/verify_yf_eps.py
"""yfinance 분기/연간 EPS 소스 확인. 실행: uv run python scripts/verify_yf_eps.py AAPL"""
import sys
import yfinance as yf

def main(ticker: str) -> None:
    t = yf.Ticker(ticker)
    print("=== quarterly_income_stmt index (EPS 후보) ===")
    qis = t.quarterly_income_stmt
    if qis is not None and not qis.empty:
        eps_rows = [r for r in qis.index if "EPS" in str(r) or "Earnings Per" in str(r)]
        print("columns(분기):", [str(c.date()) for c in qis.columns][:8])
        print("EPS rows:", eps_rows)
        for r in eps_rows:
            print(f"  {r}:", [qis.loc[r, c] for c in qis.columns[:8]])
    print("=== income_stmt (annual) EPS rows ===")
    ann = t.income_stmt
    if ann is not None and not ann.empty:
        eps_rows = [r for r in ann.index if "EPS" in str(r) or "Earnings Per" in str(r)]
        print("columns(연간):", [str(c.date()) for c in ann.columns][:6])
        print("EPS rows:", eps_rows)
    print("=== info trailingEps (TTM 단일) ===", t.info.get("trailingEps"))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "AAPL")
```

- [ ] **Step 2: 실행해 EPS 소스 확정**

Run: `uv run python scripts/verify_yf_eps.py AAPL`
기록: 분기 EPS 행 이름(예: `"Basic EPS"` / `"Diluted EPS"`)이 `quarterly_income_stmt`에 있는가? 연간(`income_stmt`)에도 있는가? 몇 분기/몇 년 제공되는가?
- **있으면**: Task 4에서 그 행을 파싱.
- **없으면**: `Net Income ÷ shares_outstanding`으로 근사 EPS 계산(Task 4에 분기 처리).

---

## Task 2: 모델 확장 (QuarterlyData.eps/eps_yoy, AnnualData, annual_data)

**Files:** Modify `src/tools/fundamental.py`; Test `tests/tools/test_fundamental_eps.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/tools/test_fundamental_eps.py
from src.tools.fundamental import QuarterlyData, AnnualData, FundamentalSnapshot

def test_quarterly_data_has_eps_fields():
    q = QuarterlyData(period="2025-Q2", eps=1920.0, eps_yoy=0.62)
    assert q.eps == 1920.0
    assert q.eps_yoy == 0.62

def test_annual_data_model():
    a = AnnualData(year="2025", eps=6564.0, revenue=3.0e14, earnings=3.0e13)
    assert a.year == "2025" and a.eps == 6564.0

def test_snapshot_holds_annual_data():
    snap = FundamentalSnapshot(annual_data=[AnnualData(year="2025", eps=6564.0)])
    assert snap.annual_data[0].eps == 6564.0
```

- [ ] **Step 2: 실행 → 실패**

Run: `uv run pytest tests/tools/test_fundamental_eps.py -v`
Expected: FAIL (`QuarterlyData` has no field `eps`; `AnnualData` not defined)

- [ ] **Step 3: 구현**

`fundamental.py`의 `QuarterlyData`에 필드 추가, `AnnualData` 신규, `FundamentalSnapshot`에 `annual_data`:

```python
class QuarterlyData(BaseModel):
    period: str
    revenue: float | None = None
    earnings: float | None = None
    revenue_yoy: float | None = None
    revenue_qoq: float | None = None
    earnings_yoy: float | None = None
    earnings_qoq: float | None = None
    eps: float | None = None          # NEW
    eps_yoy: float | None = None      # NEW


class AnnualData(BaseModel):           # NEW
    year: str
    eps: float | None = None
    revenue: float | None = None
    earnings: float | None = None
```

`FundamentalSnapshot`에 한 줄 추가:

```python
    # Annual time series (CAN SLIM A)
    annual_data: list[AnnualData] | None = None
```

- [ ] **Step 4: 실행 → 통과**

Run: `uv run pytest tests/tools/test_fundamental_eps.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/tools/fundamental.py tests/tools/test_fundamental_eps.py
git commit -m "feat(fundamental): add eps/eps_yoy + AnnualData model"
```

---

## Task 3: 한국 financial-ratio EPS 파싱 (분기 YoY + 연간)

`financial-ratio`의 `eps`를 div=1(분기), div=0(연간)으로 받아 `quarterly_data[].eps/eps_yoy` + `annual_data`를 채운다. 전년 동기 비교는 `stac_yymm` 월(`MM`) 매칭으로 한다(예: `202506` vs `202406`).

**Files:** Modify `src/tools/fundamental.py`; Test `tests/tools/test_fundamental_eps.py`

- [ ] **Step 1: 실패 테스트 (YoY 매칭 로직)**

```python
from src.tools.fundamental import FundamentalTool

def test_kis_quarterly_eps_yoy_matches_same_month():
    # financial-ratio div=1 분기 행 (최신순). eps 문자열은 KIS 응답 형식.
    rows = [
        {"stac_yymm": "202506", "eps": "1920.00"},
        {"stac_yymm": "202503", "eps": "1186.00"},
        {"stac_yymm": "202412", "eps": "4950.00"},
        {"stac_yymm": "202409", "eps": "3701.00"},
        {"stac_yymm": "202406", "eps": "1186.00"},  # 전년 동기(6월)
    ]
    q = FundamentalTool._build_quarterly_eps(rows)
    # 202506 EPS YoY = (1920 - 1186)/1186
    latest = q[0]
    assert latest.period.endswith("06")
    assert latest.eps == 1920.0
    assert abs(latest.eps_yoy - (1920.0 - 1186.0) / 1186.0) < 1e-6
```

- [ ] **Step 2: 실행 → 실패**

Run: `uv run pytest tests/tools/test_fundamental_eps.py::test_kis_quarterly_eps_yoy_matches_same_month -v`
Expected: FAIL (`_build_quarterly_eps` not defined)

- [ ] **Step 3: 구현**

`fundamental.py`에 staticmethod 추가(전년 동기 = 같은 `MM`, 1년 전 `YYYY`):

```python
@classmethod
def _build_quarterly_eps(cls, financial_ratio_q_rows: list[dict]) -> list[QuarterlyData]:
    """financial-ratio div=1 분기 행으로 EPS + YoY 계산.
    YoY는 같은 분기월(MM) 1년 전(YYYY-1) 행과 비교."""
    by_period: dict[str, float] = {}
    for row in financial_ratio_q_rows:
        ym = (row.get("stac_yymm") or "").strip()
        eps = cls._to_float(row.get("eps"))
        if len(ym) == 6 and eps is not None:
            by_period[ym] = eps

    result: list[QuarterlyData] = []
    for ym in list(by_period.keys())[:4]:   # 최신 4분기
        eps = by_period[ym]
        year, mm = ym[:4], ym[4:]
        prev = f"{int(year) - 1}{mm}"
        prev_eps = by_period.get(prev)
        eps_yoy = (eps - prev_eps) / abs(prev_eps) if prev_eps not in (None, 0) else None
        result.append(QuarterlyData(period=f"{year}-{mm}", eps=eps, eps_yoy=eps_yoy))
    return result
```

`_fetch_kis_fundamentals`에 financial-ratio 분기 호출을 추가하고, `_normalize_kis_snapshot`에서 `quarterly_data`를 위 함수로 채운다. 연간(div=0)은 `annual_data`로:

```python
# _fetch_kis_fundamentals tasks 에 추가:
"financial_ratio_q": self._run_with_retry(
    "financial_ratio_q",
    lambda: self.kis_provider.get_financial_ratio(ticker, div_cls_code="1"),
),
"financial_ratio_a": self._run_with_retry(
    "financial_ratio_a",
    lambda: self.kis_provider.get_financial_ratio(ticker, div_cls_code="0"),
),
```

```python
# _normalize_kis_snapshot 내:
quarterly_eps = self._build_quarterly_eps(financial_ratio_q or [])
annual = [
    AnnualData(year=(r.get("stac_yymm") or "")[:4], eps=self._to_float(r.get("eps")))
    for r in (financial_ratio_a or [])
    if self._to_float(r.get("eps")) is not None
][:5]
# snapshot 생성 시 quarterly_data=quarterly_eps (기존 balance 기반 대신/병합), annual_data=annual
```

> 기존 `_build_kis_quarterly_data`(balance_sheet 기반 매출/순이익 QoQ)는 유지하되, EPS는 `_build_quarterly_eps`가 채운다. 두 소스를 `period`로 병합(같은 분기면 한 `QuarterlyData`에 revenue/earnings + eps 합치기).

- [ ] **Step 4: 실행 → 통과**

Run: `uv run pytest tests/tools/test_fundamental_eps.py -v`
Expected: PASS

- [ ] **Step 5: 실데이터 검증**

Run: `uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv('/Users/user/Develop/My/invest-jarvis/.env'); from src.providers.kis import KISProvider; from src.tools.fundamental import FundamentalTool; kis=KISProvider(os.environ['KIS_APP_KEY'],os.environ['KIS_APP_SECRET']); t=FundamentalTool(kis); r=asyncio.run(t.execute('005930.KS')); print('quarterly eps:', [(q.period,q.eps,q.eps_yoy) for q in (r.data.quarterly_data or [])]); print('annual:', [(a.year,a.eps) for a in (r.data.annual_data or [])])"`
확인: 분기 EPS와 eps_yoy, 연간 EPS가 채워지는가(005930).

- [ ] **Step 6: 커밋**

```bash
git add src/tools/fundamental.py tests/tools/test_fundamental_eps.py
git commit -m "feat(fundamental): parse KR quarterly/annual EPS from financial-ratio"
```

---

## Task 4: 미국 yfinance EPS 파싱

Task 1 spike 결과에 따라 `_fetch_yfinance_fundamentals`에서 분기 EPS YoY + 연간 EPS를 채운다.

**Files:** Modify `src/tools/fundamental.py`; Test `tests/tools/test_fundamental_eps.py`

- [ ] **Step 1: 실패 테스트** — Task 1에서 확인한 EPS 행 이름으로 mock DataFrame을 구성해 `_build_yf_quarterly_eps`가 `eps_yoy`를 계산하는지 검증(전년 동기 = 4분기 전). (spike 결과의 정확한 행 이름으로 작성)

- [ ] **Step 2: 실행 → 실패**

Run: `uv run pytest tests/tools/test_fundamental_eps.py -k yf_eps -v` → FAIL

- [ ] **Step 3: 구현** — spike에서 확인된 소스로 분기 EPS 시계열 추출 → 4분기 전 대비 YoY. EPS 행이 없으면 `Net Income ÷ shares_outstanding` 근사. 연간은 `income_stmt`에서.

- [ ] **Step 4: 실행 → 통과 / Step 5: AAPL 실데이터 검증 / Step 6: 커밋**

```bash
git commit -m "feat(fundamental): parse US quarterly/annual EPS from yfinance"
```

---

## Task 5: LLM 요약 입력 + CLI 렌더 (R6)

`annual_data`/`eps_yoy`가 LLM 요약과 CLI에 반영되도록 한다(R6 — 모델 추가만으로 끝나지 않음).

**Files:** Modify `src/llm/models.py`, `src/cli/main.py`; Test 해당

- [ ] **Step 1~5:** `FundamentalSummaryInput`에 `eps_growth_quarterly: float | None`, `eps_cagr_annual: float | None` 추가 → `deep_dive`/요약 생성부에서 채움. `main.py` 펀더멘털 패널에 "연간 EPS 추세(YYYY: eps …)" 한 줄 렌더. 각 단계 TDD + 커밋.

```bash
git commit -m "feat(fundamental): surface EPS growth in LLM summary + CLI"
```

---

## Self-Review

**1. 스펙 커버리지:** §7 C(분기 EPS YoY)·A(연간) → Task 3·4 ✅; R6(모델+요약+렌더) → Task 2·5 ✅; D3(financial-ratio EPS 직접) → Task 3 ✅.
**2. Placeholder:** Task 4는 spike(Task 1) 결과에 의존하는 부분을 "확인된 행 이름으로 작성"이라 명시 — spike 패턴. Task 5는 TDD 단계 축약(반복 구조) — 구현자는 Task 2~4 패턴을 따른다.
**3. 타입 일관성:** `QuarterlyData.eps/eps_yoy`, `AnnualData.eps`, `_build_quarterly_eps`/`_build_yf_quarterly_eps` 명명 일관.

---

## 다음 단계
Plan 3: **매집일/분산일**(`accumulation.py`) — CAN SLIM I의 데이터. 이후 Plan 4(RS)·5(업종)·6(vcp/regime/Stage2)·7(canslim 종합)·8(조립/연결).
