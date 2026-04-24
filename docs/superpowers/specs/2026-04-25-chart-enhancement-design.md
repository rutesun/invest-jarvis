# 차트 시각화 개선 설계

**날짜**: 2026-04-25  
**상태**: 승인 대기  
**참조 프로젝트**: ~/Develop/My/telegram

## 1. 개요

### 목표
telegram 프로젝트의 차트 시각화 품질을 invest-jarvis에 통합하면서, 명확한 컬럼명으로 전체 코드베이스를 표준화한다.

### 현재 문제점
- **차트**: 기본 캔들스틱만 표시, 보조지표 부족
- **컬럼명**: pandas_ta 기본 네이밍 (`MACD_12_26_9`, `SUPERTd_10_3.0` 등) - 가독성 낮음
- **일관성**: DataFrame 컬럼명과 Pydantic 필드명이 혼재

### 기대 효과
- telegram 수준의 전문적인 차트 (5개 이평선, Supertrend 시그널, Stage2 음영, MACD, cRSI)
- 명확한 컬럼명으로 코드 가독성 향상
- 컬럼명 표준화로 유지보수성 개선

---

## 2. 네이밍 전략

### 2.1 레이어별 네이밍 규칙

**DataFrame 컬럼명** (데이터 레이어 - 금융 도메인):
```python
# 명확한 대문자 + 언더스코어
SMA_20, SMA_50, SMA_120, SMA_150, SMA_200
SuperTrend_Up, SuperTrend_Dn, SuperTrend_Dir
MACD, MACD_Signal, MACD_Hist
cRSI, cRSI_HighBand, cRSI_LowBand
Vol_SMA_20, Vol_SMA_50
```

**Pydantic 필드명** (애플리케이션 레이어 - Python 관례):
```python
# Python snake_case 유지
sma_20, sma_50, supertrend_direction
macd, macd_signal, macd_histogram
crsi, crsi_high_band, crsi_low_band
```

### 2.2 매핑 위치

`indicators.py`의 `create_snapshot()` 메서드에서 변환:
```python
def create_snapshot(self, df: pd.DataFrame) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        sma_20=safe_get("SMA_20"),  # DataFrame → Pydantic
        supertrend_direction=int(safe_get("SuperTrend_Dir") or 0),
        # ...
    )
```

### 2.3 전체 컬럼명 매핑

| 기존 (pandas_ta) | 새 이름 | 설명 |
|-----------------|---------|------|
| `SMA_10` | `SMA_10` | 변경 없음 (이미 명확) |
| `SMA_20` | `SMA_20` | 변경 없음 |
| `SMA_50` | `SMA_50` | 변경 없음 |
| `SMA_120` | `SMA_120` | 변경 없음 |
| `SMA_150` | `SMA_150` | 변경 없음 |
| `SMA_200` | `SMA_200` | 변경 없음 |
| `RSI` | `RSI` | 변경 없음 |
| `MACD_12_26_9` | `MACD` | 단순화 |
| `MACDs_12_26_9` | `MACD_Signal` | 명확화 |
| `MACDh_12_26_9` | `MACD_Hist` | 명확화 |
| `MACD_5_35_5` | `MACD_Fast` | 단순화 |
| `MACDs_5_35_5` | `MACD_Fast_Signal` | 명확화 |
| `MACDh_5_35_5` | `MACD_Fast_Hist` | 명확화 |
| `SUPERTl_10_3.0` | `SuperTrend_Up` | 명확화 (상승추세선) |
| `SUPERTs_10_3.0` | `SuperTrend_Dn` | 명확화 (하락추세선) |
| `SUPERTd_10_3.0` | `SuperTrend_Dir` | 명확화 (방향: 1/-1) |
| `cRSI` | `cRSI` | 변경 없음 (이미 명확) |
| `cRSI_HighBand` | `cRSI_HighBand` | 변경 없음 |
| `cRSI_LowBand` | `cRSI_LowBand` | 변경 없음 |
| `BBU_20_2.0` | `BB_Upper` | 단순화 |
| `BBL_20_2.0` | `BB_Lower` | 단순화 |
| `ADX_14` | `ADX` | 단순화 |
| `ATR` | `ATR` | 변경 없음 |
| `Vol_SMA_20` | `Vol_SMA_20` | 변경 없음 |
| `Vol_SMA_50` | `Vol_SMA_50` | 변경 없음 |
| `Vol_SMA_120` | `Vol_SMA_120` | 변경 없음 |
| (신규) | `Is_Stage2` | Stage2 플래그 추가 |

