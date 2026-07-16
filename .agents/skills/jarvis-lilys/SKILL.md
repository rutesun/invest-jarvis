---
name: jarvis-lilys
description: Fetch and clean Lilys AI digest notes from lilys.ai/digest URLs. Use when the user gives a Lilys AI digest link and wants the content summarized, analyzed, or recorded in the investment notebook.
---

# Lilys Digest Fetch

Lilys AI digest URL에서 공개 note API를 호출해 본문을 텍스트로 추출한다. 사용자가 Lily 링크 내용을 요약, 분석, 리서치 노트 기록해 달라고 하면 먼저 이 스킬로 원문 텍스트를 확보한다.

## Command

```bash
python3 .agents/skills/jarvis-lilys/scripts/fetch_lilys_note.py "https://lilys.ai/digest/{session_id}/{note_id}"
```

## Example

```bash
python3 .agents/skills/jarvis-lilys/scripts/fetch_lilys_note.py "https://lilys.ai/digest/10533202/12319149" --max-chars 6000
```

## Notes

- URL에서 `{session_id}`와 `{note_id}`를 추출한다.
- API: `.../v3/note/{session_id}/{note_id}?provider=&whisper=false`
- 출력은 제목, session id, note id, 정리된 본문 텍스트다.
- `--max-chars`는 긴 노트를 빠르게 훑을 때만 사용한다.
- `--json`은 후처리나 구조화가 필요할 때 사용한다.
- 본문 확보 후 투자 관점으로 재요약한다.
- 기록 요청이면 `jarvis-notebook`으로 `notebook/research/YYYY-MM.md`에 저장한다.
- API 실패 시 Lily URL 형식과 공개 접근 가능 여부를 먼저 확인한다.
