## Development Setup

```bash
uv sync              # Install dependencies
uv run jarvis --help # Run CLI
uv run pytest        # Run tests
```

**Environment variables**: `.env` 파일 생성 (OPENAI_API_KEY, KIS_APP_KEY 등)

**Package manager**: Always use `uv`, never `pip` directly.

**자세한 가이드**: [@docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

## Architecture

```
Providers → Tools → Pipelines → CLI
```

- **Providers**: 데이터 수집 (yfinance, KIS API, Naver, Telegram)
- **Tools**: 도메인 로직 (technical, macro, news, screener)
- **Pipelines**: 워크플로우 오케스트레이션
- **LLM**: OpenAI/Anthropic 어댑터
- **CLI**: Typer 기반 진입점

**상세 아키텍처**: [@docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Common Commands

전체 CLI 사용법: [@docs/CLI_USAGE.md](docs/CLI_USAGE.md)

```bash
uv run jarvis check AAPL        # 빠른 기술적 분석 (LLM 불필요)
uv run jarvis analyze AAPL      # 심층 분석 (기술 + 뉴스 + LLM)
uv run jarvis report            # 일일 시장 리포트
uv run jarvis portfolio         # 포트폴리오 모니터링 (KIS API)
uv run jarvis screen            # 시장 스크리너
uv run jarvis telegram fetch    # 텔레그램 채널 메시지 수집
uv run jarvis telegram catch-up # 누락분 보충 수집
```

## Documentation Rules

**모든 구현 작업 시 반드시 문서 업데이트 (같은 커밋에 포함)**:

| 변경 | 업데이트 문서 |
|------|---------------|
| 새 기능/파이프라인 | `README.md` Features 섹션 |
| 새 CLI 커맨드 | `docs/CLI_USAGE.md` |
| 아키텍처 변경 | `docs/ARCHITECTURE.md` |
| 개발 프로세스 변경 | `docs/DEVELOPMENT.md` |

**상세 가이드**: [@docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

## Skills

Location: `.claude/skills/`

**Rule**: Simple CLI wrappers only. Show command + brief description + example. Keep under 20 lines.
