#!/usr/bin/env bash
# Stop hook: warn if .py files changed without any .md doc updates

changed=$(git diff HEAD --name-only 2>/dev/null)

py_changed=$(echo "$changed" | grep -E '\.py$' | grep -v '__pycache__' | grep -v 'test_')
doc_changed=$(echo "$changed" | grep -E '\.(md|rst)$')

if [ -n "$py_changed" ] && [ -z "$doc_changed" ]; then
  printf '{"systemMessage": "⚠️  문서 업데이트 누락: Python 파일이 변경됐지만 README.md / docs/ 가 업데이트되지 않았습니다. CLAUDE.md의 Documentation Rules를 확인하세요."}'
fi
