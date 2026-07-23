---
name: jarvis-analyze
description: Deep dive analysis with LLM (technical + news + fundamentals + disclosure + flow + macro)
args: ticker symbol (e.g., AAPL, MSFT, 005930.KS)
---

# Analyze Ticker

공통 3년 기술 분석에 뉴스·재무·공시·수급·Macro를 통합한 심층 분석.
액션·타이밍은 규칙(decision_summary)이 확정하고, 최종 LLM은 그 결정을 바꾸지 않고
모든 소스를 근거로 설명만 한다.

## Usage

```bash
uv run jarvis analyze {ticker} [--provider openai|anthropic]
```

## What it does

- 공통 3년 기술 분석 + 뉴스·재무·공시·수급·Macro 통합
- 규칙이 확정한 decision(액션/타이밍)은 고정 — LLM은 설명 전용
- 모든 소스와 고정 decision을 최종 LLM에 한 번에 전달해 종합 해설 생성

## Example

```bash
uv run jarvis analyze AAPL
uv run jarvis analyze AAPL --provider anthropic
```
