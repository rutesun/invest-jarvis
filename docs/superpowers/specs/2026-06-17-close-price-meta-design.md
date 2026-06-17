# 기준 종가 메타 표기 + backfill 확장 설계 스펙

- **작성일**: 2026-06-17
- **상태**: Draft v1
- **대상**: 분석에 사용된 "마지막 종가"의 값·날짜·출처를 데이터 흐름에 실어 Summary에 표기하고, yfinance backfill을 "마감된 누락 세션 새 행 추가"까지 확장한다.
- **구현 플랜**: 작성 예정 (`docs/superpowers/plans/2026-06-17-close-price-meta.md`)

---

## 1. 배경 및 목표

### 1.1 문제 — 분석 기준 종가가 불투명하다

현재 리포트는 분석이 **어느 거래일의 종가를 기준으로 계산됐는지** 보여주지 않는다. 모든 지표(이평선·RSI·돌파·손절)는 마지막 종가 하나에서 출발하는데, 그 종가가:
- 오늘 것인지 어제 것인지 (미국장은 한국 시간 밤에 열려, 낮에 돌리면 보통 직전 거래일 기준)
- 야후가 정상 제공한 값인지, 1분봉으로 보정·보충한 값인지
- 장중 미완성봉을 제외하고 직전 완성일을 쓴 것인지

를 알 수 없다. 특히 이번 브랜치에서 backfill(1분봉 보정)을 도입한 뒤, 그 보정 여부가 사용자에게 숨겨져 있다.

### 1.2 목표

1. 마지막 종가의 **값·날짜·출처**를 판정해 분석 결과에 실어 전달한다.
2. Summary 최상단에 `기준 종가: $390.10 (2026-06-17, 정규 마감)` 형태로 표기한다.
3. backfill을 확장해 **장 마감 후 야후가 당일 행을 누락한 경우** 1분봉 완성 세션으로 새 행을 추가한다(현행은 NaN 행 채움만).

### 1.3 비목표

- 장중(미완성) 세션의 현재가를 종가로 추가하지 않는다 — 종가가 아직 확정되지 않았기 때문(현행 `_SESSION_COMPLETE_AFTER=15:55 ET` 가드 유지).
- `market_regime` 등 다른 지표의 데이터 소스 변경은 비범위.

---

## 2. 메타 모델 (신규)

`src/tools/technical/models.py`에 추가한다.

```python
class ClosePriceMeta(BaseModel):
    """분석에 사용된 마지막 종가의 출처 메타."""
    value: float        # 마지막 유효 종가
    date: str           # 그 종가가 찍힌 거래일 (YYYY-MM-DD)
    source: str         # "regular" | "intraday_fill" | "intraday_new" | "incomplete"
```

| source | 의미 | 표기 라벨 |
|--------|------|-----------|
| `regular` | 야후 일봉이 정상 제공한 완성 종가 | 정규 마감 |
| `intraday_fill` | 일봉 마지막 행이 NaN이라 1분봉 완성봉으로 채움 | 1분봉 보정 |
| `intraday_new` | 야후가 당일 행을 누락해 1분봉 완성봉으로 새 행 추가 | 1분봉 마감 |
| `incomplete` | 당일 미완성봉을 제외하고 직전 완성일 종가 사용 | ⚠️ 당일 진행 중 |

---

## 3. 출처 판정 규칙

`get_price_history`가 backfill을 적용한 뒤, 원본 일봉과 보정 결과를 비교해 마지막 유효 종가의 출처를 판정한다. 우선순위 순서로:

1. **`intraday_new`** — backfill이 1분봉으로 **새 행을 추가**했고, 그 추가된 날짜가 마지막 유효 종가다.
2. **`intraday_fill`** — 마지막 유효 종가 행이 원본에서 `Close=NaN`이었고 1분봉으로 **채워졌다**.
3. **`incomplete`** — 일봉 마지막 행이 `Close=NaN`인데 채우지 못했다(미완성 세션이거나 1분봉 부재). 마지막 유효 종가는 그 **직전 완성 행**이다.
4. **`regular`** — 위 어디에도 해당하지 않음(마지막 행이 정상, 보정 없음).

판정은 순수 함수 `resolve_close_meta(original_df, backfilled_df) -> ClosePriceMeta`로 분리한다(네트워크 없음, 단위 테스트 가능). `value`/`date`는 `backfilled_df`의 마지막 유효(non-NaN) 종가 행에서 추출한다.

---

## 4. backfill 확장 (`yfinance_provider.py`)

`backfill_daily_from_intraday(daily_df, intraday_df)`에 "새 행 추가"를 더한다.

- (현행) 일봉의 `Close=NaN`인 **완성 세션**을 1분봉 정규장 집계로 채운다.
- (신규) 1분봉의 최신 완성 세션(마지막 1분봉 시각 ≥ `_SESSION_COMPLETE_AFTER`) 날짜가 **일봉 마지막 행 날짜보다 미래**이면, 그 세션(들)을 일봉 OHLCV 행으로 **추가**한다.
- (가드 유지) 장중 미완성 세션(< 15:55 ET)은 채우지도 추가하지도 않는다.

