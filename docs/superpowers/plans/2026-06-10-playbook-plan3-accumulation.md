# 매집일/분산일 (accumulation.py) Implementation Plan (Plan 3/8)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 superpowers:executing-plans. 체크박스(`- [ ]`)로 추적.

**Goal:** 오닐(IBD)식 **매집일/분산일(Accumulation/Distribution Day)**을 세어 CAN SLIM I(기관 매수)의 거래량 기반 신호를 만든다.

**Architecture:** 순수 함수 — OHLCV `DataFrame`(또는 `TechnicalResult.raw_dataframe`)을 입력받아 `AccumulationResult`를 반환한다. 외부 I/O 없음. `src/tools/playbook/` 패키지를 이 Plan에서 시작한다(이후 Plan들이 모듈 추가).

**Tech Stack:** Python 3.12, pandas, pydantic, pytest. `uv run`.

**선행:** 없음(독립). 입력 `DataFrame`은 `Open/High/Low/Close/Volume` 컬럼 보유(기존 `TechnicalResult.raw_dataframe`가 제공).

**규칙 출처(오닐, `docs/references/trading-playbook.md`):** 분산일 = "주가는 하락하는데 거래량이 늘어나는 날"(큰손 매도). 매집일 = "상승 + 거래량 증가 + 종가가 당일 고가권 마감"(큰손 매수).

---

## File Structure

- **Create:** `src/tools/playbook/__init__.py` (빈 패키지)
- **Create:** `src/tools/playbook/models.py` — `AccumulationResult` (이후 Plan들이 result 모델 추가)
- **Create:** `src/tools/playbook/accumulation.py` — `analyze_accumulation(df)`
- **Create:** `tests/tools/playbook/__init__.py`, `tests/tools/playbook/test_accumulation.py`

---

## Task 1: 패키지 + AccumulationResult 모델

**Files:** Create `src/tools/playbook/__init__.py`, `src/tools/playbook/models.py`; Test `tests/tools/playbook/test_accumulation.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/tools/playbook/test_accumulation.py
from src.tools.playbook.models import AccumulationResult

def test_accumulation_result_model():
    r = AccumulationResult(accumulation_days=14, distribution_days=8,
                           accumulation_ratio=0.636, window=25)
    assert r.accumulation_days == 14
    assert r.distribution_days == 8
    assert abs(r.accumulation_ratio - 0.636) < 1e-6
    assert r.is_accumulating is True   # ratio > 0.5
```

- [ ] **Step 2: 실행 → 실패**

Run: `uv run pytest tests/tools/playbook/test_accumulation.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 구현**

`src/tools/playbook/__init__.py`: 빈 파일.

`src/tools/playbook/models.py`:

```python
from pydantic import BaseModel, computed_field


class AccumulationResult(BaseModel):
    """오닐식 매집일/분산일 집계 (CAN SLIM I)."""

    accumulation_days: int
    distribution_days: int
    accumulation_ratio: float   # acc / (acc + dist); 분모 0이면 0.0
    window: int

    @computed_field
    @property
    def is_accumulating(self) -> bool:
        return self.accumulation_ratio > 0.5
```

- [ ] **Step 4: 실행 → 통과 / Step 5: 커밋**

```bash
git add src/tools/playbook/ tests/tools/playbook/
git commit -m "feat(playbook): add AccumulationResult model + package"
```

---

## Task 2: analyze_accumulation 구현 (오닐식)

**Files:** Create `src/tools/playbook/accumulation.py`; Test `tests/tools/playbook/test_accumulation.py`

- [ ] **Step 1: 실패 테스트 (명시적 매집/분산 케이스)**

```python
import pandas as pd
from src.tools.playbook.accumulation import analyze_accumulation

def _df(rows):
    # rows: list of (open, high, low, close, volume)
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])

def test_distribution_day_down_close_up_volume():
    # day0 기준, day1: 종가 하락(-0.5%) + 거래량 증가 → 분산일
    df = _df([
        (100, 101, 99, 100, 1000),   # prev
        (100, 100, 97, 99, 1500),    # close 99 < 100*0.998, vol 1500>1000 → distribution
    ])
    r = analyze_accumulation(df, window=25)
    assert r.distribution_days == 1
    assert r.accumulation_days == 0

def test_accumulation_day_up_close_high_volume_top_close():
    # day1: 상승 + 거래량 증가 + 종가가 레인지 상단(>=0.5)
    df = _df([
        (100, 101, 99, 100, 1000),
        (100, 105, 100, 104, 1500),  # close 104>100, vol↑, (104-100)/(105-100)=0.8>=0.5 → accumulation
    ])
    r = analyze_accumulation(df, window=25)
    assert r.accumulation_days == 1
    assert r.distribution_days == 0

