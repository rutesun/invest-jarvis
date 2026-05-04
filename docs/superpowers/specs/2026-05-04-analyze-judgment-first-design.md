# Design: Judgment-First Analyze Output

**작성일**: 2026-05-04  
**상태**: APPROVED  
**대상**: `jarvis analyze`

## Problem Statement

현재 `jarvis analyze`는 데이터는 많지만, 사용자가 가장 먼저 알고 싶은 질문에 바로 답하지 못한다.

- 지금 이 종목에서 가장 중요한 변수 1-2개가 무엇인지 바로 보이지 않는다.
- 여러 팩터가 병렬로 나열되어, 무엇이 주도 요인인지 사용자가 직접 해석해야 한다.
- 최종 액션이 `추천`, `종합 인사이트`, `실행 가능한 투자 시그널`로 흩어져 있어 판단 축이 흔들린다.
- 한국 주식에서는 단위/이상치/오래된 패턴 같은 신뢰도 문제도 함께 존재한다.

사용자 우선순위는 아래와 같다.

1. 판단력
2. 신뢰도
3. 행동성
4. 읽는 맛

따라서 이번 설계의 목적은 문장을 부드럽게 만드는 것이 아니라, `지금 무엇이 가장 중요한지`를 먼저 선언하고 그 뒤에 데이터를 붙이는 판단 중심 출력으로 재설계하는 것이다.

## Goals

- 결과 최상단에서 `주도 팩터`, `핵심 변수`, `액션`을 10초 안에 읽을 수 있게 한다.
- 모든 팩터를 보여주되, `주도 / 보조 / 참고`로 구분해 해석 우선순위를 명확히 한다.
- 액션은 `기본 시나리오 1개 + 반대 시나리오 1개`로 단순화한다.
- 원시 데이터는 유지하되, 판단 이후에 읽히도록 순서를 재구성한다.
- Phase 2에서 한국 주식 신뢰도 문제와 오래된 패턴/이상치 문제를 별도 가드레일로 강화한다.

## Non-Goals

- `analyze`에서 원시 데이터 양을 줄이는 것
- 새로운 외부 데이터 소스를 이번 Phase 1에 반드시 추가하는 것
- 기존 technical/fundamental/news/disclosure/flow 도구 자체를 대규모 교체하는 것
- Daily report 파이프라인까지 한 번에 재설계하는 것

## Solution Overview

`jarvis analyze` 위에 `judgment layer`를 추가한다.

기존 구조:

- 기술 요약
- 펀더멘털 요약
- 뉴스 요약
- 공시/수급 나열
- 액션 패널

새 구조:

1. 상단 3줄 요약
2. 판단 요약
3. 팩터 분류 (`주도 / 보조 / 참고`)
4. 액션 시나리오 (`기본 / 반대`)
5. 원시 데이터

핵심 차이는 `모든 팩터를 같은 무게로 보여주지 않는다`는 점이다. 출력은 풍부하게 유지하되, 먼저 해석을 주고 그다음 숫자를 증거로 제공한다.

## Output Structure

### 1. Top Summary

결과 맨 위에는 아래 3줄을 고정 배치한다.

- `주도 팩터`
- `핵심 변수`
- `액션`

예시:

- `주도 팩터: 수급`
- `핵심 변수: 신고가 구간에서 외인/기관 매수 지속, RSI 과열 해소 여부`
- `액션: 관망 | 조정_대기`
  `지금 추격 매수보다 20일선 근처 눌림 확인 후 진입이 유리`

주도 팩터가 명확하지 않으면 `주도 팩터: 혼합`으로 표시한다.

`혼합`은 top summary 전용 상태값이다. 팩터 자체의 역할 분류는 여전히 `주도 / 보조 / 참고` 3단계만 사용한다.

핵심 데이터가 부족하거나 계산 가능한 팩터가 너무 적으면 `주도 팩터: 혼합` 대신 `주도 팩터: 판단 보류`를 사용한다.

`판단 보류`일 때는 결과만 표시하지 않고, 바로 아래에 짧은 이유를 함께 명시한다.

예시:

- `주도 팩터: 판단 보류`
  `이유: 수급 데이터 부재 + event 신호 약함 + 기술/밸류 점수 차이 미미`

### 2. Body Order

본문 순서는 아래와 같이 고정한다.

1. `판단 요약`
2. `팩터 분류`
3. `액션 시나리오`
4. `원시 데이터`

### 3. Factor Classification Section

모든 팩터는 아래 3단계로 분류한다.

- `주도`
- `보조`
- `참고`

`참고`는 다음을 모두 포함한다.

