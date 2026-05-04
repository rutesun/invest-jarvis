# Daily Report Quality Remediation Design

**작성일**: 2026-05-05  
**상태**: Approved for planning  
**범위**: `src/pipelines/daily_report/` 내부 품질 개선 + `jarvis report daily` 출력 포맷 개선 + Notion 업로드 반영  
**우선순위**: 정보 커버리지를 유지하면서 품질을 올리는 것이 1순위

## 1. 목표

현재 Daily Report는 정보량은 많지만, 다음 문제가 반복된다.

- 중복 이벤트가 서로 다른 카드로 과분해된다.
- 동일 이벤트의 반복 요약이 독립 근거처럼 부풀려진다.
- 단일 소스와 브로커 digest도 강한 투자 내러티브로 승격된다.
- 매크로/티커/출처 렌더링 품질이 낮아 신뢰를 깎는다.
- 빠르게 읽고 싶은 본문과 세부를 확인하고 싶은 조사성 출력이 한 문서에 섞인다.

이번 설계의 목표는 아래 세 가지를 동시에 만족하는 것이다.

1. 메인 본문은 읽기 쉬운 편집 결과물처럼 짧고 안정적으로 만든다.
2. 정보 커버리지는 확장 섹션과 워치리스트에서 유지한다.
3. 근거는 fragment/cluster 단위로 추적 가능하게 남긴다.

## 2. 비목표

이번 설계는 아래를 포함하지 않는다.

- `jarvis report daily`에 새 커맨드나 새 옵션 추가
- Daily Report와 별도인 신규 파이프라인 제품화
- Telegram 수집 포맷 전체 재설계
- LLM provider 교체
- Notion 업로드를 위한 별도 데이터 모델 분리

즉, 기존 Daily Report 제품을 유지하되 내부 구조와 출력 계약을 개선한다.

## 3. 접근 옵션과 선택

### 옵션 A. 최소 침습형

- 기존 5-stage 유지
- prompt, renderer, 일부 필터만 보강

장점:
- 변경 폭이 작다.

단점:
- 기사 묶음 row 문제
- 전역 dedupe 부재
- source mapping 오류
- evidence cluster 부재
를 구조적으로 해결하지 못한다.

### 옵션 B. 중간 재설계형

- 기존 `Ingest -> Map -> Shuffle -> Reduce -> Wrapup` 뼈대 유지
- 앞단에 `fragment split / source classify`
- 중간에 `global merge / rank / select`
- 출력단에 `brief / extended / broker pulse`
를 추가

장점:
- 현재 구조와 테스트 자산을 살릴 수 있다.
- 현재 문제의 핵심 원인을 구조적으로 해결할 수 있다.

단점:
- 모델과 stage 계약을 꽤 수정해야 한다.

### 옵션 C. 전면 재구축형

- event graph 기반 신규 파이프라인 구축

장점:
- 장기적으로 가장 견고하다.

단점:
- 범위가 너무 크고, CLI/Notion/fixture를 한 번에 흔든다.

### 선택

이번 설계는 **옵션 B**를 채택한다.

이유:
- 문제의 본질은 프롬프트가 아니라 입력 구조, dedupe, evidence 모델, 출력 계약에 있다.
- 하지만 새 파이프라인을 병행 개발할 정도로 범위를 키울 필요는 없다.

## 4. 최종 아키텍처

기존 개념:

```text
Ingest -> Map -> Shuffle -> Reduce -> Wrapup
```

개선 개념:

```text
Ingest
  -> Fragment Split
  -> Source Classify
  -> Map
  -> Global Merge
  -> Shuffle
  -> Score
  -> Select
  -> Reduce
  -> Wrapup
  -> Render
```

핵심 변화는 세 가지다.

1. `row`를 바로 해석하지 않고 `fragment`를 기본 입력 단위로 사용한다.
2. `출처 수`가 아니라 `독립 evidence cluster 수`를 사용한다.
3. 모든 테마를 본문에 싣지 않고 `핵심 / 확장 / 워치리스트`로 분리한다.

## 5. 컴포넌트 설계

### 5.1 Ingest

**대상 파일**: `src/pipelines/daily_report/stages/ingest_stage.py`

역할:
- 날짜별 CSV 로드
- historical macro 조회
- `RawMessage` 생성

변경사항:
- 매크로는 실행 시점 최신값이 아니라 `date` 기준 historical close만 사용한다.
- 조회 실패 시 `0.0`으로 대체하지 않고 `None`으로 유지한다.
- 이후 단계에서 사용할 `raw_message_id`, `channel_id`, `row_index` 정보를 보존한다.

