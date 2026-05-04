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
- `src/pipelines/daily_report/` — 텔레그램 메시지 수집 → evidence-first claim extraction/linking → brief/dump/ops 출력 (일일 시장 리포트)

## Common Commands

전체 CLI 사용법: [CLI_USAGE.md](docs/CLI_USAGE.md)

## Documentation Rules

모든 구현 작업 시 아래 규칙을 반드시 따를 것:

- **새 기능/파이프라인 추가** → `README.md`의 Features 섹션 업데이트
- **새 CLI 커맨드 추가** → `docs/CLI_USAGE.md`의 Commands 섹션에 커맨드 + 설명 + 예시 추가
- **새 모듈/패키지 추가** → `docs/` 아래 대응하는 문서 생성 또는 기존 문서 업데이트
- **아키텍처 변경** → 이 파일(AGENTS.md)의 Architecture 섹션 업데이트
- **의존성 추가** → `README.md`의 설치/설정 섹션 반영

문서 업데이트는 코드 변경과 **같은 커밋**에 포함할 것.

## Skills

Location: `.Codex/skills/`
**Rule**: Simple CLI wrappers only. Show command + brief description + example. Keep under 20 lines.
