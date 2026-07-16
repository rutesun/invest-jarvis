# Worklog — jarvis-brief

- **Branch**: feature/jarvis-brief
- **Started**: 2026-07-14
- **Status**: in-progress
- **Links**: [설계 스펙](../superpowers/specs/2026-07-14-jarvis-brief-design.md)

---

## (2026-07-14 16:25) [Decision] jarvis brief 설계 확정
- 맥락: 2026-07-02 요구사항 인터뷰에서 1차 타깃으로 확정된 "일일 포트 액션 종합" 기능의 구현 구조를 정해야 했다. 보유 SSoT(KIS 잔고 사용 불가), 파이프라인 위치, LLM 사용 수준이 핵심 갈림길.
- 후보: A) 신규 BriefPipeline (기존 부품 조립) / B) PortfolioPipeline 확장 / C) TickerReportPipeline 확장
- 선택: A — 레이어드 아키텍처 준수, 기존 명령 회귀 위험 0, 무거운 로직은 전부 기존 부품(evaluate_exit·gate·TechnicalAnalysisTool·MacroTool) 재사용. 부속 결정: playbook.yaml에 watchlist 섹션 추가(SSoT 단일 파일), 규칙이 액션·순위·근거를 결정적으로 확정하고 LLM은 배치 1콜로 슬롯 문장화만(실패 시 규칙 원문 fallback), 전 종목 풀 평가(사전 필터 탈락 없음), 종목별 출력은 구조화 불렛.
- 기각: B(KIS 실시간 잔고 전제인데 계좌 잔고가 없어 SSoT 전제 충돌 — YAML 분기를 심으면 상반된 전제 두 개 공존), C(관찰 리포트 목적이라 보유·액션·랭킹 개념 전무 — 확장하면 사실상 새 기능을 기존 파일에 욱여넣는 셈). 별도 결정: PortfolioPipeline은 존재 이유 소멸로 제거(provider의 get_balance()는 보존), TickerReportPipeline은 유지.
- ADR 후보? yes — "보유 SSoT를 KIS 잔고가 아닌 로컬 YAML로 확정"은 이후 2차(피드백 루프) DB 도입 판단에도 영향.

## (2026-07-14 16:40) [Decision] Codex 외부 설계 리뷰 반영 (스펙 v1 수정)
- 맥락: 사용자 요청으로 Codex CLI(read-only)로 목표-설계 적합성 리뷰 실행. 판정 "조건부 적합" + 고심각도 3건. 수용 전 전 건을 실제 코드로 검증함.
- 후보: 리뷰 지적 전부 수용 / 검증 후 선별 수용 / 반려
- 선택: 검증 후 선별 수용 — 고심각도 3건 전부 코드로 사실 확인되어 수용: ①exit_rules(`SMA20`)와 indicators(`SMA_20`) 컬럼 계약 불일치로 SMA 매도신호·trailing_stop이 실경로에서 침묵 누락(기존 analyze 버그, 단위테스트 자체 픽스처가 은폐 — test_exit_rules.py:29) → 선행 수정 + 실경로 회귀 테스트로 스펙에 명시. ②evaluate_exit 직접 호출 → PlaybookEngine.evaluate() 단일 진입으로 수정(RS·매집 조립이 엔진 내부). ③임박 기준 Stage2 5/7 → 필수 게이트 4중 3 충족(checklist 기반)으로 재정의. 중간 심각도: 랭킹을 버킷+동버킷 가산으로 변경(축소+스탑근접>청산 역전 방지), 로더 계약 강화, 부분 실패 픽스처 테스트 추가. 공시 슬롯 포함(사용자 확정, DisclosureTool 재사용).
- 기각: 호출 횟수 budget 검증(개인용 CLI에 과함, YAGNI), PortfolioPipeline 제거 연기 제안(사용자가 제거 확정 — 별도 커밋으로 회귀 통제).
- ADR 후보? no (스펙 문서 D9·D10에 기록됨). 단 SMA 컬럼 버그는 수정 검증 후 [Bug] 엔트리 별도 기록 예정.

## (2026-07-14 18:13) [Bug] exit_rules SMA 컬럼 계약 불일치 수정
- 증상: analyze 보유 종목 매도판정에서 SMA_SHORT/SMA_LONG 신호·trailing_stop이 발화하지 않음
- 근원(root cause): exit_rules는 "SMA20" 컬럼을 찾는데 IndicatorCalculator는 "SMA_20"을 생성. 단위테스트가 자체 픽스처("SMA20")로 계약 불일치를 은폐
- 수정: _get_ma가 양쪽 컬럼명을 순서대로 조회. 실경로 컬럼명 회귀 테스트 추가
- 재발 방지 / 배운 것: 부품 간 DataFrame 컬럼 계약은 생산자 실제 출력으로 테스트해야 함 (CLAUDE.md 골든 테스트 원칙의 단위테스트 버전)

