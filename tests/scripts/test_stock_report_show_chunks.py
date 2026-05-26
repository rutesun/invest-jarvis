from __future__ import annotations

from scripts.stock_report_show_chunks import ChunkRow, render_grouped


def test_render_grouped_prints_typed_evidence_and_warnings() -> None:
    output = render_grouped(
        [
            ChunkRow(
                chunk_id=1,
                source_pk=100,
                posted_at=None,
                channel_key="hana_us_stock",
                channel_message_id="9609",
                message_type="signal",
                event_type="해석/전망",
                category_key="반도체",
                main_theme=None,
                sub_themes=[],
                ticker_tags=["Seagate"],
                canonical_summary="Seagate 주가 하락",
                supporting_facts=["Seagate 주가는 8% 하락"],
                evidence_items=[
                    {"kind": "metric", "text": "Seagate 주가는 8% 하락"},
                    {"kind": "market_context", "text": "가격 전망은 견조"},
                ],
                qa_warnings=[{"code": "missing_metric_candidate", "detail": "test warning"}],
                provisional_category=None,
                provisional_theme=None,
                is_provisional=False,
                content_clean="Seagate 주가 8% 하락",
                raw_text="",
            ),
            ChunkRow(
                chunk_id=2,
                source_pk=100,
                posted_at=None,
                channel_key="hana_us_stock",
                channel_message_id="9609",
                message_type="signal",
                event_type="해석/전망",
                category_key="unclassified",
                main_theme=None,
                sub_themes=[],
                ticker_tags=["Seagate"],
                canonical_summary="임시 테마로만 분류됨",
                supporting_facts=["숫자 근거 링크 없음"],
                evidence_items=[
                    {"kind": "fact", "text": "숫자 근거 링크 없음"},
                ],
                qa_warnings=[{"code": "unsupported_numeric", "detail": "8% 출처 없음"}],
                provisional_category=None,
                provisional_theme="AI 반도체",
                is_provisional=False,
                content_clean="Seagate 주가 8% 하락",
                raw_text="",
            ),
        ]
    )

    assert (
        "- message_qa.warning_counts: {'missing_metric_candidate': 1, 'unsupported_numeric': 1}"
    ) in output
    assert (
        "- message_qa.taxonomy: "
        "unclassified=1, provisional_fields=1, category_provisional_mismatch=0"
    ) in output
    assert (
        "u2(cat=unclassified, main=-, prov_cat=-, prov_theme=AI 반도체, is_provisional=False)"
        in output
    )
    assert "- evidence_items.metric: Seagate 주가는 8% 하락" in output
    assert "- evidence_items.market_context: 가격 전망은 견조" in output
    assert "- qa_warnings: missing_metric_candidate: test warning" in output
    assert "- provisional: category=-, theme=AI 반도체, is_provisional=False" in output


def test_render_grouped_handles_legacy_rows_without_typed_evidence() -> None:
    output = render_grouped(
        [
            ChunkRow(
                chunk_id=1,
                source_pk=100,
                posted_at=None,
                channel_key="hana_us_stock",
                channel_message_id="9609",
                message_type="signal",
                event_type=None,
                category_key="반도체",
                main_theme=None,
                sub_themes=[],
                ticker_tags=[],
                canonical_summary="legacy row",
                supporting_facts=[],
                evidence_items=[],
                qa_warnings=[],
                provisional_category=None,
                provisional_theme=None,
                is_provisional=False,
                content_clean="legacy row",
                raw_text="",
            )
        ]
    )

    assert "- evidence_items: -" in output
    assert "- qa_warnings: -" in output
