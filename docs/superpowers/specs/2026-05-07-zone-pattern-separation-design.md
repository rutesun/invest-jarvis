# Zone / Pattern Separation Design

## Summary

`jarvis analyze`의 차트 해석을 `패턴 검출`과 `구조 레벨 탐지`로 분리한다.

핵심 방향은 아래 세 가지다.

- `Swing Extractor`를 공통 입력층으로 두고, 이후 해석을 `Zone Engine`과 `Pattern Engine`으로 나눈다.
- `박스`, `지지`, `저항`, `전환 저항/지지`는 `Zone Engine`에서 계산한다.
- `W`, `M`, `삼각형`, `컵핸들`, `헤드앤숄더` 등 형상 패턴은 `Pattern Engine`에서 계산한다.

이번 설계의 목적은 사람이 차트에서 보는 `의미 있는 박스권`과 `시간을 두고 형성된 패턴`을 서로 망치지 않게 만드는 것이다.

## Problem

현재 구조는 아래 한계를 가진다.

- `structure_zones.py`는 swing 저점/고점 클러스터에서 바로 수요/공급 zone을 만든다.
- `chart_patterns.py`는 별도 로직으로 패턴을 계산한다.
- 두 엔진이 공통 pivot 해석 계층 없이 각자 동작하기 때문에, 같은 차트를 서로 다른 언어로 설명한다.
- 구조 레벨은 `시간적으로 밀집된 반응 구간`을 잘 설명하지 못하고, 패턴 엔진은 `W/삼각형` 같은 시간 분산 구조를 계속 따로 본다.
- 결과적으로 `박스권`, `지지/저항`, `패턴`의 책임 경계가 사용자 입장에서 모호하다.

대표적으로 PGY, NVTS 같은 차트에서는 아래 혼선이 발생한다.

- 사람이 보기엔 `옛 박스권이 현재는 전환 저항`인데, 구현은 오래된 demand touch count와 supply cluster를 섞어 버린다.
- 최근 구조에선 `박스 상단/하단`이 중요하지만, 현재 로직은 `단일 수요/공급 zone`으로 잘라 보여준다.
- 반대로 `W 패턴`은 시간 떨어진 swing 관계가 중요하므로 최근 밀집도만 보면 놓친다.

## Goals

- 공통 swing 추출 레이어를 만든다.
- 구조 레벨 탐지를 `components` 레벨 모듈로 이동한다.
- 패턴 검출과 구조 레벨 탐지를 서로 독립적으로 튜닝 가능하게 만든다.
- 사용자 출력에서 `박스`, `지지`, `저항`, `전환 저항/지지`를 패턴과 분리해 표현한다.
- `무효화`는 현재 액션 방향과 가격 위치에 맞는 구조만 사용한다.
- 회귀 테스트에서 `왜 그 구조가 선택됐는지`를 episode 단위로 설명할 수 있어야 한다.
- 사용자가 리포트 첫 3줄 안에서 `현재 구조가 박스인지, 박스 하단/상단인지, 애매한지`를 판단할 수 있어야 한다.
- 의미 있는 구조가 없으면 억지로 박스/존을 만들지 않고 `no_clear_structure`를 출력할 수 있어야 한다.

## Non-Goals

- 기존 `chart_patterns.py`의 패턴 종류를 이번 설계에서 대폭 늘리지 않는다.
- `price_levels.py`의 pivot/fib/MA 실행 레벨 계산 규칙 자체는 이번 범위에서 크게 바꾸지 않는다.
- LLM 프롬프트 전체를 다시 설계하지 않는다. 다만 입력 계약은 새 구조에 맞게 갱신한다.

## Chosen Approach

`Swing Extractor`를 공통 기반으로 두고, 그 위에 `Zone Engine`과 `Pattern Engine`을 별도 component로 두는 구조를 채택한다.

### Why this approach

- `박스권`과 `W/삼각형`은 같은 차트에서도 중요하게 보는 시간이 다르다.
- `Zone Engine`은 최근성, episode 밀집도, 거래량 반응을 우선해야 한다.
- `Pattern Engine`은 swing sequence, neckline, 수렴/확산 관계를 우선해야 한다.
- 공통 입력은 공유하되, 해석 함수를 분리해야 서로의 품질을 깎아먹지 않는다.

