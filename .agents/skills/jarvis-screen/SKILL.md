---
name: jarvis-screen
description: Scan market for leading stocks and themes
args: --market kr|us|all (optional)
---

# Market Screen

시장 스크리너 - Naver 테마 + KIS 순위 기반 유니버스 구성

## Usage

```bash
uv run jarvis screen [--market kr|us|all]
```

## Example

```bash
uv run jarvis screen              # 전체 시장
uv run jarvis screen --market kr  # 한국만
```