## (2026-07-14 18:58) [Decision] Codex 구현 + Claude 리뷰 워크플로로 brief 전 태스크 완료
- 맥락: 사용자 지시 "코덱스로 구현하고 너가 리뷰해". 플랜 9개 태스크를 3배치로 나눠 Codex(codex exec, workspace-write)가 코드+테스트 작성, Claude가 배치마다 리뷰·커밋.
- 마찰: Codex의 workspace-write 샌드박스가 (1) 워크트리 실제 git 디렉터리(cwd 바깥)와 (2) 전역 uv 캐시(~/.cache/uv)에 쓰기 불가 → Codex가 커밋도 테스트도 못 함. 대응: git·pytest는 리뷰어(Claude)가 전담, Codex는 코드 편집만.
- 리뷰 발견: Task 4 테스트 mock이 결함(플랜 자체 결함) — `prompt | llm.with_structured_output(X)`는 실제 ChatPromptTemplate.__or__를 타므로 mock의 __ror__가 무시됨. 기존 analyzer 테스트 패턴(ChatPromptTemplate patch + mock_prompt.__or__)으로 교체해 통과. Codex가 이 우려를 먼저 플래그했고 리뷰에서 확정·수정.
- 결과: 전체 1144 passed / 1 failed(test_sec_fetcher_uses_cache — 네트워크 의존 기존 실패, 무관). `jarvis brief --help` 등록 확인. 커밋 8개(fix 1, feat 5, docs 2).
- ADR 후보? no

## (2026-07-15 18:00) [Decision] SMA_LONG 전환 시도 국면 강등 (실사용 피드백 반영)
- 맥락: 실제 포트폴리오로 brief 첫 실행 후 사용자 피드백 — PGY·TEM은 "200일선 아래지만 150일선을 회복했고 150일선 기울기가 양전환해 선취매한 전환(턴어라운드) 포지션"인데 SMA_LONG 강신호 하나로 "청산" 오분류. 현재 규칙(종가<SMA150 OR 종가<SMA200 → strong)이 와인스타인 원전보다 거침 — Stage 기준선은 30주선(SMA150)이고, 150선 회복+상승은 Stage2 전환 시도 국면.
- 후보: A) 규칙 정교화(종가>SMA150 && SMA150 상승이면 SMA200 이탈을 strong→weak 강등) / B) holdings에 strategy 태그(turnaround별 exit 기준 분기) / C) 무변경(해석으로 커버)
- 선택: A — 특정 종목 예외처리가 아닌 원전에 충실한 일반 규칙. 상승 판정은 21거래일 전 대비(market_regime의 SMA200 상승 판정과 동일 창). 결과: PGY 청산→비중축소(분산 중신호 잔존), TEM 청산→보유(약신호). SMA150 이탈은 여전히 강신호 유지.
- 기각: B(스키마·분기 복잡도, v1 단순성 훼손 — 2차 피드백 루프에서 재검토), C(매일 틀린 라벨 반복 → "근거 신뢰" 수용 기준 훼손).
- ADR 후보? no (스펙 D11에 기록)

## (2026-07-16) [Pivot] SMA_LONG 강등 조건: 기울기 요구 → 가격 회복만
- 이전 접근: 종가>SMA150 && SMA150 상승(21거래일 대비)이면 강등.
- 전환 이유: 실데이터 검증에서 PGY(16.13 vs 21일전 17.14)·TEM(55.50 vs 57.91) 모두 SMA150이 5/10/15/21일 어느 창으로도 하락 중 — 사용자가 본 "기울기 양전환"이 yfinance 일봉 SMA150과 불일치. 기울기 조건 유지 시 페인이 해소되지 않음을 데이터로 확인 후 사용자에게 3안(기울기 유지/가격만/평탄화) 제시, 사용자가 "가격 회복만" 선택.
- 새 접근: 종가>SMA150이면 SMA200 이탈을 weak로 강등. 기울기는 "SMA150 상승"/"SMA150 하락 중(미확인)"으로 근거에 병기해 확인 여부를 투명하게 노출. SMA150 이탈은 여전히 strong.

## (2026-07-16 10:45) [Bug] KRX 신형 영숫자 코드(0167A0) 한국 종목 미인식
- 증상: 실보유 ETF 0167A0(SOL AI반도체TOP2플러스)이 brief에서 "데이터 조회 실패" — yfinance로 라우팅되어 404.
- 근원(root cause): is_korean_ticker가 `^\d{6}$`(숫자 6자리)만 한국 코드로 인정. KRX 신형 단축코드는 영문 혼용(숫자 시작 6자리 영숫자)인데 미인식 → US 경로(yfinance)로 오라우팅.
- 수정: 패턴을 `^\d[0-9A-Z]{5}$`(IGNORECASE)로 확장 — 숫자 시작 조건이 미국 티커(문자 시작) 오탐을 방지. extract_kr_code는 대문자 정규화 추가. KIS 실경로로 0167A0 시세 조회 검증(75행).
- 재발 방지 / 배운 것: 시장 코드 체계는 변한다(KRX 영숫자 도입) — 판별 함수는 "현재 데이터의 모양"이 아니라 "코드 체계 규칙"을 기준으로 작성. is_korean_ticker는 deep_dive·flow·screener·brief가 공유하는 경계 함수라 이 수정으로 전 기능이 신형 코드를 지원.
