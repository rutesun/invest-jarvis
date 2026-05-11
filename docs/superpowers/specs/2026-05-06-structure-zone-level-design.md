# Structure Zone Level Design

## Summary

`jarvis analyze`의 지지/저항과 시나리오 출력을 `단기 계산 레벨` 중심에서 `구조 zone + 실행 line` 혼합 구조로 재설계한다.

핵심 목표는 다음 세 가지다.

- 구조적 지지/저항을 peak/trough 기반 zone으로 표현한다.
- pivot/ATR/MA/fib는 실행용 line으로 유지하되 구조 레벨과 혼동되지 않게 분리한다.
- 회귀 테스트와 튜닝이 가능한 형태로 파라미터/결과/점수 분해를 저장한다.

이번 범위에서는 `LLM as judge`는 제외한다.

## Problem

현재 `price_levels`는 MA, pivot, fib, ATR, pattern breakout을 한 리스트로 모아 현재가 근처 순으로 정렬한다. 이 방식은 단기 트레이딩 레벨을 빠르게 뽑는 데는 유용하지만, 다음 문제가 있다.

- 3년 차트 관점의 구조적 공급/수요 구간보다 피봇/ATR 같은 단기 계산 레벨이 전면에 노출된다.
- 사용자 출력에서 구조 레벨과 실행 레벨이 섞여 보이기 때문에, `지지/저항`이 장기 매물대처럼 읽히는 오해가 생긴다.
- 튜닝 포인트가 분리되어 있지 않아 레벨 품질을 개선하기 어렵다.
- 회귀 테스트가 부족해 파라미터 조정 시 품질 저하를 안정적으로 감지하기 어렵다.

## Goals

- 구조 레벨은 `zone`으로 출력한다.
- 구조 레벨 타입은 `수요 구간`, `공급 구간`, `구조 무효화`로 고정한다.
- 실행 레벨은 `line`으로 유지한다.
- 구조 레벨은 3년 후보를 보되 최근성 가중을 강하게 둔다.
- 거래량은 zone 생성이 아니라 핵심/보조 승격과 최종 정렬에 반영한다.
- 최종 출력은 `구조 레벨`과 `실행 레벨`을 분리한다.
- 테스트는 CSV fixture 기반으로 파라미터/결과/점수 분해를 저장한다.

## Product Success Criteria

이번 설계의 성공은 `zone detector를 구현했다`가 아니라, 사용자가 기존 출력보다 더 빠르고 더 덜 헷갈리게 판단하느냐로 본다.

초기 성공 기준은 다음과 같이 둔다.

- 사용자는 상단 출력만 보고 `구조 레벨`과 `실행 레벨`의 역할 차이를 바로 구분할 수 있어야 한다.
- 기존 출력 대비 `이 지지/저항이 왜 중요한지 모르겠다`는 해석 혼선을 줄여야 한다.
- 내부 비교 샘플에서 동일 종목의 기존 출력과 신규 출력을 나란히 봤을 때, 사람이 `신규 출력이 더 행동 가능하다`고 판단하는 비율이 과반을 넘어야 한다.
- 동일 종목 재실행 시 구조 zone과 구조 무효화가 불안정하게 흔들리지 않아야 한다.

정량/정성 검증은 아래 두 축으로 본다.

- 제품 검증
  - 내부 샘플 리뷰에서 `더 신뢰 가능함`, `더 행동 가능함`, `덜 기계적임`을 체크한다.
  - 기존 출력 대비 오해 사례를 수집한다.
- 엔지니어링 검증
  - fixture/golden/score decomposition 테스트로 결과 안정성을 본다.
  - latency budget과 artifact diff를 통해 튜닝의 부작용을 본다.

## Non-Goals

- 이번 범위에서 `LLM as judge`를 도입하지 않는다.
- 기존 pivot/ATR/fib 계산 자체를 버리거나 전면 교체하지 않는다.
- 매수/매도 추천 로직 전체를 재작성하지 않는다.

## Chosen Approach

`구조 zone detector 분리 + 기존 실행 레벨 유지 + 마지막에 합성` 구조를 채택한다.

### Why this approach

- peak/trough + 거래량 반응 기반 구조 레벨을 독립적으로 튜닝할 수 있다.
- 기존 `price_levels`가 제공하던 실행용 line 레벨의 장점을 그대로 유지할 수 있다.
- 구조/실행 레벨을 분리해 사용자 출력의 의미를 명확히 할 수 있다.
- 테스트 대상을 모듈 단위로 나눌 수 있어 회귀 원인 분석이 쉬워진다.

## Architecture

### 1. StructureZoneDetector

새 모듈을 추가한다. 예시 경로는 `src/tools/technical/structure_zones.py`.

입력:

- `raw_dataframe`
- `IndicatorSnapshot`
- optional config object

