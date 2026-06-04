from __future__ import annotations

import json
from textwrap import dedent
from typing import Any

from src.pipelines.stock_report.models import NormalizedMessage
from src.pipelines.stock_report.retrieval import (
    CategoryBucket,
    TickerBucket,
)


# Canonical event_type taxonomy — single source of truth. The prose enumeration inside
# SEMANTIC_EXTRACTION_SYSTEM_PROMPT must mirror this set (guarded by a test that asserts
# every member appears in the prompt). Downstream consumers (e.g. the event safety net)
# import this rather than re-hardcoding the literals, so a rename fails fast instead of
# silently degrading.
CANONICAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "자본조달",
        "수주/계약",
        "실적",
        "정책",
        "인증/승인",
        "M&A",
        "출시/제품",
        "가격/마진",
        "통계/지표",
        "해석/전망",
        "공지",
    }
)


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


# ---------------------------------------------------------------------------
# T09-F: per-category / per-ticker synthesis prompts
# ---------------------------------------------------------------------------

CATEGORY_SYNTHESIS_SYSTEM_PROMPT = dedent(
    """
    당신은 단일 카테고리 evidence bucket을 투자 요약 카드로 합성하는 분석기다.

    핵심 원칙:
    - 제공된 evidence chunk만 사용한다. 외부 지식/검색/추론 금지.
    - 모든 주장은 반드시 evidence_chunk_ids로 근거를 연결한다.
    - evidence_chunk_ids에는 패킷에 포함된 chunk_id 정수만 사용한다. 문자열 id 금지.
    - 수치(%, 금액, 성장률, 기간)는 원문에 있는 것만 쓴다. 창작 금지.
    - 구체 사실(숫자/급등락/사건명)을 보존한다. 압축하더라도 수치는 남긴다.
    - 하락·급락·실적 부진·소송·규제 같은 부정적/리스크 이벤트도 반드시 포함한다. 호재만 골라 담지 마라. 한 chunk 안에 상승·하락이 섞여 있으면 양쪽 다 반영한다.
    - M&A·IPO·대형 자본조달(증자·인수·펀드 결성)은 시장 영향이 크므로 우선 포함한다.
    - 인용한 chunk의 핵심 수치(목표주가, 계약규모, 등락률 등)는 본문에 실제로 반영한다. 출처만 달고 내용을 빠뜨리지 마라.
    - unsupported 내용은 과감히 제거한다.
    """
).strip()

TICKER_SYNTHESIS_SYSTEM_PROMPT = dedent(
    """
    당신은 단일 종목 evidence bucket을 투자 요약 카드로 합성하는 분석기다.

    핵심 원칙:
    - 제공된 evidence chunk만 사용한다. 외부 지식/검색/추론 금지.
    - 모든 주장은 반드시 evidence_chunk_ids로 근거를 연결한다.
    - evidence_chunk_ids에는 패킷에 포함된 chunk_id 정수만 사용한다. 문자열 id 금지.
    - 수치(%, 금액, 성장률, 기간)는 원문에 있는 것만 쓴다. 창작 금지.
    - 구체 사실(숫자/급등락/사건명)을 보존한다. 압축하더라도 수치는 남긴다.
    - 하락·급락·실적 부진·소송·규제 같은 부정적/리스크 이벤트도 반드시 포함한다. 호재만 골라 담지 마라. 한 chunk 안에 상승·하락이 섞여 있으면 양쪽 다 반영한다.
    - M&A·IPO·대형 자본조달(증자·인수·펀드 결성)은 시장 영향이 크므로 우선 포함한다.
    - 인용한 chunk의 핵심 수치(목표주가, 계약규모, 등락률 등)는 본문에 실제로 반영한다. 출처만 달고 내용을 빠뜨리지 마라.
    - unsupported 내용은 과감히 제거한다.
    """
).strip()


