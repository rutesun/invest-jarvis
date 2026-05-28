from __future__ import annotations

import json
from collections import defaultdict
from textwrap import dedent
from typing import Any

from src.pipelines.stock_report.models import NormalizedMessage
from src.pipelines.stock_report.retrieval import SameDayBundle, SameDayChunk, TickerBucket


FOCUS_TICKER_DETAILED_BUCKET_LIMIT = 10
FOCUS_TICKER_COMPACT_SUMMARY_LIMIT = 3


SEMANTIC_EXTRACTION_SYSTEM_PROMPT = dedent(
    """
    당신은 텔레그램 증시 메시지를 report unit으로 구조화하는 분석기다.

    핵심 원칙:
    - formatting marker(▶, *, -, 숫자)만 보고 자르지 말고 의미 단위를 기준으로 판단한다.
    - 하나의 중심 토픽을 여러 supporting section이 설명하는 메시지는 `single_topic_deep`으로 두고 unit 1개만 만든다.
    - 여러 독립 기사/헤드라인 digest는 `multi_item_digest`로 보고 item별 unit을 만든다.
    - 장 마감 시황/섹터 wrap은 `market_wrap`으로 처리한다.
    - `market_wrap`이라도 서로 다른 핵심 내러티브가 2개 이상이면 unit을 분리한다.
      예: 반도체 랠리 / 유가 급등 / 한국 증시 반응은 각각 별도 unit 후보다.
    - Daily/Digest/Review/특징주/예습/마켓레이더/US Daily 형태의 다중 아이템 메시지는
      시장 전체 headline/내러티브를 별도 unit으로 보존하고, 독립 bullet/section/company block은 각각 분리한다.
    - 공지/채널 운영/홍보는 `notice`로 처리한다.
    - 증권사 리포트의 공표 승인/배포 제한/저작권 문구는 하단 고지일 뿐이다.
      본문이 기업 분석/실적 전망이면 하단 고지 때문에 `admin`으로 분류하지 않는다.
    - `message_type`는 아래 기준을 따른다.
      - `signal`: 기업 이벤트/실적/수주/인증/협약/정책 변화처럼 투자 판단에 직접 쓰이는 사건
      - `data`: 시장 통계/판매량/비중/증감률 등 정량 수치 나열 중심
      - `opinion`: 해석/전망/코멘트 중심 (팩트보다 주장 비중 높음)
      - `admin`: 채널 운영 공지/구독/안내
    - `category_key`는 이벤트 종류가 아니라 투자 내러티브/섹터를 고른다.
      예: AI 인프라 기업의 전환사채 이슈는 `category_key=AI인프라`, `event_type=자본조달`.
    - 원인(원자재/매크로)보다 실제 수혜/피해를 받는 타깃 섹터를 우선한다.
      예: 유가 하락으로 항공주가 수혜면 `category_key=운송/물류`, `event_type=가격/마진`.
      예: ETF 출시/등록 자체 뉴스면 `category_key=금융상품`, 기반 자산 테마는 근거/설명으로 남긴다.
    - 숫자가 있다고 항상 `data`로 두지 말고, 사건성이 강하면 `signal`을 우선한다.

    출력 규칙:
    - `event_type`은 아래 canonical set 중 하나를 우선 사용한다.
      `자본조달`, `수주/계약`, `실적`, `정책`, `인증/승인`, `M&A`, `출시/제품`, `가격/마진`, `통계/지표`, `해석/전망`, `공지`.
      모호하면 null 허용.
    - `canonical_summary`는 report unit 기준의 한글 요약문이다.
    - `canonical_summary`는 20~60자 정도의 factual summary로 작성한다.
    - `canonical_summary`는 원문 첫 줄 복사나 prefix truncation이 아니어야 한다.
    - `evidence_items`는 최종 리포트가 근거를 선별할 수 있도록 충분히 넓게 보존한다.
    - `evidence_items`의 각 항목은 `kind`와 `text`를 가진다.
    - `kind`는 `fact`, `metric`, `thesis`, `risk`, `market_context`, `author_comment` 중 하나다.
    - `fact`: 특별한 수치/논리/리스크 역할이 없는 핵심 사실.
    - `metric`: %, 금액, 물량, 성장률, 기간, 밸류에이션 등 명시적 수치 근거.
    - `thesis`: 이 뉴스가 왜 투자적으로 중요한지에 대한 원문 기반 논리.
    - `risk`: 투자 논리가 깨질 수 있는 원문 기반 조건.
    - `market_context`: 숫자만 보면 안 보이는 시장/산업/가격/규제/계약 배경.
    - `author_comment`: 본문과 분리된 작성자 해석/추가 메모.
    - `evidence_items`는 중복을 제거하되, 원문에 있는 투자 논리와 핵심 수치를 빠뜨리지 않는다.
    - 수치 근거는 원문의 부호(+/-)와 단위(%, %p, $, 억/조, 달러)를 가능한 그대로 보존한다.
    - 원문에 명시적 수치가 있으면 해당 근거는 `fact`보다 `metric`을 우선 사용한다.
    - `evidence_items.text`는 원문에 근거가 있는 짧은 추출형 문장으로 작성한다.
      원문보다 더 길게 확장하거나, 원문에 없는 시장 영향/수혜/리스크를 새로 추론하지 않는다.
    - 각 `evidence_items.text` 항목은 가능하면 80자 이내로 쓴다.
    - 제목, 채널명, 날짜, 작성자명, 링크, 컴플라이언스/배포 고지는 투자 근거가 아니면 제외한다.
    - 본문 앞부분의 작성자 코멘트/해석/추가 메모는 기사 본문보다 우선적으로 검토한다.
      별도 수치, 주주 관점, 투자 포인트, 리스크 코멘트가 있으면 `evidence_items`에 반드시 보존한다.
    - `single_topic_deep`에서는 특히 아래 성격의 근거를 우선 보존한다.
      - thesis: 이 뉴스가 왜 투자적으로 중요한지.
        예: 단순 발전자산 인수가 아니라 북버지니아 데이터센터 전력 수요와 규제자산 성장 경로를 확보한다.
      - risk: 이 투자 논리가 깨지는 조건.
        예: FERC/PJM 가격 통제, 규제 승인 실패, break fee, 고객 요금 부담.
      - market_context: 숫자만 보면 안 보이는 시장/제도/가격/규제 배경.
        예: 허용 ROE와 규제자산 기반 요금 회수 구조가 유틸리티 실적에 영향을 준다.
    - `evidence_items`는 일반 메시지는 5~8개, 단건 심층 메시지는 필요하면 12~20개까지 허용한다.
    - 원문에 수치(%, 금액, 물량, 성장률)가 있다면 `metric` 근거를 최소 1개 이상 반드시 포함한다.
    - `ticker_tags`는 회사명 또는 ticker를 최대 5개까지 넣는다.
    - category/theme는 제공된 taxonomy를 우선 사용하되, 확신이 없으면 null로 둔다.
    - 호환용 근거 리스트 필드는 출력하지 않는다. 이 값은 코드가 `evidence_items.text`에서 파생한다.
    - 메시지에 없는 사실을 만들지 않는다.
    """
).strip()


