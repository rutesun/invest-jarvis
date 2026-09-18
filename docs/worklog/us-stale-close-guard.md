# Worklog — us-stale-close-guard

- **Branch**: feature/us-stale-close-guard
- **Started**: 2026-09-18
- **Status**: in-progress
- **Links**: [plan](../superpowers/plans/2026-09-18-us-stale-close-guard.md)

---

## (2026-09-18 10:55) [Decision] trailing NaN-Close 봉 정제 + 스테일 경고 배치 위치

- 맥락: yfinance가 최근 일봉을 Close=NaN으로 반환하면(실측 INTC/BE 2026-09-17: OHLC 전부
  NaN, Volume만 존재) 기술 분석이 조용히 스테일 종가를 내보낸다. 마지막 봉 해석이 소비 지점마다
  불일치: `create_snapshot`은 dropna(Close) 후 이전 유효 봉(101.05)을 쓰고,
  `build_market_context`는 dropna 없이 iloc[-1] → close=0.0으로 붕괴해 스코어링까지 오염.
- 후보:
  - A) 정제 단계에서 trailing NaN-Close 봉 드롭(지표 무결성) + 표시 가격이 오늘과 다르면 경고
  - B) get_quote 실시간가로 마지막 봉 Close 보정(OHLC 불일치 → 지표 왜곡 위험)
  - C) A + 표시 가격은 get_quote 최신가 병기 + stale 경고
- 선택: C를 채택하되 정제는 한 곳(`TechnicalAnalysisTool.execute`)에서 수행.
  - 순수 함수 `drop_trailing_nan_close(df) -> (df, StaleClose)`를 seam으로 분리(단위 테스트 용이).
  - 정제 후 계산 → 모든 소비 지점이 동일한 유효 마지막 봉을 봄(context close=0 버그 동반 해결).
  - trailing NaN이 드롭됐을 때만 `logger.warning` + `TechnicalResult.warnings`에 경고 부착,
    best-effort `provider.get_quote`로 실시간가 병기(실패해도 분석은 진행).
  - 정상 경로(마지막 봉 유효)는 no-op → 동작 불변. KR/KIS도 마지막 봉 유효 → 무경고.
- 기각:
  - B: Close만 채우면 High/Low/Volume 결측과 불일치해 ATR·밴드 등 지표가 왜곡됨.
  - provider(`get_price_history`)에서 드롭+신호 전파: 반환 타입이 KIS와 공유하는 bare
    DataFrame이라 (dropped, stale) 신호를 실으려면 계약 변경이 침습적. TechnicalResult와
    get_quote가 도달 가능한 도메인 계층(tool)이 표면화에 적합.
- ADR 후보? no (지역적 데이터 방어, 아키텍처 결정 아님)
