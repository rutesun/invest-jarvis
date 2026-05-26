from __future__ import annotations

from datetime import UTC, date, datetime

from src.pipelines.stock_report.models import ClassifiedMessage, NormalizedMessage
from src.pipelines.stock_report.tuning import run_prompt_tuning_round, select_tuning_samples


def _normalized(
    message_id: int,
    channel_key: str,
    *,
    mode: str = "full",
    clean_text: str = "샘플 텍스트",
) -> NormalizedMessage:
    return NormalizedMessage(
        telegram_message_id=message_id,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        channel_key=channel_key,
        source_channel_key=channel_key,
        source_channel_name=channel_key,
        channel_message_id=str(message_id),
        raw_text=clean_text,
        clean_text=clean_text,
        urls=[],
        has_media=False,
        content_hash=f"hash-{message_id}",
        processing_mode=mode,
        grouped_message_ids=[],
    )


def test_select_tuning_samples_respects_per_channel_and_sample_size():
    normalized_rows = [
        _normalized(1, "a"),
        _normalized(2, "a"),
        _normalized(3, "b"),
        _normalized(4, "c"),
        _normalized(5, "c", mode="grouped_only"),
    ]

    sampled = select_tuning_samples(
        normalized_rows,
        sample_size=4,
        per_channel=1,
        seed=7,
        include_grouped_only=False,
    )

    assert len(sampled) == 4
    sampled_channels = {row.channel_key for row in sampled}
    assert sampled_channels.issuperset({"a", "b", "c"})
    assert all(row.processing_mode == "full" for row in sampled)


def test_select_tuning_samples_includes_picked_messages():
    normalized_rows = [
        _normalized(1, "hana_us_stock", clean_text="alpha"),
        _normalized(2, "hana_us_stock", clean_text="beta"),
        _normalized(3, "shinhanresearch", clean_text="gamma"),
        _normalized(4, "shinhanresearch", clean_text="delta"),
    ]

    sampled = select_tuning_samples(
        normalized_rows,
        sample_size=2,
        per_channel=0,
        seed=1,
        include_grouped_only=False,
        picked_messages={("hana_us_stock", "2"), ("shinhanresearch", "4")},
        strict_picks=True,
    )

    selectors = {(row.channel_key, row.channel_message_id) for row in sampled}
    assert ("hana_us_stock", "2") in selectors
    assert ("shinhanresearch", "4") in selectors
    assert len(sampled) == 2


def test_run_prompt_tuning_round_uses_csv_samples_and_custom_prompt(tmp_path, monkeypatch):
    month_dir = tmp_path / "2026-05"
    month_dir.mkdir(parents=True)
    csv_file = month_dir / "2026-05-08-hana_us_stock.csv"
    csv_file.write_text(
        "\n".join(
            [
                "message_id,timestamp,channel_name,author,content,media_info,forward_from",
                '101,2026-05-08T09:00:00+00:00,hana_us_stock,alpha,"NVIDIA-IREN 파트너십 발표",,',
                '102,2026-05-08T09:10:00+00:00,hana_us_stock,beta,"EU 관세 이슈로 타이어 업종 변동성 확대",,',
                '103,2026-05-08T09:20:00+00:00,hana_us_stock,gamma,"채널 공지: 라이브 일정 안내",,',
            ]
        ),
        encoding="utf-8",
    )
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("CUSTOM PROMPT", encoding="utf-8")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "\n".join(
            [
                "stock_report:",
                "  normalize:",
                "    short_comment_channels: []",
                "    short_comment_max_chars: 10",
                "    group_window_minutes: 30",
            ]
        ),
        encoding="utf-8",
    )

    def _fake_classify(normalized_messages, *, taxonomy, provider, system_prompt=None):
        assert provider == "openai"
        assert system_prompt == "CUSTOM PROMPT"
        return [
            ClassifiedMessage(
                telegram_message_id=row.telegram_message_id,
                source_date=row.source_date,
                channel_key=row.channel_key,
                source_channel_key=row.source_channel_key,
                processing_mode=row.processing_mode,
                structure_type="single_topic_deep",
                unit_index=0,
                message_type="signal",
                event_type="수주/계약",
                category_key="반도체",
                main_theme=None,
                provisional_category=None,
                provisional_theme=None,
                is_provisional=False,
                sub_themes=[],
                ticker_tags=[],
                canonical_summary=f"요약-{row.channel_message_id}",
                supporting_facts=[],
            )
            for row in normalized_messages
        ]

    monkeypatch.setattr("src.pipelines.stock_report.tuning.classify_messages", _fake_classify)

    result = run_prompt_tuning_round(
        date="2026-05-08",
        data_dir=str(tmp_path),
        provider="openai",
        config_path=str(config_file),
        taxonomy_path="config/stock_report_vocabulary.yaml",
        sample_size=2,
        per_channel=1,
        seed=3,
        include_grouped_only=False,
        system_prompt_path=str(prompt_file),
        max_raw_chars=200,
    )

    assert result.csv_files == 1
    assert result.parsed_rows == 3
    assert result.sampled_rows == 2
    assert result.classified_units == 2
    assert result.message_type_counts == {"signal": 2}
    assert result.category_counts == {"반도체": 2}
    assert result.system_prompt_source == str(prompt_file)
    assert "Stock Report V2 Prompt Tuning" in result.output_markdown
    assert "event_type: `수주/계약`" in result.output_markdown
    assert "요약-101" in result.output_markdown or "요약-102" in result.output_markdown