`_maybe_backfill_recent`의 트리거를 확장한다. 현재는 `df["Close"].tail(5).isna().any()`(NaN 있을 때만)인데, "야후가 당일 행을 아예 누락한 경우"는 NaN이 없어 트리거되지 않는다. 따라서 **마지막 일봉 날짜가 가장 최근 거래일보다 과거일 수 있는 시간대**(장 마감 후)에도 1분봉을 받아 새 세션 유무를 확인하도록 트리거 조건에 "마지막 행 날짜가 오늘 이전" 조건을 더한다. 1분봉 fetch는 여전히 실패 시 원본 일봉을 그대로 반환한다(현행 graceful).

> 주의: 1분봉(`period="7d", interval="1m"`)은 야후 제약상 최근 ~7일만 커버한다. 그 이전 stale는 보충 불가(현행과 동일).

---

## 5. 데이터 흐름

`get_price_history` 반환을 `(df, ClosePriceMeta)` 튜플로 바꾼다.

```text
provider.get_price_history(ticker, period)
    → backfill 적용 → resolve_close_meta → (df, ClosePriceMeta)

tool.py (TechnicalAnalysisTool):
    df, close_meta = await provider.get_price_history(...)
    → TechnicalResult.close_meta 에 전달

evidence.py (screener):
    df, _ = await provider.get_price_history(...)   # 메타 무시

analyze_render:
    result["technical"].close_meta → Summary 표기
```

`TechnicalResult`에 `close_meta: ClosePriceMeta | None = None` 필드를 추가한다.

`BaseProvider.get_price_history`는 추상 인터페이스이므로 **모든 구현이 반환을 통일**해야 한다. `YFinanceProvider`는 §3의 4종 판정을, 한국 `KISProvider`/`KISProviderWrapper`는 종가가 정상 제공되므로 항상 `source="regular"` 메타를 반환한다(KIS 자체 보정·미완성 판정은 비범위 — §9). KIS는 backfill을 하지 않으므로 마지막 유효 종가 행에서 `value`/`date`만 채워 `regular`로 반환하면 된다.

대안으로 `df.attrs`에 메타를 싣는 방식은 pandas 연산(슬라이싱·copy)에서 조용히 유실될 수 있어 채택하지 않는다. 명시적 튜플 반환이 안전하다.

---

## 6. 표기 (`analyze_render`)

`_format_summary_section`에 `close_meta` 인자를 받아 Summary 최상단에 한 줄 추가:

```text
기준 종가: $390.10 (2026-06-17, 정규 마감)
```

- `source` → 한글 라벨 매핑(§2 표).
- `close_meta`가 None이면 줄을 생략(하위 호환).

---

## 7. 모델 변경 요약

- **신규**: `ClosePriceMeta` (`src/tools/technical/models.py`)
- **변경**: `TechnicalResult` — `close_meta: ClosePriceMeta | None = None` 필드 추가
- **변경**: `BaseProvider.get_price_history` 추상 시그니처 + 모든 구현 반환을 `(df, ClosePriceMeta)`로 — `YFinanceProvider`는 §3의 4종 판정, `KISProvider`/`KISProviderWrapper`는 항상 `regular`
- **변경**: `YFinanceProvider._get_history_sync` — backfill 후 `resolve_close_meta` 호출
- **변경**: `backfill_daily_from_intraday` — 새 행 추가 로직, `_maybe_backfill_recent` — 트리거 확장
- **신규**: `resolve_close_meta(original_df, backfilled_df) -> ClosePriceMeta` (순수 함수)
- **호출처 수정**: `tool.py`(메타 수신·전달), `evidence.py`(메타 무시)

---

## 8. 테스트 전략

- `resolve_close_meta`: 4개 source(regular/intraday_fill/intraday_new/incomplete) 각각 판정하는 단위 테스트(가짜 df 비교, 네트워크 없음).
- `backfill_daily_from_intraday`: 마감된 누락 세션이 새 행으로 추가되는지 / 미완성 세션은 추가 안 되는지(기존 NaN 채움 테스트 유지).
- `_maybe_backfill_recent`: 마지막 행이 과거 거래일일 때 1분봉 fetch가 트리거되는지(mock).
- `get_price_history`가 `(df, ClosePriceMeta)`를 반환하는지.
- `_format_summary_section`: `close_meta` 4종이 올바른 라벨로 표기되는지 / None이면 줄 생략.
- 회귀: `evidence.py` 호출부가 튜플 언패킹으로 정상 동작.

---

## 9. 범위 / 비범위

**범위**: `ClosePriceMeta` 모델, `resolve_close_meta`, backfill 새 행 추가, `get_price_history` 튜플 반환, `TechnicalResult.close_meta`, Summary 표기, 호출처 2곳 수정, 위 테스트.

**비범위(후속)**: 다른 지표의 데이터 소스 통일, 장중 미완성봉을 잠정 종가로 쓰는 옵션, KIS(한국) 종가 메타(현재 미국 yfinance 경로에 집중 — KIS도 동일 패턴으로 확장 가능하나 별도).
