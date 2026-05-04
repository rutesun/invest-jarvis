"""Extract stage: convert ingested messages into claim/fact cards."""

import re
from collections.abc import Iterable

from langsmith import traceable

from src.pipelines.daily_report.models import (
    Claim,
    ClaimType,
    ExtractResult,
    Fact,
    IngestedMessage,
    MessageType,
    Sentiment,
)


_TARGET_PRICE_PATTERN = re.compile(r"(\d+)\s*달러.*?(\d+)\s*달러")


def _detect_category(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("hbm", "dram", "micron", "마이크론", "반도체")):
        return "반도체"
    if any(token in lowered for token in ("환율", "krw", "usd", "달러원")):
        return "매크로"
    return "기타"


def _detect_polarity(text: str) -> Sentiment:
    if any(token in text for token in ("상향", "증가", "개선", "강세", "확대")):
        return Sentiment.BULL
    if any(token in text for token in ("하향", "약세", "감소", "둔화", "리스크")):
        return Sentiment.BEAR
    return Sentiment.NEUTRAL


def _detect_claim_type(message_type: MessageType) -> ClaimType:
    if message_type is MessageType.BROKER_SUMMARY:
        return ClaimType.BROKER_VIEW
    if message_type is MessageType.MARKET_SIGNAL:
        return ClaimType.MARKET_DATA
    return ClaimType.OPINION


def _extract_entities(text: str) -> list[str]:
    entities: list[str] = []
    for token in ("Micron", "마이크론", "HBM", "DRAM", "CoWoS", "KRWUSD"):
        if token.lower() in text.lower():
            entities.append(token)
    return entities


def _extract_facts(message: IngestedMessage, claim_index: int) -> Iterable[Fact]:
    match = _TARGET_PRICE_PATTERN.search(message.raw_text)
    if not match:
        return []
    return [
        Fact(
            fact_id=f"f{claim_index}-1",
            source_id=message.source_id,
            kind="broker_target_price_change",
            label="target_price",
            value=f"{match.group(1)}->{match.group(2)}",
            numeric_value=float(match.group(2)),
            unit="USD",
        )
    ]


@traceable(name="Extract Stage")
def extract_stage(messages: list[IngestedMessage], date: str) -> ExtractResult:
    del date  # reserved for future trace metadata
    if not messages:
        return ExtractResult(claims=[], facts=[])

    claims: list[Claim] = []
    facts: list[Fact] = []
    for index, message in enumerate(messages, start=1):
        fact_items = list(_extract_facts(message, index))
        facts.extend(fact_items)
        claims.append(
            Claim(
                claim_id=f"c{index}",
                category=_detect_category(message.raw_text),
                claim_type=_detect_claim_type(message.message_type),
                text=message.raw_text,
                canonical_entities=_extract_entities(message.raw_text),
                target_scope="market_view",
                polarity=_detect_polarity(message.raw_text),
                source_ids=[message.source_id],
                fact_ids=[fact.fact_id for fact in fact_items],
                confidence=0.8,
            )
        )

    return ExtractResult(claims=claims, facts=facts)