## File Structure

목표 구조는 아래와 같다.

```text
src/tools/technical/
├─ components/
│  ├─ swing_extractor.py
│  ├─ chart_patterns.py
│  └─ structure_zones.py
├─ level_composer.py
├─ price_levels.py
├─ structure_zone_inspector.py
├─ models.py
└─ tool.py / scorer.py
```

### Responsibility split

- `components/swing_extractor.py`
  - 공통 pivot/high/low 추출
  - swing strength, timestamp, volume reaction 기초 데이터 생성
- `components/structure_zones.py`
  - box detection
  - support/resistance zone detection
  - former support -> resistance, former resistance -> support 승격
  - invalidation candidate selection
- `components/chart_patterns.py`
  - W, M, triangle, flag, cup/handle, H&S 등 패턴 계산
  - `Swing Extractor` 결과를 재사용
- `level_composer.py`
  - zone/pattern/price level 최종 payload 조합
- `structure_zone_inspector.py`
  - zone 결과 디버깅, candidate/episode/selection 비교

## Data Flow

```text
OHLCV DataFrame
  -> IndicatorCalculator / Snapshot
  -> SwingExtractor
      -> ZoneEngine
      -> PatternEngine
  -> PriceLevelCollector
  -> LevelComposer
  -> DeepDivePipeline
  -> LLM / CLI
```

핵심 원칙은 아래와 같다.

- `SwingExtractor`는 공통 입력층이다.
- `ZoneEngine`은 구조 레벨만 책임진다.
- `PatternEngine`은 형상 패턴만 책임진다.
- `LevelComposer`는 탐지를 하지 않고 조합만 한다.

## Data Model

### SwingPoint

- `index`
- `timestamp`
- `price`
- `swing_type`: `high` | `low`
- `strength`
- `volume`
- `atr`

### TouchEvent

- `timestamp`
- `price`
- `event_type`: `support_touch` | `resistance_touch`
- `reaction_pct`
- `volume_multiple`
- `source_swing_indices`
- `price_basis`: `high` | `low` | `close` | `hlc3`
- `side`: `support` | `resistance`
- `box_edge`: `lower` | `upper` | `none`

### TouchEpisode

- `start_date`
- `end_date`
- `touch_count`
- `event_type`
- `lower_bound`
- `upper_bound`
- `reaction_score`
- `volume_score`
- `recency_score`
- `episode_score`
- `source_swing_indices`
- `price_basis`
- `side`
- `box_edge`

### StructureBox

- `box_type`: `active_box` | `former_supply_box` | `former_demand_box`
- `lower_bound`
- `upper_bound`
- `start_date`
- `end_date`
- `lower_touch_episode_count`
- `upper_touch_episode_count`
- `alternation_score`
- `duration_score`
- `volume_score`
- `recency_score`
- `respect_score`
- `total_score`
- `reasons`

### StructureZone

기존 `StructureZone` 모델은 유지하되, `zone_type`을 아래로 확장한다.

- `support`
- `resistance`
- `former_support`
- `former_resistance`
- `invalidation`

기존 `demand/supply/balance` 표현은 내부 호환 단계에서만 허용하고, 최종 사용자 출력에서는 제거한다.

### StructureLevelsPayloadV2

새 외부 계약은 `StructureLevelsPayloadV2`로 고정한다.

- `summary_label`: `active_box` | `former_supply_box` | `former_demand_box` | `support_zone` | `resistance_zone` | `no_clear_structure`
- `headline`
- `why`
- `active_box`
- `support_zones`
- `resistance_zones`
- `former_levels`
- `invalidation`
- `patterns_reference`

호환 정책은 아래처럼 고정한다.

- `components/*`와 `level_composer.py`는 오직 `StructureLevelsPayloadV2`만 만든다.
- top-level `structure_zones.py` wrapper만 legacy `demand/supply/balance` 입력 또는 출력 호환을 책임진다.
- `deep_dive.py`, `llm/analyzer.py`, CLI는 Phase 1 종료 시점부터 `StructureLevelsPayloadV2`만 소비한다.
- legacy wrapper는 migration 완료 후 제거 대상이며, 새 호출 경로에서 직접 참조하지 않는다.