### 5.2 Fragment Split

**신규 파일 권장**: `src/pipelines/daily_report/source_parsing.py`

역할:
- 텔레그램 한 row를 기사 단위 `ArticleFragment[]`로 분해

필요한 이유:
- `shinhanresearch`류 입력은 한 row 안에 여러 기사가 묶여 있다.
- 지금 구조로는 source excerpt가 row 첫머리 기사에 잘못 붙을 수 있다.

분해 기준:
- `▶️`
- bullet 구분
- 헤더 패턴
- 링크 단위
- 리포트 요약 템플릿 패턴

출력은 최소 아래를 가진다.

- `fragment_id`
- `raw_message_id`
- `channel_id`
- `title`
- `body`
- `url`
- `fragment_index`

### 5.3 Source Classify

**신규 파일 권장**: `src/pipelines/daily_report/evidence.py`

역할:
- fragment를 source type별로 분류

분류:
- `primary_news`
- `primary_research`
- `broker_summary`
- `market_signal`
- `video_social`
- `unknown`

활용 목적:
- 브로커 summary를 메인 narrative에서 과대 반영하지 않기
- low-confidence source를 워치리스트로 강등하기

### 5.4 Map

**대상 파일**: `src/pipelines/daily_report/stages/map_stage.py`

역할 변경:
- 지금처럼 곧바로 강한 요약 이슈를 만들지 않는다.
- 먼저 `MappedEvent` 중심으로 추출한다.

`MappedEvent`는 최소 아래 정보를 가진다.

- `category`
- `entities`
- `event_type`
- `stance`
- `keywords`
- `source_fragment_ids`
- `confidence`
- `summary_fact`
- `summary_interpretation`

원칙:
- 팩트와 해석을 분리한다.
- 브로커 전망치는 `broker_view`로 표시 가능해야 한다.

### 5.5 Global Merge

**신규 stage 권장**: `src/pipelines/daily_report/stages/global_merge_stage.py`

역할:
- 청크별 map 결과를 전역 dedupe
- 같은 사건의 반복 요약을 하나의 evidence cluster로 접기

병합 기준:
- source overlap
- entity overlap
- keyword overlap
- event type
- semantic similarity

예:
- 원노트 1개 + TP summary 3개 + 재요약 2개
- 결과적으로 `6개 카드`가 아니라 `1개 evidence cluster`

출력:
- `MergedCluster[]`

각 cluster는 아래를 가진다.
- `cluster_id`
- `canonical_theme_hint`
- `category`
- `event_ids`
- `independent_evidence_count`
- `source_diversity`
- `contains_broker_only`
- `contains_counter_signal`

### 5.6 Shuffle

**대상 파일**: `src/pipelines/daily_report/stages/shuffle_stage.py`

역할:
- merged cluster를 theme 단위로 정규화

변경 원칙:
- `issue.themes[0]` 의존 제거
- 섹터 충돌 시 merge 금지
- 서로 다른 산업 흐름이 한 theme로 섞이지 않도록 제약 추가

출력:
- `ThemeCluster[]`

### 5.7 Score / Select

**신규 stage 권장**: `src/pipelines/daily_report/stages/rank_stage.py`

역할:
- theme cluster를 점수화하고 최종 출력 레이어로 분리

점수 요소:
- `independent_evidence_count`
- `source_diversity`
- `primary_source_bonus`
- `broker_summary_penalty`
- `single_source_penalty`
- `market_signal_bonus`
- `cross_category_link_bonus`
- `novelty`
- `speculative_penalty`

선택 결과는 아래 3개 레이어다.

- `brief_candidates`
- `extended_candidates`
- `watchlist_candidates`

기본 정책:
- 메인 brief는 보통 `10~20개`
- 장이 매우 바쁜 날은 `20~25개`까지 허용
- 그 외는 extended/watchlist로 보낸다.
- 절대적으로 버리기보다 레이어를 바꾸는 것이 기본 전략이다.

### 5.8 Reduce

**대상 파일**: `src/pipelines/daily_report/stages/reduce_stage.py`

역할 변경:
- 강한 마케팅성 투자 카피 생성기에서
- evidence-first 정리기 역할로 축소

출력 구조:
- `headline`
- `what_happened`
- `why_it_matters`
- `interpretation`
- `risks`
- `related_stocks`
- `evidence_summary`

