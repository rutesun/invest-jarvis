---
name: jarvis-analyze
description: Deep dive analysis with LLM (technical + news)
args: ticker symbol (e.g., AAPL, MSFT, 005930.KS)
---

# Analyze Ticker

심층 분석 - 기술적 분석 + 뉴스 + LLM 해석

## Usage

```bash
uv run jarvis analyze {ticker} [--provider openai|anthropic]
```

## Example

```bash
uv run jarvis analyze AAPL
uv run jarvis analyze AAPL --provider anthropic
```