---

## 3. Stage2 감지 로직

### 3.1 Minervini Stage2 조건

Mark Minervini의 Stage Analysis 기준:
1. **Price > SMA_150 > SMA_200**: 가격이 중장기 이평선 위
2. **SMA_150, SMA_200 상승 중**: 20일 lookback으로 상승 확인
3. **Price >= Low_52w * 1.3**: 52주 저점 대비 최소 30% 상승
4. **Price >= High_52w * 0.75**: 52주 고점 대비 25% 이내

### 3.2 구현

`indicators.py`에 새 메서드 추가:
```python
def _calculate_stage2(self, df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Minervini Stage2 flag (상승 추세 구간)."""
    df["Is_Stage2"] = False  # default
    
    required_cols = ["SMA_150", "SMA_200", "High_52w", "Low_52w", "Close"]
    if not all(col in df.columns for col in required_cols):
        return df
    
    # 조건 1: Price > SMA_150 > SMA_200
    cond1 = (df["Close"] > df["SMA_150"]) & (df["SMA_150"] > df["SMA_200"])
    
    # 조건 2: SMA_150, SMA_200 상승 중 (20일 lookback)
    lookback = 20
    sma150_rising = df["SMA_150"] > df["SMA_150"].shift(lookback)
    sma200_rising = df["SMA_200"] > df["SMA_200"].shift(lookback)
    cond2 = sma150_rising & sma200_rising
    
    # 조건 3: Price >= Low_52w * 1.3
    cond3 = df["Close"] >= (df["Low_52w"] * 1.3)
    
    # 조건 4: Price >= High_52w * 0.75
    cond4 = df["Close"] >= (df["High_52w"] * 0.75)
    
    df["Is_Stage2"] = cond1 & cond2 & cond3 & cond4
    return df
```

### 3.3 차트 음영 표시

`charting.py`에 helper 함수 추가:
```python
def _shade_stage2(ax, df: pd.DataFrame) -> None:
    """Stage2 조건 충족 구간을 배경 음영으로 표시."""
    if "Is_Stage2" not in df.columns:
        return
    
    mask = df["Is_Stage2"].astype(bool).fillna(False).to_numpy()
    if mask.size == 0 or not mask.any():
        return
    
    idx = df.index.to_list()
    start_i: Optional[int] = None
    
    # 연속된 True 구간을 찾아 음영 처리
    for i, v in enumerate(mask):
        if v and start_i is None:
            start_i = i
        if (not v or i == len(mask) - 1) and start_i is not None:
            end_i = i if v and i == len(mask) - 1 else i - 1
            ax.axvspan(idx[start_i], idx[end_i], facecolor="green", alpha=0.08, zorder=0)
            start_i = None
```

---

## 4. 차트 시각화 설계

### 4.1 패널 구조

```
Panel 0 (비율 6): 가격
  - 캔들스틱
  - 5개 이평선 (10/20/50/120/150/200일)
  - Supertrend (상승/하락 분리 + 전환 시그널)
  - Stage2 음영 (초록 배경)
  - 패턴 마커 (기존 유지)
  - 지지/저항선 (기존 유지)
  - 우측 MA 값 라벨

Panel 1 (비율 2): 거래량
  - Volume 바 (mplfinance 기본)
  - Volume MA50 오버레이 (골드 라인)

Panel 2 (비율 2): MACD
  - MACD 히스토그램 (회색, alpha=0.55)
  - MACD 라인 (파랑)
  - Signal 라인 (주황)

Panel 3 (비율 2): cRSI
  - cRSI 라인 (마젠타)
  - 동적 밴드 (청록, 10th/90th percentile)
  - 30/70 참조선 (회색 점선)
```

### 4.2 이평선 스타일링

**우선순위별 색상 및 굵기**:

