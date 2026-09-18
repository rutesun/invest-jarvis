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

## (2026-09-18 11:30) [Decision] 독립 리뷰 반영 — 경고를 brief·analyze surface까지 확장

- 맥락: 독립 코드 리뷰(general-purpose 서브에이전트)가 Critical 1건 지적 — 경고가 `check`에만
  실리고, 플랜이 명시한 `brief`/`analyze`는 여전히 `snapshot.price`만 소비해 스테일 가격을
  무경고로 노출. Important 1건 — `drop_trailing_nan_close`의 MultiIndex 컬럼 취약성(단일
  티커는 numpy 단일원소 truthiness로 우연히 동작).
- 검증: brief.py/deep_dive.py에 `technical.warnings` 소비 지점이 없음을 grep으로 확인(유효).
- 조치:
  - `BriefItem.warnings` 추가 → `_analyze_target`이 싣고, render가 "⚠ 데이터 경고"로 표기,
    `_facts_for`에도 포함. analyze는 `format_deep_dive_output`이 가격 헤더 직후 경고 블록 렌더.
  - `drop_trailing_nan_close`에서 MultiIndex 컬럼을 평탄화(from_analysis와 동일)해 우연 의존 제거.
  - 테스트: brief 렌더·analyze 렌더·brief 파이프라인 전파·MultiIndex 방어 추가. 전체 1402 통과.
- Minor(create_snapshot/_build_score_history의 dropna가 이제 no-op)는 무해해 유지, 지적만 기록.
- ADR 후보? no
