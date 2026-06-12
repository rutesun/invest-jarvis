# 종목 상대강도 RS Implementation Plan (Plan 4/8)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 superpowers:executing-plans. 체크박스(`- [ ]`)로 추적.

**Goal:** **맨스필드식 종목 상대강도(RS)** — 종목이 시장(지수)보다 강한지를 계산한다. 게이트 C★(종목 RS)와 CAN SLIM L의 입력.

**Architecture:** 지수 OHLCV fetch는 `IndexProvider`(신규 Provider)가 담당(R5 — 순수성 분리). RS 계산 `relative_strength.py`는 **순수 함수**(stock_df + index_df 주입). **RS(Relative Strength) ≠ RSI** — RSI(`indicators.py`)는 쓰지 않는다.

**Tech Stack:** Python 3.12, yfinance, pandas, pydantic, pytest. `uv run`.

**선행:** Plan 3(`src/tools/playbook/` 패키지 + `models.py` 존재).

**검증 사실:** yfinance에서 `^GSPC`(미국), `^KS11`(코스피), `^KQ11`(코스닥) 지수 OHLCV 수신 가능(2026-06 확인).

**공식(맨스필드):** `RP[t] = 종목종가[t] / 지수종가[t]`; `Mansfield RS = (RP[now] / SMA(RP, 252) − 1) × 100`. 0 위면 시장보다 강함.

---

## File Structure

- **Create:** `src/providers/index_provider.py` — 종목→지수 매핑 + 지수 OHLCV fetch
- **Modify:** `src/tools/playbook/models.py` — `RelativeStrengthResult` 추가
- **Create:** `src/tools/playbook/relative_strength.py` — `compute_relative_strength(stock_df, index_df)` 순수 함수
- **Test:** `tests/providers/test_index_provider.py`, `tests/tools/playbook/test_relative_strength.py`

---

## Task 1: RelativeStrengthResult 모델

**Files:** Modify `src/tools/playbook/models.py`; Test `tests/tools/playbook/test_relative_strength.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/tools/playbook/test_relative_strength.py
from src.tools.playbook.models import RelativeStrengthResult

def test_rs_result_model():
    r = RelativeStrengthResult(mansfield_rs=12.3, outperform_6m=18.0,
                               rp_slope_4w=0.5, index_symbol="^GSPC")
    assert r.mansfield_rs == 12.3
    assert r.is_strong is True   # mansfield_rs > 0 and rp_slope_4w >= 0

def test_rs_weak_when_negative():
    r = RelativeStrengthResult(mansfield_rs=-3.0, outperform_6m=-5.0,
                               rp_slope_4w=-0.2, index_symbol="^KS11")
    assert r.is_strong is False
```

- [ ] **Step 2: 실행 → 실패**

Run: `uv run pytest tests/tools/playbook/test_relative_strength.py -v` → FAIL

- [ ] **Step 3: 구현** — `src/tools/playbook/models.py`에 추가:

```python
class RelativeStrengthResult(BaseModel):
    """맨스필드식 종목 상대강도 (종목 vs 시장). RSI와 무관."""

    mansfield_rs: float          # (RP / SMA(RP,252) - 1) * 100
    outperform_6m: float         # 종목 6M 수익률 - 지수 6M 수익률 (%p)
    rp_slope_4w: float           # 상대가격선 4주(20거래일) 변화
    index_symbol: str

    @computed_field
    @property
    def is_strong(self) -> bool:
        return self.mansfield_rs > 0 and self.rp_slope_4w >= 0
```

- [ ] **Step 4: 통과 / Step 5: 커밋**

```bash
git add src/tools/playbook/models.py tests/tools/playbook/test_relative_strength.py
git commit -m "feat(playbook): add RelativeStrengthResult model"
```

---

## Task 2: IndexProvider (종목→지수 매핑 + fetch)

**Files:** Create `src/providers/index_provider.py`; Test `tests/providers/test_index_provider.py`

- [ ] **Step 1: 실패 테스트 (매핑 규칙)**

