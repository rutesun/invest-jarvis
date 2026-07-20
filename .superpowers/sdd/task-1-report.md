# Task 1 Report: Scoring Contract Models

## Status

DONE

## 구현 내용

- `ComponentSignal`을 추가하고 `ComponentResult.signal_metadata`를 기본 빈 리스트로 확장했습니다.
- `MarketContext`를 추가해 raw OHLCV를 별도 score가 아닌 aggregation용 상태로 표현했습니다.
- `AggregationTraceEntry`, `TechnicalVerdict`, `ScoreHistoryPoint` 계약 모델을 추가했습니다.
- `TechnicalResult`에 `component_raw_total`, `adjusted_score`, `technical_verdict`, `score_history`, `score_history_warning`, `aggregation_trace`를 추가했습니다.
- `component_raw_total`과 `adjusted_score`가 지정되지 않으면 기존 `total_score`를 backfill하여 기존 단순합 동작을 유지합니다.
- 기존 `raw_dataframe`, legacy fields, `Config`, `from_analysis`는 유지했습니다.

## TDD 증거

### RED

명령:

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: 새 모델을 import할 수 없어 collection 단계에서 실패했습니다.

### GREEN

같은 명령 결과:

```text
3 passed, 1 warning
```

## 추가 검증

```bash
uv run pytest tests/tools/technical -q
```

결과: `198 passed, 2 warnings`

```bash
uv run pytest -q
```

결과: `1156 passed, 15 deselected, 3 warnings`

## 커밋

- `deab46e feat: add technical scoring contract models`

## Concerns

- 기존 `TechnicalResult.Config`에 대한 Pydantic deprecation warning이 계속 발생합니다. 이번 task의 범위를 벗어나므로 수정하지 않았습니다.
- 전체 테스트에서 기존 `pandas_ta` deprecation warning과 `tests/llm/test_analyzer.py`의 기존 coroutine warning도 확인되었습니다.

## Review Fix: component_raw_total contract

### 수정 내용

- `components`가 비어 있거나 score가 없는 legacy 객체는 기존처럼 `total_score`를 `component_raw_total`로 backfill합니다.
- 모든 component에 score가 있으면 component score 합계를 `component_raw_total`로 사용합니다.
- 명시된 `component_raw_total`이 component score 합계와 다르면 `ValueError`를 발생시킵니다.
- raw OHLCV score는 추가하지 않았습니다.

### 추가 테스트

- non-empty components에서 `component_raw_total` 생략 시 component score 합계 backfill
- non-empty components에서 명시된 `component_raw_total` 불일치 시 거부
- 기존 empty components legacy fallback 테스트 유지

### 검증

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: `5 passed, 1 warning`

```bash
uv run pytest tests/tools/technical/test_models.py tests/tools/technical/test_scorer.py tests/tools/technical/test_scoring_models.py -v
```

결과: `20 passed, 2 warnings`

경고는 기존 Pydantic `Config` deprecation과 `pandas_ta` `Copy-on-Write` deprecation입니다.

## Review Fix: require integer component scores

### 수정 내용

- `TechnicalResult.components`에 `score`가 있는 경우 실제 `int` 타입만 허용하도록 검증했습니다.
- `float`, `bool`, `str` 등 non-integer score는 `ValueError`로 거부합니다. `bool`은 Python에서 `int`의 subclass로 취급될 수 있어 `type(score) is int`으로 명시적으로 제한했습니다.
- `components={}`의 기존 `total_score` fallback과 정수 component score 합산/backfill 동작은 유지했습니다.
- raw OHLCV score나 aggregator 동작은 추가하지 않았습니다.

### 추가 테스트

- non-empty components의 float score rejection
- non-empty components의 bool score rejection
- 정수 component score 합산 후 `component_raw_total`이 `int`로 backfill되는지 검증

### 검증

RED:

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: 신규 rejection 테스트가 기대대로 실패했습니다(`9 passed, 2 failed`).

GREEN:

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: `11 passed, 1 warning`

