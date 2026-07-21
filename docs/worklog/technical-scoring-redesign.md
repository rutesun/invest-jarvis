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

## (2026-07-16 19:42) [Bug] LLM technical recommendation 재해석 경로 차단
- 증상: `technical_verdict=hold/watch`여도 LLM `TechnicalSummaryOutput.recommendation`이 `매수`를 반환하면 CLI와 integrated analysis 입력에서 rule verdict와 모순될 수 있음.
- 근원(root cause): prompt에는 재해석 금지를 지시했지만, 반환값을 rule verdict로 강제 보정하지 않았고 decision bundle도 LLM summary가 verdict summary를 덮을 수 있었음.
- 수정: verdict가 있으면 technical recommendation을 rule action 기반 tri-state label로 강제하고, Deep Dive에서도 방어적으로 재적용함. analyze decision은 verdict summary를 LLM summary로 교체하지 않고 adjusted score와 score history를 rule evidence로 남김.
- 재발 방지 / 배운 것: "LLM은 설명만" 계약은 prompt 문구만으로는 부족하며, downstream에 전달되는 structured field를 rule output으로 직접 고정해야 함.

## (2026-07-16 19:53) [Bug] PANW pullback add regression 계약 복구
- 증상: PANW 2026-04-30 regression이 설계 spec의 `action=add`, `entry_mode=pullback_add`, `confidence=high`와 달리 `watch`를 고정함.
- 근원(root cause): 4/30은 Supertrend 상승과 20일선 위 눌림 상태지만 component metadata에 pullback entry signal이 없어 Aggregator가 add 조건을 만족하지 못함.
- 수정: MarketContext 기반 contextual pullback add 조건을 추가해 과열/이탈이 아니고 20일선 위에서 20일 고점 대비 -2~-8% 눌림, 10일 수익률 양수, Supertrend 상승이면 `pullback_add`로 판정함. PANW 4/30 regression과 aggregator 단위 테스트를 spec 기대값으로 고정함.
- 재발 방지 / 배운 것: real regression fixture는 spec의 대표 사례와 정확히 일치해야 하며, 실제 결과가 다르면 test를 넓히기보다 rule 또는 spec을 함께 정렬해야 함.

## (2026-07-16 20:07) [Bug] Downtrend pullback add 차단
- 증상: 최종 리뷰에서 contextual pullback add 조건이 `is_downtrend`를 확인하지 않아 하락 추세의 초기 반등도 `add`로 열릴 수 있다고 지적됨.
- 근원(root cause): PANW 4/30 복구 과정에서 Supertrend 상승, 20일선 위, 20일 고점 대비 눌림, 10일 수익률 양수 조건만 보았고 하락 추세 가드를 별도로 두지 않음.
- 수정: `pullback_add` 판정과 contextual pullback helper 모두 `not context.is_downtrend`를 요구하도록 좁히고, 동일한 눌림 조건이라도 downtrend에서는 `watch`가 되는 회귀 테스트를 추가함.
- 재발 방지 / 배운 것: early trend 전환 사례(PANW)는 유지하되, downtrend에서는 buy/add를 만들지 않는 spec 가드를 별도 테스트로 고정해야 함.

## (2026-07-16 22:40) [Decision] Score history 기본/상세 출력 분리
- 맥락: 최근 점수 추이가 raw/adjusted/action/reason만 보여줘 점수 변화 원인과 신규 진입 가능 여부 변화를 한눈에 보기 어려움.
- 후보: A) 기존 한 줄 유지 / B) 항상 여러 줄 상세 출력 / C) 기본은 한 줄에 delta·driver·entry·caution을 압축하고 `--detail-history`에서 여러 줄로 확장
- 선택: C — 기본 출력의 스캔 속도를 유지하면서, 상세 모드에서는 reason/driver/entry/caution을 날짜별로 분리해 읽기 쉽게 만든다.
- 기각: A(점수 변화 원인 파악이 어려움), B(기본 CLI가 과하게 길어짐)
- ADR 후보? no

## (2026-07-16 22:52) [Bug] Score history 리뷰 지적 반영
- 증상: subagent 리뷰에서 `driver`가 전일 대비 변화 원인이 아니라 해당 날짜 절대 점수 상위 component라 `Δ` 원인처럼 오해될 수 있고, `avoid` 상단 reason이 반등 신호만 보여 판단과 반대로 읽히며, Minervini 7조건 중 5개만 출력된다고 지적됨.
- 근원(root cause): history point에 previous/current component delta가 없었고, Aggregator reason은 bullish signal을 action-supporting caution보다 먼저 쌓았으며, quick check component evidence는 일괄 5개로 제한됨.
- 수정: `change_drivers`를 전일 대비 component score 변화로 계산해 `변화`로 표시하고, risk action에서는 caution-derived reason을 먼저 배치하며, Minervini evidence는 7조건 전체를 출력하도록 변경함.
- 재발 방지 / 배운 것: score delta 근처의 라벨은 snapshot contributor가 아니라 실제 변화 원인을 나타내야 하며, Stage 2처럼 조건 개수가 계약인 component는 truncation 없이 검증 가능하게 보여줘야 함.

