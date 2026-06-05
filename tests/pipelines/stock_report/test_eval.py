"""T09-I: stock_report_eval harness tests."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

from src.pipelines.stock_report.retrieval import CategoryBucket, SameDayBundle, SameDayChunk


# Load the script module (lives under scripts/, not an importable package).
_EVAL_PATH = Path(__file__).resolve().parents[3] / "scripts" / "stock_report_eval.py"
_spec = importlib.util.spec_from_file_location("stock_report_eval", _EVAL_PATH)
assert _spec and _spec.loader
seval = importlib.util.module_from_spec(_spec)
sys.modules["stock_report_eval"] = seval  # required so @dataclass(field) can resolve the module
_spec.loader.exec_module(seval)


def _chunk(
    chunk_id: int, *, category_key: str = "반도체", message_type: str = "signal"
) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 5, 26),
        channel_key="kwusa",
        channel_name="키움 미국주식",
        channel_message_id=str(50000 + chunk_id),
        message_type=message_type,
        event_type="해석/전망",
        category_key=category_key,
        main_theme="HBM",
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        theme_tags=[],
        canonical_summary=f"summary-{chunk_id}",
        supporting_facts=[],
        evidence_items=[],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=1.0,
    )


def _bundle(buckets: list[CategoryBucket]) -> SameDayBundle:
    chunks = [c for b in buckets for c in b.chunks]
    return SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=chunks,
        category_buckets=buckets,
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )


class TestComputeCoverage:
    def test_basic_rate_and_denominator(self) -> None:
        bundle = _bundle(
            [
                CategoryBucket(category_key="반도체", chunks=[_chunk(1), _chunk(2), _chunk(3)]),
                CategoryBucket(category_key="바이오", chunks=[_chunk(4)]),
            ]
        )
        cov = seval.compute_coverage(bundle, referenced_ids={1, 2, 4})

        assert cov.denominator == 4  # deduped synthesis chunks
        assert cov.referenced_total == 3
        assert cov.coverage_rate == 0.75
        assert cov.missing_categories == []

    def test_flags_category_with_signals_and_zero_refs(self) -> None:
        bundle = _bundle(
            [
                CategoryBucket(
                    category_key="바이오",
                    chunks=[_chunk(1), _chunk(2), _chunk(3)],  # 3 signal, 0 referenced
                ),
                CategoryBucket(category_key="반도체", chunks=[_chunk(4)]),
            ]
        )
        cov = seval.compute_coverage(bundle, referenced_ids={4})

        assert "바이오" in cov.missing_categories
        bio = next(c for c in cov.categories if c.category == "바이오")
        assert bio.missing is True
        assert bio.signal_total == 3
        assert bio.referenced == 0

    def test_small_category_not_flagged(self) -> None:
        # 2 signal chunks (< MIN_SIGNAL_FOR_FLAG) with 0 refs is not a failure
        bundle = _bundle([CategoryBucket(category_key="방산", chunks=[_chunk(1), _chunk(2)])])
        cov = seval.compute_coverage(bundle, referenced_ids=set())
        assert cov.missing_categories == []

    def test_data_chunks_do_not_count_as_signal(self) -> None:
        bundle = _bundle(
            [
                CategoryBucket(
                    category_key="매크로",
                    chunks=[_chunk(i, message_type="data") for i in (1, 2, 3)],
                )
            ]
        )
        cov = seval.compute_coverage(bundle, referenced_ids=set())
        assert cov.missing_categories == []  # 0 signal chunks → not flagged


class TestParseReferencedFromMarkdown:
    def test_parses_bracket_and_chunk_forms(self) -> None:
        text = "출처 [2884], 그리고 chunk 2910 그리고 [3001]"
        assert seval.parse_referenced_from_markdown(text) == {2884, 2910, 3001}

    def test_empty_when_no_ids(self) -> None:
        assert seval.parse_referenced_from_markdown("출처 없음") == set()


class TestJudgeFaithfulness:
    def test_uses_injected_judge_and_maps_fields(self) -> None:
        def fake_judge(system: str, user: str) -> dict:
            assert "리포트 본문" in user
            return {
                "missing_events": ["디앤디파마텍 상한가"],
                "hallucinated_claims": ["오라클 데이터센터 연결"],
            }

        report = seval.judge_faithfulness(
            "## Pulse\n- 반도체 강세",
            ["반도체 강세", "디앤디파마텍 임상 성공"],
            judge_call=fake_judge,
        )
        assert report.missing_events == ["디앤디파마텍 상한가"]
        assert report.hallucinated_claims == ["오라클 데이터센터 연결"]

    def test_handles_missing_keys(self) -> None:
        report = seval.judge_faithfulness("report", ["fact"], judge_call=lambda s, u: {})
        assert report.missing_events == []
        assert report.hallucinated_claims == []


class TestGoldenCoverage:
    def test_all_present_returns_empty(self) -> None:
        must_haves = [
            {"description": "MGM 인수", "match_any": ["MGM"]},
            {"description": "퍼페추아 대출", "match_any": ["퍼페추아"]},
        ]
        report = "오늘 MGM 인수 제안과 퍼페추아 리소스 대출이 보도됐다."
        assert seval.check_golden_coverage(report, must_haves) == []

    def test_reports_missing_description(self) -> None:
        must_haves = [
            {"description": "MGM 인수", "match_any": ["MGM"]},
            {"description": "네비우스 지분", "match_any": ["네비우스", "Nebius"]},
        ]
        report = "오늘 MGM 인수 제안만 보도됐다."
        assert seval.check_golden_coverage(report, must_haves) == ["네비우스 지분"]

    def test_any_substring_counts_as_present(self) -> None:
        must_haves = [{"description": "우버-딜리버리히어로", "match_any": ["딜리버리", "우버"]}]
        assert seval.check_golden_coverage("우버가 인수를 제안했다", must_haves) == []

    def test_missing_fixture_returns_empty(self) -> None:
        assert seval.load_golden_must_haves("1999-01-01") == []

    def test_loads_frozen_fixture(self) -> None:
        events = seval.load_golden_must_haves("2026-06-02")
        assert events
        assert any("MGM" in (event.get("match_any") or []) for event in events)


def test_coverage_report_is_json_serializable() -> None:
    """Guards the `--json` path: slots dataclasses have no __dict__, so serialization
    must go through dataclasses.asdict (regression for the eval --json crash)."""
    import json
    from dataclasses import asdict

    cov = seval.CoverageReport(
        report_date="2026-06-04",
        denominator=2,
        referenced_total=1,
        coverage_rate=0.5,
        categories=[
            seval.CategoryCoverage(
                category="반도체", total=2, signal_total=2, referenced=1, missing=False
            )
        ],
        missing_categories=[],
    )

    out = json.dumps(asdict(cov), ensure_ascii=False)
    assert "반도체" in out
    assert '"category"' in out
