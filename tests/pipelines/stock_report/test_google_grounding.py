from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.pipelines.stock_report.google_grounding import (
    GOOGLE_GROUNDING_DEFAULT_MODEL,
    GoogleGroundedArtifact,
    GroundingCitation,
    _build_user_prompt,
    _extract_citations,
    synthesize_with_google_grounding,
)
from src.pipelines.stock_report.retrieval import (
    CategoryBucket,
    SameDayBundle,
    SameDayChunk,
    ThemeBucket,
    TickerBucket,
)
from src.pipelines.stock_report.synthesize import ReportSectionItem, StockReportArtifact


def _make_chunk(chunk_id: int, category: str = "AI인프라", theme: str = "AI서버") -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2025, 5, 8),
        channel_key="test_channel",
        channel_name="테스트 채널",
        channel_message_id=chunk_id,
        message_type="signal",
        event_type=None,
        category_key=category,
        main_theme=theme,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=["NVDA"],
        theme_tags=[theme],
        canonical_summary="엔비디아 H100 수요 급증",
        supporting_facts=["Q2 데이터센터 매출 +150% YoY"],
        evidence_items=[],
        qa_warnings=[],
        content_clean="엔비디아 H100 수요 급증",
        priority_score=0.9,
    )


def _make_bundle() -> SameDayBundle:
    chunk = _make_chunk(1)
    theme_bucket = ThemeBucket(theme_key="AI서버", category_key="AI인프라", chunks=[chunk])
    category_bucket = CategoryBucket(
        category_key="AI인프라", chunks=[chunk], theme_buckets=[theme_bucket]
    )
    ticker_bucket = TickerBucket(ticker="NVDA", chunks=[chunk])
    return SameDayBundle(
        report_date=date(2025, 5, 8),
        chunks=[chunk],
        category_buckets=[category_bucket],
        focus_ticker_buckets=[ticker_bucket],
        low_confidence_chunks=[],
    )


def _make_stock_report_artifact(report_date: date = date(2025, 5, 8)) -> StockReportArtifact:
    return StockReportArtifact(
        report_date=report_date,
        pulse=[ReportSectionItem(key="pulse-1", title="NVDA 수요 급증", body="엔비디아 수요 증가")],
        category_summaries=[],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=[],
    )


def _make_fake_response(text: str, grounding_chunks=None, search_queries=None):
    web_chunks = []
    for item in grounding_chunks or []:
        web = SimpleNamespace(title=item["title"], uri=item["uri"])
        web_chunks.append(SimpleNamespace(web=web))

    meta = SimpleNamespace(
        grounding_chunks=web_chunks,
        web_search_queries=search_queries or [],
    )
    candidate = SimpleNamespace(grounding_metadata=meta)
    return SimpleNamespace(text=text, candidates=[candidate])


def _minimal_llm_json() -> str:
    return json.dumps(
        {
            "pulse": [
                {
                    "title": "NVDA 수요 급증",
                    "body": "AI 서버 수요 강세",
                    "evidence_chunk_ids": [1],
                    "priority_score": 0.9,
                }
            ],
            "category_summaries": [],
            "core_themes": [],
            "focus_tickers": [],
        }
    )


class TestBuildUserPrompt:
    def test_contains_search_hints(self):
        bundle = _make_bundle()
        prompt = _build_user_prompt(bundle)
        assert "NVDA" in prompt
        assert "AI서버" in prompt

    def test_contains_report_date(self):
        bundle = _make_bundle()
        prompt = _build_user_prompt(bundle)
        assert "2025-05-08" in prompt

    def test_contains_output_sections(self):
        bundle = _make_bundle()
        prompt = _build_user_prompt(bundle)
        # Markdown 섹션 지시가 포함돼야 한다
        assert "Pulse" in prompt
        assert "Category Summaries" in prompt
        assert "Focus Tickers" in prompt

    def test_prescribes_canonical_labels(self):
        bundle = _make_bundle()
        prompt = _build_user_prompt(bundle)
        # grouped/nested labels must match MarkdownReportBuilder so the grounded report
        # aligns with the T09-A report
        for label in [
            "Narrative",
            "Impact",
            "근거",
            "핵심 주장",
            "투자 포인트",
            "촉매",
            "핵심 수치",
            "리스크/확인",
            "관련 종목",
            "출처",
        ]:
            assert label in prompt
        assert "영어 라벨 금지" in prompt
        assert "티커 심볼만" in prompt
        assert "2칸 들여쓰기" in prompt

    def test_no_markdown_output_instruction(self):
        bundle = _make_bundle()
        prompt = _build_user_prompt(bundle)
        assert "출력은 Markdown" not in prompt

    def test_is_compact(self):
        bundle = _make_bundle()
        prompt = _build_user_prompt(bundle)
        # 경량 프롬프트여야 한다 — 원본(~200K chars)의 10% 이하
        assert len(prompt) < 20_000