## (2026-07-16 22:58) [Bug] Score history 변화 tie 정렬 안정화
- 증상: BE compact/detail 리포트를 별도 프로세스로 생성하면 같은 날짜의 `변화` 상위 component가 다르게 보일 수 있음.
- 근원(root cause): previous/current component 이름 집합을 `set`으로 만든 뒤 절대 delta만으로 정렬해, 동점일 때 Python hash/order에 따라 top-N 선택이 달라짐.
- 수정: 변화 정렬을 `abs(delta) desc, component name asc`로 고정하고, top-N 밖의 component delta는 `기타`로 합산해 adjusted delta 설명이 덜 끊기게 함.
- 재발 방지 / 배운 것: 사용자 출력의 top-N은 동점 정렬 기준까지 명시해야 하며, 생략된 항목이 delta 해석을 바꿀 때는 `기타`로 합산해 보여준다.

## (2026-07-16 23:06) [Bug] Negative action reason 우선순위 보정
- 증상: BE score history에서 `avoid` action인데 top reason이 `지지 confluence`로 표시되어 매수 쪽 근거처럼 읽힘.
- 근원(root cause): action-supporting caution이 없는 `reduce/avoid`에서는 기존 bullish/support reason 목록이 그대로 1순위로 유지됨.
- 수정: 음수 adjusted score로 `reduce/avoid`가 선택된 경우 risk fallback reason을 bullish/support reason보다 먼저 배치하고, `지지 confluence`가 있어도 `avoid`의 첫 reason이 risk 우위 설명이 되는 회귀 테스트를 추가함.
- 재발 방지 / 배운 것: action label과 첫 reason은 같은 방향을 가리켜야 하며, 반대 방향 신호는 보조 정보로만 뒤에 남겨야 함.

## (2026-07-20 14:39) [Decision] 모든 기술 분석 소비 경로를 3년 계약으로 통일
- 맥락: `check`는 1년, `analyze`와 `brief`는 3년 OHLCV를 사용해 같은 `TechnicalScorer`라도 누적 지표와 최종 score/verdict가 달라질 수 있음. 사용자는 어떤 파이프라인에서도 동일한 기술 점수가 나와야 한다고 확정함.
- 후보: A) 파이프라인별 기간 유지 / B) check와 analyze만 통일 / C) `TechnicalAnalysisTool`의 canonical period를 3년으로 정해 모든 소비 경로가 사용
- 선택: C — 단일 source of truth로 미래 drift를 막고 component/raw/adjusted/verdict/history 계약을 동일하게 만든다.
- 기각: A(동일성 요구 미충족), B(다른 소비 경로에 점수 차이가 남음)
- ADR 후보? no

## (2026-07-20 14:56) [Decision] Macro와 다중 ticker 명령 책임 확정
- 맥락: `report ticker`가 다중 종목 check와 역할이 겹치고 사용되지 않는 LLM 의존을 가지며, Macro 표시와 LLM 사용 경계가 불명확함.
- 후보: A) 모든 명령에 Macro / B) analyze에만 Macro / C) analyze·brief에 표시하고 analyze 종합 LLM 해설에 전달
- 선택: C — check는 다중 ticker 기술 분석에 집중하고, analyze는 Macro를 종합 해설에 사용하며, brief는 기존 포트폴리오 Macro 표시를 유지한다.
- 기각: A(check의 가벼운 역할과 충돌), B(brief의 기존 시장 요약을 제거할 이유가 없음)
- ADR 후보? no

## (2026-07-20 15:06) [Decision] report ticker 삭제와 장기 이동평균 slope 표기
- 맥락: 사용자가 중복된 `report ticker` 삭제를 확정하고, 주요 지표에 SMA 100·200과 방향 아이콘을 항상 표시하도록 요청함. 코드 검증 결과 최종 종합 LLM에는 news와 Macro가 함께 전달되지 않는 공백도 확인됨.
- 후보: A) report ticker alias 유지 / B) 완전 삭제, slope 단순 증감 / C) 완전 삭제, 21거래일 변화율에 보합 band 적용
- 선택: C — 다중 ticker check가 기능을 대체하고, 기존 장기 추세 판정과 같은 21거래일 기준에 ±0.5% 보합 band를 적용한다. 최종 LLM에는 모든 분석 소스와 고정 decision을 전달한다.
- 기각: A(명령 중복 지속), B(미세 노이즈도 상승·하락으로 과대 표시)
- ADR 후보? no

## (2026-07-21 11:33) [Decision] Playbook 이후 시나리오 재생성과 two-stage prompt 경계
- 맥락: 실행계획 독립 리뷰에서 Playbook veto가 summary만 바꿔 기본 scenario에 이전 action이 남는 문제와 raw news가 보호되지 않은 선행 LLM prompt를 통과하는 경로가 확인됨.
- 후보: A) 최종 explanation prompt만 보호 / B) veto 후 summary만 교체하고 scenario에 주의 문구 추가 / C) veto 후 scenario를 재생성하고 news 분석·최종 explanation 모두 delimiter-safe untrusted JSON 경계 적용
- 선택: C — rule action, CLI scenario, 최종 LLM 입력을 같은 decision으로 고정하고 외부 문자열이 어느 LLM 단계에서도 prompt 구조를 닫지 못하게 한다.
- 기각: A(news 분석 결과가 rule decision에 들어가기 전 경로가 남음), B(서로 다른 action source를 유지해 사용자 출력이 모순될 수 있음)
- ADR 후보? no
