# ADR-0010: TechnicalScorer 점수를 raw total과 adjusted verdict로 분리

**상태:** 수락
**날짜:** 2026-07-16
**관련 설계:** `docs/superpowers/specs/2026-07-16-technical-scoring-redesign-design.md`

## 컨텍스트

`TechnicalScorer`는 component analyzer 결과를 단순 합산해 `total_score`를 만든다. 이 계약은 빠르고 설명하기 쉽지만, 같은 높은 점수라도 의미가 다를 수 있다.

- 상승 추세가 강해 보유할 만한 상태
- 신규 진입이 가능한 상태
- 급등 후 과열되어 신규 추격 매수를 피해야 하는 상태
- 하락 추세 속 반등 신호라서 watch에 가까운 상태

사용자가 삼성전자, BE, PANW 구간을 날짜별로 검토한 결과, 기존 점수는 추세/리스크 계기판으로 유효하지만 행동 의미가 섞여 있었다. 별도 raw OHLCV score를 만들면 같은 가격 데이터에서 나온 점수 체계가 두 개가 되어 해석이 더 어려워진다. 따라서 기존 component score는 보존하되, OHLCV는 별도 점수가 아니라 판단 context로 사용해야 한다.

이번 결정은 `technical_verdict`와 `playbook`의 책임 경계도 함께 고정한다. `technical_verdict`는 가격/거래량 기반 technical-only hint이고, 실제 보유 여부·계좌 비중·position sizing을 포함한 최종 판단은 `playbook` 계층이 맡는다.

## 고려한 옵션

### 옵션 A: raw OHLCV 별도 score 추가

- 장점:
  - 기존 component 점수와 독립적으로 검산할 수 있다.
  - 가격/거래량만 보는 단순 기준을 만들기 쉽다.
- 단점:
  - 같은 OHLCV에서 두 점수가 나와 사용자-facing 해석이 중복된다.
  - "어떤 점수를 믿어야 하는가"라는 새 문제가 생긴다.
  - 기존 component analyzer의 역할이 약해지고 회귀 비교가 어려워진다.

### 옵션 B: 기존 `total_score` 산식을 전면 교체

- 장점:
  - user-facing 숫자를 한 번에 바꿀 수 있다.
  - 고점 추격과 하락 추세 반등 신호를 강하게 억제할 수 있다.
- 단점:
  - 현재 테스트와 downstream 코드가 `total_score == sum(component scores)` 계약을 전제로 한다.
  - `analyze_decision`, `quick_check`, `deep_dive`, `brief`의 해석이 동시에 흔들린다.
  - 기존 분석 결과와 새 결과의 차이를 디버깅하기 어렵다.

### 옵션 C: `component_raw_total + adjusted_score + technical_verdict`로 확장

- 장점:
  - 기존 component 합계는 `component_raw_total`로 보존해 회귀 비교가 가능하다.
  - user-facing 판단은 `adjusted_score`와 `technical_verdict`로 분리할 수 있다.
  - OHLCV는 `MarketContext`로만 쓰므로 별도 raw score 중복이 생기지 않는다.
  - `playbook`과 technical scorer의 책임 경계가 명확해진다.
- 단점:
  - 결과 모델과 출력 경로가 늘어난다.
  - component analyzer가 구조화 metadata를 제공해야 Aggregator가 문자열 파싱을 피할 수 있다.
  - compatibility 기간 동안 `total_score`, `component_raw_total`, `adjusted_score`를 함께 관리해야 한다.

## 결정

옵션 C를 채택한다.

구체적으로 다음 구조를 확정한다.

1. `total_score`는 1차 구현에서 기존 component 단순합 계약을 유지한다.
2. 같은 값을 `component_raw_total`에도 명시해 디버그와 회귀 비교 기준으로 삼는다.
3. `adjusted_score`는 `ScoreAggregator`가 `MarketContext`, component score, structured metadata를 바탕으로 계산한다.
4. raw OHLCV는 별도 score가 아니라 `MarketContext` 상태로만 사용한다.
5. component analyzer는 `signal_metadata`를 제공하고, Aggregator는 `signals` 문자열을 파싱하지 않는다.
6. `technical_verdict`는 `buy`, `add`, `hold`, `watch`, `reduce`, `avoid` 중 하나를 반환하는 technical-only hint로 제한한다.
7. `technical_verdict`에는 `reasons`, `cautions`, `invalidation_level`, `score_trend_summary`를 포함한다.
8. ticker 분석 출력에는 최근 5거래일 `score_history`를 포함한다. 각 날짜의 점수는 해당 날짜까지의 OHLCV만 사용해 계산한다.
9. `playbook`은 최종 매매 판단의 상위 계층으로 유지한다.

## 결과

좋아지는 점:

- 높은 점수가 "신규 매수"인지 "보유 관리"인지 구분된다.
- 하락 추세의 과매도·다이버전스가 단독으로 buy를 만들 가능성이 낮아진다.
- 과열 상태는 종목 부정이 아니라 신규 진입 제한으로 표현된다.
- 사용자는 최종 판단 이유와 최근 5거래일 점수 흐름을 함께 볼 수 있다.
- 기존 단순합 계약이 보존되어 기존 테스트와 과거 결과 비교가 가능하다.

트레이드오프:

- technical result 모델이 커진다.
- component analyzer가 metadata를 작성해야 하므로 초기 구현 범위가 커진다.
- `total_score` 의미를 재정의하려면 별도 deprecation ADR이 필요하다.

운영 기준:

- `adjusted_score` 산식은 LLM이 판단하지 않는다.
- LLM은 rule output으로 확정된 verdict와 score history를 설명만 한다.
- 신규 API 호출 없이 이미 확보한 OHLCV dataframe에서 `score_history`를 만든다.
- future leakage 방지를 contract test로 고정한다.
