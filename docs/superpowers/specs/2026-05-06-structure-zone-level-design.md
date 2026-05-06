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
