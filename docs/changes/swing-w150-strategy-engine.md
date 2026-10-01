# Change Record: SWING_W150 전략 엔진 + check/brief 참고 표시

**Status**: Draft
**Date**: 2026-09-30
**PRs**: #{PR번호}
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

백테스트(#60)로 확정한 스윙 시스템 v3는 `src/backtest/` 실험 스크립트 안에만 있어서 jarvis 화면에서 쓸 수 없었다. 스크립트는 지표도 자체 계산하고 있었고(ATR 14일 단순평균, 자체 슈퍼트렌드), 이 값은 jarvis `IndicatorCalculator`(pandas_ta Wilder ATR, pandas_ta 슈퍼트렌드)와 식이 달랐다. 그대로 옮기면 같은 이름의 지표가 두 가지 정의로 존재하게 된다.

## What

1. **재료 통일 + 재검증**: 백테스트의 ATR과 슈퍼트렌드를 jarvis 지표로 바꾼 비교 스크립트(`src/backtest/universe_jarvis_indicators.py`)로 v3를 다시 돌렸다. 조건은 같은 73종목, 같은 기간이다. 미사용 기간(2016~21) 성과는 370회 1.02R에서 367회 1.02R(95% 구간 0.71~1.35)로 같았고, 전체 981건 중 925건은 진입일과 청산일이 모두 같았다. 그래서 재료를 jarvis 한 곳으로 모았다.
2. **재료 추가 (`src/tools/technical`)**:
   - `IndicatorCalculator`에 v3가 쓰는 7개 컬럼만 추가했다: `Vol_SMA_20_Prev`, `SMA_150_Slope_21`, `SMA_20_Slope_5`, `High_50_Prev`, `High_20_Prev`, `Low_20`, `Low_20_Prev`. 기존 컬럼 값은 바꾸지 않았다.
   - 확정 저점·고점 `pivots.py`를 새로 만들었다. i번 봉의 피벗은 i+3번 봉부터 알려진 것으로 처리한다. 기존 `Swing_High/Low`는 중심 창이라 미래 봉을 쓰므로 재사용하지 않았다.
3. **Strategies 레이어 신설 (`src/strategies/swing_w150/`)**:
   - 레이어 순서를 `providers → tools → strategies → pipelines → cli`로 했다. 전략은 파이프라인이 가져다 쓰는 대상이라 파이프라인과 분리했고, 전략 패키지는 `src.tools`만 import한다.
   - 파일 구성:
     - `rules.py`: S/D 진입, 구조 붕괴, 손절, 졸업, 2일/−1R 청산, 과열 매도·재매수
     - `engine.py`: `replay`는 매매 목록을, `current_state`는 오늘 상태를 낸다
     - `models.py`: 결과 모델과 `summary_line()` 한 줄 요약
   - 오늘 상태는 4가지다: 보유 / 신호 / 대기 / 대상아님. 매매가 경로 의존적이라, 오늘 상태도 전체 기간을 처음부터 재생해서 구한다.
   - 대기 상태에 `breakout_blocked` 표시를 넣었다. 오늘 종가가 이미 직전 고가 위라면 규칙상 내일은 '첫 돌파'가 성립하지 않아 신호가 날 수 없고, 이 경우 따로 알린다.
4. **정답지(골든) 고정**:
   - 종목은 COIN, AMAT, PYPL, UPST다. S·D 진입, 손절, 150일선 청산, 과열 매도·재매수, 마지막 날 보유 중인 경우를 모두 포함하도록 골랐다.
   - 원본 OHLCV(2014~)와 기준 스크립트가 낸 매매 목록을 `tests/fixtures/swing_w150/`에 저장했다. 엔진은 날짜, 종류, 청산 사유가 같고 가격·R이 1e-9 이내로 일치해야 한다.
   - 정답지 형식은 `tests/harness/swing_fixture_contract.py` contract로 로드 시점에 검증한다.
5. **check/brief 참고 표시**:
   - `summarize(df, ticker)`를 `quick_check`의 "스윙 전략 (참고)" 섹션과 brief 항목 한 줄에 배치했다.
   - 계산이 실패하면 `logger.warning`을 남기고 표시를 생략한다. 참고 정보가 화면 전체를 막지 않게 하기 위해서다.
   - 한국 종목은 가격을 소수점 없이 천 단위 구분으로 표시한다(`is_korean_ticker` 재사용).

## Before / After

```
Before: jarvis check NVDA → 기존 기술 판정만 표시
After:  jarvis check NVDA
        스윙 전략 (참고)
         • SWING_W150 보유(S) — 2026-08-28 227.11 진입, 손절 199.26, 현재 +0.0R
        jarvis check 005930
         • SWING_W150 대기(S) — 288,000 위 마감 + 거래량 1.4배
```

## Impact

- `jarvis check`와 `jarvis brief`에 SWING_W150 상태 한 줄이 추가된다. 미국·한국 종목 모두 표시하고 미검증 표기는 넣지 않는다(사용자 결정).
- 기존 판정(action, verdict, A′, brief bucket·정렬)은 바뀌지 않는다. brief에서 판정이 불변인지는 테스트로 확인한다.
- "보유"는 시스템이 가상으로 들고 있는 포지션이며, 사용자의 실제 보유 파일과 연결하지 않는다.
- 환경 변수와 마이그레이션은 없다.

## Constraints

- 제품 화면은 3년치 데이터를 쓰므로, 워밍업 250봉을 빼면 약 2년만 재생된다. 그래서 오늘 상태가 긴 데이터(2014~) 기준과 다를 수 있다. 골든 테스트는 긴 데이터로 고정했다.
- 백테스트는 미국 73종목만 대상이었다. 한국 종목 성과는 검증하지 않았고, 거래비용과 생존편향도 반영하지 않았다.
- YAGNI로 만들지 않은 것: 레시피 레지스트리·다중 전략 추상화, 추가매수, RiskLevel, WINNER 모드, 섹터·베타 필터.
- 기존 `src/backtest/` 실험 스크립트, `tools/technical/tool.py`, 기존 판정 로직(aggregator, shadow_v2)은 수정하지 않았다.
- S 거래량 1.4배 경계는 정답지 기간의 매매를 바꾸지 않아 골든 테스트로는 고정되지 않는다. 그래서 단위 테스트로 따로 고정했다.
- D 경로의 `breakout_blocked`는 정답지에 해당 사례가 없어, S와 같은 로직만 적용하고 전용 테스트는 두지 않았다.
- `tools/technical/strategies/`(하루치 점수 부품)와 이름이 겹친다. 이름 정리는 별도 작업으로 미뤘다.

## Related

- 설계: `docs/superpowers/plans/2026-09-30-swing-w150-engine.md`, `docs/trading-system-materials-recipes-design.md`, `docs/trading-system-implementation-design.md`
- 결과: `docs/backtest/results-log.md` (확정 시스템 v3)
- Worklog: `docs/worklog/swing-w150-engine.md`
- ADR: 없음 (재료/해석 분리 원칙은 ADR 후보)
- FEATURES.md: §13 SWING_W150 전략 상태 추가
- 후속:
  - 한국 종목 백테스트
  - `src/tools/brief/`를 `pipelines/brief/`로 이동
  - `tools/technical/strategies/` 이름 정리
  - screener에서 오늘 신호 종목 찾기
