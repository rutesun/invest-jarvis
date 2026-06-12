# KIS 데이터 확장 Implementation Plan (Plan 1/8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KIS provider가 (a) 재무 데이터를 **분기/연간 선택**으로 받고, (b) **성장성비율(growth-ratio)** 보조 데이터를 받고, (c) 가격을 **수정주가**로 받도록 확장한다.

**Architecture:** 기존 `kis.py`의 `_get_finance_data`는 `FID_DIV_CLS_CODE="0"`(연간)으로 하드코딩되어 있다. 이를 인자화하고, 사용처 6개 메서드 시그니처를 확장한다. 실제 KIS 응답 구조(분기 지원·EPS 필드·수정주가 코드 값)는 문서만으로 단정할 수 없으므로 **Task 1에서 실호출로 먼저 검증**한 뒤 나머지를 구현한다(사용자 지시: 부품 구현 → 실제 테스트 → 조립).

**Tech Stack:** Python 3.12, httpx(async), pytest / pytest-asyncio, KIS OpenAPI. `uv run` 사용.

**Scope:** 이 계획은 `kis.py` provider 레벨만 다룬다. 분기 EPS를 `FundamentalSnapshot`으로 가공하는 작업은 Plan 2(CAN SLIM)에서 이어진다.

**선행 조건:** `.env`에 `KIS_APP_KEY`, `KIS_APP_SECRET` 설정됨.

---

## File Structure

- **Modify:** `src/providers/kis.py`
  - `_get_finance_data(...)` — `div_cls_code` 파라미터 추가
  - `get_financial_ratio` / `get_balance_sheet` / `get_profit_ratio` / `get_income_statement` / `get_other_major_ratios` — `div_cls_code` 전달
  - `get_growth_ratio(...)` — 신규 메서드
  - `get_price_history(...)` — 수정주가 적용
- **Create:** `scripts/verify_kis_quarterly.py` — 실호출 검증 스크립트(integration, 1회용)
- **Create:** `tests/providers/test_kis_finance_params.py` — 파라미터 단위 테스트(mock)

---

## Task 1: 실호출 검증 (Spike)

KIS 재무 API가 분기를 지원하는지, EPS 필드가 분기 응답에 있는지, 수정주가 코드 값이 무엇인지를 **실제 호출로 확정**한다. 이 결과가 Task 3·4의 정확한 구현을 좌우한다.

**Files:**
- Create: `scripts/verify_kis_quarterly.py`

- [ ] **Step 1: 검증 스크립트 작성**

```python
# scripts/verify_kis_quarterly.py
"""KIS 분기 재무 / growth-ratio / 수정주가 응답 구조 1회성 검증.
실행: uv run python scripts/verify_kis_quarterly.py 005930
환경변수 KIS_APP_KEY, KIS_APP_SECRET 필요.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

from src.providers.kis import KISProvider


async def main(code: str) -> None:
    load_dotenv()
    kis = KISProvider(os.environ["KIS_APP_KEY"], os.environ["KIS_APP_SECRET"])

    # 1) profit-ratio 연간(0) vs 분기(1) — EPS 필드와 기간(stac_yymm) 확인
    for div in ("0", "1"):
        rows = await kis._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/profit-ratio",
            tr_id="FHKST66430300",
            ticker=code,
            div_cls_code=div,
        )
        periods = [r.get("stac_yymm") for r in rows[:6]]
        has_eps = bool(rows) and "eps" in rows[0]
        print(f"[profit-ratio div={div}] rows={len(rows)} periods={periods} has_eps={has_eps}")
        if rows:
            print(f"    sample keys: {sorted(rows[0].keys())}")

    # 2) growth-ratio 존재/필드 확인
    growth = await kis._get_finance_data(
        path="/uapi/domestic-stock/v1/finance/growth-ratio",
        tr_id="FHKST66430800",
        ticker=code,
        div_cls_code="1",
    )
    print(f"[growth-ratio div=1] rows={len(growth)}")
    if growth:
        print(f"    sample keys: {sorted(growth[0].keys())}")

    # 3) 수정주가 코드: 0 vs 1 종가 비교 (분할/배당 종목에서 차이)
    for adj in ("0", "1"):
        df = await kis.get_price_history(code, period="1y", _org_adj_prc=adj)
        tail = df["Close"].tail(3).tolist() if not df.empty else []
        print(f"[price FID_ORG_ADJ_PRC={adj}] rows={len(df)} last_closes={tail}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "005930"))
```

