# Worklog — bottoming-gradient

- **Branch**: feature/bottoming-gradient
- **Started**: 2026-09-10
- **Status**: in-progress
- **Links**: [설계 플랜](../superpowers/plans/2026-09-09-scoring-bottoming-gradient.md)

---

## (2026-09-10 11:13) [Decision] 바닥 그라데이션: 상한 있는 가점 + accumulate 액션
- 맥락: adjusted score가 이평 위치(추세)에 지배돼, 종가가 SMA50 아래면 저점을 계단식으로
  높여도(higher-lows) −50~−90(avoid)에 고정되다가 SMA50 재탈환 순간 컴포넌트가 한꺼번에
  뒤집혀 −62→+105로 급점프. 바닥 다지기 구조가 점수에 거의 반영되지 않는 문제.
- 후보:
  - A. 상한 있는 바닥 가점(aggregator 신규 규칙) — 바닥 신호 충족 시 avoid를 accumulate
    밴드까지만 끌어올림. 상한/게이트로 규율 유지.
  - B. 라벨만 추가(점수 불변) — action은 avoid/reduce 그대로 두고 narrative에만 "바닥 다지기".
  - C. divergence/turnaround 컴포넌트 가중치 상향 — 전 구간 스코어에 영향, 상한 보장 없음.
- 선택: A + accumulate를 1급 VerdictAction으로 추가.
  - 이유: (1) 점수는 완만히 올리되 상한(BOTTOMING_CEILING)으로 규율 유지, (2) "accumulate"
    라벨을 check/brief/analyze에 명시 노출해 watch 전 소량 관찰 단계를 사용자가 인지.
  - B 기각: action이 avoid/reduce로 남아 LLM tri-state에서 "매도"로 렌더 → 바닥주에 오해 소지.
  - C 기각: 상승 추세 구간 스코어까지 왜곡, accumulate 상한을 보장 못 함(바텀피싱화 위험).
- 불변식 준수 방법:
  - 가점은 close_above_sma50=False(추세 확인 게이트 아래)에서만 적용. NVDA 등 강세주(이평 위)는
    가점 대상 제외 → 판정 불변.
  - 거래량 동반 breakdown/Supertrend 매도 전환(forced_action)이 있으면 가점 생략 → 가짜 바닥 차단.
  - accumulate는 new_entry_allowed=False 고정. 신규진입 게이트(이평/Stage)는 불변.
  - 결과 점수는 BOTTOMING_CEILING(-15)을 못 넘음 → avoid(-90)를 accumulate 밴드까지만.
- 구현 seam: 바닥 신호 탐지는 신규 `bottoming.py`(df+components 기반, 단위테스트 용이).
  aggregator.aggregate()에 optional `bottoming` 인자 추가(기본 None → 기존 동작 불변).
  가중치·상한은 `BottomingThresholds` 상수로 노출해 튜닝 가능.
- ADR 후보? no (스코어링 규칙 조정, change-record로 충분)

## (2026-09-11 12:30) [Decision] 바닥 가점 임계값 튜닝 — MIN_SIGNALS=3, higher-low 10/30
- 맥락: 초기값(MIN_SIGNALS=2, higher-low 5/10)으로 LULU(끝까지 하락) 구간에 가짜
  accumulate 8일 발생. dead-cat 반등의 단기 higher-low+다이버전스에 과검출.
- 평가세트 스윕(고정 fixture, 실데이터):
  - BE(2026-08-03~09-02, 바닥) accumulate 일수 / LULU(2026-03-13~05-15, 하락) 가짜
    accumulate 일수 / NVDA(2026-08-06~09-09, 강세) accumulate 일수를 지표로 조합 반복.
  - (MIN2, 5/10): BE 15 / LULU 8 / NVDA 0  → LULU 과검출
  - (MIN3, 5/10): BE 10 / LULU 3 / NVDA 0  → LULU 여전
  - (MIN3, 10/30): BE 11 / LULU 0 / NVDA 0 → 채택
  - (MIN3, 10/40): BE 11 / LULU 0 / NVDA 0 → 동률(더 긴 창 불필요)
  - (MIN4, 10/30): BE 0  / LULU 0 / NVDA 0 → 바닥주까지 사망(과함)
