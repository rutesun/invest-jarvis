# Unified Technical Analysis Contract 설계 스펙

- **작성일**: 2026-07-20
- **상태**: 사용자 승인 v3
- **대상**: `check`, `analyze`, `brief`
- **범위**: 공통 3년 기술 분석, 명령 책임 정리, Analyze 종합 LLM 해설, 장기 이동평균 표시

---

## 1. 배경

모든 파이프라인은 같은 `TechnicalScorer`를 사용하지만 조회 기간은 같지 않다.

- `check`, ticker report: `TechnicalAnalysisTool` 기본값인 `1y`
- `analyze`, `brief`: 호출부에서 `period="3y"` 지정

cRSI와 Supertrend 같은 누적 지표, 52주 고저점, 장기 이동평균은 입력 OHLCV 범위의 영향을 받는다. 따라서 같은 종목이라도 파이프라인에 따라 raw component score, `adjusted_score`, `technical_verdict`가 달라질 수 있다.

또한 `report ticker`는 다중 종목 기술 확인이라는 점에서 `check`와 역할이 겹치고, 생성한 LLM을 실제로 사용하지 않는다. `analyze`의 LLM 호출도 기술·뉴스·재무·공시·수급을 하나의 최종 해설에 모두 전달하지 않아 사용자가 기대하는 종합 분석과 차이가 있다.

## 2. 목표

동일한 ticker와 동일한 OHLCV snapshot이면 어떤 소비 파이프라인에서도 다음 기술 결과가 같아야 한다.

- 8개 component score와 `component_raw_total`
- `adjusted_score`
- `technical_verdict`의 action, entry mode, confidence, 신규 진입 가능 여부
- verdict reasons, cautions, invalidation level
- 최근 5거래일 `score_history`
- `aggregation_trace`

사용자 관점의 명령 책임은 다음으로 고정한다.

- `check`: 여러 후보 종목의 기술 상태를 빠르게 비교
- `analyze`: 한 종목의 기술·뉴스·재무·공시·수급·Macro를 종합 해설
- `brief`: 보유·워치 종목의 Playbook 기반 일괄 점검

시장 가격이 바뀐 뒤 별도로 실행하거나 provider가 서로 다른 snapshot을 반환한 경우까지 같은 값을 보장하지는 않는다.

## 3. 비목표

- 세 명령의 최종 목적과 출력 형식을 같게 만들지 않는다.
- 뉴스, 공시, 수급, fundamental, Macro, Playbook을 `check`에 추가하지 않는다.
- Macro나 LLM 해설로 technical score를 변경하지 않는다.
- `technical_verdict`를 Playbook의 최종 매매 판단으로 승격하지 않는다.
- `brief`의 LLM 입력에 Macro를 추가하지 않는다.
- `screen`처럼 `TechnicalAnalysisTool`을 사용하지 않는 후보 발굴 경로는 포함하지 않는다.

## 4. 설계

### 4.1 단일 기술 분석 계약

`src/tools/technical/tool.py`에 단일 source of truth를 둔다.

```python
CANONICAL_TECHNICAL_PERIOD = "3y"
```

`TechnicalAnalysisTool.execute()`의 기본 `period`를 이 상수로 지정한다. 제품 파이프라인은 기간을 하드코딩하지 않고 기본 계약을 사용한다. 연구나 테스트 목적으로 다른 `period`를 명시하는 기능은 유지한다.

```text
check ───┐
analyze ─┼─> TechnicalAnalysisTool(period=3y) ─> TechnicalScorer
brief ───┘
```

### 4.2 다중 ticker check

`check`는 기존 단일 ticker 호출과 함께 여러 positional ticker를 받는다.

```bash
uv run jarvis check AAPL
uv run jarvis check AAPL MSFT NVDA
```

각 ticker는 독립적으로 분석한다. 일부 ticker 실패가 나머지를 막지 않으며 모든 ticker를 처리한 뒤 하나라도 실패했으면 non-zero exit code를 반환한다. `--detail-history`는 모든 성공 ticker에 동일하게 적용한다. Macro는 조회하거나 표시하지 않는다.

### 4.3 report ticker 삭제

`report ticker`는 deprecated alias를 남기지 않고 삭제한다.

- `report ticker` CLI와 `run_daily_report`, 전용 formatter 삭제
- `TickerReportPipeline` 삭제
- 관련 테스트와 문서 삭제·수정
- 사용되지 않던 LLM/provider 의존 제거

다중 종목 기술 확인은 `check AAPL MSFT NVDA`가 대체한다. Macro는 `analyze`와 `brief`에서만 표시한다.

### 4.4 Analyze Macro와 최종 LLM 해설

Macro는 기술 분석 입력이 아닌 별도 시장 context다. `analyze`는 `MacroTool`을 기본 실행해 CLI에 표시한다. 실패하면 경고를 남기고 나머지 분석을 계속한다.

기술·뉴스·재무의 전문 LLM 호출은 각 데이터만 해석한다. 모든 규칙 계산이 끝난 뒤 하나의 최종 종합 LLM 해설을 생성한다.

```text
규칙 기반 decision summary·scenarios
technical verdict·adjusted score·score history
news analysis
fundamental summary
disclosures
flow
Macro snapshot
Playbook verdict
structure·execution levels
        ↓
최종 LLM 종합 해설
```