class TestSystemPrompt:
    def test_allows_google_search(self):
        from src.pipelines.stock_report.google_grounding import _SYSTEM_PROMPT

        assert "Google Search" in _SYSTEM_PROMPT

    def test_no_local_mode_restriction(self):
        from src.pipelines.stock_report.google_grounding import _SYSTEM_PROMPT

        assert "local mode" not in _SYSTEM_PROMPT

    def test_no_json_output_instruction(self):
        from src.pipelines.stock_report.google_grounding import _SYSTEM_PROMPT

        assert "JSON 형식으로 출력하지 않는다" in _SYSTEM_PROMPT


class TestExtractCitations:
    def test_extracts_citations_from_grounding_metadata(self):
        response = _make_fake_response(
            "report text",
            grounding_chunks=[
                {"title": "Bloomberg", "uri": "https://bloomberg.com/news/1"},
                {"title": "Reuters", "uri": "https://reuters.com/news/2"},
            ],
            search_queries=["NVDA earnings 2025", "AI server demand"],
        )
        citations, queries = _extract_citations(response.candidates[0])

        assert len(citations) == 2
        assert citations[0].index == 1
        assert citations[0].title == "Bloomberg"
        assert citations[0].uri == "https://bloomberg.com/news/1"
        assert citations[1].index == 2
        assert len(queries) == 2
        assert "NVDA earnings 2025" in queries

    def test_returns_empty_when_no_grounding_metadata(self):
        candidate = SimpleNamespace(grounding_metadata=None)
        citations, queries = _extract_citations(candidate)
        assert citations == []
        assert queries == []

    def test_skips_non_web_chunks(self):
        meta = SimpleNamespace(
            grounding_chunks=[SimpleNamespace(web=None)],
            web_search_queries=[],
        )
        candidate = SimpleNamespace(grounding_metadata=meta)
        citations, queries = _extract_citations(candidate)
        assert citations == []

    def test_returns_empty_on_attribute_error(self):
        candidate = SimpleNamespace(grounding_metadata=SimpleNamespace())
        citations, queries = _extract_citations(candidate)
        assert citations == []
        assert queries == []


