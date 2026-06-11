# 시장환경 + Stage2 일원화 + VCP 돌파 Implementation Plan (Plan 6/8)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. 체크박스(`- [ ]`)로 추적.

**Goal:** 게이트의 ★A(시장환경)·★B(Stage2)·★E(셋업 VCP 돌파) 부품을 만든다.

**Architecture:** `market_regime`(순수: index_df→추세), `minervini` Stage2 **7조건 단일 출처**로 보강 + `indicators._calculate_stage2`(죽은 코드) 제거, `vcp`(기존 `patterns._detect_vcp` 수축 결과 참조 + 피벗 돌파 신규).

**Tech Stack:** Python 3.12, pandas, pydantic, pytest. `uv run`.

**선행:** Plan 4(`IndexProvider`, `models.py`), Plan 5(playbook 모듈들).

---

## File Structure
- **Modify:** `src/tools/playbook/models.py` — `MarketRegimeResult`, `VcpResult`
- **Create:** `src/tools/playbook/market_regime.py`
- **Create:** `src/tools/playbook/vcp.py`
- **Modify:** `src/tools/technical/components/minervini.py` — Stage2 7조건 + `metrics["is_stage2"]`
- **Modify:** `src/tools/technical/indicators.py` — `_calculate_stage2` 및 `Is_Stage2` 호출 제거
- **Modify:** `src/tools/technical/models.py` — `from_analysis` 화이트리스트에서 `"Is_Stage2"` 제거
- **Test:** `tests/tools/playbook/test_market_regime.py`, `tests/tools/playbook/test_vcp.py`, 기존 `tests/.../test_minervini*` 갱신

---

## Task 1: market_regime (순수, 시장환경 게이트)

- [ ] **Step 1: 실패 테스트** (`tests/tools/playbook/test_market_regime.py`)

```python
import numpy as np, pandas as pd
from src.tools.playbook.models import MarketRegimeResult
from src.tools.playbook.market_regime import assess_market_regime

def _df(closes):
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes}, index=idx)

def test_uptrend_allows_new_buy():
    df = _df(list(np.linspace(100, 200, 260)))  # 우상향
    r = assess_market_regime(df, "^GSPC")
    assert r.allow_new_buy is True and r.regime == "상승"

def test_downtrend_blocks():
    df = _df(list(np.linspace(200, 100, 260)))  # 우하향
    r = assess_market_regime(df, "^KS11")
    assert r.allow_new_buy is False
```

- [ ] **Step 2~3: 구현** — `models.py`에 `MarketRegimeResult(regime, allow_new_buy, index_symbol, detail)`; `market_regime.py`:

```python
import pandas as pd
from src.tools.playbook.models import MarketRegimeResult

def assess_market_regime(index_df: pd.DataFrame, index_symbol: str) -> MarketRegimeResult:
    close = index_df["Close"].dropna()
    if len(close) < 200:
        return MarketRegimeResult(regime="unknown", allow_new_buy=False,
                                  index_symbol=index_symbol, detail="데이터 부족(<200)")
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    last = float(close.iloc[-1])
    above = last > float(sma50.iloc[-1]) and last > float(sma200.iloc[-1])
    rising = float(sma200.iloc[-1]) > float(sma200.iloc[-21])
    allow = bool(above and rising)
    if allow:
        regime = "상승"
    elif last > float(sma200.iloc[-1]):
        regime = "조정"
    else:
        regime = "하락"
    return MarketRegimeResult(regime=regime, allow_new_buy=allow, index_symbol=index_symbol,
                              detail=f"close>{('SMA50·200' if above else 'below MA')}, SMA200 {'상승' if rising else '하락'}")
```

- [ ] **Step 4~6: 통과 + 실데이터(^GSPC, ^KS11 via IndexProvider) + 커밋** `git commit -m "feat(playbook): market regime gate (pure, index trend)"`

---

## Task 2: minervini Stage2 7조건 일원화 (+ indicators 죽은코드 제거)

- [ ] **Step 1: 실패 테스트** — `analyze_minervini(df)` 결과 `metrics["is_stage2"]`가 7조건 충족 시 1.0, 미충족 시 0.0. (픽스처: 완전 정배열 상승 종목 → 1.0; 50일선 아래 → 0.0)

```python
# tests/tools/technical/test_minervini_stage2.py (신규 또는 기존 갱신)
from src.tools.technical.components.minervini import analyze_minervini
# ... 7조건 모두 충족하는 df fixture → metrics["is_stage2"] == 1.0
# ... 종가<SMA50 fixture → metrics["is_stage2"] == 0.0
```

- [ ] **Step 2~3: 구현** — `minervini.py`의 `conditions`를 7조건으로:

```python
sma_50 = safe("SMA_50"); sma_150 = safe("SMA_150"); sma_200 = safe("SMA_200")
sma_150_prev = ... (df.iloc[-22]["SMA_150"]);  sma_200_prev = ... (기존)
conditions = {
    "ma_stack": close > sma_150 > sma_200,                 # 1,2
    "ma_50_stack": sma_50 > sma_150 > sma_200,             # 4 (완전 정배열) [신규]
    "sma_150_rising": sma_150 > sma_150_prev if sma_150_prev else False,  # 3 [신규]
    "sma_200_rising": sma_200 > sma_200_prev if sma_200_prev else False,  # 3
    "above_50": close > sma_50,                            # 5
    "above_52w_low_30pct": close >= low_52w * 1.30 if low_52w else False, # 6
    "within_52w_high_25pct": close >= high_52w * 0.75 if high_52w else False, # 7
}
met = sum(conditions.values())
is_stage2 = (met == 7)
metrics["is_stage2"] = 1.0 if is_stage2 else 0.0
# score/signals: is_stage2면 "Stage 2 (강력한 상승 국면)" score 40, above_50만이면 강세 25, else -20 (기존 유지)
```

