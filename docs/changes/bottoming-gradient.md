# Change Record: 바닥 다지기 그라데이션 + 원본 점수 추세 중복 완화

**Status**: Draft
**Date**: 2026-09-14
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

## 추가: 원본 점수 추세 중복 완화 (codex 리뷰 반영)

바닥 가점은 증상 완화(band-aid)였고, codex 독립 리뷰로 근본 원인이 **원본 점수의 추세 중복
카운팅**임이 드러났다(리뷰: `docs/worklog/bottoming-gradient-codex-review.md`). 하락 종목이
"이평 아래"를 minervini(-20)+velocity(-35)+supertrend(-25)+risk(-10)로 4중 벌점받아 -80~-90.
BE 9/2는 SMA150을 탈환했는데도 -80이었다.

1. **velocity 상태/이벤트 분리 (`components/velocity.py`)**: 종가가 이미 SMA20 위면 SMA20 기울기의
   하락은 지연(lag) 아티팩트다. '하락 가속/하락 전환점' 벌점을 억제해 반등 초입을 역방향으로
   때리지 않는다. 종가가 SMA20 아래인 날은 기존대로 벌점 유지.
2. **risk 추세 중복 벌점 제거 (`components/risk.py`)**: SMA50 아래·Supertrend 하락 재벌점(각 -5)을
   삭제. minervini·supertrend가 이미 카운팅하는 추세를 risk가 다시 벌점하던 이중 계산 제거
   (서사용 breakdown 메타데이터는 유지).

효과(BE, 원본 점수):

```
날짜        종가   before(구)  after(신)   판정 변화
2026-09-02  217.3   -80         -35        (SMA150 탈환 반영, avoid 유지)
2026-09-03  235.6   -62         -22        avoid → reduce (재탈환 직전 완화)
2026-08-24  204.0   -55         -45
2026-09-01  213.6   -85         -75        (SMA20 아래 약세일: 소폭만)
```

avoid→hold 급점프가 이제 원본 레벨에서 **avoid/reduce → reduce → watch → hold** 그라데이션이 된다.
SMA20 아래 약세일은 거의 그대로라 하락 규율은 유지. 전체 1351 테스트 통과, 회귀 0(밴드 재보정 불요).

**미착수 후속**: minervini의 SMA50 아래 -20 binary는 SMA150/200 탈환·정배열을 반영 못 한다.
그라데이션화는 전 종목·전 밴드 파급(action band 재보정 동반)이라 별도 과제로 분리.

## 평가·검증

- 평가세트 실데이터 fixture(`tests/fixtures/technical/scoring/`): BE(바닥) / NVDA(강세, 판정 불변) / LULU(끝까지 하락, avoid 유지).
- 임계값 스윕으로 수렴(worklog `bottoming-gradient.md` 참조): `(MIN3, higher-low 10/30)`에서 BE accumulate 11일 / LULU 가짜 accumulate 0일 / NVDA 0일. `MIN4`는 바닥주까지 제거(과함), 짧은 5/10 창은 LULU 과검출.
- 골든 테스트(`tests/pipelines/stock_report/test_golden_set.py`) 및 전체 1348건 통과로 회귀 없음 확인.

## 추가: A′ (점수 vs 게이트 분리) shadow 레이어 + 표시 cutover

codex와 다회 합의 후, 추세 레짐을 게이트로·차트/거래량/모멘텀을 점수로 분리하는 A′를 **병행(shadow)**
구현하고 check/brief/analyze에 **표시만 전환**했다(진입 authority는 playbook 유지, legacy 판정 불변).

- `tools/technical/shadow_v2.py`(신규): setup_score(상태만) + regime gate(weak/above50/trend=is_uptrend|Stage2)
  + supertrend 방향/flip + bottoming_watch(상태) → action_v2. [floor,ceiling] 밴드 + 비대칭 히스테리시스.
  buy = trend & ST up & !overext & fresh 종가돌파 & 52주고점근처 & setup≥0 (flip 단독 buy 제거).
- 밴드 재보정(39종목×2.5년): SETUP_STRONG 40→10(buy dead branch 해소). buy forward +2.3%/승률49%,
  승자 +12.4%/패자 −7.4%(비대칭) — 진입 후보 hint(playbook+손절 전제), standalone 알파 아님.
- scorer가 shadow 1회 계산 → `TechnicalResult.shadow_v2`. check/brief/analyze가 공유 표시.
- 검증: BE 바닥 그라데이션·NVDA 강세 안정·LULU/ARM 하락 안전·PANW 초기돌파 포착을 실데이터 회귀로 고정.

설계·합의 상세: `docs/worklog/score-vs-gate-consensus.md`. 미착수: analyze factor 수학 전환, near52 sweep.