def _build_category_chunk_entries(bucket: CategoryBucket) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for chunk in bucket.chunks:
        evidence_items = [
            {"kind": str(item.get("kind") or "fact"), "text": str(item.get("text", "")).strip()}
            for item in chunk.evidence_items
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        entries.append(
            {
                "chunk_id": chunk.id,
                "message_type": chunk.message_type,
                "priority_score": chunk.priority_score,
                "tickers": list(chunk.ticker_tags),
                "canonical_summary": chunk.canonical_summary,
                "supporting_facts": list(chunk.supporting_facts),
                "evidence_items": evidence_items,
                "source": f"{chunk.channel_name or chunk.channel_key or 'unknown'}#{chunk.channel_message_id or '-'}",
            }
        )
    return entries


def _build_ticker_chunk_entries(bucket: TickerBucket) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for chunk in bucket.chunks:
        evidence_items = [
            {"kind": str(item.get("kind") or "fact"), "text": str(item.get("text", "")).strip()}
            for item in chunk.evidence_items
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        entries.append(
            {
                "chunk_id": chunk.id,
                "category": chunk.display_category,
                "theme": chunk.display_theme,
                "message_type": chunk.message_type,
                "priority_score": chunk.priority_score,
                "canonical_summary": chunk.canonical_summary,
                "supporting_facts": list(chunk.supporting_facts),
                "evidence_items": evidence_items,
                "source": f"{chunk.channel_name or chunk.channel_key or 'unknown'}#{chunk.channel_message_id or '-'}",
            }
        )
    return entries


# Token budget: approximate character limit per category prompt (~12000 tokens ≈ 48000 chars).
# We use a char count proxy because the actual tokenizer is not available here.
CATEGORY_CONTEXT_BUDGET_CHARS = 48_000
# Minimum evidence_items to keep per chunk even when trimming
_MIN_EVIDENCE_ITEMS_PER_CHUNK = 1


def _trim_entries_to_budget(
    entries: list[dict[str, Any]],
    budget_chars: int,
) -> list[dict[str, Any]]:
    """Progressively trim supporting_facts and evidence_items on low-priority chunks
    until the serialized JSON fits within budget_chars.

    Priority order for trimming (lowest priority first):
    1. Reduce evidence_items on low priority_score chunks first
    2. Reduce supporting_facts on low priority_score chunks
    3. Sub-batch: drop entire low-priority chunks if still over budget

    Returns a new list (entries themselves are not mutated).
    """
    import copy

    working = copy.deepcopy(entries)
    # Sort ascending by priority_score so we trim the least important first
    indexed = sorted(enumerate(working), key=lambda x: (x[1].get("priority_score", 0.0), x[0]))

    def _serialized_len() -> int:
        return len(json.dumps(working, ensure_ascii=False))

    # Pass 1: trim evidence_items progressively from least-priority chunks
    for orig_idx, _entry in indexed:
        if _serialized_len() <= budget_chars:
            break
        items = working[orig_idx].get("evidence_items", [])
        while len(items) > _MIN_EVIDENCE_ITEMS_PER_CHUNK and _serialized_len() > budget_chars:
            items.pop()
        working[orig_idx]["evidence_items"] = items

    # Pass 2: trim supporting_facts progressively
    for orig_idx, _entry in indexed:
        if _serialized_len() <= budget_chars:
            break
        facts = working[orig_idx].get("supporting_facts", [])
        while facts and _serialized_len() > budget_chars:
            facts.pop()
        working[orig_idx]["supporting_facts"] = facts

    # Pass 3: drop entire chunks (sub-batch) if still over budget.
    # Walk indexed ascending (lowest priority first) and drop by object identity.
    # Each iteration rebuilds `working` without the target entry so that
    # _serialized_len() stays accurate and index positions never shift.
    for _orig_idx, target in indexed:  # ascending = lowest priority first
        if _serialized_len() <= budget_chars:
            break
        if len(working) <= 1:
            break
        working = [e for e in working if e is not target]

    return working


def build_category_synthesis_prompt(bucket: CategoryBucket) -> str:
    entries = _build_category_chunk_entries(bucket)
    entries = _trim_entries_to_budget(entries, CATEGORY_CONTEXT_BUDGET_CHARS)
    packet_json = json.dumps(entries, ensure_ascii=False, indent=2)
    return dedent(
        f"""
        category: {bucket.category_key}
        chunk_count: {len(bucket.chunks)}

        아래 evidence chunks를 사용해 이 카테고리의 투자 요약 카드를 생성하라.

        출력 schema (JSON):
        {{
          "category_key": "{bucket.category_key}",
          "title": "카테고리 핵심 내러티브 제목 (20자 이내)",
          "narrative": "이 카테고리의 핵심 투자 내러티브 (1~3문장, 구체 사실/수치 포함)",
          "evidence_bullets": ["원문 기반 핵심 근거 bullet (3~8개)", ...],
          "impact": "수혜/피해 범위, 밸류체인, 수급/실적 경로 (1~2문장)",
          "related_stocks": [{{"name": "...", "ticker": "...", "catalyst": "..."}}],
          "evidence_chunk_ids": [chunk_id 정수 배열 — 이 카드에 근거가 된 chunk id만],
          "priority_score": 0.0~1.0 (시장 영향도·반복 근거·수혜 명확성·당일성 기준)
        }}

        작성 규칙:
        - evidence_chunk_ids에는 아래 패킷에 있는 chunk_id 정수만 사용한다.
        - 수치 창작 금지 — 원문에 있는 수치만 쓴다.
        - 구체 사실(숫자/급등락/사건명)을 보존한다.
        - 카드는 반드시 1개만 출력한다 (배열 아님).

        evidence chunks (JSON):
        {packet_json}
        """
    ).strip()


def build_ticker_synthesis_prompt(bucket: TickerBucket) -> str:
    entries = _build_ticker_chunk_entries(bucket)
    entries = _trim_entries_to_budget(entries, CATEGORY_CONTEXT_BUDGET_CHARS)
    packet_json = json.dumps(entries, ensure_ascii=False, indent=2)
    return dedent(
        f"""
        ticker: {bucket.ticker}
        chunk_count: {len(bucket.chunks)}

        아래 evidence chunks를 사용해 이 종목의 투자 요약 카드를 생성하라.

        출력 schema (JSON):
        {{
          "ticker": "{bucket.ticker}",
          "investment_case": "당일 투자 포인트 (1문장, 구체 사실/수치 포함)",
          "catalysts": ["주가/관심을 움직일 촉매 (3~8개)", ...],
          "key_metrics": ["수치가 있는 핵심 근거만 (있으면)", ...],
          "risks": ["투자 논리가 약해지는 조건/확인 변수", ...],
          "evidence_chunk_ids": [chunk_id 정수 배열 — 이 카드에 근거가 된 chunk id만]
        }}

        작성 규칙:
        - evidence_chunk_ids에는 아래 패킷에 있는 chunk_id 정수만 사용한다.
        - 수치 창작 금지 — 원문에 있는 수치만 쓴다.
        - 구체 사실(숫자/급등락/사건명)을 보존한다.
        - 카드는 반드시 1개만 출력한다 (배열 아님).

        evidence chunks (JSON):
        {packet_json}
        """
    ).strip()


# ---------------------------------------------------------------------------
# T09-G: overview (reduce) synthesis prompts
# ---------------------------------------------------------------------------

OVERVIEW_SYNTHESIS_SYSTEM_PROMPT = dedent(
    """
    당신은 per-category/per-ticker 요약 카드들을 받아 당일 시장 전체 관점의 Pulse와 Core Themes를 합성하는 reduce 분석기다.

    핵심 원칙:
    - 입력은 이미 합성된 카드 요약이다. 외부 지식/검색/추론 금지.
    - 모든 주장은 source_card_indices로 어느 카드에서 나왔는지 연결한다.
    - Pulse는 단순 뉴스 나열이 아니라 **투자 인사이트**다. 3~5개, 서로 다른 카드에서 선택한다.
      각 항목은 "무슨 일이 있었나(핵심 신호+수치)"에서 멈추지 말고, **그래서 투자적으로 무엇을
      의미하는가**를 제시한다: 방향성, 수급/자금 흐름, 밸류에이션/멀티플, 포지셔닝(무엇이 수혜/피해),
      주목해야 할 포인트 중 해당되는 것을 카드 근거로 묶어 말한다. 카드에 없는 추측·수치는 금지.
    - Core Themes는 반드시 2개 이상의 서로 다른 카테고리 카드를 연결하는 상위 투자 내러티브만 만든다.
      단일 카테고리의 내용만 반복하는 테마는 금지.
    - 카드의 구체 사실(숫자/사건명/급등락)을 그대로 인용해 cross-category 연결 논리를 만든다.
    - 수치 창작 금지 — 카드에 있는 수치만 사용한다.
    - source_card_indices는 0-based 정수 배열. 입력 카드 배열의 인덱스다.
    """
).strip()


def _build_category_card_entry(card: Any, idx: int) -> dict[str, Any]:
    """Serialize a CategorySummaryCard into a compact JSON-serializable dict."""
    return {
        "card_index": idx,
        "card_type": "category",
        "category_key": getattr(card, "category_key", ""),
        "title": getattr(card, "title", ""),
        "narrative": getattr(card, "narrative", ""),
        "evidence_bullets": list(getattr(card, "evidence_bullets", []))[:6],
        "impact": getattr(card, "impact", ""),
        "related_stocks": [
            {
                "name": str(s.get("name", "") if isinstance(s, dict) else getattr(s, "name", "")),
                "ticker": s.get("ticker") if isinstance(s, dict) else getattr(s, "ticker", None),
            }
            for s in list(getattr(card, "related_stocks", []))[:5]
        ],
        "priority_score": float(getattr(card, "priority_score", 0.0)),
        "evidence_chunk_ids": list(getattr(card, "evidence_chunk_ids", [])),
    }


def _build_ticker_card_entry(card: Any, idx: int) -> dict[str, Any]:
    """Serialize a TickerCard into a compact JSON-serializable dict."""
    return {
        "card_index": idx,
        "card_type": "ticker",
        "ticker": getattr(card, "ticker", ""),
        "investment_case": getattr(card, "investment_case", ""),
        "catalysts": list(getattr(card, "catalysts", []))[:5],
        "key_metrics": list(getattr(card, "key_metrics", []))[:5],
        "risks": list(getattr(card, "risks", []))[:3],
        "evidence_chunk_ids": list(getattr(card, "evidence_chunk_ids", [])),
    }


def build_overview_prompt(
    category_cards: list[Any],
    ticker_cards: list[Any],
) -> str:
    """Build the reduce-step user prompt from CategorySummaryCard / TickerCard lists.

    Inputs are already-synthesized card summaries, not raw chunks.
    The LLM must reference source_card_indices (0-based index into the combined
    card array) for each Pulse item and Core Theme.
    """
    combined_cards: list[dict[str, Any]] = []
    for idx, card in enumerate(category_cards):
        combined_cards.append(_build_category_card_entry(card, idx))
    ticker_offset = len(category_cards)
    for rel_idx, card in enumerate(ticker_cards):
        combined_cards.append(_build_ticker_card_entry(card, ticker_offset + rel_idx))

    cards_json = json.dumps(combined_cards, ensure_ascii=False, indent=2)
    cat_count = len(category_cards)
    ticker_count = len(ticker_cards)
    return dedent(
        f"""
        category_card_count: {cat_count}
        ticker_card_count: {ticker_count}

        아래 per-category/per-ticker 요약 카드 배열을 사용해 Pulse와 Core Themes를 합성하라.

        출력 schema (JSON):
        {{
          "pulse": [
            {{
              "key": "pulse-1",
              "title": "방향성 있는 신호 제목 (20자 이내)",
              "body": "핵심 신호와 수치를 담되, 단순 사건 요약에서 멈추지 말고 그 신호의 투자 함의(방향성/수급/밸류에이션/포지셔닝/주목 포인트)를 1~2문장으로 제시. 투자자가 어떻게 읽어야 하는지가 보여야 한다.",
              "source_card_indices": [0-based card_index 정수 배열],
              "priority_score": 0.0~1.0
            }},
            ...
          ],
          "core_themes": [
            {{
              "key": "theme-1",
              "title": "테마 제목 (20자 이내)",
              "thesis": "왜 이 테마가 당일 투자적으로 중요한지 (1문장, 카드 수치 인용)",
              "connected_categories": ["연결된 category_key 배열 (2개 이상 필수)"],
              "impact": "수혜 범위/밸류체인/수급 경로 (1~2문장)",
              "watch_points": ["이 논리가 약해지는 조건 (2~4개)"],
              "source_card_indices": [0-based card_index 정수 배열],
              "priority_score": 0.0~1.0
            }},
            ...
          ]
        }}

        작성 규칙:
        - pulse: 3~5개, 서로 다른 카드에서 선택. 당일 가장 중요한 신호 우선.
        - core_themes: connected_categories에 2개 이상 서로 다른 category_key가 있어야 만든다.
          단일 카테고리 요약은 core_themes에 넣지 않는다.
        - source_card_indices는 입력 배열의 card_index 정수만 사용한다.
        - 카드에 없는 수치/사실 창작 금지.
        - JSON만 출력한다.

        cards (JSON):
        {cards_json}
        """
    ).strip()
