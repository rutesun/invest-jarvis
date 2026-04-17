---
name: jarvis-report
description: Generate daily market report from Telegram messages
args: date (YYYY-MM-DD, optional - defaults to yesterday)
---

# Daily Report

텔레그램 메시지 기반 일일 시장 리포트 생성

## Usage

```bash
uv run jarvis report daily [date]
```

## Example

```bash
uv run jarvis report daily           # 어제 리포트
uv run jarvis report daily 2026-04-16
```