최종 LLM은 이미 확정된 action과 timing을 변경하지 않는다. 다음만 설명한다.

- 해당 action의 핵심 근거와 반대 근거
- Macro가 판단을 강화하거나 약화하는 정도
- 뉴스·공시·수급·fundamental과 기술 신호의 정합성
- 핵심 가격 조건과 무효화 기준

현재 `IntegratedAnalysisInput`에 news와 Macro가 빠지고, `actionable_signal` 호출에는 받을 수 있는 news/fundamental 입력이 전달되지 않는 공백을 함께 해소한다. 최종 사용자 출력에서 중복되는 독립 recommendation을 만들지 않고 고정 decision에 대한 해설을 제공한다.

### 4.5 Brief 책임

`brief`는 기존처럼 Macro를 포트폴리오 상단에 표시한다. 종목별 기술 결과는 공통 3년 계약을 사용한다. 최종 action은 계속 보유 종목 exit 규칙과 워치 종목 Playbook gate가 결정하며, 뉴스·공시는 참고 정보로 유지한다.

### 4.6 SMA 100·200 표시와 기울기

`IndicatorCalculator`에 `SMA_100`을 추가하고 `IndicatorSnapshot`에 SMA 100 값과 SMA 100·200 slope 상태를 제공한다.

기울기는 기존 Minervini와 시장 regime의 장기 이동평균 방향 기준과 같은 21거래일 lookback을 사용한다.

```text
slope_pct = (현재 SMA / 21거래일 전 SMA - 1) × 100

slope_pct > +0.5%  → ↗ 상승
-0.5% 이상 +0.5% 이하 → → 보합
slope_pct < -0.5% → ↘ 하락
```

`check`와 `analyze`의 주요 기술 지표 섹션에서 SMA 100·200을 항상 행으로 표시한다.

```text
SMA 100: $123.45 · ↗ 상승 (+0.82%/21일)
SMA 200: $110.20 · → 보합 (+0.12%/21일)
```

신규 상장 등 데이터가 부족하면 행을 생략하지 않고 `N/A · — 데이터 부족`으로 표시한다. 이 slope는 표시용 정보이며 이번 변경에서 score나 verdict 조건에는 추가하지 않는다.

## 5. 오류와 성능

- 3년 조회 실패는 각 파이프라인의 기존 기술 분석 실패 정책을 따른다.
- Macro 실패는 `analyze`와 `brief` 전체를 중단하지 않는다.
- KIS는 100일 단위 pagination으로 3년 조회 시 `check`가 느려질 수 있다.
- 이번 변경에서는 cache를 추가하지 않는다. 동일성 계약을 우선하고 실제 지연을 측정한 뒤 별도 성능 작업으로 판단한다.

## 6. 테스트

1. `TechnicalAnalysisTool` 기본 실행이 provider에 `period="3y"`를 전달하는지 검증한다.
2. `check`, `analyze`, `brief`가 자체 period override 없이 공통 Tool 계약을 사용하는지 검증한다.
3. 동일 fixture의 core `TechnicalResult`에서 component/raw/adjusted/verdict/history가 같음을 검증한다.
4. 다중 ticker `check`가 성공·실패를 격리하고 최종 exit code를 올바르게 반환하는지 검증한다.
5. `report ticker`, `TickerReportPipeline`과 관련 문서·테스트가 제거됐는지 검증한다.
6. `analyze`가 Macro를 표시하고 최종 LLM 입력에 전달하며 Macro 실패 시 계속 실행하는지 검증한다.
7. 최종 LLM 입력에 news, fundamental, disclosure, flow, Macro, Playbook, levels, 고정 decision이 포함되는지 검증한다.
8. 최종 LLM 출력이 고정 action을 변경하지 않는지 검증한다.
9. SMA 100·200 값과 21일 slope의 상승·보합·하락·데이터 부족 경계를 검증한다.
10. `check`와 `analyze`가 SMA 100·200 행을 항상 출력하는지 검증한다.
11. 기존 scoring regression fixture(PANW, BE, 005930.KS)를 다시 실행한다.

## 7. 문서

- `docs/FEATURES.md`에 공통 3년 기술 계약, Analyze Macro 해설, SMA 장기 기울기를 명시한다.
- `docs/changes/`에 변경 기록을 추가하고 INDEX를 갱신한다.
- `docs/CLI_USAGE.md`에서 다중 ticker `check`를 안내하고 `report ticker`를 제거한다.
- `jarvis-check` 스킬의 6개 component 설명을 현재 8개 component와 3년 기준으로 정정한다.

## 8. 완료 조건

- 제품 코드에 기술 분석 기간 문자열이 중복 하드코딩되지 않는다.
- 같은 OHLCV snapshot의 기술 결과가 파이프라인과 무관하게 동일하다.
- `check`가 여러 ticker를 처리하고 `report ticker` 관련 코드가 제거된다.
- Macro는 `analyze`와 `brief`에만 표시된다.
- `analyze` 최종 LLM 해설이 모든 분석 소스와 고정 decision을 입력받는다.
- SMA 100·200과 slope 상태가 `check`·`analyze`에 항상 표시된다.
- 관련 단위·통합·회귀 테스트와 lint가 통과한다.
