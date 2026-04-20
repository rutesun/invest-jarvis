#!/bin/bash
# Daily Report Stage별 테스트 스크립트

set -e

DATE=${1:-2026-04-14}
OUTPUT_DIR="tests/pipelines/daily_report/fixtures/stage_outputs"

echo "========================================="
echo "Daily Report Pipeline 단계별 테스트"
echo "날짜: $DATE"
echo "========================================="
echo ""

# Ingest Stage
echo "📥 [1/5] Ingest Stage..."
uv run python -m src.pipelines.daily_report.stages.ingest_stage $DATE 2>&1 | grep "^✓"
echo ""

# Map Stage
echo "🗺️  [2/5] Map Stage..."
uv run python -m src.pipelines.daily_report.stages.map_stage $DATE 2>&1 | grep "^✓"
echo ""

# Shuffle Stage
echo "🔀 [3/5] Shuffle Stage..."
uv run python -m src.pipelines.daily_report.stages.shuffle_stage $DATE 2>&1 | grep "^✓"
echo ""

# Reduce Stage
echo "📰 [4/5] Reduce Stage..."
uv run python -m src.pipelines.daily_report.stages.reduce_stage $DATE 2>&1 | grep "^✓"
echo ""

# Wrapup Stage
echo "📋 [5/5] Wrapup Stage..."
uv run python -m src.pipelines.daily_report.stages.wrapup_stage $DATE 2>&1 | grep "^✓"
echo ""

# 결과 요약
echo "========================================="
echo "📊 결과 요약"
echo "========================================="

if [ -f "$OUTPUT_DIR/ingest_$DATE.json" ]; then
    MSG_COUNT=$(jq '.messages | length' "$OUTPUT_DIR/ingest_$DATE.json")
    echo "✓ Ingest: $MSG_COUNT개 메시지 로드"
fi

if [ -f "$OUTPUT_DIR/map_$DATE.json" ]; then
    ISSUE_COUNT=$(jq '. | length' "$OUTPUT_DIR/map_$DATE.json")
    AVG_SOURCES=$(jq '[.[] | .source_ids | length] | add / length' "$OUTPUT_DIR/map_$DATE.json")
    UNIQUE_THEMES=$(jq '[.[] | .themes[]] | unique | length' "$OUTPUT_DIR/map_$DATE.json")

    echo "✓ Map: $ISSUE_COUNT개 이슈 추출"
    echo "  - 평균 소스/이슈: $AVG_SOURCES"
    echo "  - 고유 테마: $UNIQUE_THEMES개"
    echo "  - 압축률: $(echo "scale=1; $ISSUE_COUNT * 100 / $MSG_COUNT" | bc)%"
fi

if [ -f "$OUTPUT_DIR/shuffle_$DATE.json" ]; then
    CATEGORIES=$(jq '.category_groups | keys | length' "$OUTPUT_DIR/shuffle_$DATE.json")
    THEMES=$(jq '.category_groups | to_entries | map(.value | keys | length) | add' "$OUTPUT_DIR/shuffle_$DATE.json")
    echo "✓ Shuffle: $CATEGORIES개 카테고리, $THEMES개 테마"
fi

if [ -f "$OUTPUT_DIR/reduce_$DATE.json" ]; then
    NEWS_COUNT=$(jq '. | length' "$OUTPUT_DIR/reduce_$DATE.json")
    STOCK_COUNT=$(jq '[.[] | .stocks | length] | add' "$OUTPUT_DIR/reduce_$DATE.json")
    echo "✓ Reduce: $NEWS_COUNT개 테마 분석"
    echo "  - 관련 종목: $STOCK_COUNT개"
fi

if [ -f "$OUTPUT_DIR/wrapup_$DATE.json" ]; then
    INSIGHT_COUNT=$(jq '.key_insights | length' "$OUTPUT_DIR/wrapup_$DATE.json")
    echo "✓ Wrapup: $INSIGHT_COUNT개 핵심 인사이트"
fi

echo ""
echo "========================================="
echo "📝 출력 파일"
echo "========================================="
ls -lh "$OUTPUT_DIR/"*_$DATE.json 2>/dev/null || echo "파일 없음"
