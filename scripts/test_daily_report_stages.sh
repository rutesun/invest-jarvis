#!/bin/bash
# Daily Report runtime smoke test + artifact verification

set -euo pipefail

DATE=${1:-2026-04-29}
ARTIFACT_DIR="artifacts/daily_report/$DATE/run-1"

echo "========================================="
echo "Daily Report Runtime Stage Check"
echo "Date: $DATE"
echo "========================================="
echo ""

echo "[1/2] Run daily report pipeline"
uv run jarvis report daily "$DATE"

echo ""
echo "[2/2] Verify runtime artifacts"
test -f "$ARTIFACT_DIR/ingest.json"
test -f "$ARTIFACT_DIR/extract.json"
test -f "$ARTIFACT_DIR/link.json"
test -f "$ARTIFACT_DIR/select.json"
test -f "$ARTIFACT_DIR/main_report.md"
test -f "$ARTIFACT_DIR/research_dump.md"
test -f "$ARTIFACT_DIR/ops_report.md"

echo "✓ Required artifact files exist"

INGEST_COUNT=$(jq '.messages | length' "$ARTIFACT_DIR/ingest.json")
EXTRACT_COUNT=$(jq '.claims | length' "$ARTIFACT_DIR/extract.json")
CLUSTER_COUNT=$(jq '.clusters | length' "$ARTIFACT_DIR/link.json")
SELECT_COUNT=$(jq '.selected_clusters | length' "$ARTIFACT_DIR/select.json")

echo "✓ ingest.messages: $INGEST_COUNT"
echo "✓ extract.claims: $EXTRACT_COUNT"
echo "✓ link.clusters: $CLUSTER_COUNT"
echo "✓ select.selected_clusters: $SELECT_COUNT"

