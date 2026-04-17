---
name: jarvis-report
description: Generate daily market report from Telegram messages
args: optional date (YYYY-MM-DD)
---

# Daily Market Report

텔레그램 기반 일일 리포트 생성

## Usage

```bash
uv run jarvis report daily
uv run jarvis report daily 2026-04-17
uv run jarvis report daily 2026-04-17 --notion
```

## What it does

- 텔레그램 메시지 수집 및 분석
- MapReduce 5단계 파이프라인
- 테마별 클러스터링 및 인사이트
- `reports/YYYY-MM/daily_YYYY-MM-DD.md` 자동 저장
- Notion 업로드 지원 (--notion 옵션)

## Requirements

- OPENAI_API_KEY or ANTHROPIC_API_KEY
- NOTION_TOKEN (Notion 업로드 시)
- NOTION_DATABASE_ID (Notion 업로드 시)

## Example

```bash
# MD 파일만 저장
uv run jarvis report daily

# Notion에도 업로드
uv run jarvis report daily --notion
```