문체 규칙:
- single-source면 `본격화`, `폭증`, `구조적 수혜` 금지
- 브로커 전망은 반드시 `전망`, `추정`, `의견`으로 표시
- low confidence 항목은 watchlist 전용 톤 사용

### 5.9 Wrapup

**대상 파일**: `src/pipelines/daily_report/stages/wrapup_stage.py`

역할:
- `brief_candidates` 중심으로 key insight 생성
- mixed signal 보존

변경사항:
- key insight는 단순 `list[str]`가 아니라 추적 가능한 객체로 저장
- 각 insight는 최소 1개 이상의 cluster/source bundle 참조를 가진다.

권장 필드:
- `title`
- `summary`
- `cluster_ids`
- `source_fragment_ids`
- `counter_signal_ids`

## 6. 데이터 모델 설계

### 추가 모델

- `RawMessage`
- `ArticleFragment`
- `SourceType`
- `MappedEvent`
- `MergedCluster`
- `ThemeCluster`
- `ScoredTheme`
- `KeyInsight`

### 기존 모델 변경

- `MacroSnapshot`
  - sentinel numeric fallback 제거
- `NewsItem`
  - 최종 출력 레이어(`brief`, `extended`, `watchlist`) 식별 가능해야 함
- `DailyReport`
  - `brief_items`
  - `extended_items`
  - `broker_pulse_items`
  - `key_insights`
  를 구조적으로 저장

## 7. 출력 구조

출력은 하나의 리포트 안에 3개 층을 가진다.

### 7.1 Daily Brief

- `Key Insights 3~5개`
- `핵심 테마 10~20개`
- 빠르게 읽히는 본문

### 7.2 Extended Themes

- 커버리지를 유지하는 확장 영역
- 섹션 타이틀은 항상 보임
- 내부 theme 카드 상세만 접을 수 있게 설계

### 7.3 Broker Pulse / Watchlist

- 브로커 요약, 단일 소스, speculative 항목
- 기본적으로 낮은 확신 레이어
- 메인 본문과 구분된 톤 사용

## 8. CLI 계약

대상 명령:

```bash
uv run jarvis report daily <date>
```

유지:
- 명령 이름
- 인자 형식
- `--notion`

변경:
- Markdown 구조
- 각 카드 필드 구조

권장 섹션 순서:

```text
# Daily Market Report - YYYY-MM-DD

## Macro Snapshot
## Daily Brief
## Extended Themes
## Broker Pulse
```

표현 규칙:
- `UNKNOWN`, `PRIVATE`, `0.0` 직접 노출 금지
- canonical ticker 없으면 ticker 출력 생략
- 비상장은 `비상장`, 프록시는 `상장 프록시`로 표기

## 9. Notion 계약

대상 파일:
- `src/integrations/notion.py`

원칙:
- CLI와 같은 정보 계층을 유지한다.
- Notion만 다른 의미 구조를 만들지 않는다.

권장 블록 구조:
- 페이지 제목
- Macro Snapshot
- Daily Brief
- Extended Themes
- Broker Pulse

표현 방식:
- `Extended Themes` 섹션 타이틀은 항상 보이게 유지
- 각 theme 카드의 상세는 toggle block으로 접기
- `Broker Pulse`도 같은 방식으로 접기

## 10. 테스트 설계

테스트 전략은 아래 3층 구조를 사용한다.

### 10.1 단계별 결정적 회귀 테스트

대상 파일 권장:

- `tests/pipelines/daily_report/test_source_parsing.py`
- `tests/pipelines/daily_report/test_evidence.py`
- `tests/pipelines/daily_report/test_global_merge.py`
- `tests/pipelines/daily_report/test_rank_stage.py`
- 기존 stage 테스트 확장

검증 포인트:
- fragment split 결과 수
- source type 분류
- evidence cluster dedupe
- rank 결과 레이어 분류
- reduce 문체 제약
- wrapup 추적성

### 10.2 날짜별 골든셋 회귀 테스트

대표 날짜:

- `2026-04-27`
- `2026-04-28`
- `2026-04-29`
- `2026-04-30`
- `2026-05-04`

fixture 구조 권장:

```text
tests/pipelines/daily_report/fixtures/golden/<date>/
  raw_messages.json
  fragments.json
  mapped_events.json
  merged_clusters.json
  ranked_selection.json
  final_report_assertions.json
```

중요:
- final report 전체 문자열 exact match는 목표가 아니다.
- 대신 아래 속성을 고정한다.

