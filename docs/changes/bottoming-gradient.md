# Change Record: 바닥 다지기 그라데이션 (avoid→hold 급점프 완화)

**Status**: Draft
**Date**: 2026-09-11
**PRs**: -
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

adjusted score는 추세 확인형(Minervini Stage 2 계열)이라 사실상 "SMA50 위/아래"에 연동된다. 종가가 SMA50 아래면 저점을 계단식으로 높여도(higher-lows) 점수가 −50~−90(avoid)에 고정되고, SMA50를 되찾는 순간 컴포넌트가 한꺼번에 뒤집혀 점수가 avoid→hold로 급점프한다. 저점 높이기·강세 다이버전스·거래량 마름 같은 **바닥 다지기 구조가 점수에 거의 반영되지 않아**, 확인 전 조기 관찰·소량 접근을 판단할 근거가 없었다.

실증(BE, Bloom Energy — 우리 시스템 계산):

```
before: 2026-08-03~09-02 내내 avoid(-50~-90) 고정
        → 09-03 -62(avoid) → 09-04 +33(watch) → 09-08 +105(hold)  (avoid→hold 급점프)
```

## What

건설적 바닥 구조를 as-of 안전하게 계량해 avoid를 accumulate 밴드까지만 **상한 있게** 끌어올린다. 바텀피싱 도구가 아니라 "전환의 완만화·조기 관찰"이 목적이다.

1. **바닥 구조 탐지 (`tools/technical/bottoming.py`, 신규)**: 4개 신호를 as-of 안전하게 계량.
   - higher_low: 최근 10일 저점 > 직전 30일 저점 (신저점을 계속 깨는 하락주 배제)
   - bullish_divergence: divergence 컴포넌트의 강세 reversal 메타데이터
   - volume_dry: 최근 5일 평균 거래량 < 직전 20일 평균의 0.85배 (매도 소진)
   - momentum_improving: velocity SMA20 기울기 변화율(slope_change) > 0
   - `MIN_SIGNALS=3` 동시 충족(confluence) 시에만 후보 자격. 가중치·상한은 `BottomingThresholds` 상수.
2. **상한 있는 가점 + accumulate 액션 (`tools/technical/aggregator.py`)**: 후보 자격 + 종가가 SMA50 아래 + 신선한 거래량 동반 이탈/Supertrend 매도 전환 없음일 때만 가점. 결과 점수는 `BOTTOMING_CEILING(-15)`를 못 넘고, `[ACCUMULATE_FLOOR(-40), CEILING]` 구간에서만 `accumulate` 라벨. `new_entry_allowed=False` 고정.
3. **downstream 매핑**: `analyzer` tri-state `accumulate→"중립"`, `analyze_decision` factor score `accumulate→5`(watch 4 < accumulate 5 < hold 6), bias는 neutral.

## Before / After

BE(Bloom Energy) 2026, 같은 날짜에 바닥 가점 유무 비교:

```
date        close | before        | after                | bottom
2026-08-12  237.2 | -55  avoid    | -25  accumulate      | 3sig
2026-08-14  229.9 | -20  reduce   | -15  accumulate      | 3sig
2026-08-18  209.0 | -50  avoid    | -20  accumulate      | 3sig
2026-08-20  202.5 | -60  avoid    | -30  accumulate      | 3sig
2026-08-21  201.4 | -90  avoid    | -90  avoid           | -      (깊은 약세일: 불변)
2026-08-27  217.8 | -30  avoid    | -15  accumulate      | 3sig
2026-08-31  206.3 | -35  avoid    | -15  accumulate      | 3sig
2026-09-03  235.6 | -62  avoid    | -62  avoid           | -      (SMA50 재탈환: 불변)
2026-09-04  252.9 |  33  watch    |  33  watch           | -
2026-09-08  277.2 | 105  hold     | 105  hold            | -
```

SMA50 재탈환 ~3주 전에 accumulate 그라데이션(−15~−30)이 나타나 조기 관찰 단계를 제공한다. 상한(−15)으로 avoid가 hold/buy로 뒤집히지 않는다.

## Impact

- check/brief/analyze에서 바닥 다지기 종목이 avoid 대신 accumulate로 표기돼, SMA50 확인 전 조기 관찰·소량 접근 판단이 가능해진다.
- 비적격일은 before=after로 완전 하위호환. 가점은 SMA50 아래에서만 적용돼 이미 이평 위 강세주(NVDA 등) 판정은 불변.

## Constraints (불변식)

- **추세 확인 규율 유지**: 바닥 신호만으로 avoid를 buy/hold로 뒤집지 않는다. 상한(−15)으로 accumulate 밴드까지만.
- **신규진입 게이트 불변**: accumulate는 `new_entry_allowed=False`. 이평/Stage 기준 진입 허용은 그대로.
- **가짜 바닥 차단**: 거래량 동반 breakdown/Supertrend 매도 전환(forced_action) 앞에서는 가점 생략. 신저점을 계속 깨는 하락주는 higher_low(10/30)·MIN_SIGNALS=3로 구조적 배제.
- **재탈환 확인 불blunt**: SMA50 재탈환 순간의 확인 점프 자체는 완만화하지 않는다(조기 관찰만 추가).

## 평가·검증

- 평가세트 실데이터 fixture(`tests/fixtures/technical/scoring/`): BE(바닥) / NVDA(강세, 판정 불변) / LULU(끝까지 하락, avoid 유지).
- 임계값 스윕으로 수렴(worklog `bottoming-gradient.md` 참조): `(MIN3, higher-low 10/30)`에서 BE accumulate 11일 / LULU 가짜 accumulate 0일 / NVDA 0일. `MIN4`는 바닥주까지 제거(과함), 짧은 5/10 창은 LULU 과검출.
- 골든 테스트(`tests/pipelines/stock_report/test_golden_set.py`) 및 전체 1348건 통과로 회귀 없음 확인.