- 신호는 있지만 너무 오래됨
- 신호는 있으나 현재 액션과 직접 연결되지 않음
- 다른 더 강한 팩터에 밀림

`참고`로 분류된 팩터는 반드시 강등 이유를 함께 표시한다.

예시 이유:

- `145일 전 완성된 패턴이라 현재 액션과 거리 있음`
- `신호는 유효하지만 수급/가격보다 설명력이 약함`
- `데이터는 있으나 현재 시점 actionability가 낮음`

예시:

- `주도: 수급`
  `외인/기관 5일 연속 순매수, 신고가 구간에서도 매수 유지`
- `보조: 기술`
  `신고가 돌파와 거래량 급증은 긍정적이나 RSI 과열로 추격 부담`
- `참고: 더블바닥 패턴`
  `패턴은 감지됐지만 145일 전 완성이라 현재 액션 근거로는 약함`

### 4. Scenario Section

시나리오는 2개만 제공한다.

- `기본 시나리오`
- `반대 시나리오`

분기 기준은 `가격 레벨 우선`, `팩터 변화 보조`다.

예시:

- `기본 시나리오`
  `20일선 위 유지 + 수급 유지 시 눌림 후 재상승`
- `반대 시나리오`
  `20일선 이탈 + 거래량 둔화 시 과열 해소가 아니라 추세 훼손으로 해석`

### 5. Raw Data Section

기존 출력의 원시 데이터 섹션은 유지한다.

- 기술 지표
- 펀더멘털
- 뉴스
- 공시
- 수급
- 차트 관련 정보

다만 노출 순서를 뒤로 보내, 판단 이후에 검증용으로 읽히게 한다.

## Judgment Layer Design

새 `factor prioritizer`는 각 팩터를 평가해 `주도 / 보조 / 참고`로 분류한다.

### 평가 대상 팩터

- `technical`
- `flow`
- `event`
  Phase 1에서는 `뉴스 + 공시 메타데이터`만 포함한다.
  구조화된 실적/가이던스 추출은 아직 범위 밖이며, 이는 Phase 2 이후 별도 확장 대상으로 둔다.
- `valuation`
  밸류에이션, 성장 둔화, 수익성, 재무 건전성 포함

### 평가 기준

각 팩터는 최소 아래 3개 기준으로 평가한다.

- `freshness`: 지금 판단에 얼마나 최신인가
- `magnitude`: 주가 방향을 설명할 만큼 강한가
- `actionability`: 지금 매수/대기/회피 판단에 바로 연결되는가

Phase 1에서는 이 기준을 규칙 기반으로 계산한다. LLM은 최종 문장 생성에만 사용하고, 우선순위 계산 자체는 코드가 담당한다.

### Scoring Contract (Phase 1)

각 팩터(`technical`, `flow`, `event`, `valuation`)는 아래 3개 점수를 `0-5` 범위의 정수로 계산한다.

- `freshness_score`
- `magnitude_score`
- `actionability_score`

총점은 단순 합산(`0-15`)으로 계산한다.

기본 분류 규칙:

- 총점이 `10점 이상`이고 2위 팩터와의 차이가 `2점 이상`이면 해당 팩터를 `주도`로 분류한다.
- 총점이 `7점 이상`이면 `보조` 후보로 분류한다.
- 총점이 `7점 미만`이면 `참고`로 분류한다.
- 1위와 2위의 차이가 `2점 미만`이면 top summary의 `주도 팩터`는 `혼합`으로 표시한다.

tie-break 규칙:

- 동점이면 `freshness_score`가 높은 팩터 우선
- freshness도 같으면 `actionability_score`가 높은 팩터 우선
- 그래도 같으면 `혼합`

결측 데이터 규칙:

- 해당 팩터 입력이 없으면 해당 팩터는 점수 계산에서 제외한다.
- 계산 가능한 팩터가 `2개 미만`이면 top summary는 `주도 팩터: 판단 보류`를 사용한다.
- 1위 팩터 총점이 `7점 미만`이면 action은 `관망 | 보류`로 제한한다.

freshness 최소 가드레일:

- `60일 초과` 완료 패턴은 `주도` 불가
- `120일 초과` 완료 패턴은 `보조` 불가, `참고`만 가능
- 현재 액션과 직접 연결되지 않는 오래된 패턴은 action 근거에서 제외한다

### Classification Rules

- `주도`
  다른 팩터보다 분명히 앞설 때만 부여
- `보조`
  현재 액션 해석에 의미가 있지만 최우선은 아닌 팩터
- `참고`
  맥락 설명에는 필요하지만 액션 중심 근거로는 약한 팩터

`혼합`은 분류 role이 아니라 decision summary 상태값이다. 즉 개별 팩터는 여전히 `주도 / 보조 / 참고`로만 표시하고, top summary에서만 `주도 팩터: 혼합`을 사용할 수 있다.

