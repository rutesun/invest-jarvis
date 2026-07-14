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
