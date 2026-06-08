from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date
from textwrap import dedent

from src.pipelines.stock_report.retrieval import SameDayBundle


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
- 맞춤법을 정확히 지킨다.
""").strip()


def _build_user_prompt(bundle: SameDayBundle) -> str:
    chunk_packet = [
        {
            "chunk_id": chunk.id,
            "category": chunk.display_category,
            "theme": chunk.display_theme,
            "tickers": chunk.ticker_tags,
            "summary": chunk.canonical_summary,
            "supporting_facts": chunk.supporting_facts,
            "source": f"{chunk.channel_name or chunk.channel_key or 'unknown'}#{chunk.channel_message_id or ''}",
        }
        for chunk in bundle.chunks
    ]
    chunk_json = json.dumps(chunk_packet, ensure_ascii=False, indent=2)

    prompt = dedent(f"""
report_date: {bundle.report_date.isoformat()}

아래 당일 Telegram evidence chunks를 바탕으로, Google Search로 관련 최신 뉴스/공시/데이터를 검색해 보강한 **Markdown 리포트**를 작성하라.

출력 형식 (Markdown). 섹션 순서와 **라벨·중첩 구조를 아래와 정확히 일치**시킨다.
상단에 `#` 제목을 붙이지 말고 `## Pulse`부터 시작한다.
각 항목은 "라벨 줄 + 들여쓴 내용"의 2단 구조다: 라벨은 `- 라벨`, 내용은 그 아래
`  - 내용`(공백 2칸 들여쓰기). 라벨과 내용을 한 줄에 합치지 않는다.

## Pulse
- (방향성 있는 신호 제목)
  - (투자 인사이트: 핵심 신호와 수치를 담되 단순 뉴스 나열에서 멈추지 말고, 그 신호의 투자 함의 — 방향성/수급/밸류에이션/포지셔닝/주목 포인트 — 를 1~2문장으로. 투자자가 어떻게 읽어야 하는지가 보여야 한다.)
- 3~5개, 서로 다른 신호.

## Category Summaries
### (카테고리명)
- Narrative
  - (이 카테고리의 핵심 투자 내러티브 1~3문장, 수치 포함)
- Impact
  - (수혜/피해 범위·밸류체인·수급 경로 1~2문장)
- 근거
  - (개별 사실/근거 bullet)
  - (여러 개)
- 관련 종목
  - 종목명(티커): 촉매
- 출처: chunk {{chunk_id}} {{source}}, chunk {{chunk_id}} {{source}}  ← 한 줄, 콤마 구분

## Core Themes
### (테마명)
- 핵심 주장
  - (2개 이상 카테고리를 잇는 상위 투자 논리 1문장, 수치 인용)
- Impact
  - (수혜 범위/밸류체인/수급 경로)
- 확인 변수
  - (이 논리가 약해지는 조건)
- 연결 카테고리
  - (연결된 category 2개 이상)
- 출처: chunk {{chunk_id}} {{source}}, chunk {{chunk_id}} {{source}}  ← 한 줄, 콤마 구분

## Focus Tickers
### (티커 심볼만. 예: AVGO, MRVL, SK하이닉스. 괄호·풀네임 금지)
- 투자 포인트
  - (당일 투자 포인트 1문장)
- 촉매
  - (주가/관심 촉매)
- 핵심 수치
  - (수치 근거)
- 리스크/확인
  - (논리가 약해지는 조건)
- 출처: chunk {{chunk_id}} {{source}}, chunk {{chunk_id}} {{source}}  ← 한 줄, 콤마 구분

## Low Confidence
- 당일 확인되지 않은 항목

라벨·구조 규칙 (정확히 지킬 것):
- 라벨 줄(`- 라벨`)과 내용(`  - 내용`, 2칸 들여쓰기)을 분리한다. 한 줄에 합치지 않는다.
  단 `출처`만 예외로 `- 출처: ...` 한 줄에 콤마로 모아 쓴다.
- 라벨은 위 표기 그대로 쓴다. `Investment Case` 같은 임의 영어 라벨 금지. 라벨을 굵게(`**`) 처리하지 않는다.
- Focus Tickers의 `###` 제목은 티커 심볼만 쓴다(괄호·풀네임 금지). 같은 종목을 회사명과 티커로 중복 표기하지 않는다(예: Tesla와 TSLA를 따로 만들지 말고 TSLA 하나로 합친다).
- 출처는 `- 출처: chunk {{chunk_id}} {{source}}, chunk ...` 한 줄. source는 각 chunk의 source 필드 값(channel_name#message_id)을 그대로 쓴다.
- Google Search 보강 내용은 출처가 명확한 경우에만 반영한다.
- 추측하거나 evidence에 없는 내용을 새로 만들지 않는다.
- core_themes는 최소 2개 이상의 카테고리를 연결하는 경우만 작성한다.
- JSON 형식으로 출력하지 말 것.

evidence chunks (JSON):
{chunk_json}
""").strip()
    return prompt


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
    """Google grounding returns Markdown; strip any code fence and return as-is."""
    return _strip_code_fence(raw_text)


def _extract_citations(candidate) -> tuple[list[GroundingCitation], list[str]]:
    citations: list[GroundingCitation] = []
    search_queries: list[str] = []
    try:
        meta = candidate.grounding_metadata
        if not meta:
            return citations, search_queries
        for chunk in meta.grounding_chunks or []:
            if chunk.web:
                # Number web citations contiguously (1-based). Non-web chunks are skipped
                # without consuming a number, so the first web citation is always [1].
                citations.append(
                    GroundingCitation(
                        index=len(citations) + 1,
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

            # Retry when grounding did not fire: an ungrounded response is pure
            # parametric Gemini output (no search), which fabricates numbers/entities.
            # Try to recover real grounding before falling back to a suppressed report.
            # not-fired and exception retries deliberately share one bounded budget
            # (max _MAX_RETRIES + 1 total calls) to cap per-request grounding cost;
            # not-fired is the common case and gets the budget unless exceptions intervene.
            if not grounding_active and attempt < _MAX_RETRIES:
                wait = _RETRY_BASE_WAIT_SECONDS**attempt
                logger.warning(
                    "google grounding did not fire (attempt %d/%d), retrying in %ds",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    wait,
                )
                time.sleep(wait)
                continue

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