예시 assertions:
- brief narrative 수 범위
- `UNKNOWN`, `PRIVATE`, `0.0` 미노출
- 특정 오분류 제거
- 특정 중복 테마 병합
- mixed signal 유지
- 잘못된 source mapping 제거

### 10.3 수동 재현 경로

목표:
- 실제 LLM/운영과 유사한 수동 테스트 경로 제공

원칙:
- 자동 테스트와 같은 레벨로 개발자가 직접 재현 가능해야 한다.
- 날짜별 stage 실행 명령과 체크리스트를 표준화한다.

예시 흐름:

```bash
uv run python -m src.pipelines.daily_report.stages.ingest_stage 2026-04-28
uv run python -m src.pipelines.daily_report.stages.map_stage 2026-04-28
uv run python -m src.pipelines.daily_report.stages.global_merge_stage 2026-04-28
uv run python -m src.pipelines.daily_report.stages.rank_stage 2026-04-28
uv run jarvis report daily 2026-04-28
```

수동 체크리스트 예:
- 메인 brief가 과도하게 길지 않은가
- 잘못된 카테고리 카드가 제거됐는가
- source excerpt가 올바른 fragment에 붙는가
- 브로커 digest가 메인을 장악하지 않는가
- Extended Themes는 제목이 보이고 내부 상세만 접히는가

## 11. 오류 처리

- `source_parsing` 실패 시
  - row 단위 fallback
  - low-confidence source로 표시
- `global_merge` 실패 시
  - flatten 결과로 fallback
  - dedupe 미적용 내부 플래그 유지
- `rank_stage` 실패 시
  - 메인 brief 최소화 + extended 다수 fallback
- macro 조회 실패 시
  - `데이터 없음` 렌더
- ticker 정규화 실패 시
  - ticker 생략, 회사명만 사용

## 12. 도입 순서

### Phase 1. 신뢰도 복원

1. macro historical 조회 및 sentinel 제거
2. source parsing
3. source type 분류
4. renderer hygiene (`UNKNOWN`, `PRIVATE`, source excerpt`)

### Phase 2. 중복 제어

5. evidence clustering
6. global merge
7. rank/select

### Phase 3. 출력 구조 전환

8. brief / extended / broker pulse 렌더
9. CLI/Notion 동일 구조 반영
10. 날짜별 골든셋 회귀 정착

## 13. 성공 기준

아래 조건을 만족하면 remediation이 유효하다고 본다.

- 메인 brief만 읽어도 오늘의 핵심 narrative를 파악할 수 있다.
- Extended Themes로 정보 커버리지가 유지된다.
- Broker Pulse가 잡음 격리 역할을 한다.
- 브로커 digest가 메인 narrative를 직접 지배하지 못한다.
- 동일 이벤트 반복 요약이 evidence cluster 단위로 접힌다.
- mixed signal이 필요한 날짜에는 실제로 유지된다.
- `UNKNOWN`, `PRIVATE`, `0.0` 같은 신뢰도 저하 표기가 본문에서 사라진다.
- CLI와 Notion이 동일한 정보 계층을 유지한다.

## 14. 변경 대상 파일

수정 대상:

- `src/pipelines/daily_report/models.py`
- `src/pipelines/daily_report/pipeline.py`
- `src/pipelines/daily_report/prompts.py`
- `src/pipelines/daily_report/stages/ingest_stage.py`
- `src/pipelines/daily_report/stages/map_stage.py`
- `src/pipelines/daily_report/stages/shuffle_stage.py`
- `src/pipelines/daily_report/stages/reduce_stage.py`
- `src/pipelines/daily_report/stages/wrapup_stage.py`
- `src/integrations/notion.py`
- `src/cli/main.py`
- 관련 테스트 및 fixture

신규 파일 권장:

- `src/pipelines/daily_report/source_parsing.py`
- `src/pipelines/daily_report/evidence.py`
- `src/pipelines/daily_report/stages/global_merge_stage.py`
- `src/pipelines/daily_report/stages/rank_stage.py`

## 15. 최종 요약

이 설계는 Daily Report를 새로 만들지 않는다.  
대신 기존 파이프라인에 아래 네 가지를 추가해 신뢰도와 사용성을 동시에 복구한다.

1. 기사 fragment 기반 입력 처리
2. evidence cluster 기반 dedupe
3. rank/select 기반 편집 레이어
4. brief / extended / broker pulse 기반 출력 구조

결과적으로 메인 본문은 짧고 읽히게 만들고, 정보량은 확장 섹션에서 유지하며, 근거 추적성과 테스트 가능성은 오히려 강화한다.