### Why Rule-First

이번 설계는 판단력을 높이되, 먼저 신뢰 가능한 하한선을 만든다.

- 오래된 패턴이 갑자기 핵심 이유로 올라오는 문제를 줄일 수 있다.
- 한국 주식의 이상치/단위 문제를 LLM 서사보다 먼저 제어할 수 있다.
- 같은 입력에서 우선순위가 크게 흔들리는 문제를 줄일 수 있다.

Phase 2 이후에는 `규칙 기반 후보 선정 + LLM 서술 강화` 형태로 확장할 수 있지만, Phase 1의 최종 분류 자체는 규칙 기반으로 유지한다.

## Action Rules

최종 액션은 `주도 팩터 + 보조 팩터`로 결정한다. `참고` 팩터는 맥락 설명용이며, 액션을 뒤집는 핵심 근거로 쓰지 않는다.

### Canonical Judgment Artifact

Phase 1의 최종 판단 source of truth는 `AnalyzeDecisionSummary`다.

- top summary의 `주도 팩터 / 핵심 변수 / action / timing / action_sentence`는 모두 `AnalyzeDecisionSummary`에서만 렌더링한다.
- 기존 `technical_summary.recommendation`은 사용자-facing 최종 판단으로 사용하지 않는다.
- 기존 `integrated_analysis.recommendation`과 `action_summary`는 evidence-only 설명으로 강등한다.
- `actionable_signal` 패널은 `AnalyzeDecisionSummary.action/timing`을 재표현하는 보조 출력으로만 유지하며, 독립적으로 다른 판단을 생성하지 않는다.

### Action Output Shape

구조화된 필드는 유지한다.

- `action`: `매수 | 매도 | 관망`
- `timing`: `지금 | 조정_대기 | 보류`

여기에 자연어 한 줄을 추가한다.

예시:

- `관망 | 조정_대기`
- `지금 추격 매수보다 20일선 눌림 확인 후 진입이 유리`

### Low-Evidence Fallback

아래 조건이면 top summary는 강한 단정 대신 `판단 보류` 상태를 사용한다.

- 계산 가능한 팩터가 `2개 미만`
- 1위 팩터 총점이 `7점 미만`
- 핵심 데이터에 신뢰도 경고가 있는 경우

이 경우에도 원시 데이터는 그대로 출력하되, action은 `관망 | 보류`로 제한한다.

또한 `판단 보류`에는 아래 중 하나 이상의 이유를 반드시 함께 노출한다.

- 어떤 핵심 데이터가 비어 있는지
- 어떤 팩터들이 비슷해서 우열을 가르기 어려운지
- 어떤 값이 신뢰도 경고로 action 근거에서 제외됐는지

### Scenario Logic

- `기본 시나리오`
  현재 가장 가능성이 높은 흐름
- `반대 시나리오`
  현재 판단이 깨지는 흐름

시나리오 분기는 아래 원칙을 따른다.

- 주 기준: 가격 레벨
- 보조 기준: 수급 둔화, 거래량 감소, 이벤트 무효화 같은 팩터 변화

이 설계에서 invalidation은 가격과 조건을 함께 다룬다. 가격 주도 종목은 주요 이탈/돌파 레벨이 중심이 되고, 이벤트 주도 종목은 실적 미스, 가이던스 변경, 공시 업데이트 같은 조건을 함께 명시한다.

## Phase Plan

### Phase 1: Judgment-First Output

목표는 판단 중심 출력으로 재구성하는 것이다.

범위:

- 상단 3줄 요약 추가
- `주도 / 보조 / 참고` 분류 섹션 추가
- `기본 / 반대` 시나리오 섹션 추가
- 기존 원시 데이터 섹션 순서 재구성
- 액션 구조화 값 + 자연어 한 줄 추가
- `factor prioritizer` 도입
- 최소 freshness 가드레일 적용
  - `60일 초과` 완료 패턴은 `주도` 불가
  - `120일 초과` 완료 패턴은 `보조` 불가, `참고`만 가능
  - 오래된 패턴은 action 근거에서 제외
- 최종 판단의 단일 source of truth를 `AnalyzeDecisionSummary`로 고정
- 저증거 상태에서 `판단 보류` fallback 적용

### Phase 2: Reliability Guardrails

목표는 판단 레이어의 신뢰도를 높이는 것이다.

범위:

- 한국 주식 펀더멘털 단위/통화 정규화
- 비정상 수치 sanity check
  예: 비현실적 배당 수익률, 이상치 현금흐름
