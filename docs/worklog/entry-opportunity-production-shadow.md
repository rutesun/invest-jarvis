# Worklog — entry-opportunity-production-shadow

- **Branch**: feature/scorecard-strategy-position-separation
- **Started**: 2026-10-19
- **Status**: 구현·검증 완료 (미커밋)
- **Links**: [구현 계획](../superpowers/plans/2026-10-19-entry-opportunity-production-shadow.md)

---

## (2026-10-19 18:16) [Decision] Production 판정과 Shadow 연구 기록 분리

- 맥락: 최신 구현 지시는 미검증 WATCH/failure 규칙을 실제 신규 진입 gate에 넣지 않고 제품을 연결하도록 요구한다.
- 후보: Strategy DB 재도입 / 파이프라인 외곽 JSONL 연구 기록 / 기록 없음
- 선택: 기존 20봉·+5%·시장 gate 및 explicit failure를 유지하고, 독립 Shadow 진단을 JSONL로 기록한다. Strategy는 이 기록을 읽지 않는다.
- 기각: Strategy DB 재도입(기존 책임 분리와 충돌), 기록 없음(후속 분석 요구 미충족)
- ADR 후보? no

## (2026-10-19 18:27) [Bug] 최초 확정 종료와 동일일 exit 우선 복원

- 증상: entry보다 배열상 앞에 있는 동일일 exit를 놓치고, 만료 후 늦은 exit가 최초 만료 원인을 바꿀 수 있었다.
- 근원(root cause): signal 배열상의 위치만으로 invalidator를 선택하고 invalidator 전체를 age보다 먼저 검사했다.
- 수정: source 날짜 이상인 명시적 invalidator와 age 초과 session 중 최초 FINAL 사건을 날짜·exit 우선순위로 재구성한다. source별 terminal 날짜/finality를 반환한다.
- 재발 방지 / 배운 것: root focused 154 passed 및 독립 spec/quality PASS. 원래 지지선은 매일 바뀌는 resolved evidence 값 대신 observation 시작일 차트에서 복원한다. 기존 Signal·Score·Planner는 변경하지 않았다.

## (2026-10-19 18:49) [Decision] 제품 적용 검증을 완료하고 연구 승격은 분리

- 맥락: 세 Task 구현 후 전체 1,928 passed, 실제 5개 ticker·60봉 prefix의 71개 전환 및 CLI·JSONL을 확인했고, xhigh 최종 독립 리뷰가 READY(Spec/Quality PASS, Critical·Important·Minor 각 0건)를 반환했다.
- 후보: 제품 구현 마감 / 추가 parameter 연구 / 즉시 git integration
- 선택: 제품 구현·검증·문서화를 완료한다. 기존 운영 gate는 보존하고 독립 Shadow의 미검증 수치는 가설로 유지한다. `work-status` 스냅샷도 완료 상태로 갱신했다.
- 기각: 추가 연구(이번 구현 지시 범위 밖), commit/push/merge(별도 승인 없음)
- ADR 후보? no

## (2026-10-21 22:43) [Decision] 돌파 기준선 -1 ATR에서 진입 허가 취소

- 맥락: ALAB의 과거 돌파 기회가 큰 하락 후에도 기존 상단 +5% 조건을 통과해 ALLOW로 남았다. 사용자가 돌파 기준선에서 source 당시 ATR 1배 하락 시 허가 취소를 확정했다.
- 후보: 다음 거래일 시가 기준 / Signal 종가 기준 / 원래 돌파 기준선 기준
- 선택: TREND_BREAKOUT_ENTRY의 원래 돌파 기준선 - source ATR 1배 이하에서 INVALIDATED. FINAL 실패는 해당 source에서 유지하고 장중은 PROVISIONAL로 재평가한다. 새 Signal은 별도로 평가한다.
- 기각: 다음 시가·Signal 종가(사용자가 돌파 기준선을 선택), 실제 보유 매도 연결(진입 기회와 책임이 다름)
- ADR 후보? no

## (2026-10-21 22:52) [Bug] 돌파 실패 후 남아 있던 신규 진입 허가 취소

- 증상: 원래 돌파선보다 크게 하락한 차트도 상단 +5% 조건만 통과하여 ALLOW로 남았다.
- 근원(root cause): Production 기회 gate에 source 돌파선·ATR을 사용하는 하단 가격 실패 조건이 없었다.
- 수정: TREND_BREAKOUT_ENTRY에 고정 돌파선 − source ATR(14) × 1.0 이하 종가를 INVALIDATED로 연결했다. 명시 exit·가격 failure·만료 순서를 보존하고, adapter의 대표 기회와 Observation source 모두 같은 feature로 판정한다. 가격 failure는 가짜 Signal 없이 종료 날짜/finality와 실측 evidence를 반환한다.
- 재발 방지 / 배운 것: RED 9 failed/1 passed에서 focused 125 passed로 검증했다. 1차 전체 2,155 passed/15 deselected, 기존 warning2이며 Ruff·format·diff 검사를 통과했다. controller는 저장 ALAB에서 돌파선377.8699951171875·ATR22.97301577054907·취소선354.89697934663843, 최초 FINAL 취소일10/8(close347.04998779296875), 양 profile 및 Observation/Shadow ON/OFF 판정 일치를 확인했다. frozen 연구 결과·Signal ID·보유 매도 규칙은 보존했다.

## (2026-10-21 22:55) [Bug] 가격 failure의 Observation 종료 사유 보존

- 증상: 독립 리뷰에서 가격 failure가 Observation source context에 ENTRY_EXPIRED로 전달되는 문제를 확인했다.
- 근원(root cause): 기존 코드가 invalidated_by 없는 terminal을 모두 만료로 간주했다. 새 가격 failure는 가짜 Signal을 만들지 않아 invalidated_by가 없다.
- 수정: adapter와 연구용 source context 모두 명시 exit는 원래 Signal code, 나머지 terminal은 opportunity의 첫 evidence reason을 전달한다.
- 재발 방지 / 배운 것: adapter integration에 terminal_reason 검증을 추가해 ENTRY_EXPIRED != BREAKOUT_ATR_INVALIDATED 실패를 확인하고 수정 후 1 passed로 검증했다. 연구용 _find_terminal_reclaim의 동일 경계에도 회귀 검증을 연결했다. 수정 후 focused 125 passed(74.76s), 최종 전체 2,158 passed/15 deselected(184.09s), 기존 warning2를 확인했다. 변경 Python 6개 Ruff·format과 diff 검사를 통과했다.
