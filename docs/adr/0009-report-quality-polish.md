# ADR-0009: 리포트 가독성 개선 — 기타 단신 통합·출처 dedup·티커 dedup 전략

**상태:** 수락  
**날짜:** 2026-06-08  
**관련 브랜치:** `feature/report-quality-polish`

## 컨텍스트

PR #33(ADR-0007/0008) 이후 `daily_v2_2026-06-04` 리포트 리뷰에서 4종의 가독성 문제가
확인됐다. 이 ADR은 그 중 아키텍처 레벨 결정이 있었던 세 가지를 기록한다.

### 1. 저가치 롱테일 카테고리 카드 (minor category consolidation)

chunk < 3 카테고리는 `synthesize_category`의 raw fallback 분기를 탄다(ADR-0007 확정 임계값).
raw 카드는 LLM 없이 summary를 이어붙여 만들므로 Narrative가 단순 사실 나열이고, Impact가
비며, related_stocks catalyst가 빈 문자열이 돼 `티커: -`로 렌더된다. 당일 리포트에서 minor
카테고리가 10개(각 1~2 chunk)였고, 이들이 별개 카드로 노출돼 Category Summaries 하단에
저품질 잡음 묶음이 형성됐다.

**선택지:**

| 옵션 | 설명 | 문제 |
|------|------|------|
| A: 개별 카드 유지 | 현행 | 10개 저품질 카드가 주요 카드를 희석 |
| B: minor 제외 | chunk < 3 카테고리를 렌더에서 숨김 | 조용한 누락. 헤드라인 정보 손실 |
| C: 기타 단신 통합 | minor 카테고리를 단일 compact 항목으로 병합 | - |

옵션 B는 `StockReportArtifact.evidence_refs` 영속에도 영향 없이 숨길 수 있으나, 카테고리
단신(소형 수주, ETF 출시, 원자재 가격)이 당일 투자 판단에 유효한 경우가 있어 기각했다.
특히 고임팩트 이벤트(M&A/자본조달)가 thin 카테고리에 떨어질 수 있어 조용한 누락은 ADR-0008
안전망 원칙에 반한다.

### 2. 출처 줄 가독성 (source line dedup / cap)

Core Themes 카드 한 줄에 출처가 최대 26개까지 나열됐다. chunk-level 중복 제거만 했기 때문에
같은 채널의 메시지가 `chunk 3782 채널A#101, chunk 3783 채널A#102, ...` 형태로 반복됐다.

완전한 chunk 단위 출처는 `report_evidence` 테이블에 영속되고, T09-A 경로는
`StockReportArtifact.evidence_refs`를 직접 사용해 DB에 저장한다 — 렌더된 마크다운을
재파싱하지 않는다(T09-B Gemini 경로만 `parse_referenced_from_markdown` 사용).
따라서 렌더 표시를 채널 단위로 축약해도 추적성이 손실되지 않는다.

**선택지:**

| 옵션 | 단위 | 결과 |
|------|------|------|
| A: chunk-level dedup(현행) | 개별 chunk | 26개 줄 |
| B: 채널-level dedup + cap | 채널당 대표 1개 | 최대 N개 + 외 K건 |
| C: 완전 숨김 | - | 출처 없음 → 신뢰성 하락 |

옵션 C는 신뢰성 측면에서 기각. 옵션 B를 채택하되 cap N = 6(경험적: 채널 다양성 vs 줄 길이
균형)으로 설정. "외 K건" suffix로 절단이 투명하게 노출된다.

### 3. Focus Ticker 이름/티커 별칭 dedup

같은 종목이 `Tesla(chunk 2개)`·`SpaceX(chunk 2개)`·`TSLA(chunk 3개)` 처럼 별개 버킷으로
생성돼 중복 카드가 노출되는 현상이 보고됐다. 검토한 dedup 전략:

**선택지:**

| 옵션 | 방식 | 검증 결과 |
|------|------|----------|
| A: chunk 집합 완전 동일 | `frozenset(chunk.ids)` 동일 시만 병합 | 보수적, 안전 |
| B: 부분집합 병합 | name bucket ⊆ symbol bucket 시 병합 | 위험 (아래 참조) |
| C: LLM name→ticker 정규화 | entity resolution via LLM | 비용/비결정적 |

**2026-06-04 실데이터 검증으로 확인된 사실:**

- `Tesla={3759,3763}`, `TSLA={3759,3794,3820}`, `SpaceX={3761,3819}`
  → Tesla⊄TSLA(3763 단독), SpaceX∩TSLA=∅ (별개 뉴스)
- 부분집합 관계(`name ⊆ symbol`)가 성립한 사례: `Ford⊆GM`, `삼성디스플레이⊆BOE`,
  `KOSDAQ⊆KOSPI` 등 → **동시언급 ≠ 동일 회사**이므로 옵션 B는 오병합 위험.
- 옵션 C는 이번 SpaceX 문제에 무효(SpaceX≠TSLA 별개 회사)이면서 합성 경로에 LLM 추가 비용.