## Swing Extractor Design

### Purpose

공통 pivot 집합을 만들어 zone/pattern 양쪽이 같은 원재료를 보게 한다.

### Contract

`SwingExtractor`는 `SwingExtractorOutput`을 반환한다.

- `df`
- `snapshot`
- `swing_points`
- `swing_windows`
- `params`

엔진별 입력 계약은 아래처럼 고정한다.

- `ZoneEngineInput = snapshot + swing_points`
- `PatternEngineInput = df + snapshot + swing_points + swing_windows`

즉, pattern engine은 `swings only`가 아니라 `df + swings`를 함께 받는다. 이유는 neckline, breakout, local slice 검증이 여전히 raw OHLC 문맥을 필요로 하기 때문이다.

### Rules

- 기본 입력: `df`, `snapshot`
- 반전 최소 폭:
  - `max(1.5 * ATR14, 6%)`
- 최소 swing 간격:
  - `5 ~ 10 거래일`
- 너무 약한 micro swing은 strength 기준으로 제거

### Output guarantees

- 같은 구간에서 지나치게 촘촘한 pivot이 남지 않는다.
- pattern/zone 두 엔진이 동일한 swing timestamp/price 집합을 본다.
- `chart_patterns.py`는 extractor 밖에서 다시 독자적인 peak universe를 만들지 않는다.
- pattern에 필요한 local slice 정보는 `swing_windows`로 재사용한다.

## Zone Engine Design

## 1. First-class concept: Box

박스는 `zone의 부산물`이 아니라 `구조 해석의 1급 개념`으로 둔다.

### Box candidate rules

- 하단 터치 episode `>= 2`
- 상단 터치 episode `>= 2`
- 터치 순서가 `L-H-L-H` 또는 `H-L-H-L`처럼 번갈아 나타남
- 패턴 길이 `>= 20 거래일`
- box 폭은 중심가 대비 `4% ~ 25%`
- box 내부 체류 일수 비율이 일정 이상

### Box scoring

- `touch_balance_score`
- `alternation_score`
- `duration_score`
- `volume_score`
- `recency_score`
- `post_break_respect_score`

### Box state

- `active_box`: 현재가가 box 내부
- `former_supply_box`: box 하단 이탈 후 현재가가 box 아래
- `former_demand_box`: box 상단 돌파 후 현재가가 box 위

## 2. Touch episode instead of raw touch count

핵심 원칙:

- raw touch count는 직접 점수화하지 않는다.
- 날짜가 가까운 touch event를 `episode`로 먼저 묶는다.
- zone relevance는 `episode 품질`로 계산한다.

### Episode grouping rule

- 같은 가격대 touch event가 `7~15 거래일` 이내에 이어지면 한 episode로 묶는다.
- episode 간 공백이 길면 다른 regime으로 본다.

### Episode score

- episode 내 touch count
- touch 후 반등/하락 크기
- 거래량 반응
- episode recency

### Zone score

- strongest episode score
- recent episode bonus
- independent episode count
- 오래된 단발 event decay

즉, `17회 터치`보다 `2024-06 ~ 2024-09에 집중된 강한 support episode`가 더 중요하다고 본다.

## 3. Support / Resistance extraction

박스로 설명되지 않는 나머지 구조에서 zone을 만든다.

### Support zone

- low-side touch episode가 반복
- touch 이후 반등 반응 존재
- 현재가 아래 또는 현재가를 포함하는 zone 우선

### Resistance zone

- high-side touch episode가 반복
- touch 이후 하락 반응 존재
- 현재가 위 또는 현재가를 포함하는 zone 우선

### Former support / resistance

- 과거 support가 깨졌고 현재가 위에 있으면 `former_support -> resistance`
- 과거 resistance가 돌파됐고 현재가 아래에 있으면 `former_resistance -> support`

## 4. Invalidation rule

무효화는 현재 액션 방향과 가격 위치를 따라야 한다.