```python
# tests/providers/test_index_provider.py
from src.providers.index_provider import index_symbol_for

def test_index_symbol_mapping():
    assert index_symbol_for("005930.KS") == "^KS11"
    assert index_symbol_for("035720.KQ") == "^KQ11"
    assert index_symbol_for("AAPL") == "^GSPC"
    assert index_symbol_for("005930") == "^KS11"   # 6자리 → 기본 코스피
```

- [ ] **Step 2: 실행 → 실패** → FAIL (module not found)

- [ ] **Step 3: 구현** — `src/providers/index_provider.py`:

```python
import pandas as pd

from src.providers.yfinance_provider import YFinanceProvider


def index_symbol_for(ticker: str) -> str:
    """종목 티커 → 비교 시장지수 심볼."""
    if ticker.endswith(".KS"):
        return "^KS11"
    if ticker.endswith(".KQ"):
        return "^KQ11"
    code = ticker.replace(".KS", "").replace(".KQ", "")
    if code.isdigit() and len(code) == 6:
        return "^KS11"   # 시장 불명 6자리 → 코스피 기본 (KOSDAQ는 .KQ로 구분)
    return "^GSPC"        # 미국/기타


class IndexProvider:
    """시장지수 OHLCV fetch (yfinance). RS·시장환경 모듈에 DataFrame 주입용."""

    def __init__(self, yf_provider: YFinanceProvider | None = None):
        self._yf = yf_provider or YFinanceProvider()

    async def get_index_history(self, ticker: str, period: str = "2y") -> tuple[str, pd.DataFrame]:
        """종목에 맞는 지수의 OHLCV를 반환. (index_symbol, df)."""
        symbol = index_symbol_for(ticker)
        df = await self._yf.get_price_history(symbol, period)
        return symbol, df
```

- [ ] **Step 4: 통과 / Step 5: 실데이터**

Run: `uv run python -c "import asyncio; from src.providers.index_provider import IndexProvider; s,df=asyncio.run(IndexProvider().get_index_history('005930.KS')); print(s, len(df), df['Close'].tail(2).tolist())"`
확인: `^KS11`, 충분한 행 수(>250), 종가 값 정상.

- [ ] **Step 6: 커밋**

```bash
git add src/providers/index_provider.py tests/providers/test_index_provider.py
git commit -m "feat(providers): add IndexProvider (ticker->index mapping + fetch)"
```

---

## Task 3: relative_strength.py (순수 Mansfield RS)

**Files:** Create `src/tools/playbook/relative_strength.py`; Test `tests/tools/playbook/test_relative_strength.py`

- [ ] **Step 1: 실패 테스트 (합성 시계열로 계산 검증)**

```python
import numpy as np
import pandas as pd
from src.tools.playbook.relative_strength import compute_relative_strength

def _series_df(closes):
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes}, index=idx)

def test_rs_strong_when_stock_outpaces_index():
    n = 300
    # 종목은 지수보다 더 가파르게 상승 → RP 우상향 → Mansfield RS > 0
    stock = _series_df(list(np.linspace(100, 200, n)))
    index = _series_df(list(np.linspace(100, 120, n)))
    r = compute_relative_strength(stock, index, index_symbol="^GSPC")
    assert r.mansfield_rs > 0
    assert r.rp_slope_4w > 0
    assert r.is_strong is True

def test_rs_handles_misaligned_dates():
    stock = _series_df(list(np.linspace(100, 150, 300)))
    index = _series_df(list(np.linspace(100, 130, 300)))
    # 인덱스가 일부 다른 경우에도 공통 날짜로 정렬
    index = index.iloc[5:]
    r = compute_relative_strength(stock, index, index_symbol="^GSPC")
    assert isinstance(r.mansfield_rs, float)
```

- [ ] **Step 2: 실행 → 실패** → FAIL

- [ ] **Step 3: 구현** — `src/tools/playbook/relative_strength.py`:

