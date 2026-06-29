#!/usr/bin/env bash
# Pre-push hook: LLM으로 기능 변경 여부 판단 → FEATURES.md + docs/changes/ 업데이트 강제
# .pre-commit-config.yaml의 pre-push stage에서 호출됨

set -euo pipefail

BASE_BRANCH="main"

CHANGED=$(git diff "$BASE_BRANCH"...HEAD --name-only)

# src/ 변경이 없으면 패스
if ! echo "$CHANGED" | grep -q "^src/"; then
    exit 0
fi

features_updated=$(echo "$CHANGED" | grep -q "^docs/FEATURES.md" && echo 1 || echo 0)
changes_updated=$(echo "$CHANGED" | grep -q "^docs/changes/" && echo 1 || echo 0)

# 필수 문서가 모두 업데이트되었으면 LLM 호출 없이 패스
if [ "$features_updated" = 1 ] && [ "$changes_updated" = 1 ]; then
    exit 0
fi

# claude CLI 존재 확인
if ! command -v claude &> /dev/null; then
    echo "⚠️  claude CLI가 없어 기능 변경 체크를 건너뜁니다."
    exit 0
fi

echo "🔍 LLM으로 기능 변경 여부 확인 중..."

DIFF=$(git diff "$BASE_BRANCH"...HEAD -- src/)
FEATURES=$(cat docs/FEATURES.md)

VERDICT=$(echo "$DIFF" | claude -p \
    "You are a code change classifier. Analyze this git diff and determine if it changes user-facing feature BEHAVIOR (new features, changed inputs/outputs, new dependencies, config changes, removed functionality) or if it's purely internal (refactoring, bugfixes, performance, code style, test changes).

Current FEATURES.md for reference:
---
$FEATURES
---

Answer ONLY one word: FEATURE_CHANGE or INTERNAL" 2>/dev/null || echo "ERROR")

if [ "$VERDICT" = "ERROR" ]; then
    echo "⚠️  LLM 호출 실패. 체크를 건너뜁니다."
    exit 0
fi

if echo "$VERDICT" | grep -q "FEATURE_CHANGE"; then
    echo ""
    echo "❌ 기능 변경이 감지되었습니다. 다음 문서를 업데이트하고 다시 push하세요:"
    [ "$features_updated" = 0 ] && echo "   - docs/FEATURES.md (현재 기능 상태)"
    [ "$changes_updated" = 0 ] && echo "   - docs/changes/{name}.md (변경 기록) — '/change-record'로 초안 생성"
    echo ""
    exit 1
fi

echo "✅ 내부 변경으로 판단. 문서 업데이트 불필요."
exit 0