- long/investor 관점 기본 무효화:
  - 현재가 아래 support zone 또는 active box lower bound
- support가 없으면 fallback:
  - swing low
  - 150/200MA

절대 허용하지 않는 것:

- 현재가보다 위에 있는 zone을 long invalidation으로 쓰는 것

## 5. Selection priority and exclusion

최종 구조 선택은 아래 우선순위를 따른다.

1. `active_box`
2. `nearest support/resistance zone`
3. `former_support` / `former_resistance`
4. `fallback invalidation`

구체 규칙은 아래처럼 고정한다.

| 상황 | 남기는 것 | 제거/강등 |
|---|---|---|
| `active_box` 하단과 support zone이 같은 가격대 | `active_box` 하단만 대표 구조로 사용 | support zone은 evidence-only |
| `active_box` 상단과 resistance zone이 같은 가격대 | `active_box` 상단만 대표 구조로 사용 | resistance zone은 evidence-only |
| former resistance와 현재 resistance zone이 중첩 | 최근성이 높은 쪽 1개만 유지 | 나머지는 drop |
| invalidation과 support zone이 사실상 동일 | support zone을 invalidation source로 승격 | 별도 invalidation line 생성 금지 |
| 구조 점수가 임계치 미달 | `no_clear_structure` | 억지 구조 생성 금지 |

추가 cap 규칙:

- 대표 노출은 `active_box` 최대 1개
- `support_zones` 최대 2개
- `resistance_zones` 최대 2개
- `former_levels` 최대 2개
- 동일 가격대 중복은 하나로 합치고, 이유 문자열에 근거를 병합한다.

## Pattern Engine Design

Pattern engine은 기존 `chart_patterns.py`를 유지하되, 입력을 `SwingExtractor` 결과 중심으로 재정렬한다.

### Pattern engine responsibilities

- swing sequence 기반 형상 인식
- neckline/breakout/support_level 계산
- `days_ago`와 timing 정보 유지

### Pattern engine non-responsibilities

- 현재 유효한 support/resistance zone 정의
- active/former box 상태 분류
- invalidation 후보 선택

즉, `W 패턴`은 pattern engine이, `11~13 구조 지지 box`는 zone engine이 설명한다.

## Output Contract

최종 사용자 출력은 아래 구조를 기본으로 둔다.

### Top judgment block

- `현재 가장 중요한 구조`
- `headline` 한 줄
- `why` 한 줄

예시:

- `현재 가장 중요한 구조: former_supply_box`
- `headline: 20~25 박스 하단 이탈 이후 전환 저항이 우세`
- `why: 최근 3개월 반등이 같은 상단에서 반복 거절되고 현재가는 박스 아래에 있다`

### Structure block

- `현재 활성 박스`
- `상위 전환 저항 박스`
- `핵심 지지 존`
- `핵심 저항 존`
- `구조 무효화`

`밸런스 존`이라는 표현은 최종 출력에서 제거한다.

`no_clear_structure`일 때는 아래처럼 축약한다.

- `현재 가장 중요한 구조: no_clear_structure`
- `headline: 최근 가격 반응이 분산돼 뚜렷한 박스/핵심 지지/저항이 없다`
- `why: 최근 episode 점수가 분산되고 대표 구조 임계치를 넘는 후보가 없다`

### Pattern block

- 감지된 패턴 최대 2개
- freshness가 높은 패턴 우선
- stale pattern은 `참고`로만 내린다
- pattern은 항상 `주도`가 아니라 구조 대비 `주도` 또는 `참고`를 함께 표기한다.

### Execution block

- pivot / ATR / fib / MA line
- 구조와 충돌할 경우 구조 우선

### Product acceptance examples

- `PGY`에서는 박스권이 뚜렷하면 `former_supply_box` 또는 `active_box`가 첫 줄에 와야 한다.
- `NVTS`에서는 최근 의미 없는 오래된 터치 군집보다 최근 episode가 먼저 선택돼야 한다.
- `ALAB`처럼 추세가 강해 박스보다 추세 지지가 더 자연스러우면 `support_zone`이 첫 줄에 올 수 있다.
- 구조가 애매한 종목은 `no_clear_structure`가 허용돼야 한다.