class TestSynthesizeWithGoogleGrounding:
    def test_returns_artifact_with_markdown(self):
        bundle = _make_bundle()
        fake_response = _make_fake_response(
            _minimal_llm_json(),
            grounding_chunks=[{"title": "Bloomberg", "uri": "https://bloomberg.com/1"}],
            search_queries=["NVDA AI demand"],
        )
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("src.pipelines.stock_report.google_grounding.genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock_client
            artifact = synthesize_with_google_grounding(bundle)

        assert isinstance(artifact, GoogleGroundedArtifact)
        assert artifact.report_date == date(2025, 5, 8)
        assert isinstance(artifact.synthesis_markdown, str)
        assert len(artifact.synthesis_markdown) > 0
        assert len(artifact.citations) == 1
        assert artifact.citations[0].title == "Bloomberg"
        assert artifact.search_queries == ["NVDA AI demand"]
        assert artifact.model == GOOGLE_GROUNDING_DEFAULT_MODEL
        assert artifact.grounding_active is True

    def test_markdown_response_used_as_is(self):
        bundle = _make_bundle()
        markdown_text = "## Pulse\n- NVDA 수요 급증\n"
        fake_response = _make_fake_response(markdown_text, [], [])
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("src.pipelines.stock_report.google_grounding.genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock_client
            artifact = synthesize_with_google_grounding(bundle)

        assert artifact.synthesis_markdown.strip() == markdown_text.strip()
        assert artifact.grounding_active is False

    def test_strips_code_fence_from_response(self):
        bundle = _make_bundle()
        fenced = "```markdown\n## Pulse\n- NVDA 수요 급증\n```"
        fake_response = _make_fake_response(fenced, [], [])
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("src.pipelines.stock_report.google_grounding.genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock_client
            artifact = synthesize_with_google_grounding(bundle)

        # 코드펜스는 벗겨지고 본문만 남는다 (google는 Markdown 반환)
        assert "## Pulse" in artifact.synthesis_markdown
        assert "```" not in artifact.synthesis_markdown

    def test_uses_custom_model(self):
        bundle = _make_bundle()
        fake_response = _make_fake_response(_minimal_llm_json(), [], [])
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("src.pipelines.stock_report.google_grounding.genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock_client
            artifact = synthesize_with_google_grounding(bundle, model="gemini-3.5-flash")

        assert artifact.model == "gemini-3.5-flash"
        call_kwargs = mock_client.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-3.5-flash"

    def test_uses_env_api_key(self):
        bundle = _make_bundle()
        fake_response = _make_fake_response(_minimal_llm_json(), [], [])
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "env-api-key"}),
            patch("src.pipelines.stock_report.google_grounding.genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock_client
            synthesize_with_google_grounding(bundle)

        mock_genai.Client.assert_called_once_with(api_key="env-api-key")

    def test_raises_when_no_api_key(self):
        bundle = _make_bundle()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("src.pipelines.stock_report.google_grounding.genai"),
            pytest.raises(ValueError, match="GOOGLE_API_KEY"),
        ):
            synthesize_with_google_grounding(bundle)

    def test_raises_import_error_when_genai_missing(self):
        bundle = _make_bundle()
        import src.pipelines.stock_report.google_grounding as gg_module

        with (
            patch.object(gg_module, "_GENAI_AVAILABLE", False),
            pytest.raises(ImportError, match="google-genai"),
        ):
            synthesize_with_google_grounding(bundle, api_key="key")

    def test_retries_on_failure_then_succeeds(self):
        bundle = _make_bundle()
        fake_response = _make_fake_response("## Pulse\n- ok\n", [], [])
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            RuntimeError("transient error"),
            fake_response,
        ]

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("src.pipelines.stock_report.google_grounding.genai") as mock_genai,
            patch("src.pipelines.stock_report.google_grounding.time") as mock_time,
        ):
            mock_genai.Client.return_value = mock_client
            artifact = synthesize_with_google_grounding(bundle)

        assert isinstance(artifact.synthesis_markdown, str)
        assert mock_client.models.generate_content.call_count == 2
        mock_time.sleep.assert_called_once()

    def test_raises_after_all_retries_exhausted(self):
        bundle = _make_bundle()
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("persistent error")

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("src.pipelines.stock_report.google_grounding.genai") as mock_genai,
            patch("src.pipelines.stock_report.google_grounding.time"),
        ):
            mock_genai.Client.return_value = mock_client
            with pytest.raises(RuntimeError, match="failed after"):
                synthesize_with_google_grounding(bundle)


class TestRenderGoogleGroundedReport:
    def _make_artifact(self, citations=None, queries=None, grounding_active=True):
        return GoogleGroundedArtifact(
            report_date=date(2025, 5, 8),
            synthesis_markdown="## Pulse\n- 엔비디아 수요 급증\n",
            citations=citations or [],
            search_queries=queries or [],
            model="gemini-3.5-flash",
            grounding_active=grounding_active,
        )

    def test_appends_citations_section(self):
        from src.pipelines.stock_report.render_markdown import render_google_grounded_report

        artifact = self._make_artifact(
            citations=[
                GroundingCitation(index=1, title="Bloomberg", uri="https://bloomberg.com/1"),
                GroundingCitation(index=2, title="Reuters", uri="https://reuters.com/2"),
            ],
            queries=["NVDA 2025"],
        )
        result = render_google_grounded_report(artifact)

        assert "## Pulse" in result
        assert "EXPERIMENTAL" in result
        assert "## 검색 출처" in result
        assert "[1] [Bloomberg](https://bloomberg.com/1)" in result
        assert "[2] [Reuters](https://reuters.com/2)" in result
        assert "## 검색 쿼리" in result
        assert "- NVDA 2025" in result
        assert result.endswith("\n")

    def test_shows_grounding_status(self):
        from src.pipelines.stock_report.render_markdown import render_google_grounded_report

        active = render_google_grounded_report(self._make_artifact(grounding_active=True))
        inactive = render_google_grounded_report(self._make_artifact(grounding_active=False))
        assert "Grounding 활성" in active
        assert "미발동" in inactive

    def test_starts_with_canonical_h1_title(self):
        from src.pipelines.stock_report.render_markdown import render_google_grounded_report

        result = render_google_grounded_report(self._make_artifact())
        # H1 matches the T09-A canonical report (MarkdownReportBuilder) so both share layout
        assert result.startswith("# Daily Stock Report V2 - 2025-05-08")
        assert result.index("# Daily Stock Report V2") < result.index("EXPERIMENTAL")
        assert result.index("EXPERIMENTAL") < result.index("## Pulse")

    def test_no_citation_section_when_empty(self):
        from src.pipelines.stock_report.render_markdown import render_google_grounded_report

        result = render_google_grounded_report(self._make_artifact())
        assert "## 검색 출처" not in result
        assert "## 검색 쿼리" not in result
        assert result.endswith("\n")

    def test_uses_uri_as_label_when_title_empty(self):
        from src.pipelines.stock_report.render_markdown import render_google_grounded_report

        artifact = GoogleGroundedArtifact(
            report_date=date(2025, 5, 8),
            synthesis_markdown="content",
            citations=[GroundingCitation(index=1, title="", uri="https://example.com/page")],
            search_queries=[],
            model="gemini-3.5-flash",
        )
        result = render_google_grounded_report(artifact)
        assert "[1] [https://example.com/page](https://example.com/page)" in result


