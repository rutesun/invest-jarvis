---
name: jarvis-analyze
description: Deep dive analysis with LLM (technical + news)
args: ticker symbol (e.g., AAPL, MSFT)
---

# Deep Dive Analysis

LLM 기반 심층 분석 (기술 + 뉴스 + 해석)

## Usage

```bash
uv run jarvis analyze {ticker}
uv run jarvis analyze {ticker} --provider anthropic
```

## What it does

- 기술적 분석 + LLM 해석
- 최근 뉴스 감성 분석
- 투자 추천 및 근거 제시
- OpenAI/Anthropic 지원

## Example

```bash
uv run jarvis analyze AAPL
uv run jarvis analyze TSLA --provider anthropic
```
