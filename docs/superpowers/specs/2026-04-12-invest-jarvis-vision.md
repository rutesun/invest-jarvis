# invest-jarvis 비전 설계서

**작성일**: 2026-04-11  
**배경**: telegram 프로젝트(Codex/ANTIGRAVITY)를 Claude Code 기반으로 완전 대체  
**범위**: 3개 핵심 기능 영역의 목표 상태 정의

---

## 전체 구조

```
Telegram 채널 수집
        ↓
  CSV 저장 (날짜별)     외부 데이터 (뉴스, 공시)
  grep 기반 검색              ↓
        ↓         ──────────────────
   ┌────────────────────────────────┐
   │         분석 파이프라인          │
   │  Daily Report │ Portfolio │ Analysis │
   └────────────────────────────────┘
        ↓
   리포트 출력 (CLI + Notion)
```

> **RAG 미사용 결정**: Telegram 데이터는 CSV로 저장하고, 종목별 검색은 ticker/회사명 grep으로 충분. 의미 기반 검색이 필요한 케이스가 현재 없음.

---

## 1. Daily Report

→ **상세 설계**: [Telegram 수집 파이프라인 설계서](2026-04-11-telegram-collection-design.md) → [Daily Report 설계서](2026-04-11-daily-report-design.md)

매일 아침, 시장을 이해하기 위해 알아야 할 것들을 한 번에 정리한 리포트.
- 시장 전반 (매크로 + 주목 뉴스 Top 5 + 시장 내러티브)
- 테마별 브리핑 (동적 테마 감지 + Smart Money 시그널)
- 특징주 (수급 필터링 + 텔레그램 사전 언급 여부)

---

## 2. Portfolio 점검

→ **상세 설계**: [Portfolio 점검 설계서](2026-04-11-portfolio-check-design.md)

내 보유 종목 각각에 대해, 지금 알아야 할 것들을 종합적으로 정리.
- 이벤트 랭킹 (공시 > 뉴스 > 텔레그램 가중치 기반)
- 차트 스코어(0-60) + 뉴스·공시 스코어(0-40) = 종합 100점
- 위험 종목 우선 표시 + 포트폴리오 레벨 인사이트

---

## 3. Analysis 개선

→ **상세 설계**: [Analysis 개선 설계서](2026-04-11-analysis-enhancement-design.md)

`jarvis analyze` 커맨드에 공시 분석 + 수급 분석을 추가해 멀티팩터 딥다이브로 격상.
- SEC EDGAR / DART 공시 (3개월, 키워드 필터링)
- 수급 동향 (외인/기관 순매수, 한국주식)
- 동종업계 비교 + 컨센서스 + 이벤트 캘린더

---

## 이식 우선순위 (합의된 순서)

| 단계 | 기능 | 상태 |
|------|------|------|
| 1-a | 차트 렌더링 (mplfinance) | 🔲 |
| 1-b | 수급 분석 (외인/기관 플로우) | 🔲 |
| 2-a | **공시 분석 (SEC/DART)** | 🔲 — Analysis #3 |
| 2-b | **포트폴리오 브리프 고도화** | 🔲 — Portfolio #2 |
| 3 | **Telegram 수집** | 🔲 — [Telegram 수집 파이프라인 설계서](2026-04-11-telegram-collection-design.md) |
| 4 | **Daily Report 전체** | 🔲 — [Daily Report 설계서](2026-04-11-daily-report-design.md), Telegram 수집 완성 후 |
| 부가 | Notion 발행 | 🔲 |

---

## 결정된 사항

| 항목 | 결정 |
|------|------|
| Telegram 채널 관리 | `config.yaml` (id + include/exclude regex 지원, telegram 프로젝트 방식 계승) |
| 테마 목록 | 동적 — Naver 당일 상위 테마 + LLM 뉴스/Telegram에서 추가 감지 |
| 리포트 발행 주기 | 수동 실행 (`jarvis daily-report`) |
| 공시 조회 범위 | 최근 3개월, 키워드 필터링 (계약, 내부자 매도, 사업보고서) |
| RAG | 미사용 — CSV grep으로 충분 |
