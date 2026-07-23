# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**invest-jarvis** - Korean/US stock investment analysis CLI tool.
Replacing the previous `telegram` project (built with Codex/ANTIGRAVITY). Full feature migration in progress.

## Development Setup

```bash
# Install dependencies
uv sync

# Install with dev dependencies
uv sync --dev

# Run CLI
uv run jarvis --help

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src
```

**Required environment variables** (`.env` file):
```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...       # optional, for --provider anthropic
KIS_APP_KEY=...             # Korean stocks (KIS OpenAPI)
KIS_APP_SECRET=...
TELEGRAM_API_ID=...         # Telegram message collection
TELEGRAM_API_HASH=...
```

**Package manager**: Always use `uv`, never `pip` directly.

## Code Design Principles
Apply the following principles on every code change and refactor:
- Martin Fowler: identify code smells, favor small safe refactorings, and make intent explicit in design.
- Robert C. Martin: enforce SOLID, keep functions/classes small with single responsibility, and keep dependency direction coherent.
- Kent Beck: choose the simplest design that works, remove duplication, and optimize for testability.
- Michael Feathers: identify hard-to-change code and propose seams to create testable boundaries before invasive edits.
- DDD / Eric Evans (when applicable): keep domain model and ubiquitous language consistent with business concepts.

## Testing Principles

외부 금융 API(KIS, DART, yfinance)는 응답의 '의미'가 암묵적이다 — 누적값인지 단독값인지, 행 종류가 혼재하는지 등은 타입 시스템이 잡지 못한다. 아래 두 레이어로 이를 방어한다.

**경계 계약 (Boundary Contract)**
- KIS/DART Provider 코드를 수정할 때는 해당 API 응답의 형식 가정을 `tests/harness/`의 contract 함수로 명시한다.
- contract 함수는 conftest fixture에 연결해 로드 즉시 검증되게 한다 — 가정이 깨지면 테스트 setup 단계에서 즉시 실패.
- 런타임에도 가정이 벗어나면 잘못된 값을 조용히 내려보내지 말고 `logger.warning` 또는 예외로 즉시 표면화한다.

**골든 테스트 (Golden Test)**
- 외부 API를 쓰는 신규 기능은 실제 raw 응답을 `tests/fixtures/`에 저장하고, 실제로 확인한 정답값과 비교하는 골든 테스트를 포함한다.
- 골든 테스트는 중간 로직이 아닌 전체 경로(raw 응답 → 최종 결과)를 고정한다 — KIS 응답 형식이 바뀌거나 변환 로직이 잘못 수정되면 이 테스트가 깨져서 알려준다.

## Architecture

Layered architecture — data flows one way:

```
Providers → Tools → Pipelines → CLI (src/cli/main.py)
```

| Layer | Location | Role |
|-------|----------|------|
| **Providers** | `src/providers/` | Raw data fetching (yfinance, KIS API, Naver, Telegram) |
| **Tools** | `src/tools/` | Domain logic (technical analysis, macro, news, screener) |
| **Pipelines** | `src/pipelines/` | Orchestration, combines tools into workflows |
| **LLM** | `src/llm/` | OpenAI/Anthropic adapters, report generation |
| **CLI** | `src/cli/main.py` | Typer-based entrypoint, rich output |

**Key modules**:
- `src/tools/technical/` — 5 strategy system (Trend, Oscillator, Divergence, Disparity, Risk) with 15+ indicators
- `src/providers/ticker_resolver.py` — LLM-based name→ticker resolution with 6-month cache
- `src/tools/screener/` — Universe building from Naver themes + KIS rankings, evidence scoring
- `src/tools/disclosure.py` — SEC EDGAR + DART 통합 공시 페처
- `src/tools/flow.py` — KIS API 수급 데이터 (외인/기관 순매수)

**Pipelines**:
- `src/pipelines/quick_check.py` — 기술적 분석만 (LLM 없이 빠른 체크)
- `src/pipelines/deep_dive.py` — 기술 + 펀더멘털 + 뉴스 + 공시 + 수급 + Macro + LLM 종합 분석 (Macro는 규칙 액션을 바꾸지 않고 최종 해설에만 반영)
- `src/pipelines/daily_report/` — 텔레그램 메시지 수집 → MapReduce 5단계 파이프라인 → 테마별 인사이트 (일일 시장 리포트)

## Common Commands

전체 CLI 사용법: [CLI_USAGE.md](docs/CLI_USAGE.md)

## Documentation Rules

문서 생성/업데이트 원칙과 ADR 운영 규칙의 기준 문서는 `docs/DOCUMENTATION.md`.

기능 변경(`src/`)이 있는 PR을 마무리할 때는 `docs/changes/` 변경 기록을 작성하고 `docs/changes/INDEX.md`를 갱신한다. pre-push에서 LLM이 기능 변경으로 판정하면 `docs/FEATURES.md`와 `docs/changes/` 누락 시 push가 차단된다.

## Collaboration Rules

`AGENTS.md`와 `CLAUDE.md`는 같은 수준의 최상위 작업 문서다. 모델/도구 특화 내용을 제외한 공통 규칙은 두 문서에 동일하게 반영한다.

### 응답 방식
- 코드·주석·변수명을 제외한 모든 응답은 한글로 작성
- 권한 수락 프롬프트를 유발하는 동작 직전에, 왜 그 명령/도구를 실행하는지 한 문장으로 먼저 설명할 것
- 기술적 작업 결과는 "한 줄 요약(뭘 했고 왜 중요한지)" → 상세 내용 순서로 작성
- 전문 용어 사용 시 괄호 안에 쉬운 설명 병기 (예: E402(import 위치 오류))

설계/브레인스토밍 단계에서 사용자가 선택해야 하는 질문을 할 때는 아래 형식을 따른다:

- 질문 전에 **왜 이 질문이 필요한지** 1-3문장으로 먼저 설명할 것
- 선택지가 있으면 각 옵션의 **의미, 장점, 단점**을 짧게 함께 설명할 것
- 추천안이 있으면 이유와 함께 명시할 것
- 한 번에 하나의 질문만 할 것

목표는 사용자가 질문의 의도와 각 선택지의 차이를 바로 이해하고, 추가 왕복 없이 판단할 수 있게 만드는 것이다.

## Skills

Location: `.Codex/skills/`
**Rule**: Simple CLI wrappers only. Show command + brief description + example. Keep under 40 lines.
**Exception**: 워크플로를 담는 프로세스 스킬(예: `work-log`)은 허용하며 40줄을 넘어도 된다. 단, 하나의 워크플로에 집중한다.

### Worklog (작업 일지)

작업 중 아래 체크포인트에서 `work-log` 스킬을 호출해 `docs/worklog/<topic>.md`에 엔트리를 남긴다.

- 설계 결정이 확정된 직후 → `[Decision]`
- 버그 수정이 검증된 후 → `[Bug]`
- 도구 부재로 막히거나 맥락을 잘못 잡았을 때 → `[Friction]`
- 접근을 폐기·전환할 때 → `[Pivot]`

worklog는 change-record/ADR의 1차 재료다. 누락은 감수하며(스킬 기반 트레이드오프), 강제 훅은 두지 않는다.
