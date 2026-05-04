"""Evidence classification for daily report fragments."""

from __future__ import annotations

import re

from src.pipelines.daily_report.models import ArticleFragment, SourceType


_NEWS_TOKENS = (
    "reuters",
    "bloomberg",
    "yonhap",
    "연합뉴스",
    "속보",
    "breaking",
)
_BROKER_CHANNEL_TOKENS = (
    "research",
    "증권",
    "리서치",
    "securities",
)
_MARKET_SIGNAL_TOKENS = (
    "수급",
    "선물",
    "옵션",
    "호가",
    "flow",
)
_SOCIAL_TOKENS = (
    "youtube",
    "x.com",
    "twitter.com",
    "threads.net",
)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def classify_source_type(
    channel_id: str,
    title: str,
    body: str,
    url: str | None = None,
) -> SourceType:
    """Classify source type from channel/text/url features."""
    channel = channel_id.lower()
    title_body = f"{title}\n{body}".lower()
    url_text = (url or "").lower()
    combined = f"{title_body}\n{url_text}"

    if _contains_any(channel, _BROKER_CHANNEL_TOKENS):
        return SourceType.BROKER_SUMMARY

    if _contains_any(combined, _SOCIAL_TOKENS):
        return SourceType.VIDEO_SOCIAL

    if _contains_any(channel, _MARKET_SIGNAL_TOKENS) or _contains_any(
        title_body, _MARKET_SIGNAL_TOKENS
    ):
        return SourceType.MARKET_SIGNAL

    if _contains_any(combined, _NEWS_TOKENS):
        return SourceType.PRIMARY_NEWS

    if re.search(r"https?://", combined):
        return SourceType.PRIMARY_NEWS

    return SourceType.UNKNOWN


def classify_fragment(fragment: ArticleFragment) -> ArticleFragment:
    """Return fragment with classified source type."""
    classified = classify_source_type(
        channel_id=fragment.channel_id,
        title=fragment.title,
        body=fragment.body,
        url=fragment.url,
    )
    return fragment.model_copy(update={"source_type": classified})