class TestRunGoogleGroundingOnly:
    def _make_grounded_artifact(self) -> GoogleGroundedArtifact:
        return GoogleGroundedArtifact(
            report_date=date(2025, 5, 8),
            synthesis_markdown="## Pulse\n- NVDA 수요 급증\n",
            citations=[
                GroundingCitation(index=1, title="Bloomberg", uri="https://bloomberg.com/1")
            ],
            search_queries=["NVDA 2025"],
            model="gemini-3.5-flash",
            grounding_active=True,
        )

    def test_returns_result_with_markdown(self):
        from src.pipelines.stock_report.pipeline import (
            GoogleGroundingOnlyResult,
            run_google_grounding_only,
        )

        bundle = _make_bundle()
        artifact = self._make_grounded_artifact()

        with (
            patch(
                "src.pipelines.stock_report.pipeline.resolve_db_dsn",
                return_value="postgresql://test",
            ),
            patch("src.pipelines.stock_report.pipeline.connect_db") as mock_connect,
        ):
            mock_connect.return_value.__enter__ = lambda s: MagicMock()
            mock_connect.return_value.__exit__ = MagicMock(return_value=False)
            with (
                patch(
                    "src.pipelines.stock_report.pipeline._stage_load_same_day_bundle",
                    return_value=bundle,
                ),
                patch(
                    "src.pipelines.stock_report.google_grounding.synthesize_with_google_grounding",
                    return_value=artifact,
                ),
                patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            ):
                result = run_google_grounding_only(date="2025-05-08")

        assert isinstance(result, GoogleGroundingOnlyResult)
        assert result.date == "2025-05-08"
        assert "NVDA" in result.google_grounding_markdown
        assert result.chunk_count == len(bundle.chunks)
        assert result.category_bucket_count == len(bundle.category_buckets)
        assert result.focus_ticker_count == len(bundle.focus_ticker_buckets)
        assert result.model == "gemini-3.5-flash"

    def test_raises_when_no_chunks_in_db(self):
        from src.pipelines.stock_report.pipeline import run_google_grounding_only
        from src.pipelines.stock_report.retrieval import SameDayBundle

        empty_bundle = SameDayBundle(
            report_date=date(2025, 5, 8),
            chunks=[],
            category_buckets=[],
            focus_ticker_buckets=[],
            low_confidence_chunks=[],
        )

        with (
            patch(
                "src.pipelines.stock_report.pipeline.resolve_db_dsn",
                return_value="postgresql://test",
            ),
            patch("src.pipelines.stock_report.pipeline.connect_db") as mock_connect,
        ):
            mock_connect.return_value.__enter__ = lambda s: MagicMock()
            mock_connect.return_value.__exit__ = MagicMock(return_value=False)
            with (
                patch(
                    "src.pipelines.stock_report.pipeline._stage_load_same_day_bundle",
                    return_value=empty_bundle,
                ),
                patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
                pytest.raises(ValueError, match="knowledge_chunks가 없습니다"),
            ):
                run_google_grounding_only(date="2025-05-08")

    def test_validates_date_format(self):
        from src.pipelines.stock_report.pipeline import run_google_grounding_only

        with pytest.raises(ValueError):
            run_google_grounding_only(date="not-a-date")
