# 업종 강도 Implementation Plan (Plan 5/8)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 superpowers:executing-plans. 체크박스(`- [ ]`)로 추적.

**Goal:** 종목 업종이 시장 대비 강한지를 판정한다 — 게이트 C★의 "업종" 조건 + CAN SLIM L. 미국=FMP 업종 perf, 한국=KIS 업종지수.

**Architecture:** 데이터 소스 2개(미국 FMP / 한국 KIS) → **추상 인터페이스 `SectorStrengthProvider` + 2 구현**(YAGNI 해소). fetch는 provider, 판정은 가능한 순수하게. 종목→업종 매핑: 미국 yfinance `industry`(↔FMP industry 정규화), 한국 quote `bstp_cls_code`(업종코드).

**Tech Stack:** Python 3.12, httpx, yfinance, KIS, pydantic, pytest. `uv run`. `FMP_API_KEY`/`KIS_*` in `.env`.

**선행:** Plan 1(kis `_get_finance_data`), Plan 4(`src/tools/playbook/models.py`).

**검증된 응답(2026-06 실호출):**
- FMP `stable/industry-performance-snapshot?date=YYYY-MM-DD&apikey=` → `[{date, industry, exchange, averageChange}, …]` (exchange별, 무료 OK)
- FMP `stable/historical-industry-performance?industry=<name>&apikey=` → 시계열 `[{date, industry, exchange, averageChange}, …]` (무료 OK)
- KIS `inquire-daily-indexchartprice` (tr `FHKUP03500100`, `FID_COND_MRKT_DIV_CODE=U`, `FID_INPUT_ISCD=<업종코드>`, `FID_PERIOD_DIV_CODE=D`, 날짜) → `output1`(현재) + `output2`(일별 차트). 코스피종합=`0001`.

---

## File Structure

- **Modify:** `src/tools/playbook/models.py` — `SectorStrengthResult`
- **Create:** `src/providers/fmp_provider.py` — FMP 업종 perf fetch (미국)
- **Modify:** `src/providers/kis.py` — `get_sector_index_history(sector_code, period)` (업종지수 OHLCV) + `get_quote`에서 업종코드 노출(이미 응답에 `bstp_cls_code`)
- **Create:** `src/tools/playbook/sector_strength.py` — `SectorStrengthProvider`(ABC) + `FmpSectorStrength` + `KisSectorStrength`
- **Test:** `tests/providers/test_fmp_provider.py`, `tests/tools/playbook/test_sector_strength.py`

---

## Task 1: SectorStrengthResult 모델

- [ ] **Step 1: 실패 테스트** (`tests/tools/playbook/test_sector_strength.py`)

```python
from src.tools.playbook.models import SectorStrengthResult

def test_sector_strength_result():
    r = SectorStrengthResult(industry="Semiconductors", rank_pct=0.12,
                             trend="up", is_strong=True, source="FMP")
    assert r.is_strong is True and r.source == "FMP"

def test_sector_strength_none_when_unmapped():
    r = SectorStrengthResult(industry=None, rank_pct=None, trend="unknown",
                             is_strong=None, source="none")
    assert r.is_strong is None
```

- [ ] **Step 2: 실행 → 실패 / Step 3: 구현** (`models.py`에 추가)

```python
class SectorStrengthResult(BaseModel):
    """업종 강도 (게이트 C★ 업종 조건 + CAN SLIM L)."""
    industry: str | None
    rank_pct: float | None        # 미국: 전체 업종 중 백분위(0=최강). 한국: None(코스피 대비로 대체)
    trend: str                    # "up" | "down" | "flat" | "unknown"
    is_strong: bool | None        # None = 매핑 실패/데이터 없음 → 게이트는 종목 RS만(graceful)
    source: str                   # "FMP" | "KIS" | "none"
    detail: str = ""
```

- [ ] **Step 4: 통과 / Step 5: 커밋** `git commit -m "feat(playbook): add SectorStrengthResult model"`

---

## Task 2: fmp_provider.py (미국 업종 perf)

- [ ] **Step 1: 실패 테스트** (mock httpx — snapshot/historical 파싱)

