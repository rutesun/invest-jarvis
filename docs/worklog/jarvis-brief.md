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