- 선택: MIN_SIGNALS=3, HIGHER_LOW_RECENT=10, HIGHER_LOW_PRIOR=30.
  - 이유: 하락주 가짜 바닥 0, 바닥주 그라데이션 유지, 강세주 불변을 동시 만족하는 최소침습.
  - "동시 충족(confluence)" 3신호 요구가 dead-cat 단발 신호를 배제. higher-low를 10/30
    장기창으로 늘려 신저점을 계속 깨는 하락주를 구조적으로 제외.
- 기각: MIN2/짧은창(과검출), MIN4(바닥주까지 제거).
- 가중치(W_HL=12/W_DIV=10/W_VD=8/W_MO=10, BONUS_MAX=40, CEILING=-15, FLOOR=-40)는
  밴드 내 lift 크기만 좌우 → 스윕에서 판정 뒤집힘 없어 초기값 유지.
- before/after(BE): 8/12~8/31 avoid/reduce→accumulate(-15~-30, 상한 준수), 깊은 약세일·
  재탈환 확인 구간 불변, 비적격일 before=after(하위호환).
- ADR 후보? no

## (2026-09-14 10:00) [Pivot] band-aid → 원본 점수 추세 중복 근본 수정
- 이전 접근: 바닥 가점(상한 가점)으로 avoid→hold 완만화(band-aid).
- 전환 이유: codex 독립 리뷰(FAIL) + 사용자 비판 재검증 — 원본 점수가 "하락 추세"를 4중 벌점
  (minervini binary -20 + velocity -35 + supertrend -25 + risk 중복 -10 = -90). velocity는 SMA20
  기울기 지연으로 반등일에 역방향 벌점. 9/2는 SMA150 탈환에도 -80. 근본은 원본 점수.
- 새 접근(점진·측정):
  1. velocity 상태/이벤트 분리 — 종가가 SMA20 위면 하락 기울기 벌점 억제(lag 보정).
  2. risk에서 SMA50 아래/Supertrend 하락 중복 벌점 제거.
  3. minervini SMA50 아래 -20 고정 → 구조 조건(SMA150/200 탈환·정배열) 부분 반영 그라데이션.
  4. 단계별 평가세트+전체 테스트 측정, 필요시 action 밴드 재보정.
  5. 원본 개선 후 바닥 가점 존치/단순화 재평가.
- 리뷰 기록: docs/worklog/bottoming-gradient-codex-review.md

## (2026-09-14 11:20) [Bug] 원본 점수 추세 중복 카운팅 완화 (velocity lag + risk 중복)
- 증상: 하락 종목이 "이평 아래" 사실을 4중 벌점(minervini -20 + velocity -35 + supertrend -25
  + risk -10)받아 -80~-90. 9/2는 SMA150 탈환에도 -80. 하루 단위 -20~-90 급변동.
- 근원:
  - velocity: SMA20 기울기 지연으로 종가가 이미 SMA20 위인 반등일에 '하락 가속(-10)+
    하락 전환점(-15)'을 역방향으로 부과.
  - risk: SMA50 아래(-5)·Supertrend 하락(-5)을 재차 벌점 — minervini·supertrend가 이미 카운팅.
- 수정:
  - velocity.py: 종가>SMA20이면 하락 기울기 벌점·하락 전환점 억제(상태 vs 이벤트 분리).
  - risk.py: SMA50 아래/Supertrend 하락 중복 벌점 점수 제거(메타데이터·서사는 유지).
- 효과(BE): 9/2 -80→-35, 9/3 -62(avoid)→-22(reduce). avoid→hold 급점프가
  avoid/reduce→reduce→watch→hold 그라데이션으로. SMA20 아래 약세일(8/21,9/1)은 그대로.
- 검증: 신규 velocity 2 + risk 1 테스트, 전체 1351 passed, 회귀 0(밴드 재보정 불필요).
- 재발 방지: velocity는 '상태(기울기)'와 '이벤트(전환점)'를 분리, risk는 추세 벌점 미보유 원칙.
- 후속(미착수): minervini SMA50 아래 -20 binary → SMA150/200 탈환·정배열 그라데이션은 전 종목·
  전 밴드 파급이라 별도 과제(band 재보정 동반).
