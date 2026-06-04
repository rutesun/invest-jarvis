from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date
from textwrap import dedent

from src.pipelines.stock_report.prompts import (
    _build_chunk_packet,
)
from src.pipelines.stock_report.retrieval import SameDayBundle
from src.pipelines.stock_report.synthesize import (
    LocalEvidenceSynthesisOutput,
    _from_llm_output,
)


try:
    from google import genai
    from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    GenerateContentConfig = None  # type: ignore[assignment]
    GoogleSearch = None  # type: ignore[assignment]
    Tool = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False


logger = logging.getLogger(__name__)

GOOGLE_GROUNDING_DEFAULT_MODEL = "gemini-3.5-flash"
_MAX_RETRIES = 2
_RETRY_BASE_WAIT_SECONDS = 2


@dataclass(slots=True)
class GroundingCitation:
    index: int
    title: str
    uri: str
    snippet: str | None = None


@dataclass(slots=True)
class GoogleGroundedArtifact:
    report_date: date
    synthesis_markdown: str
    citations: list[GroundingCitation]
    search_queries: list[str]
    model: str
    grounding_active: bool = False


# T09-A와 동일한 시스템 프롬프트에서 "local mode" 제약만 Google Search 허용으로 교체
_SYSTEM_PROMPT = dedent("""
당신은 한국/미국 주식 데일리 리포트 합성기다.

핵심 원칙:
- 제공된 Telegram evidence와 Google Search 검색 결과를 함께 사용해 합성한다.
- 사실을 추측하거나 새로 만들지 않는다.
- Google Search 결과는 evidence에 근거가 있는 내용에 한해 보강에 사용한다.
- 출력은 사용자 프롬프트에서 지정한 Markdown 형식을 따른다.
- JSON 형식으로 출력하지 않는다.
""").strip()


def _build_user_prompt(bundle: SameDayBundle) -> str:
    chunk_packet = _build_chunk_packet(bundle)
    chunk_json = json.dumps(chunk_packet, ensure_ascii=False, indent=2)

    prompt = dedent(f"""
report_date: {bundle.report_date.isoformat()}

아래 당일 Telegram evidence chunks를 바탕으로, Google Search로 관련 최신 뉴스/공시/데이터를 검색해 보강한 **Markdown 리포트**를 작성하라.

출력 형식 (Markdown, 섹션 순서 고정):

## Pulse
- (3~5개 bullet) 당일 핵심 시장 신호 요약. 각 항목은 1~2문장.

## Category Summaries
### (카테고리명)
- 투자 내러티브, 수혜 종목, Google 검색으로 보강된 최신 데이터 포함
- 출처: chunk 2884 키움증권 미국주식 톡톡#58426, chunk 2910 신한 리서치#51081 (이 형태로)

## Core Themes
### (테마명)
- 2개 이상 카테고리를 연결하는 상위 투자 논리
- thesis, 근거, impact, 확인 변수 포함
- 출처: chunk 2884 키움증권 미국주식 톡톡#58426 (이 형태로)

## Focus Tickers
### (종목명 / 티커)
- 각 chunk의 tickers 필드에 등장하는 종목 중 근거가 많은 것을 선택
- investment case, 촉매, 핵심 수치, 리스크
- 출처: chunk 2884 키움증권 미국주식 톡톡#58426 (이 형태로)

## Low Confidence
- 당일 확인되지 않은 항목

작성 규칙:
- 출처는 반드시 `chunk {{chunk_id}} {{source}}` 형태로 명시한다. source는 각 chunk의 source 필드 값(channel_name#message_id)을 그대로 사용한다.
- 예시: `출처: chunk 2884 키움증권 미국주식 톡톡#58426, chunk 2910 신한 리서치#51081`
- Google Search 보강 내용은 출처가 명확한 경우에만 반영한다.
- 추측하거나 evidence에 없는 내용을 새로 만들지 않는다.
- core_themes는 최소 2개 이상의 카테고리를 연결하는 경우만 작성한다.
- JSON 형식으로 출력하지 말 것.

evidence chunks (JSON):
{chunk_json}
""").strip()
    return prompt


def _parse_json_output(text: str) -> dict:
    text = text.strip()
    # JSON 블록이 마크다운 코드펜스로 감싸진 경우 추출
    if text.startswith("```"):
        lines = text.splitlines()
        start = next((i + 1 for i, line in enumerate(lines) if line.startswith("```")), 1)
        end = next(
            (i for i in range(len(lines) - 1, start, -1) if lines[i].startswith("```")), len(lines)
        )
        text = "\n".join(lines[start:end])
    return json.loads(text)


