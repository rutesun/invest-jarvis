# Worklog — technical-scoring-redesign

- **Branch**: main
- **Started**: 2026-07-16
- **Status**: in-progress
- **Links**: [설계 스펙](../superpowers/specs/2026-07-16-technical-scoring-redesign-design.md)

---

## (2026-07-16 16:40) [Decision] 기술 점수 개선 방향 확정
- 맥락: 삼성전자, BE, PANW의 날짜별 기술 점수와 raw OHLCV 재검산을 비교한 결과, 기존 점수는 추세/리스크 계기판으로는 유효하지만 신규 매수·보유·축소 행동을 한 숫자로 표현해 고점 추격 오판이 생길 수 있음.
- 후보: A) 별도 raw OHLCV score 추가 / B) 기존 component 점수 산식 전면 교체 / C) MarketContext + ScoreAggregator + technical-only verdict 추가
- 선택: C — raw score 중복을 만들지 않고, OHLCV는 context 상태로만 제공한다. 기존 component 점수는 유지하되 context cap, overextension gate, risk override를 적용하고, 최종 판단은 technical-only hint로 제한한다.
- 기각: A(raw OHLCV가 별도 점수 체계가 되어 중복·혼선 발생), B(기존 점수 회귀 비교가 어려워지고 downstream 계약 변경 위험이 큼).
- ADR 후보? yes

## (2026-07-16 16:40) [Decision] subagent 설계 리뷰 반영
- 맥락: 사용자 요청으로 subagent read-only 리뷰를 실행. 리뷰 결과 설계 방향은 적합하지만 `total_score` 계약, playbook 책임 경계, 문자열 signal 파싱 위험이 주요 리스크로 지적됨.
- 후보: A) 원안 유지 / B) total_score 즉시 재정의 / C) 단계적 계약 확장
- 선택: C — `component_raw_total`로 기존 단순합을 보존하고, `adjusted_score`와 `technical_verdict`를 추가한다. `technical_verdict`는 가격·거래량 기준의 technical-only hint로 한정하고, playbook final verdict와 구분한다. Aggregator는 문자열 signal이 아니라 구조화 metadata를 사용한다.
- 기각: A(리뷰 지적을 반영하지 않아 downstream 혼선 가능), B(analyze_decision·tests·playbook 연동 파급이 커서 위험).
- ADR 후보? yes

## (2026-07-16 16:56) [Decision] ticker 분석 reason과 5거래일 점수 추이 추가
- 맥락: 사용자가 ticker 분석에서 판단 이유와 최근 5일 정도의 점수 추이를 함께 보고 싶다고 요청함. 이는 점수의 신뢰도를 높이고, 현재 점수가 개선 중인지 악화 중인지 구분하는 데 필요함.
- 후보: A) component evidence만 그대로 노출 / B) 최종 verdict reason만 추가 / C) 최종 verdict reason + 최근 5거래일 score history 추가
- 선택: C — `technical_verdict.reasons`, `cautions`, `invalidation_level`, `score_trend_summary`를 추가하고, 최근 5거래일 `score_history`를 해당 날짜까지의 데이터만 사용해 계산한다.
- 기각: A(정보량은 많지만 행동 의미가 흐려짐), B(오늘 판단 이유는 알 수 있지만 점수 추세를 볼 수 없음).
- ADR 후보? no