```python
# tests/providers/test_fmp_provider.py
import pytest
from src.providers.fmp_provider import FmpProvider

@pytest.mark.asyncio
async def test_industry_snapshot_parses(monkeypatch):
    sample = [{"date":"2026-06-10","industry":"Semiconductors","exchange":"NASDAQ","averageChange":2.1},
              {"date":"2026-06-10","industry":"Semiconductors","exchange":"NYSE","averageChange":1.5},
              {"date":"2026-06-10","industry":"Airlines","exchange":"NASDAQ","averageChange":-0.8}]
    class R:
        status_code=200
        def raise_for_status(self): ...
        def json(self): return sample
    class C:
        def __init__(self,*a,**k): ...
        async def __aenter__(self): return self
        async def __aexit__(self,*a): ...
        async def get(self,*a,**k): return R()
    monkeypatch.setattr("src.providers.fmp_provider.httpx.AsyncClient", C)
    fmp = FmpProvider("KEY")
    snap = await fmp.industry_snapshot("2026-06-10")
    # 같은 industry는 exchange 평균으로 합산
    assert snap["Semiconductors"] == pytest.approx((2.1+1.5)/2)
    assert "Airlines" in snap
```

- [ ] **Step 2: 실행 → 실패 / Step 3: 구현** (`src/providers/fmp_provider.py`)

```python
import httpx

_BASE = "https://financialmodelingprep.com/stable"


class FmpProvider:
    """FMP 업종/섹터 perf (미국). 무료 티어 stable 엔드포인트."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def industry_snapshot(self, date: str) -> dict[str, float]:
        """특정일 industry별 평균 등락(%). exchange별 값을 industry 단위로 평균."""
        url = f"{_BASE}/industry-performance-snapshot"
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(url, params={"date": date, "apikey": self.api_key})
            r.raise_for_status()
            rows = r.json()
        agg: dict[str, list[float]] = {}
        for row in rows:
            ind = row.get("industry")
            ch = row.get("averageChange")
            if ind is not None and ch is not None:
                agg.setdefault(ind, []).append(float(ch))
        return {k: sum(v) / len(v) for k, v in agg.items() if v}

    async def historical_industry(self, industry: str) -> list[dict]:
        """industry 시계열 [{date, averageChange}, …] (최신순)."""
        url = f"{_BASE}/historical-industry-performance"
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(url, params={"industry": industry, "apikey": self.api_key})
            r.raise_for_status()
            return r.json()
```

- [ ] **Step 4: 통과 / Step 5: 실데이터** `uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv('.env'); from src.providers.fmp_provider import FmpProvider; f=FmpProvider(os.environ['FMP_API_KEY']); s=asyncio.run(f.industry_snapshot('2026-06-10')); print('industries:',len(s)); print('Semiconductors:', s.get('Semiconductors'))"`
- [ ] **Step 6: 커밋** `git commit -m "feat(providers): FMP industry performance (snapshot + historical)"`

---

## Task 3: KIS 업종지수 + 종목→업종코드

- [ ] **Step 1: 실패 테스트** — `get_sector_index_history`가 `inquire-daily-indexchartprice`(tr=FHKUP03500100, MRKT_DIV=U)를 호출하는지(mock) + `output2`를 OHLCV DataFrame으로 파싱.

- [ ] **Step 2~3: 구현** — `src/providers/kis.py`:

```python
async def get_sector_index_history(self, sector_code: str, period: str = "1y") -> pd.DataFrame:
    """국내 업종지수 일별 OHLCV. sector_code 예: '0001'(코스피종합).
    inquire-daily-indexchartprice (tr FHKUP03500100, FID_COND_MRKT_DIV_CODE='U')."""
    token = await self._get_access_token()
    url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
    headers = {
        "Authorization": f"{token.token_type} {token.access_token}",
        "appkey": self.app_key, "appsecret": self.app_secret,
        "tr_id": "FHKUP03500100", "Content-Type": "application/json; charset=utf-8",
    }
    days = {"1mo":30,"3mo":90,"6mo":180,"1y":365,"2y":730}.get(period, 365)
    from datetime import datetime, timedelta
    end = datetime.now(); start = end - timedelta(days=days)
    params = {
        "FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": sector_code,
        "FID_INPUT_DATE_1": start.strftime("%Y%m%d"), "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
        "FID_PERIOD_DIV_CODE": "D",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
    rows = []
    for it in data.get("output2", []):
        if not it.get("stck_bsop_date"):
            continue
        rows.append({
            "Date": pd.to_datetime(it["stck_bsop_date"]),
            "Open": float(it.get("bstp_nmix_oprc", 0) or 0),
            "High": float(it.get("bstp_nmix_hgpr", 0) or 0),
            "Low": float(it.get("bstp_nmix_lwpr", 0) or 0),
            "Close": float(it.get("bstp_nmix_prpr", 0) or 0),
            "Volume": int(it.get("acml_vol", 0) or 0),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates("Date").set_index("Date").sort_index()
        df.index = df.index.tz_localize("Asia/Seoul")
    return df
```