출력:

- `StructureZoneSet`
  - `demand_zones`
  - `supply_zones`
  - `invalidation_candidates`
  - `invalidation_zone`
  - `all_candidates`

역할:

- swing high/low 후보 추출
- 3년 후보 수집
- ATR + 퍼센트 하한/상한 혼합 규칙으로 zone 생성
- 거래량 기반 승격/강등
- 점수 분해 계산

### 2. ExecutionLevelCollector

기존 `price_levels.py`를 유지하되 역할을 명확히 한다.

역할:

- pivot
- ATR
- MA
- fib
- pattern breakout

출력:

- 기존 `PriceLevels`

비고:

- MA 수집은 현재처럼 유지하되, 실행 레벨이라는 의미를 문서와 출력에 명확히 반영한다.

### 3. LevelComposer

구조 레벨과 실행 레벨을 최종 출력용으로 합친다.

출력 원칙:

- `구조 레벨`
  - 수요 zone 2개
  - 공급 zone 2개
  - 구조 무효화 1개
- `실행 레벨`
  - pivot / ATR / MA / fib 중 현재 액션과 가까운 핵심 line

### 4. Test Harness

CSV fixture와 결과 스냅샷을 사용하는 테스트/튜닝 보조 장치를 만든다.

## Output Contract

구현자, 테스트, LLM 프롬프트가 같은 계약을 보도록 최종 출력 계약을 먼저 고정한다.

### StructureZoneSet contract

| field | type | rule |
|-------|------|------|
| `demand_zones` | list[`StructureZone`] | `total_score DESC` 정렬, 최대 `top_n_per_side` 보관 |
| `supply_zones` | list[`StructureZone`] | `total_score DESC` 정렬, 최대 `top_n_per_side` 보관 |
| `invalidation_candidates` | list[`StructureZone`] | 내부 전용, 최종 노출 전 후보 저장 |
| `invalidation_zone` | `StructureZone \| None` | 최종 한 개만 선택 |
| `all_candidates` | list[`StructureZone`] | 디버깅/테스트용 전체 후보 |

동점 처리 규칙:

- 1순위: `total_score DESC`
- 2순위: `last_touch_date DESC`
- 3순위: `touch_count DESC`
- 4순위: 현재가와의 거리 절대값 `ASC`

### Final analyze output contract

Phase 1의 기본 출력 수량은 아래처럼 고정한다. 이는 영구 UI 정책이 아니라 초기 안정화용 계약이다.

| block | count | selection rule |
|-------|-------|----------------|
| `구조 레벨 > 수요 구간` | 최대 2개 | `demand_zones` 상위 순 |
| `구조 레벨 > 공급 구간` | 최대 2개 | `supply_zones` 상위 순 |
| `구조 레벨 > 구조 무효화` | 최대 1개 | `invalidation_zone` |
| `실행 레벨` | 최대 3개 | 현재가 근접도 + line 타입 우선순위로 선택 |

출력 부족 시 fallback 규칙:

- 유효한 수요/공급 zone이 2개 미만이면 존재하는 개수만 노출한다.
- 유효한 `invalidation_zone`이 없으면 장기 MA 기반 fallback을 사용한다.
- 실행 레벨이 부족하면 pivot → MA → ATR → fib 순으로 후보를 보충한다.

### LLM payload contract

LLM에는 기존 `지지/저항` 평문 묶음 대신 구조/실행 분리 payload를 전달한다.

필수 필드:

- `structure_levels.demand_zones[]`
- `structure_levels.supply_zones[]`
- `structure_levels.invalidation`
- `execution_levels[]`
- `structure_summary`
- `execution_summary`

LLM은 아래 원칙을 따른다.

- 구조 레벨은 방향과 무효화 기준 설명에 사용한다.
- 실행 레벨은 진입/추격/대기/손절의 실행 문장에 사용한다.
- 구조와 실행이 충돌하면 `구조 우선, 실행 보조` 원칙으로 해석한다.

## Data Model

### StructureZone

- `zone_type`: `demand` | `supply` | `invalidation`
- `lower_bound`
- `upper_bound`
- `mid_price`
- `touch_count`
- `last_touch_date`
- `touch_score`
- `recency_score`
- `volume_reaction_score`
- `confluence_score`
- `total_score`
- `strength`: `core` | `secondary`
- `reasons`: list[str]

### StructureZoneConfig

- `lookback_days`
- `atr_width_multiplier`
- `min_zone_width_pct`
- `max_zone_width_pct`
- `recent_window_days`
- `mid_window_days`
- `volume_baseline_window`
- `top_n_per_side`
- `score_weights`

### ZoneTestArtifact

- `schema_version`
- `symbol`
- `csv_path`
- `params`
- `candidates`
- `selected_zones`
- `score_breakdown`

