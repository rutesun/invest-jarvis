---
name: jarvis-check
description: Run quick technical analysis for one or more tickers
args: one or more ticker symbols (e.g., AAPL MSFT 005930.KS)
---

# Quick Check

여러 ticker의 공통 3년 기술 분석을 LLM 없이 빠르게 확인한다.

## Usage

```bash
uv run jarvis check {ticker} [ticker ...]
```

## What it does

- 공통 3년 데이터 기반 8개 컴포넌트 기술 분석 (SMA 100·200 방향 포함)
- component_raw_total / adjusted_score / technical_verdict 표시
- 여러 ticker를 한 번에 처리 (일부 실패해도 나머지는 계속 출력)
- LLM 사용 안 함, Macro 미포함 (빠르고 무료)

## Example

```bash
uv run jarvis check AAPL MSFT 005930.KS
```