> 이 스크립트는 `_get_finance_data`에 `div_cls_code` 인자가, `get_price_history`에 `_org_adj_prc` 인자가 있다고 가정한다 — Task 2·4에서 추가한다. **순서상 Task 2·4를 먼저 구현하고 이 스크립트를 실행**한다(Task 1 Step 2 참조).

- [ ] **Step 2: Task 2·4 완료 후 실행해 응답 구조 기록**

Run: `uv run python scripts/verify_kis_quarterly.py 005930`
기록할 것(다음 Task의 구현 근거):
- profit-ratio `div=1`이 분기 데이터를 주는가? `stac_yymm`이 분기말(예: `202503`, `202412`...)로 5개 이상 오는가?
- 분기 응답에 `eps` 필드가 있는가?
- growth-ratio 응답 키에 EPS 증가율 필드가 있는가(예: `eps_grs` 등)? 없으면 순이익증가율만.
- 수정주가: `FID_ORG_ADJ_PRC` 어느 값에서 종가가 분할 보정되는가(분할 이력 종목으로 재확인 권장, 예: `005930` 액면분할 2018).

- [ ] **Step 3: 검증 결과를 스펙에 메모**

`docs/superpowers/specs/2026-06-10-playbook-engine-design.md` §7.2 "구현 전 실호출 검증" 항목 아래에 확인된 사실(분기 지원 여부, EPS 필드명, 수정주가 코드)을 1~3줄로 적어 후속 Plan이 참조하게 한다.

> 검증 결과 분기 미지원 또는 EPS 필드 부재면, Plan 2에서 "연간 EPS" 또는 "순이익증가율 fallback"으로 분기한다(스펙 D3).

---

## Task 2: `_get_finance_data` div_cls_code 인자화

**Files:**
- Modify: `src/providers/kis.py` (`_get_finance_data` 및 6개 호출 메서드)
- Test: `tests/providers/test_kis_finance_params.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_kis_finance_params.py
import pytest

from src.providers.kis import KISProvider


@pytest.mark.asyncio
async def test_get_finance_data_passes_div_cls_code(monkeypatch):
    kis = KISProvider("k", "s")

    captured = {}

    async def fake_token():
        from src.providers.kis_models import KISToken
        return KISToken(access_token="t", token_type="Bearer", expires_in=10)

    monkeypatch.setattr(kis, "_get_access_token", fake_token)

    class FakeResp:
        def raise_for_status(self): ...
        def json(self): return {"output": [{"stac_yymm": "202503"}]}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def get(self, url, headers=None, params=None):
            captured["params"] = params
            return FakeResp()

    monkeypatch.setattr("src.providers.kis.httpx.AsyncClient", FakeClient)

    await kis.get_profit_ratio("005930", div_cls_code="1")
    assert captured["params"]["FID_DIV_CLS_CODE"] == "1"

    await kis.get_profit_ratio("005930")  # default
    assert captured["params"]["FID_DIV_CLS_CODE"] == "0"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/providers/test_kis_finance_params.py -v`
Expected: FAIL (`get_profit_ratio() got an unexpected keyword argument 'div_cls_code'`)

- [ ] **Step 3: 구현**

`src/providers/kis.py`:

```python
async def _get_finance_data(
    self, path: str, tr_id: str, ticker: str, div_cls_code: str = "0"
) -> list[dict]:
    """Get domestic stock finance data from KIS API.

    div_cls_code: "0"=연간, "1"=분기 (Task 1 실호출로 확정).
    """
    token = await self._get_access_token()
    url = f"{self.BASE_URL}{path}"
    headers = {
        "Authorization": f"{token.token_type} {token.access_token}",
        "appkey": self.app_key,
        "appsecret": self.app_secret,
        "tr_id": tr_id,
        "Content-Type": "application/json; charset=utf-8",
    }
    params = {
        "FID_DIV_CLS_CODE": div_cls_code,
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker.replace(".KS", "").replace(".KQ", ""),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    return data.get("output", [])


async def get_financial_ratio(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
    return await self._get_finance_data(
        path="/uapi/domestic-stock/v1/finance/financial-ratio",
        tr_id="FHKST66430100", ticker=ticker, div_cls_code=div_cls_code,
    )

async def get_balance_sheet(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
    return await self._get_finance_data(
        path="/uapi/domestic-stock/v1/finance/balance-sheet",
        tr_id="FHKST66430200", ticker=ticker, div_cls_code=div_cls_code,
    )

async def get_profit_ratio(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
    return await self._get_finance_data(
        path="/uapi/domestic-stock/v1/finance/profit-ratio",
        tr_id="FHKST66430300", ticker=ticker, div_cls_code=div_cls_code,
    )

async def get_income_statement(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
    return await self._get_finance_data(
        path="/uapi/domestic-stock/v1/finance/income-statement",
        tr_id="FHKST66430400", ticker=ticker, div_cls_code=div_cls_code,
    )

async def get_other_major_ratios(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
    return await self._get_finance_data(
        path="/uapi/domestic-stock/v1/finance/other-major-ratios",
        tr_id="FHKST66430500", ticker=ticker, div_cls_code=div_cls_code,
    )
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/providers/test_kis_finance_params.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/kis.py tests/providers/test_kis_finance_params.py
git commit -m "feat(kis): parameterize FID_DIV_CLS_CODE for quarterly/annual finance"
```

---

## Task 3: get_growth_ratio 신규 (보조)

성장성비율 API를 보조 데이터로 추가한다(C·A의 순이익증가율 교차검증·fallback).

**Files:**
- Modify: `src/providers/kis.py`
- Test: `tests/providers/test_kis_finance_params.py` (추가)

- [ ] **Step 1: 실패하는 테스트 추가**

```python
@pytest.mark.asyncio
async def test_get_growth_ratio_uses_growth_endpoint(monkeypatch):
    kis = KISProvider("k", "s")

    async def fake_token():
        from src.providers.kis_models import KISToken
        return KISToken(access_token="t", token_type="Bearer", expires_in=10)

    monkeypatch.setattr(kis, "_get_access_token", fake_token)

    captured = {}

    class FakeResp:
        def raise_for_status(self): ...
        def json(self): return {"output": [{"stac_yymm": "202503"}]}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def get(self, url, headers=None, params=None):
            captured["url"] = url
            return FakeResp()

    monkeypatch.setattr("src.providers.kis.httpx.AsyncClient", FakeClient)

    await kis.get_growth_ratio("005930", div_cls_code="1")
    assert captured["url"].endswith("/finance/growth-ratio")
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `uv run pytest tests/providers/test_kis_finance_params.py::test_get_growth_ratio_uses_growth_endpoint -v`
Expected: FAIL (`'KISProvider' object has no attribute 'get_growth_ratio'`)

- [ ] **Step 3: 구현**

```python
async def get_growth_ratio(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
    """성장성비율 (매출/영업이익/순이익 증가율). EPS증가율은 응답에 없을 수 있음 — Task 1 검증."""
    return await self._get_finance_data(
        path="/uapi/domestic-stock/v1/finance/growth-ratio",
        tr_id="FHKST66430800", ticker=ticker, div_cls_code=div_cls_code,
    )
```

> tr_id `FHKST66430800`은 Task 1 실호출로 정확성 확인. 다르면 검증값으로 교정.

- [ ] **Step 4: 실행 → 통과 확인**

Run: `uv run pytest tests/providers/test_kis_finance_params.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/kis.py tests/providers/test_kis_finance_params.py
git commit -m "feat(kis): add get_growth_ratio endpoint"
```

---

## Task 4: get_price_history 수정주가 적용

분할·배당 왜곡을 막기 위해 수정주가로 받는다. 옵션은 인자화하되 기본을 수정주가로 둔다.

**Files:**
- Modify: `src/providers/kis.py` (`get_price_history`)
- Test: `tests/providers/test_kis_finance_params.py` (추가)

- [ ] **Step 1: 실패하는 테스트 추가**

```python
@pytest.mark.asyncio
async def test_get_price_history_uses_adjusted_price_by_default(monkeypatch):
    kis = KISProvider("k", "s")

    async def fake_token():
        from src.providers.kis_models import KISToken
        return KISToken(access_token="t", token_type="Bearer", expires_in=10)

    monkeypatch.setattr(kis, "_get_access_token", fake_token)

    seen = []

    class FakeResp:
        def raise_for_status(self): ...
        def json(self): return {"output2": []}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def get(self, url, headers=None, params=None):
            seen.append(params["FID_ORG_ADJ_PRC"])
            return FakeResp()

    monkeypatch.setattr("src.providers.kis.httpx.AsyncClient", FakeClient)

    await kis.get_price_history("005930", period="1mo")
    assert all(v == ADJUSTED for v in seen)  # ADJUSTED = Task 1에서 확정한 수정주가 코드값
```

> `ADJUSTED` 상수는 Task 1 검증으로 확정(KIS 문서상 수정주가/원주가 코드). 테스트 작성 시 검증값으로 치환.

- [ ] **Step 2: 실행 → 실패 확인**

Run: `uv run pytest tests/providers/test_kis_finance_params.py::test_get_price_history_uses_adjusted_price_by_default -v`
Expected: FAIL

- [ ] **Step 3: 구현**

`get_price_history` 시그니처에 `_org_adj_prc` 추가, 기본을 수정주가 코드로. 루프 내 params 수정:

```python
async def get_price_history(
    self, ticker: str, period: str = "1y", _org_adj_prc: str = ADJUSTED
) -> pd.DataFrame:
    ...
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": batch_start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": batch_end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": _org_adj_prc,
            }
    ...