```python
# 최우선 (가장 굵고 강한 색)
addplots.append(mpf.make_addplot(df["SMA_50"], color="#00D1FF", width=3.0))   # 밝은 청록
addplots.append(mpf.make_addplot(df["SMA_200"], color="#FF2D55", width=2.8))  # 진한 빨강

# 차선 (중간 굵기, 선명한 색)
addplots.append(mpf.make_addplot(df["SMA_120"], color="#FF8C00", width=2.0))  # 주황
addplots.append(mpf.make_addplot(df["SMA_20"], color="#4DA3FF", width=1.8))   # 밝은 파랑

# 참고용 (얇고 연한 색)
addplots.append(mpf.make_addplot(df["SMA_10"], color="#B0B0B0", width=1.0))   # 연한 회색
addplots.append(mpf.make_addplot(df["SMA_150"], color="#8A8A8A", width=0.9))  # 회색
```

**시각적 효과**:
```
━━━━━━━━━━  50일 (청록, 가장 굵음)
━━━━━━━━━   200일 (빨강, 두번째 굵음)
━━━━━━━━    120일 (주황, 중간)
━━━━━━━     20일 (파랑, 중간)
━━━━━       10일 (회색, 얇음)
━━━━        150일 (회색, 가장 얇음)
```

**우측 라벨 순서** (위→아래):
```python
labels = [
    ("MA50", "SMA_50", "#00D1FF", 0),      # 최상단
    ("MA200", "SMA_200", "#FF2D55", -10),
    ("MA120", "SMA_120", "#FF8C00", -20),
    ("MA20", "SMA_20", "#4DA3FF", 10),
    ("MA150", "SMA_150", "#8A8A8A", 20),   # 최하단
]
```

### 4.3 Supertrend 시각화

```python
# 방향에 따라 색상 분리
st_dir = df["SuperTrend_Dir"].astype("int64")
st_up = df["SuperTrend_Up"].where(st_dir == 1)   # 상승추세: 초록
st_dn = df["SuperTrend_Dn"].where(st_dir == -1)  # 하락추세: 빨강

addplots.append(mpf.make_addplot(st_up, color="green", width=2))
addplots.append(mpf.make_addplot(st_dn, color="red", width=2))

# 전환 시그널 마커
buy_signal = (st_dir == 1) & (st_dir.shift(1) == -1)
sell_signal = (st_dir == -1) & (st_dir.shift(1) == 1)

buy_y = df["SuperTrend_Up"].where(buy_signal)
sell_y = df["SuperTrend_Dn"].where(sell_signal)

addplots.append(mpf.make_addplot(buy_y, type="scatter", marker="o", markersize=35, color="green"))
addplots.append(mpf.make_addplot(sell_y, type="scatter", marker="o", markersize=35, color="red"))
```

### 4.4 Volume 패널

```python
# mplfinance 기본 volume=True (녹색/빨강 바)
# Volume MA50 오버레이
addplots.append(mpf.make_addplot(df["Vol_SMA_50"], panel=1, color="gold", width=1))
```

### 4.5 MACD 패널

```python
# 히스토그램 (회색, 투명도)
addplots.append(mpf.make_addplot(
    df["MACD_Hist"],
    panel=2,
    type="bar",
    color="#888888",
    alpha=0.55,
    width=0.7,
))

# MACD 라인 (파랑)
addplots.append(mpf.make_addplot(df["MACD"], panel=2, color="#4DA3FF", width=1.3))

# Signal 라인 (주황)
addplots.append(mpf.make_addplot(df["MACD_Signal"], panel=2, color="#FF8C00", width=1.1))
```

### 4.6 cRSI 패널

```python
# cRSI 라인 (마젠타)
addplots.append(mpf.make_addplot(
    df["cRSI"],
    panel=3,
    color="#FF00FF",
    width=1.2,
    ylim=(0, 100),
))

# 동적 밴드 (청록)
addplots.append(mpf.make_addplot(df["cRSI_LowBand"], panel=3, color="#00FFFF", width=1.0, alpha=0.9))
addplots.append(mpf.make_addplot(df["cRSI_HighBand"], panel=3, color="#00FFFF", width=1.0, alpha=0.9))

# 30/70 참조선 (회색 점선)
addplots.append(mpf.make_addplot(
    pd.Series(30.0, index=df.index),
    panel=3,
    color="#B0B0B0",
    width=0.8,
    linestyle="dashed",
    alpha=0.7,
))
addplots.append(mpf.make_addplot(
    pd.Series(70.0, index=df.index),
    panel=3,
    color="#B0B0B0",
    width=0.8,
    linestyle="dashed",
    alpha=0.7,
))
```

