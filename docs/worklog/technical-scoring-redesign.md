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

## (2026-07-16 17:05) [Decision] scoring redesign ADR 승격 및 구현 계획 작성
- 맥락: 사용자가 ADR 문서 생성과 implementation plan 전환을 요청함. 설계 문서의 ADR 후보 중 `total_score` 계약 확장과 technical verdict/playbook 책임 경계는 구현 범위에 직접 영향을 주는 아키텍처 결정임.
- 후보: A) 설계 문서 후보로만 유지 / B) 구현 후 ADR 작성 / C) 구현 계획 전에 ADR-0010으로 수락 기록
- 선택: C — 구현자가 `total_score`, `component_raw_total`, `adjusted_score`, `technical_verdict`, `playbook` 경계를 혼동하지 않도록 ADR에서 결정 이유와 결과를 먼저 고정한다.
- 기각: A(구현 중 계약 해석이 흔들릴 수 있음), B(구현 계획 단계에서 이미 결정 경계가 필요함).
- ADR 후보? yes

## (2026-07-16 18:57) [Bug] Deep Dive와 decision bundle의 technical verdict 연동 검증
- 증상: LLM technical summary 입력에 verdict/score history가 없고, decision bundle은 `total_score`만 사용해 `technical_verdict`가 있어도 반영하지 않음.
- 근원(root cause): 새 technical scoring 계약의 downstream 전달과 verdict 우선 평가가 구현되지 않음.
- 수정: TechnicalSummaryInput과 prompt에 고정 rule facts를 추가하고, deep dive 전달 및 verdict 기반 factor score 매핑을 적용함.
- 재발 방지 / 배운 것: `total_score` raw sum 계약은 유지하고, `adjusted_score`와 `technical_verdict`는 별도 필드로만 소비하도록 통합 테스트로 고정함.

## (2026-07-16 19:01) [Friction] Serena symbol extraction 비활성 상태
- 막힌 점: Task 7 review fix 중 Serena `get_symbols_overview`가 `Active languages: []`로 Python symbol extraction을 수행하지 못함.
- 임시 대응: 변경 범위를 리뷰 지적 파일로 제한하고 `rg`/`sed`로 필요한 위치만 확인한 뒤 `apply_patch`로 좁게 수정한다.
- 개선 아이디어 (스킬·훅·프롬프트): worktree 시작 시 Serena project/language activation 상태를 확인하는 preflight를 추가한다.

## (2026-07-16 19:18) [Bug] Scoring regression fixture의 cutoff 계산 누수 제거
- 증상: regression test가 fixture 전체에 indicator를 계산한 뒤 과거 날짜로 slice해 swing extrema 같은 미래 bar 기반 지표가 과거 verdict에 섞일 수 있음.
- 근원(root cause): fixture loader와 cutoff scorer의 책임이 섞여 raw OHLCV cutoff보다 indicator 계산이 먼저 실행됨.
- 수정: raw OHLCV를 먼저 cutoff 날짜까지 자른 뒤 `IndicatorCalculator`와 `TechnicalScorer`를 실행하도록 테스트 helper를 변경하고, PANW 2026-04-22/04-30의 entry eligibility를 명시적으로 고정함.
- 재발 방지 / 배운 것: 과거 날짜 regression은 production `score_history`와 같은 원칙으로 raw slice → indicator calculate → score 순서를 따라야 함.