```python
import pandas as pd

from src.tools.playbook.models import RelativeStrengthResult

_RP_SMA = 252      # 맨스필드 기준선 (≈1년)
_SLOPE_DAYS = 20   # 4주
_PERF_DAYS = 126   # 6개월


def compute_relative_strength(
    stock_df: pd.DataFrame, index_df: pd.DataFrame, index_symbol: str
) -> RelativeStrengthResult:
    """맨스필드 RS. stock_df/index_df는 'Close' 컬럼 + 날짜 인덱스."""
    s = stock_df["Close"].dropna()
    i = index_df["Close"].dropna()
    common = s.index.intersection(i.index)
    rp = (s.loc[common] / i.loc[common]).dropna()

    if len(rp) < 2:
        return RelativeStrengthResult(
            mansfield_rs=0.0, outperform_6m=0.0, rp_slope_4w=0.0, index_symbol=index_symbol
        )

    sma_window = min(_RP_SMA, len(rp))
    rp_sma = rp.rolling(window=sma_window, min_periods=max(20, sma_window // 4)).mean()
    last_rp = float(rp.iloc[-1])
    last_sma = float(rp_sma.iloc[-1])
    mansfield = ((last_rp / last_sma) - 1.0) * 100.0 if last_sma else 0.0

    slope_n = min(_SLOPE_DAYS, len(rp) - 1)
    rp_slope = float(rp.iloc[-1] - rp.iloc[-1 - slope_n])

    def _perf(series: pd.Series) -> float:
        n = min(_PERF_DAYS, len(series) - 1)
        past = float(series.iloc[-1 - n])
        return ((float(series.iloc[-1]) - past) / past) * 100.0 if past else 0.0

    outperform = _perf(s.loc[common]) - _perf(i.loc[common])

    return RelativeStrengthResult(
        mansfield_rs=round(mansfield, 2),
        outperform_6m=round(outperform, 2),
        rp_slope_4w=round(rp_slope, 6),
        index_symbol=index_symbol,
    )
```

- [ ] **Step 4: 통과**

Run: `uv run pytest tests/tools/playbook/test_relative_strength.py -v` → PASS

- [ ] **Step 5: 실데이터 검증 (AAPL vs ^GSPC, 005930 vs ^KS11)**

Run:
```
uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv('.env'); from src.providers.yfinance_provider import YFinanceProvider; from src.providers.index_provider import IndexProvider; from src.tools.playbook.relative_strength import compute_relative_strength;
async def m():
 yf=YFinanceProvider(); ip=IndexProvider(yf)
 for tk in ['AAPL','005930.KS']:
  s=await yf.get_price_history(tk,'2y'); sym,idf=await ip.get_index_history(tk,'2y')
  print(tk, compute_relative_strength(s, idf, sym))
import asyncio; asyncio.run(m())"
```
확인: AAPL/005930의 Mansfield RS·6M 초과수익이 합리적 범위(대략 −100~+100), is_strong 판정.

- [ ] **Step 6: 커밋**

```bash
git add src/tools/playbook/relative_strength.py tests/tools/playbook/test_relative_strength.py
git commit -m "feat(playbook): Mansfield relative strength (pure, RS != RSI)"
```

---

## Self-Review

**1. 스펙 커버리지:** §8(맨스필드 RS, RP/SMA252, 4주 기울기, 6M 초과수익) → Task 3 ✅; R5(IndexProvider fetch 분리, RS 순수) → Task 2·3 ✅; §20 코스피/코스닥 매핑(.KS/.KQ, 6자리 기본 코스피) → Task 2 ✅.
**2. Placeholder:** 없음.
**3. 타입 일관성:** `RelativeStrengthResult(mansfield_rs, outperform_6m, rp_slope_4w, index_symbol, is_strong)`; `compute_relative_strength(stock_df, index_df, index_symbol)`; `index_symbol_for(ticker)`, `IndexProvider.get_index_history`.

> **RS vs RSI:** 이 모듈은 `indicators.py`의 RSI(14)를 import/사용하지 않는다. 입력은 종가 시계열뿐.

---

## 다음 단계
Plan 5: **업종 강도**(`fmp_provider`(미국) + KIS 업종지수(한국) + `sector_strength.py`). C★의 업종 조건.