Focused regression:

```bash
uv run pytest tests/tools/technical/test_models.py tests/tools/technical/test_scorer.py tests/tools/technical/test_scoring_models.py -v
```

결과: `26 passed, 2 warnings`

경고는 기존 Pydantic `Config` deprecation과 `pandas_ta` `Copy-on-Write` deprecation입니다.

## Review Fix: total_score contract

### 수정 내용

- 모든 component에 `score`가 있으면 component score 합계와 `total_score`가 다를 때 `ValueError`를 발생시킵니다.
- 합계가 일치하는 경우 `component_raw_total` 생략 시 합계로 backfill하고, `adjusted_score` 생략 시 검증된 `total_score`로 backfill합니다.
- `components={}`인 legacy 객체의 nonzero `total_score` fallback 동작은 유지했습니다.

### 추가 테스트

- component score 합계와 일치하는 `total_score=15` 성공 및 `component_raw_total`/`adjusted_score` backfill
- component score 합계 `15`에 `total_score=99` 지정 시 rejection

### 검증

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: `6 passed, 1 warning`

```bash
uv run pytest tests/tools/technical/test_models.py tests/tools/technical/test_scorer.py tests/tools/technical/test_scoring_models.py -v
```

결과: `21 passed, 2 warnings`

경고는 기존 Pydantic `Config` deprecation과 `pandas_ta` `Copy-on-Write` deprecation입니다.

## Review Fix: legacy component_raw_total fallback consistency

### 수정 내용

- `components`가 비어 있거나 score를 완전히 계산할 수 없는 경우에도 명시된 `component_raw_total`이 `total_score`와 다르면 `ValueError`를 발생시킵니다.
- 모든 component score가 숫자인 경우의 합계 검증과 `adjusted_score` backfill 동작은 유지했습니다.
- 빈 component에서 `component_raw_total`을 생략하는 기존 legacy fallback은 유지했습니다.

### 추가 테스트

- `components={}`, `total_score=80`, `component_raw_total=20` 지정 시 rejection
- score가 없는 non-empty component에서 `component_raw_total`이 `total_score`와 다를 때 rejection

### 검증

RED:

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: 신규 rejection 테스트 2건이 기대대로 실패했습니다(`6 passed, 2 failed`).

GREEN:

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: `8 passed, 1 warning`

Focused regression:

```bash
uv run pytest tests/tools/technical/test_models.py tests/tools/technical/test_scorer.py tests/tools/technical/test_scoring_models.py -v
```

결과: `23 passed, 2 warnings`

경고는 기존 Pydantic `Config` deprecation과 `pandas_ta` `Copy-on-Write` deprecation입니다.

## Review Fix: strict ComponentResult score

### 수정 내용

- `ComponentResult.score`를 Pydantic v2의 `StrictInt`로 변경해 component 경계에서 `20.0`과 `True`의 coercion을 거부합니다.
- 기존의 `TechnicalResult` raw dict score validation은 유지했습니다.
- raw OHLCV score와 aggregator 동작은 추가하지 않았습니다.

### 추가 테스트

- `ComponentResult(score=20.0, ...)` rejection
- `ComponentResult(score=True, ...)` rejection
- `ComponentResult(score=20, ...)` acceptance

### 검증

RED:

```bash
uv run pytest tests/tools/technical/test_scoring_models.py -v
```

결과: 신규 component rejection 테스트 2건이 기대대로 실패했습니다(`12 passed, 2 failed`).

Covering tests:

```bash
uv run pytest tests/tools/technical/test_scoring_models.py tests/tools/technical/test_models.py -v
```

결과: `23 passed, 1 warning`

Focused regression:

```bash
uv run pytest tests/tools/technical/test_models.py tests/tools/technical/test_scorer.py tests/tools/technical/test_scoring_models.py -v
```

결과: `29 passed, 2 warnings`

경고는 기존 Pydantic `Config` deprecation과 `pandas_ta` `Copy-on-Write` deprecation입니다.