def test_run_prompt_tuning_round_renders_typed_evidence_and_warning_counts(tmp_path, monkeypatch):
    month_dir = tmp_path / "2026-05"
    month_dir.mkdir(parents=True)
    csv_file = month_dir / "2026-05-08-hana_us_stock.csv"
    csv_file.write_text(
        "\n".join(
            [
                "message_id,timestamp,channel_name,author,content,media_info,forward_from",
                '101,2026-05-08T09:00:00+00:00,hana_us_stock,alpha,"Seagate 주가 8% 하락",,',
            ]
        ),
        encoding="utf-8",
    )
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "\n".join(
            [
                "stock_report:",
                "  normalize:",
                "    short_comment_channels: []",
                "    short_comment_max_chars: 10",
                "    group_window_minutes: 30",
            ]
        ),
        encoding="utf-8",
    )

    def _fake_classify(normalized_messages, *, taxonomy, provider, system_prompt=None):
        from src.pipelines.stock_report.models import EvidenceItem, QAWarning

        row = normalized_messages[0]
        return [
            ClassifiedMessage(
                telegram_message_id=row.telegram_message_id,
                source_date=row.source_date,
                channel_key=row.channel_key,
                source_channel_key=row.source_channel_key,
                processing_mode=row.processing_mode,
                structure_type="single_topic_deep",
                unit_index=0,
                message_type="signal",
                event_type="해석/전망",
                category_key="반도체",
                main_theme=None,
                provisional_category=None,
                provisional_theme=None,
                is_provisional=False,
                sub_themes=[],
                ticker_tags=["Seagate"],
                canonical_summary="Seagate 주가 하락에도 가격 전망은 견조",
                supporting_facts=["Seagate 주가는 8% 하락"],
                evidence_items=[
                    EvidenceItem(kind="metric", text="Seagate 주가는 8% 하락"),
                    EvidenceItem(kind="market_context", text="가격 전망은 견조"),
                ],
                qa_warnings=[QAWarning(code="missing_metric_candidate", detail="test warning")],
            ),
            ClassifiedMessage(
                telegram_message_id=row.telegram_message_id,
                source_date=row.source_date,
                channel_key=row.channel_key,
                source_channel_key=row.source_channel_key,
                processing_mode=row.processing_mode,
                structure_type="single_topic_deep",
                unit_index=1,
                message_type="signal",
                event_type="해석/전망",
                category_key="unclassified",
                main_theme=None,
                provisional_category="반도체",
                provisional_theme="AI 반도체",
                is_provisional=False,
                sub_themes=[],
                ticker_tags=["Seagate"],
                canonical_summary="카테고리 매핑 실패, 임시 테마로 분류",
                supporting_facts=[],
                evidence_items=[
                    EvidenceItem(kind="fact", text="카테고리 매핑 실패"),
                ],
                qa_warnings=[QAWarning(code="unsupported_numeric", detail="8% 출처 없음")],
            ),
            ClassifiedMessage(
                telegram_message_id=row.telegram_message_id,
                source_date=row.source_date,
                channel_key=row.channel_key,
                source_channel_key=row.source_channel_key,
                processing_mode=row.processing_mode,
                structure_type="single_topic_deep",
                unit_index=2,
                message_type="signal",
                event_type="해석/전망",
                category_key="반도체",
                main_theme="메모리",
                provisional_category=None,
                provisional_theme="HBM",
                is_provisional=False,
                sub_themes=[],
                ticker_tags=["Seagate"],
                canonical_summary="정식 카테고리지만 임시 테마가 남아 있음",
                supporting_facts=[],
                evidence_items=[
                    EvidenceItem(kind="fact", text="HBM 수급 기대"),
                ],
                qa_warnings=[QAWarning(code="duplicate_unit_candidate", detail="요약 중복 가능")],
            ),
        ]

    monkeypatch.setattr("src.pipelines.stock_report.tuning.classify_messages", _fake_classify)

    result = run_prompt_tuning_round(
        date="2026-05-08",
        data_dir=str(tmp_path),
        provider="openai",
        config_path=str(config_file),
        taxonomy_path="config/stock_report_vocabulary.yaml",
        sample_size=1,
        per_channel=0,
        seed=3,
        include_grouped_only=False,
        max_raw_chars=200,
    )

    assert "## QA Review" in result.output_markdown
    assert (
        "- warning counts by code: "
        "`{'duplicate_unit_candidate': 1, 'missing_metric_candidate': 1, 'unsupported_numeric': 1}`"
    ) in result.output_markdown
    assert "### warning: missing_metric_candidate" in result.output_markdown
    assert "### warning: unsupported_numeric" in result.output_markdown
    assert "### warning: duplicate_unit_candidate" in result.output_markdown
    assert "### taxonomy-gap samples (category_key=unclassified)" in result.output_markdown
    assert "### category/provisional mismatch samples" in result.output_markdown
    assert "prov_theme=AI 반도체 is_prov=False" in result.output_markdown
    assert "prov_theme=HBM is_prov=False" in result.output_markdown
    assert "warning=unsupported_numeric: 8% 출처 없음" in result.output_markdown
    assert "- evidence_items.metric: `Seagate 주가는 8% 하락`" in result.output_markdown
    assert "- evidence_items.market_context: `가격 전망은 견조`" in result.output_markdown
    assert "- qa_warnings: `missing_metric_candidate: test warning`" in result.output_markdown