def test_ratio_and_window():
    # 평탄(거래량 감소) → 둘 다 0, ratio 0.0
    df = _df([(100, 101, 99, 100, 1000)] * 5 + [(100, 100, 99, 100, 500)])
    r = analyze_accumulation(df, window=25)
    assert r.accumulation_days == 0 and r.distribution_days == 0
    assert r.accumulation_ratio == 0.0
```

- [ ] **Step 2: 실행 → 실패**

Run: `uv run pytest tests/tools/playbook/test_accumulation.py -v`
Expected: FAIL (`analyze_accumulation` not defined)

- [ ] **Step 3: 구현**

`src/tools/playbook/accumulation.py`:

```python
import pandas as pd

from src.tools.playbook.models import AccumulationResult

# 오닐 분산일 임계: 전일 대비 종가 하락폭 (>= 0.2%)
_DISTRIBUTION_DROP = 0.002
# 매집일: 종가가 당일 레인지 상단에 마감 (>= 50%)
_TOP_CLOSE_RATIO = 0.5


def analyze_accumulation(df: pd.DataFrame, window: int = 25) -> AccumulationResult:
    """최근 `window` 거래일의 오닐식 매집일/분산일을 센다.

    분산일: 종가 < 전일종가 × (1 - 0.2%)  AND  거래량 > 전일거래량
    매집일: 종가 > 전일종가  AND  거래량 > 전일거래량  AND  (close-low)/(high-low) >= 0.5
    """
    needed = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or df.empty or not needed.issubset(df.columns) or len(df) < 2:
        return AccumulationResult(
            accumulation_days=0, distribution_days=0, accumulation_ratio=0.0, window=window
        )

    recent = df.tail(window + 1).reset_index(drop=True)  # +1: 첫 행의 전일 비교용
    acc = 0
    dist = 0
    for i in range(1, len(recent)):
        prev_close = float(recent.loc[i - 1, "Close"])
        prev_vol = float(recent.loc[i - 1, "Volume"])
        close = float(recent.loc[i, "Close"])
        high = float(recent.loc[i, "High"])
        low = float(recent.loc[i, "Low"])
        vol = float(recent.loc[i, "Volume"])

        vol_up = vol > prev_vol
        if not vol_up:
            continue

        if close < prev_close * (1 - _DISTRIBUTION_DROP):
            dist += 1
        elif close > prev_close:
            rng = high - low
            top_close = (close - low) / rng if rng > 0 else 1.0
            if top_close >= _TOP_CLOSE_RATIO:
                acc += 1

    total = acc + dist
    ratio = acc / total if total > 0 else 0.0
    return AccumulationResult(
        accumulation_days=acc, distribution_days=dist,
        accumulation_ratio=round(ratio, 4), window=window,
    )
```

- [ ] **Step 4: 실행 → 통과**

Run: `uv run pytest tests/tools/playbook/test_accumulation.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 실데이터 검증**

Run:
```
uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv('.env'); from src.providers.yfinance_provider import YFinanceProvider; from src.tools.technical.indicators import IndicatorCalculator; from src.tools.playbook.accumulation import analyze_accumulation; df=asyncio.run(YFinanceProvider().get_price_history('AAPL','6mo')); df=IndicatorCalculator().calculate(df); print(analyze_accumulation(df))"
```
확인: AAPL 최근 25일 매집/분산일 수와 ratio가 합리적인 범위(0~25, ratio 0~1)인지.

- [ ] **Step 6: 커밋**

```bash
git add src/tools/playbook/accumulation.py tests/tools/playbook/test_accumulation.py
git commit -m "feat(playbook): O'Neil accumulation/distribution day counter"
```

---

## Self-Review

**1. 스펙 커버리지:** §7.1 매집일/분산일 정의(전일 대비 거래량↑, 분산=−0.2%↓, 매집=상승+종가 상단) → Task 2 ✅. `AccumulationResult` → §14에 추가 필요(이 Plan에서 models.py에 정의, 스펙 §14 모델 목록과 정합).
**2. Placeholder:** 없음 — 모든 코드 complete.
**3. 타입 일관성:** `analyze_accumulation(df, window) -> AccumulationResult`; 필드 `accumulation_days/distribution_days/accumulation_ratio/window/is_accumulating` 일관.

> **참고:** Pocket Pivot(스펙 §7.1 "가중")은 별도 계산하지 않고, CAN SLIM I 종합(Plan 7)에서 기존 `components["volume"]`의 Pocket Pivot 결과를 **참조**한다. 이 Plan은 25일 매집/분산 카운트만 담당(중복 방지).

---

## 다음 단계
Plan 4: **종목 상대강도 RS**(`index_provider.py` + `relative_strength.py`, 맨스필드식).