`indicators.py`: `calculate()`에서 `df = self._calculate_stage2(df)`(line ~162) 호출 삭제 + `_calculate_stage2` 메서드 삭제.
`technical/models.py`: `from_analysis`의 indicator_cols 화이트리스트에서 `"Is_Stage2"` 항목 삭제.

- [ ] **Step 4: 통과** — `uv run pytest tests/tools/technical/ -q` (기존 minervini/indicator 테스트 깨지면 7조건 반영해 갱신).
- [ ] **Step 5: 실데이터** — `jarvis check 005930.KS`로 minervini 컴포넌트 metrics에 `is_stage2`가 나오는지(0/1).
- [ ] **Step 6: 커밋** `git commit -m "refactor(technical): Stage2 single source in minervini (7 conditions), remove dead _calculate_stage2"`

---

## Task 3: vcp 피벗 돌파 (셋업 E)

- [ ] **Step 1: 사전 확인** — `src/tools/technical/components/patterns.py`의 `_detect_vcp`(또는 `analyze_patterns`) 시그니처/반환을 읽어, VCP 수축 여부와 마지막 수축 피벗 정보를 어떻게 얻는지 파악.

- [ ] **Step 2: 실패 테스트** (`tests/tools/playbook/test_vcp.py`) — 수축 후 돌파 케이스:
  - 수축 구간(변동성 축소) + 마지막 봉이 직전 N일 고점 상향 돌파 + 거래량 ≥ `Vol_SMA_50 × 1.5` → `breakout=True`
  - 수축만, 돌파 없음 → `in_vcp=True, breakout=False`

- [ ] **Step 3: 구현** — `models.py`에 `VcpResult(in_vcp, pivot, breakout, detail)`; `vcp.py`:

```python
import pandas as pd
from src.tools.playbook.models import VcpResult
from src.tools.technical.components.patterns import _detect_vcp  # 수축 판정 재사용

_PIVOT_LOOKBACK = 20
_VOL_MULT = 1.5

def detect_vcp_breakout(df: pd.DataFrame) -> VcpResult:
    """기존 _detect_vcp(수축)에 '마지막 수축 피벗 상향 돌파 + 거래량' 판정을 더한다."""
    vcp = _detect_vcp(df)            # 반환 형식은 Step 1에서 확인해 맞춤
    in_vcp = bool(vcp.get("detected")) if isinstance(vcp, dict) else bool(vcp)
    if not in_vcp or len(df) < _PIVOT_LOOKBACK + 1:
        return VcpResult(in_vcp=in_vcp, pivot=None, breakout=False, detail="수축 없음 또는 데이터 부족")
    recent = df.iloc[-(_PIVOT_LOOKBACK + 1):]
    pivot = float(recent["High"].iloc[:-1].max())   # 직전 구간 고점 = 피벗
    last = df.iloc[-1]
    vol_sma = float(last.get("Vol_SMA_50")) if "Vol_SMA_50" in df.columns and pd.notna(last.get("Vol_SMA_50")) else None
    vol_ok = vol_sma is not None and float(last["Volume"]) >= vol_sma * _VOL_MULT
    breakout = bool(float(last["Close"]) > pivot and vol_ok)
    return VcpResult(in_vcp=True, pivot=round(pivot, 2), breakout=breakout,
                     detail=f"pivot={pivot:.2f}, close={float(last['Close']):.2f}, vol_ok={vol_ok}")
```

- [ ] **Step 4~6: 통과 + 실데이터(AAPL/005930 df) + 커밋** `git commit -m "feat(playbook): VCP pivot breakout (reuses patterns._detect_vcp)"`

---

## Self-Review
**1. 스펙 커버리지:** §9(market_regime) → T1 ✅; §0.3·D4·D5(Stage2 7조건 단일출처, indicators 제거) → T2 ✅; §6.1 E·R21(VCP 수축 재사용+돌파 신규) → T3 ✅.
**2. Placeholder:** T3 `_detect_vcp` 반환형은 Step 1에서 실코드 확인해 맞춤(시그니처 미상 부분만 명시).
**3. 타입 일관성:** `MarketRegimeResult`, `VcpResult`, `assess_market_regime`, `detect_vcp_breakout`, `metrics["is_stage2"]` 일관.

> **주의(T2):** `Is_Stage2` 제거 전 `grep -rn "Is_Stage2" src/`로 잔여 소비처 재확인(현재까지 `indicators`·`technical/models` 화이트리스트뿐). 새 소비처가 있으면 보고.

---

## 다음 단계
Plan 7: **CAN SLIM 종합**(`canslim.py` — C·A·I 계산 + N·S·L·M 참조) + 분기 EPS 시계열 병합 정리(Plan 2 잔여). Plan 8: gate·sizing·exit_rules·holdings·engine·연결.
