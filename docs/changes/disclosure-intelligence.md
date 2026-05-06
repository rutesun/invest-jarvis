# Change Record: 공시 원문 파싱 + 정량 시뮬레이션 (Disclosure Intelligence)

**Status**: Draft
**Created**: 2026-04-29
**PRs**: -
**Tasks**: ROADMAP Task 1 + Task 6

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`jarvis analyze AAPL` 실행 시 공시 **제목만** 출력됨.
계약 금액, 가이던스, 희석 비율 같은 투자 판단 핵심 숫자가 없음.
현재는 ChatGPT에 10-K 원문 수동 복붙해서 분석. 자동화 필요.

## What

1. SEC/DART 공시 원문에서 **19개 재무 숫자** 자동 추출 (XBRL)
2. **텍스트 인사이트** — US: Guidance + Risk, KR: 제품/수주/설비/R&D (LLM 구조화 추출)
3. **4가지 공시 유형별 정량 시뮬레이션** — 실적발표, 유상증자, 전환사채, 공급계약
4. CLI에 재무 테이블 + 임팩트 패널 + 사업 인사이트 출력
5. Golden Set 10종목 검증 (recall 80% 목표)

## Design

**하이브리드**: 숫자는 규칙 (XBRL/정규식), 해석은 LLM. Confidence 태깅 (XBRL=high, regex=medium, LLM=low).

```
DisclosureTool (기존, 메타데이터) → filing URLs
SECFilingParser / DARTFilingParser (신규) → FilingFacts
ImpactCalculator (신규) → FilingImpact (원본 facts 참조 보존)
```

각 컴포넌트 독립적 — DeepDive 외 파이프라인에서도 재사용 가능.

**SEC**: companyfacts API (숫자) + edgartools markdown (텍스트). 검증 완료 (AAPL, NVDA, JPM).
**DART**: fnlttSinglAcntAll API (숫자) + document.xml (텍스트). 검증 완료 (삼성전자).
**캐시**: JSON 파일 (`data/cache/filings/`). 기존 패턴 일치.

## Constraints

- edgartools 외부 의존성 추가
- LLM 비용: 종목당 ~$0.02-0.05 (Haiku)
- SEC API rate limit 10 req/sec
- filing_parser 미설정 시 기존 동작 유지 (하위 호환)

## Checklist

- [ ] 데이터 모델 + XBRL concept mapping
- [ ] SECFilingParser + DARTFilingParser
- [ ] ImpactCalculator (4가지 유형)
- [ ] DeepDivePipeline 통합 + IntegratedAnalysisInput 확장
- [ ] CLI 출력 (Rich Table + Panel)
- [ ] 단위 테스트 + Golden Set 검증
- [ ] `docs/FEATURES.md` 업데이트

## Related

- 상세 설계: `docs/superpowers/specs/2026-04-29-disclosure-intelligence-design.md`
- 기존 설계: `~/.gstack/projects/rutesun-invest-jarvis/user-main-design-20260423-174653.md`
- ADR: 없음 (구현 시 작성)