실데이터에서 Tesla/TSLA chunk 집합이 달라 현행 옵션 A로는 병합되지 않으므로 SpaceX thin
카드 문제는 잔존한다. 이 문제의 근본 원인은 chunk < 3 thin ticker 카드이며, 사용자가 현행
유지(옵션 B의 thin ticker 제외 대신 현 구현 그대로)를 선택했다.

## 결정

**세 결정을 각각 채택한다:**

### 1. 기타 단신 통합 (옵션 C)

- chunk < 3 카테고리 버킷을 map 단계에서 `_partition_category_buckets`로 분리
- minor 버킷들을 `_build_minor_categories_item`으로 단일 `ReportSectionItem`(key=`__minor_briefs__`)으로 통합
- 각 버킷에서 priority\_score 내림차순으로 대표 chunk를 선발, 고임팩트 이벤트(`M&A`/`자본조달`)를 우선 배치
- cap = 12(내부 상수 `_MINOR_BRIEF_MAX_ITEMS`). 초과분은 `… 외 N건 생략`으로 비침투적 노출
- 렌더러는 이 항목을 플랫 bullet list로 처리(기존 Narrative/Impact/근거 그룹 레이아웃 없음)
- threshold = `_CATEGORY_RAW_FALLBACK_THRESHOLD`(=3)을 재사용해 설계 일관성 유지

> 구현: `src/pipelines/stock_report/synthesize.py` — `_partition_category_buckets`,
> `_build_minor_categories_item`, `MINOR_CATEGORY_ITEM_KEY`  
> `src/pipelines/stock_report/render_markdown.py` — `_render_minor_briefs`

### 2. 채널 단위 출처 dedup + cap (옵션 B)

- `_build_source_lookup` 반환 타입을 `list[str]` → `list[tuple[channel_name, display_line]]`으로 변경
- `_format_sources`: 채널 단위 dedup → 빈도 내림차순 정렬 → 상위 `_MAX_SOURCES_SHOWN`(=6)
  + `외 K건` suffix
- DB attribution(`report_evidence` 테이블 + `evidence_refs`)은 chunk 단위 그대로 유지.
  렌더 표시만 요약.

> 구현: `src/pipelines/stock_report/render_markdown.py` — `_build_source_lookup`,
> `_format_sources`, `_MAX_SOURCES_SHOWN`

### 3. 티커 dedup (옵션 A, 보수적)

- chunk 집합이 **완전히 동일**한 버킷 그룹 중 `_is_ticker_like` 라벨(ASCII 대문자 ≤5자 또는
  숫자 코드)이 정확히 1개인 경우만 해당 티커 라벨로 병합.
- 집합이 다르거나 티커-like 라벨이 2개 이상이면 병합 안 함(보수적: 오병합 없음 보장).

> 구현: `src/pipelines/stock_report/synthesize.py` — `_is_ticker_like`,
> `_dedupe_ticker_buckets`

## Consequences

**장점:**
- Category Summaries에서 저품질 raw 카드 10개가 사라지고 구조화된 단신 1개로 대체 → SNR 개선
- 출처 줄이 채널 단위로 압축돼 인간 독자의 채널 출처 파악이 쉬워짐
- DB evidence 영속에 영향 없음 — eval·coverage 지표 불변
- 결정론적 구현: LLM nondeterminism 의존 없음

**단점/트레이드오프:**
- 조용한 날엔 기타 단신이 빈약해 보일 수 있음(단, 데이터에 충실)
- Tesla/TSLA chunk 집합이 달라 alias dedup이 안 되는 엣지케이스 잔존 (사용자 수락)
- 채널 대신 chunk 단위 출처를 보려면 eval 스크립트나 DB 직접 조회 필요

**운영:**
- `_MINOR_BRIEF_MAX_ITEMS`(12)·`_MAX_SOURCES_SHOWN`(6)은 상수로 노출돼 튜닝 가능
- thin ticker 카드 문제 재발 시 ADR 업데이트 후 이슈 3항 옵션 A(thin ticker 제외) 검토

## 부록: Google Grounding not-fired 억제 정책 변경

이번 브랜치(`feature/report-quality-polish`)에서 `synthesize_with_google_grounding`의
**not-fired 재시도 + 결과 억제 로직**이 제거됐다. 이는 리포트 가독성 이슈와 직접 관련은
없으나 같은 PR에 포함된 의도적 정리다.

**변경 전**: grounding이 발동되지 않으면(no citations, no search queries) 최대
`_MAX_RETRIES`회 재시도 후에도 not-fired면 결과를 억제해 빈 artifact를 반환.

**변경 후**: 억제 없이 Gemini 응답을 그대로 반환. `grounding_active=False`이면
렌더러 배너에 "Grounding 미발동" 표시만 남긴다.

**이유**: 이 경로는 `## [EXPERIMENTAL]` 태그를 달고 T09-A(기본 OpenAI 경로)와 비교
목적으로만 운영된다. 억제 로직이 재시도 예산(API 비용)을 소비하면서 비교 데이터 자체를
버려 실험 목적에 반했다. not-fired 응답은 grounding 없이 Gemini 파라메트릭 지식만
쓴 결과이므로, 억제 대신 "미발동" 레이블로 노출해 비교군으로 활용하는 것이 실험 설계에
더 적합하다. 프로덕션 경로(T09-A)에 영향 없음.
