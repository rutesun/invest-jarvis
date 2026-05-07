# Structure Zone 테스트/튜닝 가이드

## 목적

구조 zone 로직은 "무슨 zone이 선택됐는가"와 "왜 그 zone이 선택됐는가"를 함께 봐야 튜닝이 된다.
이 문서는 structure zone 관련 테스트를 어디서 검증하는지, 로컬에서 어떤 순서로 튜닝하는지 정리한 운영 가이드다.

## 테스트 구조

### 1. 단위 테스트

구성 요소별 규칙을 빠르게 검증한다.

- `tests/tools/technical/test_structure_zones.py`
  - zone 정렬
  - invalidation fallback
  - 점수/기본 설정 모델
- `tests/tools/technical/test_level_composer.py`
  - 구조 레벨과 실행 레벨 payload 조합
  - invalidation label, summary 생성

### 2. 회귀 테스트

실제 가격 CSV fixture로 detector/composer가 함께 동작했을 때 출력이 깨지지 않는지 본다.

- `tests/tools/technical/test_structure_zone_regression.py`
  - fixture 기반 payload 생성
  - `structure_levels`, `execution_levels`, `invalidation` 형태 검증
  - `candidates`, `selected_zones`, `score_breakdown` artifact 저장 검증

### 3. 계약 테스트

구조 zone 결과가 상위 계층까지 정상 전달되는지 본다.

- `tests/pipelines/test_deep_dive.py`
  - `DeepDivePipeline`이 structure/execution level을 조합해 전달하는지 검증
- `tests/llm/test_analyzer.py`
  - LLM 입력 포맷에 structure context가 반영되는지 검증
- `tests/cli/test_analyze_output.py`
  - 최종 출력에서 구조 레벨/실행 레벨/판단 요약이 기대한 형태로 보이는지 검증

## Fixture

현재 structure zone 회귀 fixture는 아래 3개다.

- `tests/fixtures/technical/structure_zones/033100.KQ.csv`
- `tests/fixtures/technical/structure_zones/066970.KQ.csv`
- `tests/fixtures/technical/structure_zones/ALAB.csv`

fixture는 "실제 튜닝에 다시 써볼 대표 사례"를 남기는 용도다. 한국/미국 종목을 섞어 두는 이유도 detector가 시장별 가격 스케일에서 지나치게 치우치지 않는지 보기 위해서다.

## 로컬 튜닝 루프

### 1. fixture 갱신

```bash
uv run python scripts/export_structure_zone_fixtures.py
```

실데이터를 다시 fixture로 고정할 때만 사용한다. 튜닝 중에는 fixture를 자주 바꾸기보다, 같은 fixture에 대해 선택 결과가 어떻게 달라지는지 먼저 본다.

### 2. 회귀 테스트 단독 실행

```bash
uv run pytest tests/tools/technical/test_structure_zone_regression.py -v
```

zone 선택 결과, artifact 저장 형식, 기본 payload 모양이 유지되는지 가장 먼저 확인하는 테스트다.

### 3. 핵심 구조 테스트 묶음 실행

```bash
uv run pytest \
  tests/tools/technical/test_structure_zones.py \
  tests/tools/technical/test_level_composer.py \
  tests/tools/technical/test_structure_zone_regression.py -v
```

점수 규칙, payload 조합, fixture 회귀를 같이 확인할 때 쓴다.

### 4. 상위 계약까지 확인

```bash
uv run pytest \
  tests/pipelines/test_deep_dive.py \
  tests/llm/test_analyzer.py \
  tests/cli/test_analyze_output.py -v
```

구조 zone 결과가 pipeline, LLM 입력, CLI 출력까지 자연스럽게 이어지는지 확인한다.

### 5. 실제 CLI spot check

```bash
MPLCONFIGDIR=/private/tmp/mpl-jarvis uv run jarvis analyze ALAB
```

테스트는 통과하지만 사람이 보기엔 어색한 경우가 있으므로, 튜닝 후에는 실제 analyze 출력까지 한 번 확인하는 편이 좋다.

### 6. inspect 스크립트로 후보/점수 확인

```bash
uv run python scripts/inspect_structure_zone.py ALAB
uv run python scripts/inspect_structure_zone.py --fixture-csv tests/fixtures/technical/structure_zones/ALAB.csv
uv run python scripts/inspect_structure_zone.py ALAB --output artifacts/structure_zones/ALAB-inspect.json
uv run python scripts/inspect_structure_zone.py ALAB --compare-json artifacts/structure_zones/ALAB-baseline.json
```

이 스크립트는 구조 zone 디버깅용이다.

- 기본값: 사람이 읽는 텍스트 출력
- `--json`: stdout JSON 출력
- `--output`: inspect payload JSON 저장
- `--compare-json`: 저장된 inspect JSON과 현재 결과를 비교해 selection/score diff 출력
- `--fixture-csv`: 네트워크 호출 없이 fixture 기준 inspect

즉, `analyze`는 최종 사용자 결과를 보고, `inspect_structure_zone.py`는 왜 그 zone이 뽑혔는지를 보는 용도다.

## 무엇을 비교하나

튜닝할 때는 단순히 "존이 나왔는가"보다 아래 항목을 같이 본다.

- `structure_levels`
  - demand zone / supply zone 개수와 순서
  - invalidation 기준이 어디를 잡는지
- `execution_levels`
  - 구조 레벨 아래에서 어떤 실행 레벨이 노출되는지
- `score_breakdown`
  - `touch_score`
  - `recency_score`
  - `volume_reaction_score`
  - `confluence_score`
  - `total_score`

즉, 결과 비교는 "선택된 존"과 "선택 이유 점수"를 같이 봐야 의미가 있다.

## Artifact 해석

회귀 테스트는 JSON artifact를 `tmp_path`에 기록한다.

- `candidates`: detector가 고려한 전체 zone 후보
- `selected_zones`: 최종 구조/실행 레벨 결과
- `score_breakdown`: 후보별 점수 상세

이 artifact는 테스트 중 검증용으로 쓰는 임시 산출물이다. 현재는 장기 보존용 inspect 스크립트나 별도 저장소는 없다.

## 운영 원칙

- 파라미터를 바꿀 때는 먼저 회귀 테스트로 selection drift를 본다.
- fixture를 바로 고치기보다, 기존 fixture에서 왜 다른 zone이 선택됐는지 먼저 설명 가능해야 한다.
- 마지막에는 CLI 출력까지 보고 사람이 읽을 때 자연스러운지 확인한다.
