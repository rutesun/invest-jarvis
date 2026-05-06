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
- `src/pipelines/deep_dive.py` — 기술 + 펀더멘털 + 뉴스 + 공시 + 수급 + LLM 종합 분석
- `src/pipelines/ticker_report.py` — 매크로 지표 + 다중 종목 기술 분석 (티커 기반 일일 리포트)
- `src/pipelines/daily_report/` — 텔레그램 메시지 수집 → MapReduce 5단계 파이프라인 → 테마별 인사이트 (일일 시장 리포트)

## Common Commands

전체 CLI 사용법: [CLI_USAGE.md](docs/CLI_USAGE.md)

## Documentation Rules

문서 생성/업데이트 원칙과 ADR 운영 규칙의 기준 문서는 `docs/DOCUMENTATION.md`.

## Collaboration Rules

`AGENTS.md`와 `CLAUDE.md`는 같은 수준의 최상위 작업 문서다. 모델/도구 특화 내용을 제외한 공통 규칙은 두 문서에 동일하게 반영한다.

설계/브레인스토밍 단계에서 사용자가 선택해야 하는 질문을 할 때는 아래 형식을 따른다:

- 질문 전에 **왜 이 질문이 필요한지** 1-3문장으로 먼저 설명할 것
- 선택지가 있으면 각 옵션의 **의미, 장점, 단점**을 짧게 함께 설명할 것
- 추천안이 있으면 이유와 함께 명시할 것
- 한 번에 하나의 질문만 할 것

목표는 사용자가 질문의 의도와 각 선택지의 차이를 바로 이해하고, 추가 왕복 없이 판단할 수 있게 만드는 것이다.

## Skills

Location: `.Codex/skills/`
**Rule**: Simple CLI wrappers only. Show command + brief description + example. Keep under 20 lines.