## Detection Logic

### 1. Candidate extraction

- 3년치 데이터에서 swing high/low 후보를 추출한다.
- peak/trough는 패턴 감지와 같은 저수준 도우미를 재활용하거나 같은 기준으로 정렬한다.
- 각 후보는 날짜, 가격, 반응 강도, 거래량 정보를 가진다.

### 2. Zone width

zone 폭은 `ATR + 퍼센트 하한/상한 혼합` 규칙으로 계산한다.

예시 개념:

- 기본 폭: `atr_width_multiplier * ATR`
- 하한: `min_zone_width_pct * price`
- 상한: `max_zone_width_pct * price`

최종 zone half-width는 위 세 값의 제한을 반영해 계산한다.

이 규칙으로 변동성 높은 종목과 낮은 종목 모두에서 과도하게 좁거나 넓은 zone을 피한다.

### 3. Clustering

- 가까운 swing 후보들을 같은 zone으로 묶는다.
- zone은 line이 아니라 가격대 범위로 유지한다.
- cluster 후 lower/upper/mid를 계산한다.

### 4. Volume handling

거래량은 zone 생성이 아니라 zone 평가에 반영한다.

구체 규칙:

- zone 생성은 price-based cluster로 수행
- 거래량은 `volume_reaction_score`와 `core/secondary` 분류에 사용

거래량 평가는 `zone에 속한 날짜의 단순 거래량 합`이 아니라, `터치 이벤트별 반응 점수 합산`으로 계산한다.

터치 이벤트 점수 요소:

- baseline 대비 거래량 배수
- 터치 후 반등/반락 강도
- 이벤트 최근성

### 5. Scoring

초기 점수 축은 다음 네 가지다.

- `touch_score`
- `recency_score`
- `volume_reaction_score`
- `confluence_score`

초기 원칙:

- 거래량과 반복 터치에 높은 비중
- 최근성은 강하게 반영
- confluence는 보조 가점

정확한 수치는 config로 분리하고 fixture로 튜닝한다.

### 6. Zone type classification

- `demand`: swing low cluster 중심
- `supply`: swing high cluster 중심
- `invalidation`: 수요/공급 zone과 장기 MA(특히 150/200일선)를 고려한 구조 붕괴 기준

`구조 무효화`는 최종 한 개만 노출하되, 내부적으로는 여러 후보를 둘 수 있다.

### 7. Invalidation and conflict handling

`구조 무효화`는 사용자가 `이 시나리오가 틀렸다고 보는 기준`으로 읽는 값이므로, 선택 규칙을 고정한다.

우선순위:

1. 가장 강한 `core demand zone`의 하단 이탈
2. 가장 설명력이 높은 장기 MA 이탈
3. 최근 주요 swing low 이탈

세부 규칙:

- `core demand zone`이 존재하면 그 하단을 1차 무효화 후보로 둔다.
- 150일선 또는 200일선이 1차 무효화 후보와 `3%` 이내면 `복합 무효화`로 묶어 설명한다.
- 강한 수요 zone이 없으면 장기 MA 기반 후보를 사용한다.
- zone과 MA가 모두 약하면 최근 주요 swing low를 fallback으로 사용한다.
- 세 후보 모두 품질 기준 미달이면 `구조 무효화 계산 불충분` 상태로 두고, 실행 레벨 기반 손절선으로 대체하지 않는다.

구조/실행 충돌 처리:

- 구조는 상방인데 실행 레벨은 단기 저항 압력이 큰 경우: `구조는 유효하지만 추격보다 조정 대기`로 쓴다.
- 구조는 약한데 실행 레벨은 단기 반등 신호가 있는 경우: `단기 반등 가능, 구조 추세 전환 확인 전 보수적 접근`으로 쓴다.
- 실행 레벨은 구조 레벨을 뒤집지 않는다. 구조는 방향, 실행은 타이밍으로 제한한다.

## Output Design

### Analyze output

최종 사용자 출력은 구조/실행 레벨을 분리한다.

- `구조 레벨`
  - 핵심 수요 구간 2개
  - 핵심 공급 구간 2개
  - 구조 무효화 1개
- `실행 레벨`
  - 단기 진입/추격/손절용 pivot / ATR / MA / fib line

구조는 zone으로 표시한다.

예시:

- 수요 구간: `204,000~206,000`
- 공급 구간: `222,000~224,000`
- 구조 무효화: `150일선 126,000 하향 이탈`

실행은 line으로 표시한다.

예시:

- 단기 지지: `205,000 pivot`
- 단기 저항: `223,000 pivot`
- 추격 확인: `224,000 상향 안착`

### Actionable signal

이번 범위에서는 기존 LLM signal을 유지하되, 입력 텍스트를 바꾼다.