def build_semantic_extraction_user_prompt(
    row: NormalizedMessage,
    *,
    taxonomy_outline: str,
) -> str:
    return dedent(
        f"""
        아래는 단일 텔레그램 메시지다. 이 메시지를 report unit 배열로 구조화하라.

        taxonomy:
        {taxonomy_outline}

        message metadata:
        - telegram_message_id: {row.telegram_message_id}
        - channel_key: {row.channel_key}
        - source_channel_key: {row.source_channel_key}
        - processing_mode: {row.processing_mode}

        분류 힌트:
        - `single_topic_deep`: 하나의 회사/이벤트/내러티브를 여러 supporting bullet이 설명하는 경우
        - `multi_item_digest`: 서로 독립적인 기사/회사/이벤트가 한 메시지에 나열된 경우
        - `market_wrap`: 하루 시황/섹터 흐름을 묶은 경우
        - `market_wrap`에서도 반도체 랠리, 유가/지정학, 국내 증시 반응처럼 주제가 다르면 unit을 나눈다
        - Daily/Digest/Review/특징주/예습/마켓레이더/US Daily 다중 아이템 메시지는 시장 headline unit을 먼저 따로 두고,
          남은 독립 bullet/section/company block을 각각 분리한다
        - `notice`: 운영 공지, 채널 안내, 구독 유도
        - 사건성 기사형 아이템(상장/수주/협약/인증/정책발표 등)은 기본적으로 `signal` 우선
        - `category_key`는 내러티브/섹터, `event_type`은 촉발 이벤트 축으로 분리한다

        message:
        {row.clean_text}
        """
    ).strip()


REPORT_SYNTHESIS_SYSTEM_PROMPT = dedent(
    """
    당신은 한국/미국 주식 데일리 리포트 합성기다.

    핵심 원칙:
    - 제공된 evidence packet과 schema만 사용해 합성한다.
    - 외부 검색/브라우징/추가 소스 탐색은 금지한다(local mode).
    - 사실을 추측하거나 새로 만들지 않는다.
    - 모든 주장/요약은 반드시 evidence_chunk_ids로 근거를 연결한다.
    - evidence_chunk_ids에는 packet에 포함된 chunk id만 사용한다.
    - unsupported 근거가 많으면 과감히 항목 수를 줄인다.
    - low confidence 항목은 호출자가 별도로 처리하므로 출력하지 않는다.
    """
).strip()


