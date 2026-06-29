#!/usr/bin/env bash
# Stop hook: feature 브랜치에서 src/ 변경이 있는데 docs/changes/ 기록이 없으면
# 에이전트에게 change record 작성을 유도(block)한다.
# 무한 루프는 stop_hook_active 가드로 방지 — 한 번 막은 뒤에는 통과시킨다.

input=$(cat)
stop_active=$(echo "$input" | jq -r '.stop_hook_active // false')

# 이 hook으로 인해 이미 재개된 상태면 다시 막지 않는다
if [ "$stop_active" = "true" ]; then
  exit 0
fi

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# main 또는 detached HEAD면 대상 아님
if [ "$branch" = "main" ] || [ -z "$branch" ]; then
  exit 0
fi

# 브랜치 전체 변경(커밋된 것 + 워킹트리 + untracked 신규 파일)
# --porcelain은 untracked(`/change-record`로 갓 만든 기록)까지 잡는다 — git diff는 못 잡음
changed=$( { git diff main...HEAD --name-only; git status --porcelain -uall | cut -c4-; } 2>/dev/null )

src_changed=$(echo "$changed" | grep -E '^src/' | grep -v '__pycache__' || true)
changes_doc=$(echo "$changed" | grep -E '^docs/changes/.*\.md$' || true)

if [ -n "$src_changed" ] && [ -z "$changes_doc" ]; then
  reason="src/ 변경이 있지만 docs/changes/ 기록이 없습니다. 기능 변경이면 '/change-record'로 change record 초안을 만들고 docs/changes/INDEX.md를 갱신하세요. 순수 내부 변경(리팩터링/버그픽스/테스트)이면 이 메시지를 무시하고 작업을 마쳐도 됩니다."
  jq -n --arg r "$reason" '{decision: "block", reason: $r}'
fi

exit 0
