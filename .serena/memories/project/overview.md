# Invest-Jarvis Project Overview

## Purpose
Financial investment analysis CLI tool for Korean and US stocks. Part of a larger investment management system (currently in Plan 5 - Screener implementation).

## Tech Stack
- **Language**: Python 3.12+
- **Build/Package**: UV (uv.lock, pyproject.toml)
- **Web Framework**: Typer (CLI)
- **Data/APIs**: Pydantic, Pandas, pandas-ta, yfinance, httpx
- **ML/LLM**: LangChain + Anthropic/OpenAI
- **Testing**: pytest with asyncio support

## Architecture
- `src/` - main source code
  - `cli/` - CLI commands
  - `tools/screener/` - stock screener implementation
    - `models.py` - Pydantic models (UniverseStock, ScreenerEvidence)
    - `scoring.py` - 5-factor scoring functions
  - `providers/` - Data providers
    - `naver.py` - Naver Finance API for KR market
    - `kis.py` - KIS (Korean Investment Service) API
    - `yfinance_provider.py` - Yahoo Finance for US market
- `tests/` - test files (pytest)

## Current Work (Plan 5 - Screener)
Tasks 1-4 completed. Task 5 (UniverseBuilder) in progress.