- [ ] **Step 3b (spike — 종목→업종코드):** `get_quote` 응답의 업종코드 필드 확인. 실행:
`uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv('.env'); from src.providers.kis import KISProvider; k=KISProvider(os.environ['KIS_APP_KEY'],os.environ['KIS_APP_SECRET']); ... raw inquire-price output 의 'bstp_cls_code'/'bstp_kor_isnm' 출력"`
→ 종목의 `bstp_cls_code`(업종코드)를 `get_sector_index_history`의 `sector_code`로 쓸 수 있는지 확인. 코드 체계가 다르면 매핑 테이블 필요(확인 결과 기록).

- [ ] **Step 4~6: 통과 + 실데이터(0001 업종지수 OHLCV) + 커밋** `git commit -m "feat(kis): domestic sector index OHLCV"`

---

## Task 4: sector_strength.py (인터페이스 + 2 구현)

- [ ] **Step 1: 실패 테스트** — `FmpSectorStrength.evaluate(industry, snapshot, historical)` 순수 판정: snapshot 백분위 + historical 추세 → is_strong. `KisSectorStrength`는 업종지수 df + 코스피 df → 코스피 대비 강세 + 추세.

- [ ] **Step 2~3: 구현** (`src/tools/playbook/sector_strength.py`)

```python
from abc import ABC, abstractmethod
import pandas as pd
from src.tools.playbook.models import SectorStrengthResult


class SectorStrengthProvider(ABC):
    @abstractmethod
    async def evaluate(self, ticker: str) -> SectorStrengthResult: ...


def _rank_pct(snapshot: dict[str, float], industry: str) -> float | None:
    if industry not in snapshot:
        return None
    vals = sorted(snapshot.values(), reverse=True)   # 높은 변동이 상위
    pos = vals.index(snapshot[industry])
    return pos / max(1, len(vals) - 1)               # 0=최강


def _trend_from_hist(hist: list[dict], lookback: int = 60) -> str:
    chs = [float(h["averageChange"]) for h in hist[:lookback] if h.get("averageChange") is not None]
    if not chs:
        return "unknown"
    s = sum(chs)
    return "up" if s > 0 else ("down" if s < 0 else "flat")
```
- `FmpSectorStrength(fmp_provider, yf_industry_lookup, normalize_map)`: 종목 yfinance `industry` → 정규화 매핑 → `snapshot`/`historical` → `_rank_pct` + `_trend_from_hist`. `is_strong = rank_pct <= 0.5 and trend == "up"`. 매핑 실패 → `is_strong=None, source="none"`.
- `KisSectorStrength(kis_provider)`: 종목 업종코드 → `get_sector_index_history` + 코스피(`0001`) → 업종지수가 코스피 대비 강세(상대가격 우상향) AND 업종지수 상승추세 → `is_strong`. `rank_pct=None`(코스피 대비로 대체), `source="KIS"`.

- [ ] **Step 4~6: 통과 + 실데이터(AAPL→FMP, 005930→KIS) + 커밋** `git commit -m "feat(playbook): sector strength (FMP + KIS, interface)"`

---

## Self-Review

**1. 스펙 커버리지:** §9.1(FMP snapshot 순위 + historical 추세; KIS 업종지수; 인터페이스 2구현; 매핑 실패 None) → Task 2·3·4 ✅. R26(KIS 업종 지원) ✅. R24(yfinance↔FMP industry 정규화) → Task 4 매핑 ✅. R25(historical degrade)는 **불필요 확인**(무료 OK) — Task 2가 historical 직접 사용.
**2. Placeholder:** Task 3b(종목→업종코드)는 spike로 명시(KIS 코드 체계 미확정). Task 4의 정규화 매핑 테이블은 Task 2 실데이터의 industry 목록으로 작성.
**3. 타입 일관성:** `SectorStrengthResult(industry, rank_pct, trend, is_strong, source, detail)`; `FmpProvider.industry_snapshot/historical_industry`; `get_sector_index_history(sector_code, period)`; `SectorStrengthProvider.evaluate`.

---

## 다음 단계
Plan 6: VCP 피벗 돌파 + 시장환경(market_regime) + Stage2 일원화(minervini). 이후 Plan 7(canslim 종합), Plan 8(gate·sizing·exit·engine·연결).
