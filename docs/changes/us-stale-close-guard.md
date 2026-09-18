# Change Record: 스테일 종가 방어 (trailing NaN-Close 가드)

**Status**: Draft
**Date**: 2026-09-18
**PRs**: #{PR번호}
**Type**: fix

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

yfinance가 아직 마감되지 않은 최신 일봉을 `Close=NaN`(OHLC 전부 NaN, Volume만 존재)으로
반환하면, 기술 분석이 이 봉을 조용히 이전 유효 봉으로 대체해 며칠 지난 스테일 종가·점수를 실제
값처럼 내보냈다. 실측(2026-09-18, 마지막 봉 2026-09-17 Close=NaN):

| 종목 | 파이프라인 출력(스테일) | 실시간 get_quote | 오차 |
|------|------|------|------|
| INTC | 101.05 | 108.80 | -7.7% |
| BE | 270.02 | 280.76 | -4.0% |

또한 마지막 봉 해석이 소비 지점마다 갈렸다: `create_snapshot`은 `dropna(Close)` 후 이전
유효 봉을, `build_market_context`는 `iloc[-1]`로 `close=0.0`을 사용해 스코어링까지 오염됐다
(INTC adjusted 20, BE 25 — close=0 기반의 잘못된 값).

## What

1. **trailing NaN-Close 정제 순수 함수** (`src/tools/technical/staleness.py` 신규):
   `drop_trailing_nan_close(df) -> (df, StaleClose)`로 끝에서부터 연속된 `Close=NaN` 봉만
   걷어내고, 몇 개를 걷어냈는지·마지막 유효 봉 날짜를 `StaleClose`로 돌려준다. 중간 NaN은
   건드리지 않는다. 순수 함수로 분리해 단위 테스트 seam을 만들었다(Feathers).

2. **tool 계층에서 한 번 정제 + 스테일 표면화** (`src/tools/technical/tool.py`):
   `get_price_history` 직후·`calculate` 직전에 한 번 정제해 모든 소비 지점이 동일한 유효
   마지막 봉을 보게 했다(= `context.close=0.0` 붕괴 동반 해결). trailing NaN이 걷혔을 때만
   `logger.warning`(런타임 즉시 표면화)와 `TechnicalResult.warnings`에 경고를 부착하고,
   best-effort `get_quote`로 실시간가를 병기한다(조회 실패해도 분석은 진행). 정제 결과가
   비면 성공 대신 명시적 실패를 반환한다.
   - 정제(가드)를 provider가 아닌 tool에 둔 이유: `get_price_history`는 KIS와 공유하는 bare
     `DataFrame`을 반환해 (dropped, stale) 신호 전파가 침습적이다. `TechnicalResult.warnings`와
     `get_quote`가 도달 가능한 도메인 계층이 표면화에 적합하다.
   - 표시 가격을 실시간가로 덮어쓰지 않고 병기한 이유: `snapshot.price`는 price_levels·구조
     zone 등 지표 계산과 일관돼야 하므로 유효 봉 기준을 유지하고, 실시간가는 경고로 노출한다.

3. **경계 계약 + 골든 테스트**: 실제 raw 응답 fixture(`tests/fixtures/technical/stale_close/
   INTC_2y.csv`, `BE_2y.csv`)로 raw→최종 결과 전 구간을 고정한다. (a) 스테일 종가가 조용히
   나가지 않고 경고가 뜨는지, (b) 가드 없이는 `context.close=0.0`으로 붕괴하지만 가드 후에는
   유효 종가가 되는지를 함께 고정. 순수 함수 단위 테스트(`test_staleness.py`)와 tool 통합
   테스트(`test_tool.py`)도 추가.

## Before / After

```
Before (no guard):
  snapshot.price = 101.05  # 스테일, 경고 없음
  build_market_context().close = 0.0  # NaN 마지막 봉 → 붕괴
  adjusted_score: INTC 20 / BE 25  # close=0 기반 오염
  warnings: None

After (guard):
  snapshot.price = 101.05  # 지표 무결성 위해 유효 봉 유지
  build_market_context().close = 101.05  # 정제로 복구
  adjusted_score: INTC 43 / BE 55
  logger.warning: "Stale close for INTC: dropped 1 trailing NaN-close bar(s) up to
                   2026-09-17, analyzed with 2026-09-16 ($101.05), live=$108.80"
  warnings: ["최신 봉(2026-09-17) 종가가 비어 있어 마지막 유효 종가(2026-09-16, $101.05)로
             분석했습니다. 실시간 가격은 약 $108.80입니다. 표시 가격·변동률·점수가 실제와
             다를 수 있습니다."]
```

## Impact

- `check`(quick_check)는 스테일 시 기존 "### 주의" 블록에 경고를 렌더한다(경로 이미 존재).
  brief/analyze 등 `TechnicalResult.warnings`를 소비하는 경로에 동일하게 실린다.
- 정상 경로(마지막 봉 유효)는 정제가 no-op이라 출력·점수 불변. KR(KIS)은 마지막 봉이 유효해
  경고 없이 그대로.
- 스테일이 아니던 종목의 점수는 불변. 스테일이던 종목은 `context.close=0` 붕괴가 사라져 점수가
  정상화된다(부수적 정확도 개선).

## Constraints

- 표시 가격을 실시간가로 덮어쓰지 않았다(지표 일관성 유지). 실시간가는 경고 병기로만 노출.
- 마지막 봉 Close를 get_quote로 채워 넣는 보정(플랜 후보안 2)은 기각 — High/Low/Volume 결측과
  불일치해 ATR·밴드 등 지표를 왜곡한다.
- 트레일링이 아닌 중간 NaN-Close는 이번 범위 밖(관측된 문제는 트레일링 봉).
- get_quote 실패는 분석을 막지 않는다(경고만 실시간가 없이 유지).

## Related

- 설계: `docs/superpowers/plans/2026-09-18-us-stale-close-guard.md`, worklog
  `docs/worklog/us-stale-close-guard.md`
- ADR: 없음(지역적 데이터 방어, 아키텍처 결정 아님)
- FEATURES.md: 해당 없음(사용자 향 신규 기능 아님, 데이터 방어)
- 후속: 없음