### 4.7 패널 라벨 배지

```python
def _badge(ax, text: str, *, xy=(0.01, 0.96), color="#111111") -> None:
    """패널 좌측 상단에 라벨 배지를 표시."""
    ax.text(
        xy[0], xy[1], text,
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=8.5,
        color=color,
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#DDDDDD", alpha=0.85),
        zorder=5,
    )

# 적용
_badge(panels[1], "VOL + VOL_MA50", xy=(0.01, 0.92))
_badge(panels[2], "MACD(12,26,9)", xy=(0.01, 0.92))
_badge(panels[3], "cRSI(dc=20,vib=10,lvl=10%)", xy=(0.01, 0.92))
```

### 4.8 기존 기능 유지

- `_mark_patterns()`: 차트 패턴 마커 (Cup & Handle 등)
- `_draw_support_resistance()`: 지지/저항선 (Fibonacci, Swing levels)
- `_setup_korean_font()`: 한글 폰트 설정
- `_ensure_dir()`: 출력 디렉토리 생성

---

## 5. 영향 받는 파일

### 5.1 indicators.py

**변경 사항**:
1. `calculate()` 메서드에서 컬럼명 표준화
   - pandas_ta 결과를 명확한 이름으로 재할당
   - 예: `df["MACD"] = macd["MACD_12_26_9"]`

2. `_calculate_stage2()` 메서드 추가
   - Minervini Stage2 조건 체크
   - `Is_Stage2` 컬럼 생성

3. `create_snapshot()` 메서드 업데이트
   - 새 컬럼명으로 매핑
   - 예: `sma_20=safe_get("SMA_20")`

### 5.2 components/

**supertrend.py**:
```python
# Before
supertrend_dir = latest.get("SUPERTd_10_3.0")

# After
supertrend_dir = latest.get("SuperTrend_Dir")
```

**divergence.py**:
```python
# Before
macd = latest.get("MACD_12_26_9")
signal = latest.get("MACDs_12_26_9")

# After
macd = latest.get("MACD")
signal = latest.get("MACD_Signal")
```

**velocity.py, minervini.py**:
```python
# SMA 컬럼명은 이미 명확하므로 변경 없음
# 단, 대소문자 일관성 확인 (SMA_50 vs sma_50)
```

**crsi.py**:
- 변경 없음 (이미 `cRSI`, `cRSI_HighBand`, `cRSI_LowBand` 사용)

### 5.3 charting.py

**변경 사항**:
1. 새 helper 함수 추가
   - `_shade_stage2()`: Stage2 음영

2. `_right_value_labels()` 업데이트
   - MA150 라벨 추가
   - 순서 변경 (MA50 최상단)

3. `render_technical_chart()` 주요 로직
   - 5개 이평선 추가 (우선순위별 스타일)
   - Supertrend 시그널 마커
   - Volume MA50 오버레이
   - MACD/cRSI 패널 추가
   - Stage2 음영 호출
   - 패널 라벨 배지

4. 컬럼명 참조 업데이트
   - `sma_20` → `SMA_20`
   - `supertrend_direction` → `SuperTrend_Dir`

### 5.4 scorer.py

**변경 사항**:
- 컬럼명 참조만 업데이트
- 로직 변경 없음

### 5.5 tests/

**변경 사항**:
- 모든 컬럼명 기대값 업데이트
- 예: `assert "MACD_12_26_9" in df.columns` → `assert "MACD" in df.columns`
- Stage2 컬럼 추가 테스트

---

## 6. 구현 전략

### 6.1 워크트리 격리

```bash
# 새 워크트리 생성
git worktree add .worktrees/chart-enhancement -b feature/chart-enhancement

# 작업 디렉토리 이동
cd .worktrees/chart-enhancement
```

