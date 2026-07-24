# LLM 모델 설정 일원화 설계

- 날짜: 2026-07-24
- 상태: 설계 확정 대기
- 범위: daily_report, stock_report, deep_dive, brief 파이프라인의 LLM 모델 설정

## 배경

LLM 모델 설정이 3가지 방식으로 흩어져 있다.

| 파이프라인 | 현재 방식 | 위치 |
|---|---|---|
| daily_report (`report daily`) | Python 상수 하드코딩 (Bedrock Claude Haiku 4.5) | `src/pipelines/daily_report/config.py:38-60` |
| stock_report (`report daily-v2`) | env 변수 4단 체인 + 하드코딩 폴백 | `src/pipelines/stock_report/config.py:38-64` |
| deep_dive (`analyze`) / brief (`brief`) | CLI `--provider` 플래그만, 모델 지정 불가 | `src/cli/main.py` |

문제점:
- 지금 어떤 모델이 쓰이는지 한눈에 알 수 없다.
- 모델 교체마다 코드 수정 또는 env 변수 조합 파악이 필요하다.
- `StageLLMConfig`(create_llm + build_messages)가 daily_report와 stock_report에 중복 정의돼 있다.
- `src/llm/analyzer.py:482`가 미정의 함수 `get_llm_instance`를 import하는 죽은 폴백 경로를 갖고 있다.

## 결정 사항

1. **설정 위치**: 루트 `config.yaml`에 `llm:` 섹션 추가. `src/core/config.py`의 Pydantic `AppConfig`로 로딩.
2. **단일 소스**: config.yaml만 모델 설정 소스로 사용.
   - `STOCK_REPORT_*` env 변수 체인 전부 삭제.
   - CLI `--provider` 플래그 삭제 (`analyze`, `brief`, `report daily-v2`).
   - API 키·Bedrock 엔드포인트 등 인증 정보는 지금처럼 `.env` 유지.
3. **키 네이밍**: CLI 명령 기준 — `daily`, `daily_v2`, `analyze`, `brief`.
4. **모델**: GPT-5.6 패밀리(sol/terra/luna)만 사용. 디폴트는 terra.
5. **범위 제외**: 티커 리졸버(`gpt-4o` 하드코딩), Google Grounding(`gemini-3.5-flash`)은 현상 유지.

## config.yaml 스키마

```yaml
llm:
  defaults:
    provider: openai
    model: gpt-5.6-terra
    temperature: 0.0
  daily:                 # jarvis report daily (src/pipelines/daily_report)
    map:     { model: gpt-5.6-luna, temperature: 0.2 }   # 80K 청크 병렬, 고볼륨
    shuffle: { model: gpt-5.6-luna, temperature: 0.1 }   # 단순 정규화
    reduce:  { temperature: 0.3 }                        # terra (디폴트 상속)
    wrapup:  { temperature: 0.4 }                        # terra (디폴트 상속)
  daily_v2:              # jarvis report daily-v2 (src/pipelines/stock_report)
    extraction: { model: gpt-5.6-luna, temperature: 0.1 }  # 메시지별 병렬 추출, 고볼륨
    synthesis:  { model: gpt-5.6-sol,  temperature: 0.1 }  # 최종 리포트 작문
  analyze: {}            # jarvis analyze (src/pipelines/deep_dive) → terra
  brief:   {}            # jarvis brief (src/pipelines/brief) → terra
```

병합 규칙: 각 리프는 `defaults`를 상속하고, 명시한 필드만 오버라이드한다.

모델 배정 근거: 기존 코드의 티어 선택을 승계 — 고볼륨 스테이지(map/shuffle/extraction)는 기존에도 최저가 티어(Haiku/mini)였으므로 luna, stock_report synthesis는 기존에도 플래그십(gpt-5.4)이었으므로 sol, 나머지는 디폴트 terra.

## 컴포넌트 설계

### 1. `src/core/config.py` 확장

```python
class LLMEntryConfig(BaseModel):        # 부분 오버라이드용 — 전 필드 optional
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None

class LLMConfig(BaseModel):
    defaults: LLMEntryConfig
    daily: dict[str, LLMEntryConfig]     # map/shuffle/reduce/wrapup
    daily_v2: dict[str, LLMEntryConfig]  # extraction/synthesis
    analyze: LLMEntryConfig
    brief: LLMEntryConfig

    def resolve(self, pipeline: str, stage: str | None = None) -> ResolvedLLMConfig: ...
```

- `resolve()`는 defaults와 병합된 완성형(`provider`/`model`/`temperature` 모두 확정) 설정을 반환.
- config.yaml에 `llm:` 섹션이 없거나 일부 키가 빠져도 **위 스키마의 값과 동일한 코드 기본값**으로 동작 (Pydantic default). 설정 파일 없이도 안전.

### 2. `StageLLMConfig` 통합 → `src/llm/stage_config.py`

daily_report와 stock_report에 중복된 `StageLLMConfig`(create_llm + build_messages, Anthropic prompt caching 분기)를 `src/llm/`로 한 벌만 이동. `ResolvedLLMConfig`에서 생성.

### 3. 파이프라인별 변경

| 대상 | 변경 |
|---|---|
| `daily_report/config.py` | `MAP_LLM` 등 4개 상수 삭제 → `AppConfig.llm.resolve("daily", stage)` 참조 |
| `stock_report/config.py` | `get_semantic_extraction_llm_config`/`get_report_synthesis_llm_config`의 provider 파라미터·env 체인 삭제 → config 참조 |
| `src/cli/main.py` | `analyze`/`brief`/`report daily-v2`에서 `--provider` 삭제, config로 LLM 생성해 주입 (주입 구조 유지) |
| `src/llm/analyzer.py` | `get_llm_instance` 죽은 폴백 경로 제거 (LLM 항상 주입) |
| `docs/CLI_USAGE.md`, 스킬 문서 | `--provider` 언급 제거 |

### 4. 데이터 흐름

```
config.yaml → AppConfig.llm → resolve(pipeline, stage) → ResolvedLLMConfig
  → StageLLMConfig.create_llm() → BaseChatModel → 파이프라인에 주입
```

## 에러 처리

- config.yaml 파싱 실패·타입 불일치: Pydantic ValidationError를 그대로 표면화 (조용한 폴백 금지 — 잘못된 모델로 비용 발생 방지).
- `resolve()`에 알 수 없는 pipeline/stage 키: `KeyError`로 즉시 실패.
- provider/model 최종값이 비면 ValidationError.

## 테스트

- config 해석 단위 테스트: defaults 상속, 스테이지별 필드 오버라이드, `llm:` 섹션 부재 시 코드 기본값 일치.
- 잘못된 키/타입에서 즉시 실패하는지.
- 기존 테스트 중 `--provider`/`STOCK_REPORT_*` env를 참조하는 것 수정.
- daily_report가 Anthropic(Bedrock) → OpenAI로 바뀌므로, 전환 후 `jarvis report daily` 1회 실행으로 품질 스모크 체크 (temperature 실험값 0.2는 Haiku 기준이었음).

## 마이그레이션 참고

- 기존 `.env`의 `STOCK_REPORT_*`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`은 이 파이프라인들에서 더 이상 읽지 않는다 (티커 리졸버 등 범위 밖 코드는 기존 동작 유지).
- `LLMProvider.create`의 팩토리 기본값(`gpt-4o`, `claude-3-5-sonnet-20241022`)은 범위 밖 호출자가 있으므로 이번엔 건드리지 않는다.