def _sanitize_obj_chunk_ids(obj: object) -> None:
    """Recursively sanitize evidence_chunk_ids in a parsed JSON object.

    Removes non-integer ids in-place. Used for Gemini output that may
    contain string ids. Delegates integer validation to the synthesize-layer
    _sanitize_chunk_ids when bundle ids are known; this variant is used when
    no bundle context is available (raw JSON pass).
    """
    if isinstance(obj, dict):
        if "evidence_chunk_ids" in obj:
            ids = obj["evidence_chunk_ids"]
            if isinstance(ids, list):
                obj["evidence_chunk_ids"] = [v for v in ids if isinstance(v, int)]
        for v in obj.values():
            _sanitize_obj_chunk_ids(v)
    elif isinstance(obj, list):
        for item in obj:
            _sanitize_obj_chunk_ids(item)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = next((i + 1 for i, line in enumerate(lines) if line.startswith("```")), 1)
        end = next(
            (i for i in range(len(lines) - 1, start, -1) if lines[i].startswith("```")), len(lines)
        )
        return "\n".join(lines[start:end])
    return text


def _to_markdown(bundle: SameDayBundle, raw_text: str) -> str:
    """JSON 응답이면 StockReportArtifact로 파싱 후 렌더링, Markdown이면 그대로 반환."""
    from src.pipelines.stock_report.render_markdown import render_stock_report_markdown

    try:
        parsed = _parse_json_output(raw_text)
        _sanitize_obj_chunk_ids(parsed)
        llm_output = LocalEvidenceSynthesisOutput.model_validate(parsed)
        artifact = _from_llm_output(bundle, llm_output)
        logger.debug("google grounding: JSON parsed and rendered")
        return render_stock_report_markdown(artifact)
    except Exception:
        logger.debug("google grounding: response is Markdown, using as-is")
        return _strip_code_fence(raw_text)


def _extract_citations(candidate) -> tuple[list[GroundingCitation], list[str]]:
    citations: list[GroundingCitation] = []
    search_queries: list[str] = []
    try:
        meta = candidate.grounding_metadata
        if not meta:
            return citations, search_queries
        for idx, chunk in enumerate(meta.grounding_chunks or []):
            if chunk.web:
                citations.append(
                    GroundingCitation(
                        index=idx + 1,
                        title=chunk.web.title or "",
                        uri=chunk.web.uri or "",
                    )
                )
        search_queries = list(meta.web_search_queries or [])
    except Exception:
        logger.debug("Failed to extract grounding metadata", exc_info=True)
    return citations, search_queries


def synthesize_with_google_grounding(
    bundle: SameDayBundle,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> GoogleGroundedArtifact:
    if not _GENAI_AVAILABLE:
        raise ImportError(
            "google-genai is required for Google Search Grounding. Run: uv add google-genai"
        )

    resolved_api_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "GOOGLE_API_KEY environment variable is required for Google Search Grounding"
        )

    resolved_model = (
        model or os.getenv("STOCK_REPORT_GOOGLE_MODEL") or GOOGLE_GROUNDING_DEFAULT_MODEL
    )
    user_prompt = _build_user_prompt(bundle)

    client = genai.Client(api_key=resolved_api_key)
    gen_config = GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        tools=[Tool(google_search=GoogleSearch())],
        temperature=0.1,
    )

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=resolved_model,
                contents=user_prompt,
                config=gen_config,
            )
            raw_text = response.text or ""
            citations, search_queries = _extract_citations(response.candidates[0])
            grounding_active = bool(citations or search_queries)

            synthesis_markdown = _to_markdown(bundle, raw_text)
            logger.info(
                "google grounding synthesis completed: date=%s model=%s "
                "grounding=%s citations=%d queries=%d chars=%d",
                bundle.report_date,
                resolved_model,
                grounding_active,
                len(citations),
                len(search_queries),
                len(synthesis_markdown),
            )
            return GoogleGroundedArtifact(
                report_date=bundle.report_date,
                synthesis_markdown=synthesis_markdown,
                citations=citations,
                search_queries=search_queries,
                model=resolved_model,
                grounding_active=grounding_active,
            )
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                wait = _RETRY_BASE_WAIT_SECONDS**attempt
                logger.warning(
                    "google grounding attempt %d/%d failed, retrying in %ds: %s",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    wait,
                    exc,
                )
                time.sleep(wait)

    raise RuntimeError(
        f"Google grounding synthesis failed after {_MAX_RETRIES + 1} attempts"
    ) from last_exc