- 기존 `지지/저항` 나열 대신
- `구조 레벨` + `실행 레벨`을 구분한 컨텍스트 전달

## Testing Strategy

### 1. CSV fixtures

실시간 API를 매 테스트마다 호출하지 않는다.

종목별 고정 CSV를 저장한다.

초기 대상 예시:

- 엘앤에프
- 제룡전기
- ALAB
- 박스권 종목
- 급등 후 조정 종목

### 2. Unit tests

- swing 추출
- zone cluster 생성
- ATR + 퍼센트 하한/상한 폭 계산
- 거래량 반응 점수
- 구조 무효화 선택

### 3. Golden regression tests

종목별 기대 구조 레벨을 고정한다.

검증 대상 예:

- 수요/공급 zone 상위 2개 범위
- 구조 무효화 위치
- 최종 순위

완전 문자열 비교보다 구조화된 필드 비교를 우선한다.

### 4. Score decomposition tests

zone별 점수 분해를 검증한다.

- `touch_score`
- `recency_score`
- `volume_reaction_score`
- `confluence_score`
- `total_score`

### 5. Test artifact persistence

테스트 산출물은 다음을 함께 저장한다.

- 입력 CSV
- 사용 파라미터
- 후보 zone 목록
- 최종 선택 zone
- 점수 분해 결과

이 구조로 튜닝 시 결과 변화의 원인을 추적한다.

## Tuning Workflow

- fixture CSV를 기준으로 detector 실행
- 파라미터/후보/최종 결과를 artifact로 저장
- 기대값과 비교
- 필요 시 파라미터 조정
- regression suite 재실행

## Rollout and Operational Guardrails

이번 변경은 계산 로직뿐 아니라 최종 LLM 입력과 사용자 출력 해석을 바꾸므로, 안전하게 rollout한다.

### Rollout strategy

- 초기에는 feature flag 뒤에서 old/new 결과를 병행 생성한다.
- old/new 비교 대상:
  - 구조 레벨 상위 zone 범위
  - 구조 무효화 위치
  - 실행 레벨 상위 후보
  - 최종 한줄 판단 차이
- 초기 샘플 리뷰는 소수 종목 수동 검토로 시작한다.

### Latency budget

- `jarvis analyze` 단건 실행에서 structure zone 계산이 추가하는 지연은 기본적으로 제한되어야 한다.
- Phase 1의 임시 예산은 `기존 analyze baseline 대비 +20% 이내`를 기본 원칙으로 두고, 단건 추가 지연은 `+500ms` 이내를 우선 목표로 둔다.
- baseline, 측정 구간, p50/p95 집계 방식은 implementation plan에서 고정하고 결과는 artifact에 남긴다.
- fixture 기반 regression은 CI에서 실행 가능해야 하며, tuning용 상세 artifact 생성은 운영 경로와 분리한다.

### Artifact and golden governance

- `ZoneTestArtifact`에는 schema version을 둔다.
- score 축이나 정렬 규칙이 바뀌면 artifact version도 같이 올린다.
- golden 갱신은 `의도된 변경`일 때만 fixture, expected output, score breakdown을 함께 갱신한다.
- golden diff는 단순 문자열보다 구조화 필드 diff를 우선 사용한다.

### Rollback conditions

아래 조건 중 하나라도 발생하면 old path로 즉시 되돌릴 수 있어야 한다.

- 구조 zone 미검출률이 비정상적으로 증가
- 구조 무효화가 자주 비거나 fallback만 반복됨
- analyze latency가 예산을 넘김
- 내부 샘플 리뷰에서 `기존 대비 더 혼란스럽다` 평가가 우세

## Excluded for this phase

- 차트 이미지 기반 `LLM as judge`
- 실시간 UI 브라우저 리뷰 자동화
- 구조 zone을 이용한 추천 엔진 전체 재작성

## Risks

- zone 폭 파라미터가 종목군에 따라 과적합될 수 있음
- volume reaction 계산이 특정 뉴스성 급등 종목에 과민 반응할 수 있음
- 구조/실행 레벨 분리 후 출력 길이가 길어질 수 있음

## Mitigations

- 파라미터를 config로 외부화
- 종목 유형별 fixture를 최소 5개 이상 확보
- 사용자 출력은 구조 zone 2개/2개 + 무효화 1개로 제한
- 실행 레벨은 line 몇 개만 노출

## Implementation Notes

- 기존 `price_levels.py`는 즉시 폐기하지 않는다.
- 새 detector를 먼저 도입하고, compose 단계에서 기존 레벨과 함께 사용한다.
- `deep_dive.py`는 detector + composer를 호출하도록 확장한다.
- 차트 렌더링은 후속 단계에서 structure zone overlay를 추가할 수 있도록 인터페이스만 열어둔다.