### 6.2 커밋 시퀀스 (5개)

**Commit 1: indicators.py 표준화**
```
refactor(technical): Standardize indicator column names to clear naming

- indicators.py: SMA_*, SuperTrend_*, MACD → 명확한 컬럼명
- Update create_snapshot() mapping (DataFrame → Pydantic)
- 변경: pandas_ta 결과를 명확한 이름으로 재할당

Test: uv run pytest tests/tools/technical/test_indicators.py -v
```

**Commit 2: Stage2 감지 추가**
```
feat(technical): Add Stage2 detection flag for Minervini analysis

- indicators.py: _calculate_stage2() method
- Is_Stage2 column based on:
  - Price > SMA150 > SMA200
  - SMA150/200 rising (20-day lookback)
  - Price >= Low_52w * 1.3
  - Price >= High_52w * 0.75

Test: uv run pytest tests/tools/technical/test_indicators.py::test_stage2 -v
```

**Commit 3: components 업데이트**
```
refactor(technical): Update components to use new column names

- components/supertrend.py: SuperTrend_Dir
- components/divergence.py: MACD, MACD_Signal
- components/velocity.py, minervini.py: SMA 일관성
- scorer.py: column references

Test: uv run pytest tests/tools/technical/ -v
```

**Commit 4: 차트 개선**
```
feat(charting): Enhance chart with telegram-style technical indicators

- 5 moving averages with priority styling (50/200 > 120/20 > 10/150)
  - MA50: #00D1FF, width=3.0 (최고 강조)
  - MA200: #FF2D55, width=2.8
  - MA120: #FF8C00, width=2.0
  - MA20: #4DA3FF, width=1.8
  - MA10/150: 회색, 얇게
- Supertrend with buy/sell signal markers (markersize=35)
- Stage2 shading (green background, alpha=0.08)
- Volume MA50 overlay (gold line)
- MACD panel (histogram + lines)
- cRSI panel (dynamic bands + 30/70 reference lines)
- Panel badges for indicators
- Right-side MA value labels

Test: uv run jarvis analyze AAPL
```

**Commit 5: 테스트 및 문서**
```
test: Update technical tests for new column names

- test_indicators.py: SMA_*, SuperTrend_*, MACD
- test_charting.py: new indicator expectations
- test_components.py: column name updates

docs: Update FEATURES.md for chart enhancements

Test: uv run pytest
```

### 6.3 테스트 전략

**각 커밋 후**:
```bash
# 단위 테스트
uv run pytest tests/tools/technical/ -v

# 통합 테스트 (Commit 4 이후)
uv run jarvis check AAPL
uv run jarvis analyze AAPL  # 차트 생성 확인
ls -lh charts/
```

**전체 완료 후**:
```bash
# 전체 테스트 스위트
uv run pytest

# 실제 데이터로 검증
uv run jarvis analyze AAPL
uv run jarvis analyze 삼성전자
uv run jarvis analyze NVDA
```

### 6.4 문서 업데이트

**docs/FEATURES.md** (Commit 5에 포함):
```markdown
## 1.1 차트 시각화

invest-jarvis는 기술적 분석 결과를 시각적으로 표현하는 전문적인 차트를 생성합니다.

### 주요 기능

**가격 패널**:
- 캔들스틱 차트
- 6개 이동평균선 (10/20/50/120/150/200일)
  - 우선순위별 스타일링 (50일/200일 가장 굵게)
- Supertrend 추세 지표
  - 매수/매도 전환 시그널 마커
- Stage2 구간 음영 (Minervini 기준 상승 추세)
- 차트 패턴 마커 (Cup & Handle, Double Bottom 등)
- 지지선/저항선 (Fibonacci, Swing levels)
- 우측 MA 값 라벨

**보조지표 패널**:
- 거래량 (Volume MA50 오버레이)
- MACD(12,26,9) - 히스토그램 + 시그널 라인
- cRSI - 동적 밴드 + 30/70 참조선

### 사용법

```bash
# analyze 명령 시 자동 생성
uv run jarvis analyze AAPL