```

`ADJUSTED`는 모듈 상수로 정의(Task 1 검증값).

- [ ] **Step 4: 실행 → 통과 확인**

Run: `uv run pytest tests/providers/test_kis_finance_params.py -v`
Expected: PASS

- [ ] **Step 5: 실데이터 회귀 — quick_check 비교**

Run: `uv run jarvis check 005930.KS`
확인: 분할 이력 종목에서 52주 고저·이동평균이 비현실적으로 튀지 않는지(수정주가 적용 효과). 이전 동작과 비교.

- [ ] **Step 6: 커밋**

```bash
git add src/providers/kis.py tests/providers/test_kis_finance_params.py
git commit -m "feat(kis): use adjusted close in get_price_history (D1)"
```

---

## Self-Review

**1. 스펙 커버리지(Plan 1 범위 = §7.2 kis.py 부분 + D1):**
- `div_cls_code` 인자화 → Task 2 ✅
- `get_growth_ratio` → Task 3 ✅
- 수정주가 → Task 4 ✅
- 분기/EPS/수정주가 실호출 검증(§7.2) → Task 1 ✅
- 업종지수 API(R26) → Plan 5로 분리(범위 밖, 명시됨) ✅
- fundamental `eps_yoy`/`annual_data`(R6, D3) → Plan 2로 이어짐(명시됨) ✅

**2. Placeholder 스캔:** `ADJUSTED` 상수는 Task 1 검증값으로 치환하라고 명시 — 미정 값이지만 검증 절차가 task에 있음(spike 패턴). 그 외 placeholder 없음.

**3. 타입/시그니처 일관성:** `_get_finance_data(path, tr_id, ticker, div_cls_code)` — 6개 메서드 모두 `div_cls_code` 키워드 전달로 일치. `get_price_history(ticker, period, _org_adj_prc)` 일관.

---

## 다음 단계
Plan 1 완료 후 → **Plan 2: CAN SLIM 아이템**(`fundamental.py`에 `QuarterlyData.eps/eps_yoy`·`annual_data` 추가 + `canslim.py` C·A·I 계산). Task 1 검증 결과(분기 EPS 가용 여부)가 Plan 2의 분기 전략을 결정한다.