## Migration Plan

### Phase 1. Output contract lock and adapter boundary

- `StructureLevelsPayloadV2` 추가
- top-level `structure_zones.py`를 legacy adapter로 한정
- `deep_dive.py`, `llm/analyzer.py`, CLI 소비 계약을 V2로 고정
- golden output fixture 추가

### Phase 2. File boundary refactor

- `components/swing_extractor.py` 추가
- `structure_zones.py` 로직을 `components/structure_zones.py`로 이동

### Phase 3. Zone engine rewrite

- raw touch -> touch episode 전환
- box candidate / box scoring 추가
- support/resistance extraction 재구성
- `no_clear_structure` 임계치 추가
- selection priority / dedupe / cap 구현

### Phase 4. Pattern engine integration

- `chart_patterns.py`가 `SwingExtractor` 결과를 사용할 수 있게 리팩터링
- 기존 패턴 검출 결과가 유지되는지 회귀 테스트 추가

### Phase 5. Output / prompt update

- `headline/detail` 분리 반영
- `현재 가장 중요한 구조` + `why` 노출
- pattern의 `주도/참고` 표기 반영

### Shadow mode

- 마이그레이션 중에는 old detector와 new detector를 같은 fixture에 동시에 돌린다.
- `inspect_structure_zone.py`는 old/new diff를 함께 출력할 수 있어야 한다.
- diff 항목은 `selected structure`, `headline source`, `invalidation`, `display caps`를 포함한다.

## Testing Strategy

### Unit tests

- `tests/tools/technical/components/test_swing_extractor.py`
- `tests/tools/technical/components/test_structure_zones_v2.py`
- `tests/tools/technical/components/test_chart_patterns_shared_swings.py`

### Regression fixtures

대표 fixture:

- `PGY`
- `NVTS`
- `ALAB`
- `066970.KQ`

각 fixture에서 아래를 본다.

- active box / former box가 자연스러운가
- support/resistance가 현재가 위치와 일치하는가
- invalidation이 현재가 아래 구조에서 선택되는가
- pattern 결과가 기존 대비 깨지지 않는가
- `no_clear_structure`가 필요한 종목에서 억지 구조를 만들지 않는가
- `headline` 첫 줄만 읽어도 현재 구조 해석이 가능한가

### Contract and golden tests

- `tests/tools/technical/test_structure_levels_payload_v2.py`
- `tests/pipelines/test_deep_dive_structure_contract.py`
- `tests/cli/test_analyze_structure_golden.py`

검증 포인트:

- `level_composer -> deep_dive -> llm/analyzer -> CLI`가 같은 구조 타입을 끝까지 유지하는가
- legacy adapter를 거치지 않는 새 경로에서 `demand/supply/balance`가 다시 나타나지 않는가
- `headline`, `why`, `summary_label`이 fixture 기대값과 일치하는가

### Inspector enhancements

`inspect_structure_zone.py`는 아래를 추가한다.

- `touch_events`
- `touch_episodes`
- `box_candidates`
- `selected_boxes`
- `legacy_vs_v2_diff`
- `selection_priority_trace`

이렇게 해야 `왜 이 존이 나왔는지`를 raw touch count가 아니라 episode 기반으로 설명할 수 있다.

## Risks

- zone engine과 pattern engine이 같은 swing extractor를 쓰면서도 해석 기준이 달라 혼동될 수 있다.
- box detection이 과도하게 공격적이면 구조가 너무 많아질 수 있다.
- episode 규칙이 너무 보수적이면 박스가 잘 안 잡힐 수 있다.

대응:

- output contract를 먼저 고정한다.
- fixture 회귀를 종목 단위로 유지한다.
- inspector에서 episode와 box 후보를 직접 보이게 한다.

## Decision

이번 설계의 최종 결정은 아래와 같다.

- `zone`과 `pattern`은 분리한다.
- `박스`는 `Zone Engine` 소속이다.
- `박스 돌파`는 `Pattern Engine`이 해석한다.
- `components` 안에는 탐지 로직만 둔다.
- top-level technical 모듈에는 조합과 출력 로직만 둔다.
