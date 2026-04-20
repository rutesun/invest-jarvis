#!/usr/bin/env bash
# Pre-push hook: LLM으로 기능 변경 여부 판단 → FEATURES.md 업데이트 강제
# .pre-commit-config.yaml의 pre-push stage에서 호출됨

set -euo pipefail

BASE_BRANCH="main"

# src/ 변경이 없으면 패스
if ! git diff "$BASE_BRANCH"...HEAD --name-only | grep -q "^src/"; then
    exit 0
fi

# FEATURES.md가 이미 업데이트되었으면 패스
if git diff "$BASE_BRANCH"...HEAD --name-only | grep -q "^docs/FEATURES.md"; then
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
    echo "❌ 기능 변경이 감지되었지만 docs/FEATURES.md가 업데이트되지 않았습니다."
    echo "   FEATURES.md를 업데이트하고 다시 push하세요."
    echo ""
    exit 1
fi

echo "✅ 내부 변경으로 판단. FEATURES.md 업데이트 불필요."
exit 0
