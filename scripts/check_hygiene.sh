#!/usr/bin/env bash
set -e

echo "🧹 코드 위생 점검 시작..."
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0

# 1. Ruff check (imports, unused variables, etc.)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Ruff: Import & Code Quality Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if uv run --group dev ruff check src tests; then
    echo -e "${GREEN}✓ Ruff check passed${NC}"
else
    echo -e "${RED}✗ Ruff check failed${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 2. Ruff format check
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎨 Ruff: Format Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if uv run --group dev ruff format --check src tests; then
    echo -e "${GREEN}✓ Format check passed${NC}"
else
    echo -e "${YELLOW}⚠ Format issues found (run: uv run ruff format src tests)${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 3. Vulture (unused code detection)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🦅 Vulture: Unused Code Detection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if uv run --group dev vulture src --min-confidence 80; then
    echo -e "${GREEN}✓ No unused code detected${NC}"
else
    echo -e "${YELLOW}⚠ Potential unused code found (review above)${NC}"
    # Don't fail on vulture (too many false positives)
fi
echo ""

# 4. Test suite (fast unit tests only)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 Pytest: Unit Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if uv run pytest tests/ --ignore=tests/integration -x --tb=short -q; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
else
    echo -e "${RED}✗ Unit tests failed${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ 코드 위생 점검 통과 (0 errors)${NC}"
    exit 0
else
    echo -e "${RED}✗ 코드 위생 점검 실패 ($ERRORS errors)${NC}"
    echo ""
    echo "Fix suggestions:"
    echo "  - Imports: uv run ruff check src tests --fix"
    echo "  - Format: uv run ruff format src tests"
    echo "  - Tests: uv run pytest tests/ -v --ignore=tests/integration"
    exit 1
fi