def _build_chunk_packet(bundle: SameDayBundle) -> list[dict[str, object]]:
    packet: list[dict[str, object]] = []
    for chunk in bundle.chunks:
        evidence_excerpt = [
            item.get("text", "").strip()
            for item in chunk.evidence_items
            if isinstance(item, dict) and item.get("text")
        ]
        packet.append(
            {
                "chunk_id": chunk.id,
                "category": chunk.display_category,
                "theme": chunk.display_theme,
                "tickers": chunk.ticker_tags,
                "canonical_summary": chunk.canonical_summary,
                "supporting_facts": chunk.supporting_facts[:3],
                "evidence_items_excerpt": evidence_excerpt[:4],
                "source": f"{chunk.channel_name or chunk.channel_key or 'unknown'}#{chunk.channel_message_id or '-'}",
            }
        )
    return packet


def _dedupe_texts(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(value.strip().split())
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _evidence_items_for_chunk(chunk: SameDayChunk) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in chunk.evidence_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        kind = str(item.get("kind") or "fact").strip() or "fact"
        items.append({"kind": kind, "text": text})
    return items


def _evidence_by_kind(chunks: list[SameDayChunk]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        for item in _evidence_items_for_chunk(chunk):
            grouped[item["kind"]].append(item["text"])
    return {kind: _dedupe_texts(values) for kind, values in sorted(grouped.items())}


def _source_for_chunk(chunk: SameDayChunk) -> str:
    return (
        f"{chunk.channel_name or chunk.channel_key or 'unknown'}#{chunk.channel_message_id or '-'}"
    )


def _ticker_detail_level(bucket: TickerBucket) -> str:
    evidence_count = sum(len(_evidence_items_for_chunk(chunk)) for chunk in bucket.chunks)
    fact_count = sum(len(chunk.supporting_facts) for chunk in bucket.chunks)
    if len(bucket.chunks) >= 2 or evidence_count + fact_count >= 8:
        return "deep"
    return "brief"


def _build_detailed_focus_ticker_bucket(bucket: TickerBucket) -> dict[str, Any]:
    supporting_facts = _dedupe_texts(
        [fact for chunk in bucket.chunks for fact in chunk.supporting_facts]
    )
    return {
        "ticker": bucket.ticker,
        "detail_level": _ticker_detail_level(bucket),
        "chunk_count": len(bucket.chunks),
        "evidence_item_count": sum(
            len(_evidence_items_for_chunk(chunk)) for chunk in bucket.chunks
        ),
        "categories": sorted({chunk.display_category for chunk in bucket.chunks}),
        "themes": sorted({theme for chunk in bucket.chunks if (theme := chunk.display_theme)}),
        "source_chunks": [
            {
                "chunk_id": chunk.id,
                "canonical_summary": chunk.canonical_summary,
                "category": chunk.display_category,
                "theme": chunk.display_theme,
                "source": _source_for_chunk(chunk),
            }
            for chunk in bucket.chunks
        ],
        "supporting_facts": supporting_facts,
        "evidence_by_kind": _evidence_by_kind(bucket.chunks),
    }


def _build_compact_focus_ticker_bucket(bucket: TickerBucket) -> dict[str, Any]:
    return {
        "ticker": bucket.ticker,
        "detail_level": _ticker_detail_level(bucket),
        "chunk_count": len(bucket.chunks),
        "categories": sorted({chunk.display_category for chunk in bucket.chunks}),
        "themes": sorted({theme for chunk in bucket.chunks if (theme := chunk.display_theme)}),
        "chunk_ids": [chunk.id for chunk in bucket.chunks],
        "top_summaries": [
            chunk.canonical_summary
            for chunk in bucket.chunks[:FOCUS_TICKER_COMPACT_SUMMARY_LIMIT]
            if chunk.canonical_summary
        ],
    }


def _build_focus_ticker_packet(bundle: SameDayBundle) -> dict[str, Any]:
    detailed_buckets: list[dict[str, Any]] = []
    compact_buckets: list[dict[str, Any]] = []
    for index, bucket in enumerate(bundle.focus_ticker_buckets):
        if index >= FOCUS_TICKER_DETAILED_BUCKET_LIMIT:
            compact_buckets.append(_build_compact_focus_ticker_bucket(bucket))
            continue
        detailed_buckets.append(_build_detailed_focus_ticker_bucket(bucket))
    return {
        "detailed_buckets": detailed_buckets,
        "compact_buckets": compact_buckets,
        "detailed_bucket_limit": FOCUS_TICKER_DETAILED_BUCKET_LIMIT,
    }


def _build_synthesis_packet(bundle: SameDayBundle) -> dict[str, object]:
    return {
        "chunks": _build_chunk_packet(bundle),
        "focus_ticker_packet": _build_focus_ticker_packet(bundle),
    }


def build_report_synthesis_user_prompt(bundle: SameDayBundle) -> str:
    packet = _build_synthesis_packet(bundle)
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2)
    return dedent(
        f"""
        report_date: {bundle.report_date.isoformat()}

        아래 evidence packet을 사용해 구조화된 리포트를 생성하라.
        출력 schema:
        - pulse: 3~5개 (title, body, evidence_chunk_ids, priority_score)
        - category_summaries: 투자 내러티브 카드 배열
          (category_key, title, evidence_bullets, impact, related_stocks[name,ticker,catalyst],
           evidence_chunk_ids, priority_score)
        - core_themes: 핵심 상위 내러티브 카드 배열
          (key, title, thesis, evidence_bullets, impact, watch_points,
           related_categories, related_stocks[name,ticker,catalyst], evidence_chunk_ids, priority_score)
        - focus_tickers: 핵심 종목 카드 배열
          (key, title, investment_case, catalysts, evidence_bullets,
           key_metrics, risks_or_watch_points, related_themes, evidence_chunk_ids, priority_score)

        작성 규칙:
        - 카드는 자르지 말고 evidence packet에서 의미 있는 투자 내러티브를 모두 보여준다.
        - 모든 카드 배열은 priority_score가 높은 순서로 작성한다.
        - priority_score는 0.0~1.0 사이 숫자이며, 시장 영향도·반복 근거 수·수혜 종목 명확성·당일성으로 판단한다.
        - 서로 다른 category에 있어도 같은 투자 논리와 수혜 구조면 하나의 카드로 병합한다.
        - 비슷해 보여도 수혜 구조나 리스크가 다르면 별도 카드로 유지한다.
        - pulse는 가능하면 서로 다른 category/theme에서 고른다.
        - 같은 category/theme를 pulse에 2개 이상 넣는 것은 해당 축이 당일 시장을 압도할 때만 허용한다.
        - Core Themes는 상위 카테고리 반복 요약이 아니라 여러 chunk/category/ticker를 관통하는
          핵심 투자 내러티브를 뽑는다.
        - Core Themes는 최소 2개 이상의 category 또는 3개 이상의 chunk를 연결할 때만 만든다.
        - Core Themes는 예를 들어 `AI 데이터센터 투자 확대 -> 전력/반도체/부품 수요 확산`처럼
          원인, 수혜 경로, 연결 섹터가 보이는 경우를 우선한다.
        - Core Themes가 category_summaries와 같은 말이면 만들지 말고, 더 상위의 연결 논리로 재작성한다.
        - Core Themes의 thesis는 `왜 이 테마가 당일 투자적으로 중요한지`를 한 문장으로 쓴다.
        - Core Themes의 evidence_bullets는 서로 다른 chunk/category에서 가져온 근거 3~6개를 우선한다.
        - Core Themes의 impact는 수혜 범위, 밸류체인 확산, 수급/실적 경로를 설명한다.
        - Core Themes의 watch_points는 이 논리가 약해지는 조건이나 확인할 변수 2~5개를 쓴다.
        - Focus Tickers는 단순 1문단 요약이 아니라 해당 종목을 왜 오늘 봐야 하는지 설명한다.
        - Focus Tickers는 `focus_ticker_packet`을 우선 사용하고, `detail_level=deep`인 종목은
          중요한 수치·논리·리스크를 과도하게 압축하지 않는다.
        - Focus Tickers의 investment_case는 `이 종목의 당일 투자 포인트`를 한 문장으로 쓴다.
        - Focus Tickers의 catalysts는 주가/관심을 움직일 촉매를 쓴다. deep 종목은 4~8개까지 허용한다.
        - Focus Tickers의 key_metrics는 수치가 있는 핵심 근거만 분리해 쓴다.
        - Focus Tickers의 evidence_bullets는 원문 기반 핵심 근거를 보존한다. deep 종목은 8~15개까지 허용한다.
        - Focus Tickers의 risks_or_watch_points는 이 종목 논리가 약해지는 조건이나 확인 변수를 쓴다.
        - Focus Tickers의 related_themes는 이 종목이 연결되는 테마를 1~5개 쓴다.

        evidence packet(JSON):
        {packet_json}
        """
    ).strip()