# 차트 저장 위치
charts/AAPL_technical.png
```

### 기술 명세

- 렌더링: mplfinance
- 해상도: 130 DPI
- 패널 비율: (6, 2, 2, 2) - 가격:거래량:MACD:cRSI
- 한글 폰트 지원: Noto Sans CJK KR, AppleGothic 등
```

---

## 7. 예상 작업 시간

| 단계 | 예상 시간 |
|------|----------|
| Commit 1: indicators.py 표준화 | 20분 |
| Commit 2: Stage2 추가 | 10분 |
| Commit 3: components 업데이트 | 20분 |
| Commit 4: charting.py 개선 | 40분 |
| Commit 5: 테스트 및 문서 | 30분 |
| **Total** | **~2시간** |

---

## 8. 리스크 및 완화 전략

### 8.1 컬럼명 변경 리스크

**리스크**: 컬럼명 변경 시 놓친 참조로 인한 런타임 에러

**완화**:
- 각 커밋 후 테스트 실행
- Grep으로 구 컬럼명 검색: `grep -r "MACD_12_26_9" src/`
- 워크트리 격리로 main 브랜치 영향 없음

### 8.2 차트 렌더링 성능

**리스크**: 패널 증가로 차트 생성 시간 증가

**완화**:
- mplfinance는 이미 최적화됨 (C 확장)
- 단일 `mpf.plot()` 호출로 모든 패널 한번에 렌더링
- 예상 렌더링 시간: 1-2초 (변화 없음)

### 8.3 Pydantic 모델 호환성

**리스크**: Pydantic 필드명은 snake_case 유지해야 LLM 호환성 유지

**완화**:
- `create_snapshot()`에서 명시적 매핑
- 기존 LLM 프롬프트는 변경 불필요
- 테스트로 검증

---

## 9. 의사결정 기록

### 9.1 왜 전체 표준화? (옵션 B 선택)

**대안**:
- A) 두 가지 네이밍 모두 제공 (호환성)
- B) 전체 코드베이스 표준화 (선택됨)
- C) 차트 렌더링 직전에만 매핑

**선택 이유**:
- 한 번 작업하면 앞으로 계속 명확
- 코드 가독성 대폭 향상
- 새 개발자 온보딩 용이
- 중복 컬럼 없음 (메모리 효율)

### 9.2 왜 telegram 로직 차용?

**이유**:
- 이미 검증된 코드 (실전 운영 중)
- 금융 차트 Best Practice 적용
- Stage2 음영, Supertrend 시그널 등 고급 기능
- 색상/굵기 조합이 시각적으로 효과적

### 9.3 Stage2 필수 포함 이유

**이유**:
- Minervini Stage Analysis는 유명한 기법
- 시각적 피드백으로 상승 추세 구간 한눈에 파악
- 이미 `components/minervini.py`에 로직 존재
- telegram에서 유용성 검증됨

### 9.4 이평선 색상 선택 근거

**우선순위**:
- 50일/200일 최고 강조 (가장 많이 참조)
- 120일/20일 차선 강조
- 10일/150일 참고용

**색상 선택**:
- 50일(청록) vs 200일(빨강): 명확한 대비
- 120일(주황): 중간 톤으로 구분
- 20일(파랑): 50일과 같은 계열이지만 밝기로 구분
- 10일/150일(회색): 보조적 역할

---

## 10. 후속 작업 (이번 범위 제외)

- [ ] 사용자 정의 차트 스타일 (config.yaml 설정)
- [ ] 다크 모드 차트 테마
- [ ] 차트 PNG 외 SVG 포맷 지원
- [ ] 인터랙티브 HTML 차트 (plotly 전환)
- [ ] 차트 비교 뷰 (여러 종목 나란히)

---

## 11. 체크리스트

- [x] 컬럼명 매핑 표 작성
- [x] Stage2 계산 로직 정의
- [x] 차트 패널 구조 설계
- [x] 이평선 색상/굵기 확정
- [x] 커밋 시퀀스 정의
- [x] 테스트 전략 수립
- [x] 리스크 식별 및 완화 방안
- [x] 문서 업데이트 계획
- [ ] 사용자 승인
- [ ] 구현 계획 작성 (writing-plans skill)
