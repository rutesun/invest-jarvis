# Change Record: Disclosure Intelligence (공시 원문 파싱 + 정량 시뮬레이션)

**Status**: Draft
**Date**: 2026-04-29
**PRs**: #25 (feature/disclosure-intelligence)
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`jarvis analyze AAPL` 실행 시 공시 **제목만** 출력된다. 계약 금액, 가이던스, 희석 비율 같은
투자 판단 핵심 숫자가 없다. 현재는 ChatGPT에 10-K 원문을 수동으로 붙여넣고 분석하는 구조다.
SEC/DART 공시는 XBRL로 구조화된 데이터를 공개하고 있어 자동화의 선행 조건이 갖춰져 있다.

## What

1. **하이브리드 추출 전략**: 숫자는 규칙 기반(XBRL + 정규식), 해석은 LLM. XBRL로 추출한
   숫자는 `confidence=high`, regex는 `medium`, LLM 구조화 추출은 `low`로 태깅한다.
   숫자와 해석을 같은 LLM 호출에 묶으면 숫자 오류가 해석 품질에 끌려가는 문제가 있어서 분리했다.

2. **파서 레이어 분리 (`SECFilingParser` / `DARTFilingParser`)**: 두 파서가 같은 `FilingFacts`
   인터페이스를 반환한다. SEC는 companyfacts API(숫자) + edgartools markdown(텍스트),
   DART는 fnlttSinglAcntAll API(숫자) + document.xml(텍스트). 각 파서는 독립적이어서
   DeepDive 외 파이프라인에서도 재사용 가능하다. 검증: AAPL/NVDA/JPM(SEC), 삼성전자(DART).

3. **ImpactCalculator — 4가지 공시 유형별 시뮬레이션**: 실적발표(EPS miss/beat → 주가 반응
   히스토리 패턴), 유상증자(희석 비율 → 주당 가치 하락), 전환사채(CB 조건 → 희석 상한),
   공급계약(계약 금액 / 연간 매출 → 매출 기여도). 유형 외 공시는 텍스트 인사이트만 반환.

4. **CLI 출력**: Rich Table(재무 19개 숫자) + Panel(임팩트 시뮬레이션) + 섹션(사업 인사이트).
   `filing_parser` 미설정 시 기존 공시 제목 출력 경로를 유지한다(하위 호환).

## Before / After

```
Before:
  jarvis analyze AAPL
  → 공시: [2026-04-29] Form 10-Q filed (제목만)

After:
  jarvis analyze AAPL
  → 공시 재무 지표 (19개):
    Revenue: $94.9B  |  EPS: $1.65  |  Gross Margin: 47.1%  ...
  → 임팩트 시뮬레이션 (실적발표):
    EPS Beat +12% → 과거 패턴 기반 +3~5% 단기 반응 예상
  → 사업 인사이트:
    Services 매출 YoY +14%, iPhone 중국 점유율 회복 언급
```

## Impact

`jarvis analyze` 출력에 재무 테이블(Rich Table) + 임팩트 패널 + 사업 인사이트 섹션이
추가된다. `filing_parser` 미설정 시 기존 공시 제목 출력만 하는 경로가 유지된다.
`edgartools` 패키지가 의존성에 추가된다(`uv sync` 필요).

## Constraints

- **edgartools 외부 의존성 추가**: edgartools가 SEC HTML 파싱을 담당한다. 향후 SEC 구조
  변경 시 파서 유지보수가 필요하다.
- **LLM 비용**: 종목당 ~$0.02-0.05(Haiku 기준). 캐시(`data/cache/filings/`) 로 중복 호출을
  방지한다. SEC API rate limit 10 req/sec 준수.
- **XBRL concept 매핑 한계**: 19개 재무 지표 매핑은 US GAAP 기준이며, IFRS 기반 한국 종목은
  DARTParser가 별도 매핑을 관리한다. 매핑 밖 지표는 추출하지 않는다(false positive 방지).
- **유형 분류 실패**: 공시가 4가지 유형 중 어디에도 해당하지 않으면 `ImpactCalculator`는
  텍스트 인사이트만 반환하고 시뮬레이션을 건너뛴다.

## Related

- 설계: `docs/superpowers/specs/2026-04-29-disclosure-intelligence-design.md`
- ADR: 없음 (구현 완료 시 작성)
- FEATURES.md: 머지 후 업데이트
- 후속: Golden Set 10종목 검증(recall 80% 목표) → PR 머지
