from __future__ import annotations

import re
from collections import Counter

from src.pipelines.stock_report.models import ClassifiedMessage, NormalizedMessage
from src.pipelines.stock_report.taxonomy import TaxonomyRegistry, build_match_dictionary


MESSAGE_TYPES = {"signal", "opinion", "data", "admin"}
ADMIN_KEYWORDS = ("공지", "안내", "광고", "구독", "오픈채팅", "문의", "이벤트", "공지사항")
OPINION_KEYWORDS = ("의견", "관점", "추정", "전망", "코멘트", "생각")
DATA_HINT_PATTERN = re.compile(r"[%$€¥]|[0-9]+(?:\.[0-9]+)?|시가총액|매출|영업이익|EPS")
TICKER_PATTERN = re.compile(r"\b(?:[A-Z]{1,5}(?:\.[A-Z]{1,2})?|[0-9]{6}\.(?:KS|KQ))\b")
MARKDOWN_SYMBOL_PATTERN = re.compile(r"[*_`#>~]")
MULTISPACE_PATTERN = re.compile(r"\s+")
ADMIN_LINK_PATTERN = re.compile(
    r"(https?://t\.me/|t\.me/|오픈채팅|문의[:：]|입장[:：])", re.IGNORECASE
)
STRONG_SIGNAL_HINT_KEYWORDS = (
    "가이던스",
    "실적공시",
    "실적발표",
    "속보",
    "공시",
    "인수",
    "합병",
    "컨센서스",
    "수주",
    "정책 발표",
)
RESEARCH_OPINION_HINT_KEYWORDS = (
    "리서치 요약",
    "목표주가",
    "투자의견",
    "상향",
    "하향",
    "리포트",
)
NON_TICKER_UPPER_TOKENS = {
    "HBM",
    "DRAM",
    "NAND",
    "EPS",
    "FOMC",
    "DXY",
    "WTI",
    "USD",
    "KRW",
    "AI",
    "GPU",
    "NPU",
}


def _extract_ticker_tags(clean_text: str) -> list[str]:
    matches = TICKER_PATTERN.findall(clean_text)
    if not matches:
        return []
    unique_tags: list[str] = []
    seen: set[str] = set()
    for ticker in matches:
        if ticker in NON_TICKER_UPPER_TOKENS:
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        unique_tags.append(ticker)
    return unique_tags


def _has_market_signal(clean_text: str) -> bool:
    if any(keyword in clean_text for keyword in STRONG_SIGNAL_HINT_KEYWORDS):
        return True
    if any(keyword in clean_text for keyword in RESEARCH_OPINION_HINT_KEYWORDS):
        return True
    if len(DATA_HINT_PATTERN.findall(clean_text)) >= 3:
        return True
    return bool(_extract_ticker_tags(clean_text))


def _is_admin_message(clean_text: str) -> bool:
    # 운영 목적 메시지로 보이는 경우에만 admin으로 분류한다.
    if _has_market_signal(clean_text):
        return False

    keyword_hits = sum(1 for keyword in ADMIN_KEYWORDS if keyword in clean_text)
    has_admin_link = bool(ADMIN_LINK_PATTERN.search(clean_text))
    return keyword_hits >= 2 or (keyword_hits >= 1 and has_admin_link)


def _classify_message_type(clean_text: str) -> str:
    lowered = clean_text.lower()
    data_hint_count = len(DATA_HINT_PATTERN.findall(clean_text))
    has_strong_signal_hint = any(keyword in clean_text for keyword in STRONG_SIGNAL_HINT_KEYWORDS)
    has_research_opinion_hint = any(
        keyword in clean_text for keyword in RESEARCH_OPINION_HINT_KEYWORDS
    )

    # 숫자/표/가격 신호는 admin보다 data 우선
    if data_hint_count >= 8 and not has_research_opinion_hint:
        return "data"
    if _is_admin_message(clean_text):
        return "admin"
    if has_strong_signal_hint:
        return "signal"
    # 증권사 리서치/목표주가/투자의견 계열은 기본 opinion으로 둔다.
    if has_research_opinion_hint and data_hint_count < 6:
        return "opinion"
    if data_hint_count >= 4 and any(
        token in clean_text for token in ("%", "매출", "영업이익", "EPS")
    ):
        return "data"
    if any(keyword in clean_text for keyword in OPINION_KEYWORDS):
        return "opinion"
    if lowered.startswith("rt ") or lowered.startswith("re:"):
        return "opinion"
    return "signal"


def _build_canonical_summary(clean_text: str) -> str:
    if not clean_text:
        return "-"

    line = clean_text.split("\n")[0]
    line = MARKDOWN_SYMBOL_PATTERN.sub(" ", line)
    line = MULTISPACE_PATTERN.sub(" ", line).strip()

    if len(line) <= 30:
        return line
    return line[:30].rstrip()


def _classify_taxonomy(
    clean_text: str,
    category_map: dict[str, str],
    theme_map: dict[str, tuple[str, str]],
) -> tuple[str, str | None, list[str]]:
    lowered = clean_text.lower()
    category_votes: Counter[str] = Counter()
    matched_themes: list[tuple[str, str]] = []

    for alias, category_key in category_map.items():
        if alias in lowered:
            category_votes[category_key] += 1

    for alias, info in theme_map.items():
        if alias in lowered:
            matched_themes.append(info)
            category_votes[info[0]] += 2

    if not category_votes:
        return "unclassified", None, []

    category_key = category_votes.most_common(1)[0][0]
    category_themes = [theme for cat, theme in matched_themes if cat == category_key]
    unique_themes: list[str] = []
    seen: set[str] = set()
    for theme in category_themes:
        if theme in seen:
            continue
        seen.add(theme)
        unique_themes.append(theme)

    main_theme = unique_themes[0] if unique_themes else None
    sub_themes = unique_themes[1:3]
    return category_key, main_theme, sub_themes


def classify_messages(
    normalized_messages: list[NormalizedMessage],
    *,
    taxonomy: TaxonomyRegistry,
) -> list[ClassifiedMessage]:
    category_map, theme_map = build_match_dictionary(taxonomy)
    classified: list[ClassifiedMessage] = []

    for row in normalized_messages:
        message_type = _classify_message_type(row.clean_text)
        category_key, main_theme, sub_themes = _classify_taxonomy(
            row.clean_text, category_map, theme_map
        )
        ticker_tags = _extract_ticker_tags(row.clean_text)
        canonical_summary = _build_canonical_summary(row.clean_text)

        if message_type not in MESSAGE_TYPES:
            message_type = "signal"

        classified.append(
            ClassifiedMessage(
                telegram_message_id=row.telegram_message_id,
                source_date=row.source_date,
                channel_key=row.channel_key,
                source_channel_key=row.source_channel_key,
                processing_mode=row.processing_mode,
                message_type=message_type,
                category_key=category_key,
                main_theme=main_theme,
                sub_themes=sub_themes,
                ticker_tags=ticker_tags,
                canonical_summary=canonical_summary,
            )
        )

    return classified
