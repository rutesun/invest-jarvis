---
name: jarvis-screen
description: Scan market for leading stocks and themes
args: optional --market (kr|us|all)
---

# Market Screener

시장 스크리너 (테마 + 순위 기반)

## Usage

```bash
uv run jarvis screen
uv run jarvis screen --market kr
uv run jarvis screen --market us
```

## What it does

- Naver 테마 + KIS 순위 기반 유니버스
- 누적/상승일/거래량 폭발 스코어링
- 후보 종목 랭킹 및 리포트

## Example

```bash
uv run jarvis screen --market all
```