- 액션 근거로 사용할 수 없는 값의 제외 또는 경고
- 팩터 충돌이 큰 경우 자연어 판단에 불확실성 명시
- structured earnings/guidance extraction 및 event 신뢰도 확장

## Proposed Code Changes

### New/Changed Models

새 모델을 추가하거나 기존 결과 dict를 typed object로 정리한다.

Phase 1에서는 기존 `DeepDivePipeline`의 broad dict 반환 구조를 유지하고, 그 위에 additive wrapper 성격의 typed object를 추가한다. 기존 반환 구조 자체를 전면 교체하는 리팩터링은 Phase 1 범위에 포함하지 않는다.

- `FactorAssessment`
  - `factor_type`
  - `role`
  - `freshness_score`
  - `magnitude_score`
  - `actionability_score`
  - `summary`
  - `role_reason`
  - `evidence`
- `AnalyzeDecisionSummary`
  - `leader`
  - `core_variables`
  - `action`
  - `timing`
  - `action_sentence`
  - `defer_reason`
- `AnalyzeScenario`
  - `name`
  - `trigger_price_levels`
  - `confirming_factors`
  - `invalidation_conditions`
  - `expected_path`
  - `recommended_action`

### Pipeline Changes

`DeepDivePipeline`에서 기존 tool 결과를 모은 뒤 아래 단계를 추가한다.

1. tool result collection
2. factor assessment
3. decision summary generation
4. scenario generation
5. render-ready output assembly

### Rendering Changes

`format_deep_dive_output()`와 `display_actionable_signal()` 책임을 재조정한다.

- `format_deep_dive_output()`
  판단 중심 markdown 본문 렌더링
- `display_actionable_signal()`
  액션 필드만 보여주는 보조 패널로 축소하거나, top summary와 중복되지 않도록 역할 분리

권장 방향은 `Top Summary`를 markdown 본문 상단으로 옮기고, 패널은 `액션/시나리오 강조`용으로만 유지하는 것이다. 이 패널은 독립 판단을 만들지 않고 canonical judgment를 재표현만 한다.

## Testing Strategy

### Unit Tests

- 팩터별 점수 계산 규칙 테스트
- `주도`, `보조`, `참고` 분류 테스트
- `혼합`과 `판단 보류` top-summary 상태 테스트
- 오래된 패턴이 `참고`로 분류되는 테스트
- `참고` 강등 이유가 함께 생성되는지 테스트
- `판단 보류` 이유가 함께 생성되는지 테스트
- `기본 / 반대` 시나리오 생성 테스트
- invalidation 조건 생성 테스트

### CLI Snapshot Tests

- 상단 3줄이 항상 먼저 나오는지 확인
- `주도 / 보조 / 참고` 섹션 구조 확인
- 액션 구조화 값과 자연어 한 줄이 함께 출력되는지 확인
- 원시 데이터 섹션이 여전히 유지되는지 확인

### Acceptance Tests

아래 질문에 결과가 바로 답해야 한다.

- 지금 이 종목에서 제일 중요한 변수는 무엇인가?
- 왜 그 팩터가 주도인가?
- 지금 해야 할 행동은 무엇인가?
- 어떤 가격/조건에서 판단이 깨지는가?

이 acceptance 검증은 snapshot만으로 끝내지 않고, KR/US, 기술 주도/event 주도, stale pattern 케이스를 포함한 small golden set으로 보완한다.

## Success Criteria

- 사용자가 상단 3줄만 읽고도 현재 판단을 요약할 수 있다.
- 모든 팩터가 노출되지만, 같은 무게로 보이지 않는다.
- `참고`와 `판단 보류`에는 상태만이 아니라 이유가 함께 붙는다.
- 오래된 패턴이 `주도` 또는 `보조`로 과대 노출되지 않는다.
- 액션이 `추천`, `종합 인사이트`, `시그널` 사이에서 서로 충돌하지 않는다.
- 원시 데이터는 유지되지만, 판단 이후 검증용으로 읽히는 구조가 된다.

## Risks

- 규칙이 너무 단순하면 `혼합`이 과도하게 늘어날 수 있다.
- 지표 점수화가 과도하면 다시 기계적인 느낌을 줄 수 있다.
- 기존 패널과 markdown 상단 요약이 중복되면 출력이 장황해질 수 있다.

이를 피하기 위해 Phase 1에서는 기준을 적게 두고, 역할 분리와 출력 순서 개선에 집중한다.

## Rollout Recommendation

권장 구현 순서는 아래와 같다.

1. top summary + factor classification 렌더링
2. factor prioritizer 규칙 도입
3. scenario section 도입
4. 기존 action panel 역할 축소 또는 정리
5. Phase 2 신뢰도 가드레일 적용
