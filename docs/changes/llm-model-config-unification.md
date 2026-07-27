# Change Record: LLM 모델 설정 일원화 (config.yaml llm 섹션)

**Status**: Draft
**Date**: 2026-07-24
**PRs**: #52
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

LLM 모델 설정이 3가지 방식으로 흩어져 있었다: daily_report는 Python 상수 하드코딩(Bedrock Claude Haiku 4.5), stock_report는 `STOCK_REPORT_*` env 변수 4단 체인 + 하드코딩 폴백, deep_dive/brief는 CLI `--provider` 플래그만 있고 모델 지정이 불가능했다. 지금 어떤 모델이 쓰이는지 한눈에 알 수 없고, 모델 교체마다 코드 수정 또는 env 조합 파악이 필요했다. GPT-5.6 패밀리(sol/terra/luna) 전환을 계기로 설정을 단일 소스로 통합했다.

## What

1. **config.yaml `llm:` 섹션 신설**: 4개 파이프라인(daily/daily_v2/analyze/brief)의 provider/model/temperature를 한 곳에서 관리. 키는 CLI 명령 기준(`daily`, `daily_v2`)으로 정해 모듈명(daily_report/stock_report)과 명령명 불일치로 인한 혼동을 피했다. `defaults` 상속 + 필드 단위 오버라이드 구조.
2. **`AppConfig.llm` + `resolve(pipeline, stage)`** (`src/core/config.py`): defaults 병합된 완성형 설정을 반환. `llm:` 섹션이 없거나 일부 스테이지가 빠져도 코드 기본값(배포 yaml과 동일)으로 동작 — 부분 지정 시 형제 스테이지 기본값을 보존하기 위해 default dict 위에 병합한다.
3. **잘못된 설정 즉시 실패**: `extra="forbid"`(필드 오타 거부), `provider: Literal["openai","anthropic"]`, 빈 모델명 차단(`min_length=1`), 알 수 없는 pipeline/stage는 KeyError. 오타가 조용히 기본 모델로 폴백돼 잘못된 모델로 비용이 발생하는 경로를 막았다.
4. **공용 `StageLLMConfig` 통합** (`src/llm/stage_config.py`): daily_report와 stock_report에 중복 정의돼 있던 create_llm/build_messages(Anthropic 프롬프트 캐싱 분기)를 한 벌로 이동. `resolve_stage_llm(pipeline, stage)`가 config 해석과 LLM 생성 seam을 제공한다.
5. **provider 파라미터 스레딩 제거**: stock_report의 classify/synthesize/pipeline/pdf_classify/pdf_ingest에서 `provider: str`을 함수마다 넘기던 것을 진입점 1회 해석 + `StageLLMConfig` 주입으로 교체. 실험(tuning)은 env 몽키패칭(`with_model_override`) 대신 명시적 config 주입으로 전환.
6. **CLI `--provider` 삭제**: `analyze`/`brief`/`report daily-v2`/`report ingest-pdf`. 모델 변경은 config.yaml 수정으로 대체. `STOCK_REPORT_*` env 체인도 전부 삭제.
7. **모델 배정**: 기존 티어 선택을 승계 — 디폴트 `gpt-5.6-terra`, 고볼륨 스테이지(map/shuffle/extraction, 기존 Haiku/mini 티어) `gpt-5.6-luna`, daily-v2 synthesis(기존 플래그십 gpt-5.4) `gpt-5.6-sol`.
8. **골든 정합성 테스트**: 배포 config.yaml의 llm 섹션 == 코드 기본값을 테스트로 고정해 둘의 drift를 차단.

## Before / After

```
Before: 모델 변경 = 코드 수정(daily_report/config.py 상수) 또는 env 조합
        (STOCK_REPORT_SYNTHESIS_OPENAI_MODEL → STOCK_REPORT_OPENAI_MODEL → OPENAI_MODEL → 하드코딩)
        uv run jarvis analyze AAPL --provider anthropic   # 모델 지정 불가

After:  config.yaml 한 곳 수정
        llm:
          daily_v2:
            synthesis: { model: gpt-5.6-sol, temperature: 0.1 }
        uv run jarvis analyze AAPL   # config.yaml llm.analyze 참조
```

## Impact

- **BREAKING(스크립트)**: `--provider`를 넘기던 기존 cron/스크립트는 typer unknown-option으로 즉시 실패한다(침묵 아님). 플래그 제거 필요.
- **daily 리포트 모델 전환**: Bedrock Claude Haiku → OpenAI gpt-5.6 luna/terra. cron 환경에 `OPENAI_API_KEY`(게이트웨이 사용 시 `OPENAI_BASE_URL`) 필요, `CLAUDE_CODE_USE_BEDROCK` 경로는 daily에서 더 이상 사용하지 않는다.
- **env 무시**: `.env`의 `STOCK_REPORT_*`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`은 이 4개 파이프라인에서 더 이상 읽지 않는다.
- **품질 검증**: 7/15 동일 데이터로 신구 A/B 비교 — 새 모델이 정확성(구모델 종목코드 오류 30건+ vs 거의 0건), 분석 깊이, 실행 가능성 전 항목 우세. temperature 재튜닝 불필요 판정.

## Constraints

- 티커 리졸버(`gpt-4o` 하드코딩), Google Grounding(`gemini-3.5-flash` + `STOCK_REPORT_GOOGLE_MODEL` env), `LLMProvider.create` 팩토리 기본값은 범위 밖 호출자가 있어 이번에 건드리지 않았다.
- `report daily-v2 --config-path`는 normalize 설정 전용 — llm 섹션은 항상 루트 config.yaml에서 읽는다(제거한 파라미터 스레딩을 재도입하지 않기 위해 문서 명시로 처리, help 텍스트에 반영).
- brief는 LLM 초기화 실패 시 규칙 원문으로 폴백하는 기존 동작을 유지하되, config 해석 오류는 try 밖으로 빼서 즉시 실패하게 했다.
- 스테이지 항목을 부분 오버라이드하면 미지정 필드는 (스테이지 기본값이 아닌) defaults에서 상속된다 — config.yaml에 주석으로 경고.

## Related

- 설계: `docs/superpowers/specs/2026-07-24-llm-model-config-design.md`, `docs/superpowers/plans/2026-07-24-llm-model-config.md`
- ADR: 없음
- FEATURES.md: analyze(입력), Daily Report 파이프라인 표(모델), Stock Report PDF Ingest(옵션) 갱신
- 후속: A/B 비교에서 확인된 파이프라인 개선 후보 — ① wrapup 프롬프트에 매크로 스냅샷-본문 모순 감지 지시, ② shuffle 단계 유사 테마 dedup 강화, ③ M&A·정책 이벤트 보존 가드
