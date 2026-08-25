# Change Records Index

> PR/머지 단위 변경 기록 목록. 최신순. 현재 기능 상태는 `docs/FEATURES.md` 기준.

| Date | Type | Status | 변경 | PR | Record |
|------|------|--------|------|----|--------|
| 2026-08-25 | feat | Draft | 턴어라운드 신호 (발굴·해석 보조) — 4마커 점수화 순수함수 + check/screen(`--turnaround`)/brief 배선. 예측 알파 아님(나이브 기준선 미통과), 후보 표면화+마커+check확인+손절선 제공, 판단은 사용자 | #{PR 번호} | [turnaround-signal.md](turnaround-signal.md) |
| 2026-08-06 | feat | Draft | 지표값 기반 change_drivers + 당일 이벤트 노출 — score history 서술을 점수 델타에서 지표값(cRSI·SMA20 기울기) 변화로 재작성, 일회성 이벤트 롤오프 유령 신호 억제, `이벤트:` 세그먼트 추가 (스코어링 로직 불변) | #54 | [change-drivers-indicator-based.md](change-drivers-indicator-based.md) |
| 2026-07-27 | fix | Draft | Daily Report OpenAI strict schema 회귀 수정 + Notion 업로드 버그 — ThemeMapping dict→groups 배열, strict 계약 테스트, 카테고리 alias 6종, 해시태그 무한 루프·upload 날짜 필터·중복 방지 | #53 | [daily-report-strict-schema-fix.md](daily-report-strict-schema-fix.md) |
| 2026-07-24 | feat | Draft | LLM 모델 설정 일원화 — config.yaml llm 섹션 단일 소스, GPT-5.6 전환(terra/luna/sol), --provider·STOCK_REPORT_* env 삭제, StageLLMConfig 통합 | #52 | [llm-model-config-unification.md](llm-model-config-unification.md) |
| 2026-07-22 | feat | Merged | Unified Technical Analysis Contract — check/analyze/brief 공통 3년 계약, 다중 티커 check, 설명 전용 종합 해설(ActionableSignal 제거), report ticker 제거 | #51 | [unified-technical-analysis-contract.md](unified-technical-analysis-contract.md) |
| 2026-07-16 | feat | Draft | Technical Scoring Redesign — raw 합계와 adjusted verdict 분리 | - | [technical-scoring-redesign.md](technical-scoring-redesign.md) |
| 2026-07-16 | feat | Draft | jarvis brief — 일일 포트 액션 종합 CLI (+ PortfolioPipeline 제거, exit_rules SMA 버그픽스, SMA_LONG 전환국면 강등, KRX 영숫자 코드 인식) | #48 | [jarvis-brief.md](jarvis-brief.md) |
| 2026-06-17 | feat | Merged | Stock Report V2 Phase 2 — PDF ingest + semantic search | #41 | [stock-report-v2-pdf-ingest.md](stock-report-v2-pdf-ingest.md) |
| 2026-06-12 | feat | Merged | Playbook 엔진 (5대 대가 규칙) + analyze 통합 | #40 | [playbook-engine.md](playbook-engine.md) |
| 2026-06-04 | feat | Merged | Stock Report V2 합성 엔진 (map-reduce + 이벤트 안전망 + Google grounding) | #33–#39 | [stock-report-v2-synthesis-engine.md](stock-report-v2-synthesis-engine.md) |
| 2026-05-28 | feat | In Progress | Stock Report V2 Typed Evidence + QA Warnings | - | [stock-report-v2-typed-evidence.md](stock-report-v2-typed-evidence.md) |
| 2026-05-07 | feat | In Progress | Structure Zone Reporting 개선 | - | [structure-zone-reporting.md](structure-zone-reporting.md) |
| 2026-05-06 | refactor | In Progress | Map Stage 클러스터링 개선 | - | [map-stage-clustering-improvements.md](map-stage-clustering-improvements.md) |
| 2026-04-29 | feat | In Progress | Daily Report 인과관계 추론 | - | [daily-report-causal-reasoning.md](daily-report-causal-reasoning.md) |
| 2026-04-29 | feat | Draft | Disclosure Intelligence (공시 원문 파싱 + 정량 시뮬레이션) | #25 | [disclosure-intelligence.md](disclosure-intelligence.md) |
