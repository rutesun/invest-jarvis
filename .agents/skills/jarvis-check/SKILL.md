---
name: jarvis-check
description: Run quick technical analysis for a ticker
args: ticker symbol (e.g., AAPL, MSFT, 005930.KS)
---

# Quick Check

빠른 기술적 분석 (LLM 없음, 6개 컴포넌트 분석)

## Usage

```bash
uv run jarvis check {ticker}
```

## What it does

- 6개 컴포넌트로 기술적 분석 (Minervini, Velocity, cRSI, Volume, Patterns, Supertrend)
- 총점 (-100 ~ +100)
- 각 컴포넌트별 점수와 근거 표시
- LLM 사용 안함 (빠르고 무료)

## Example

```bash
uv run jarvis check AAPL
```
