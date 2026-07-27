from __future__ import annotations

import asyncio
import logging
import time
from functools import lru_cache

from src.llm.stage_config import StageLLMConfig
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.stock_report.config import (
    SEMANTIC_EXTRACTION_MAX_CONCURRENCY,
    SEMANTIC_EXTRACTION_MAX_RETRIES,
    SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    get_semantic_extraction_llm_config,
)
from src.pipelines.stock_report.models import (
    ClassifiedMessage,
    EvidenceItem,
    NormalizedMessage,
    QAWarning,
    SemanticExtractionDraft,
    SemanticExtractionLLMOutput,
    SemanticUnitDraft,
)
from src.pipelines.stock_report.prompts import (
    SEMANTIC_EXTRACTION_SYSTEM_PROMPT,
    build_semantic_extraction_user_prompt,
)
from src.pipelines.stock_report.taxonomy import (
    CategoryNode,
    TaxonomyRegistry,
    build_match_dictionary,
    render_taxonomy_outline,
)


logger = logging.getLogger(__name__)
MULTISPACE_PATTERN = __import__("re").compile(r"\s+")
NUMERIC_PATTERN = __import__("re").compile(r"[0-9]|%|[+-][0-9]")
NUMERIC_TOKEN_PATTERN = __import__("re").compile(
    r"\$?[+-]?\d[\d,]*(?:\.\d+)?(?:\s?(?:퍼센트|%|%p|bp|bps|x|배|억달러|조달러|억|조|만|천|원|달러|톤|대|주|명|개월|개|MW|GW|년|B))?",
    __import__("re").IGNORECASE,
)
INDEX_LABEL_PATTERN = __import__("re").compile(
    r"\b(?:S&P|NASDAQ)\s?\d+\b", __import__("re").IGNORECASE
)
DATE_TOKEN_PATTERN = __import__("re").compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b|"
    r"\b\d{2,4}년\s?\d{1,2}월\s?\d{1,2}일\b|"
    r"\b\d{1,2}월\s?\d{1,2}일\b|"
    r"\b\d{1,2}:\d{2}\b"
)
STOCK_CODE_PATTERN = __import__("re").compile(
    r"\([0-9]{4,6}(?:\.[A-Z]{2})?\)|\b[0-9]{6}(?:\.[A-Z]{2})?\b"
)
FULL_URL_PATTERN = __import__("re").compile(r"https?://\S+|www\.\S+", __import__("re").IGNORECASE)
PHONE_PATTERN = __import__("re").compile(
    r"(?:☎|tel|전화|문의|[0-9]{2,3}-[0-9]{3,4}-[0-9]{4})",
    __import__("re").IGNORECASE,
)
URL_PATTERN = __import__("re").compile(r"https?://|www\\.", __import__("re").IGNORECASE)
ASCII_WORD_PATTERN = __import__("re").compile(r"^[a-z0-9 _./+-]+$")
YEAR_TOKEN_PATTERN = __import__("re").compile(r"^['’]?\d{2}년$|^\d{4}년$")
PERCENT_TOKEN_PATTERN = __import__("re").compile(r"^[+-]?\d+(?:\.\d+)?%$")
BASIS_POINT_TOKEN_PATTERN = __import__("re").compile(r"^[+-]?\d+(?:\.\d+)?(?:%p|bp|bps)$")
SIGNED_PERCENT_TOKEN_PATTERN = __import__("re").compile(r"^[+-]\d+(?:\.\d+)?%$")
SIGNED_BASIS_POINT_TOKEN_PATTERN = __import__("re").compile(r"^[+-]\d+(?:\.\d+)?(?:%p|bp|bps)$")
DOLLAR_TOKEN_PATTERN = __import__("re").compile(r"^\$([+-]?\d+(?:\.\d+)?)$")
DOLLAR_B_TOKEN_PATTERN = __import__("re").compile(r"^\$([+-]?\d+(?:\.\d+)?)b$")
CURRENCY_TOKEN_PATTERN = __import__("re").compile(
    r"^[+-]?\d+(?:\.\d+)?(?:억달러|조달러|억|조|만|천|원|달러|톤|대|주|명|개|mw|gw|배|x)$"
)
BULLET_LINE_PATTERN = __import__("re").compile(r"^(?:[-*•●▶]|(?:\d+[\).]))\s*")
TOKEN_PATTERN = __import__("re").compile(r"[a-zA-Z가-힣][a-zA-Z가-힣0-9&/+.-]*")
NUMERIC_UNIT_SUFFIXES = (
    "퍼센트",
    "%",
    "%p",
    "bp",
    "bps",
    "x",
    "배",
    "억달러",
    "조달러",
    "억",
    "조",
    "만",
    "천",
    "원",
    "달러",
    "톤",
    "대",
    "주",
    "명",
    "개",
    "mw",
    "gw",
    "b",
)
SIGNAL_HINT_KEYWORDS = (
    "상장",
    "협약",
    "체결",
    "인증",
    "승인",
    "수주",
    "인수",
    "합병",
    "출시",
    "공시",
    "가이던스",
    "투자",
    "파트너십",
    "개발 성공",
    "정책 발표",
)
DATA_HINT_KEYWORDS = (
    "yoy",
    "qoq",
    "전년비",
    "증가",
    "감소",
    "비중",
    "판매",
    "등록",
    "점유율",
    "매출",
    "영업이익",
    "eps",
    "통계",
    "지수",
)
OPINION_HINT_KEYWORDS = ("전망", "추정", "코멘트", "의견", "우려", "판단", "가능성")
ADMIN_HINT_KEYWORDS = ("공지", "안내", "구독", "입장", "문의", "채널")
REPORT_DISCLOSURE_KEYWORDS = (
    "조사분석자료",
    "공표 승인",
    "배포되는 자료",
    "재배포",
    "원문 확인",
)
DIGEST_SOURCE_KEYWORDS = (
    "daily",
    "digest",
    "review",
    "market wrap",
    "us daily",
    "특징주",
    "예습",
    "마켓레이더",
    "시황",
    "데일리",
)
TOPIC_STOPWORDS = {
    "daily",
    "digest",
    "review",
    "market",
    "wrap",
    "headline",
    "요약",
    "시장",
    "시황",
}
OVER_MERGED_LIST_LIKE_KEYWORDS = (
    "집계",
    "일괄",
    "리스트",
    "일정",
    "캘린더",
    "공모청약",
    "변경상장",
    "추가상장",
    "보호예수",
    "주가",
    "등락률",
    "밸류체인",
    "종목",
)
SUPPORTING_FACT_LIMIT = 20
LONG_EVIDENCE_CHAR_LIMIT = 160
EVENT_TYPE_ALIAS_MAP = {
    "자본조달": "자본조달",
    "전환사채": "자본조달",
    "cb": "자본조달",
    "convertible bond": "자본조달",
    "capped call": "자본조달",
    "수주/계약": "수주/계약",
    "계약": "수주/계약",
    "수주": "수주/계약",
    "파트너십": "수주/계약",
    "partnership": "수주/계약",
    "실적": "실적",
    "earnings": "실적",
    "가이던스": "실적",
    "정책": "정책",
    "규제": "정책",
    "policy": "정책",
    "인증/승인": "인증/승인",
    "인증": "인증/승인",
    "승인": "인증/승인",
    "approval": "인증/승인",
    "certification": "인증/승인",
    "m&a": "M&A",
    "인수합병": "M&A",
    "인수": "M&A",
    "합병": "M&A",
    "출시/제품": "출시/제품",
    "출시": "출시/제품",
    "제품": "출시/제품",
    "price/margin": "가격/마진",
    "가격/마진": "가격/마진",
    "가격": "가격/마진",
    "마진": "가격/마진",
    "통계/지표": "통계/지표",
    "통계": "통계/지표",
    "지표": "통계/지표",
    "해석/전망": "해석/전망",
    "전망": "해석/전망",
    "코멘트": "해석/전망",
    "공지": "공지",
}


def _dedupe_preserve_order(values: list[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
        if limit is not None and len(result) >= limit:
            break
    return result


def _normalize_category_key(value: str | None, category_map: dict[str, str]) -> str:
    if not value:
        return "unclassified"
    return category_map.get(value.strip().lower(), "unclassified")


def _normalize_theme(
    value: str | None,
    theme_map: dict[str, tuple[str, str]],
) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    match = theme_map.get(value.strip().lower())
    if not match:
        return None, None
    return match


def _normalize_event_type(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return EVENT_TYPE_ALIAS_MAP.get(stripped.lower(), stripped)


def _extract_numeric_tokens(text: str) -> list[str]:
    """원문 텍스트에서 숫자 후보 토큰을 추출한다.

    필요한 이유:
    - LLM 추출 결과를 QA할 때, 원문 기준의 결정적 숫자 기준선이 필요하다.
    - 원문에는 날짜/URL/전화번호/종목코드처럼 숫자 모양 노이즈가 많아서
      이를 먼저 제거하지 않으면 경고가 과다 발생한다.

    목적:
    - metric 검증 가치가 있는 숫자 후보를 중복 없이 수집한다.
    - 여기서는 후보를 넓게 잡고, 실제 유의미성 판단은 후속 필터에 위임한다.
    """
    if not text:
        return []

    scrubbed = INDEX_LABEL_PATTERN.sub(" ", text)
    scrubbed = DATE_TOKEN_PATTERN.sub(" ", scrubbed)
    scrubbed = FULL_URL_PATTERN.sub(" ", scrubbed)
    scrubbed = URL_PATTERN.sub(" ", scrubbed)
    scrubbed = PHONE_PATTERN.sub(" ", scrubbed)
    scrubbed = STOCK_CODE_PATTERN.sub(" ", scrubbed)
    tokens: list[str] = []
    seen: set[str] = set()
    for match in NUMERIC_TOKEN_PATTERN.findall(scrubbed):
        token = match.strip()
        if not token:
            continue
        digits = "".join(ch for ch in token if ch.isdigit())
        lowered = token.lower()
        if (
            len(digits) < 2
            and "%" not in token
            and "퍼센트" not in token
            and not lowered.startswith("$")
            and not lowered.endswith("b")
            and not _has_numeric_unit_suffix(lowered)
        ):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        tokens.append(token)
    return tokens


def _has_numeric_unit_suffix(token: str) -> bool:
    return any(token.endswith(suffix) for suffix in NUMERIC_UNIT_SUFFIXES)


def _normalize_numeric_token(token: str) -> str:
    normalized = (
        token.lower().replace(",", "").replace("퍼센트", "%").replace("’", "'").replace(" ", "")
    )
    dollar_match = DOLLAR_TOKEN_PATTERN.fullmatch(normalized)
    if dollar_match:
        return f"{dollar_match.group(1)}달러"
    if PERCENT_TOKEN_PATTERN.fullmatch(normalized):
        return normalized
    if BASIS_POINT_TOKEN_PATTERN.fullmatch(normalized):
        suffix = "bp"
        if normalized.endswith("%p"):
            suffix = "%p"
        elif normalized.endswith("bps"):
            suffix = "bps"
        magnitude = normalized[: -len(suffix)]
        return f"{magnitude}{suffix}"
    year_match = YEAR_TOKEN_PATTERN.fullmatch(normalized)
    if year_match:
        bare = normalized.replace("'", "").replace("년", "")
        if len(bare) == 2:
            return f"20{bare}년"
        return f"{bare}년"
    dollar_b_match = DOLLAR_B_TOKEN_PATTERN.fullmatch(normalized)
    if dollar_b_match:
        value = dollar_b_match.group(1)
        try:
            return f"{float(value) * 10:g}억달러"
        except ValueError:
            return normalized
    return normalized


def _is_meaningful_numeric_token(token: str) -> bool:
    if not token:
        return False
    if YEAR_TOKEN_PATTERN.fullmatch(token):
        return False
    if token.isdigit():
        return False
    if CURRENCY_TOKEN_PATTERN.fullmatch(token):
        return True
    if "%" in token or "bp" in token or "%p" in token:
        return True
    return bool(DOLLAR_TOKEN_PATTERN.fullmatch(token) or DOLLAR_B_TOKEN_PATTERN.fullmatch(token))


def _source_numeric_set(source_text: str) -> set[str]:
    normalized_tokens: set[str] = set()
    for token in _extract_numeric_tokens(source_text):
        normalized = _normalize_numeric_token(token)
        if not _is_meaningful_numeric_token(normalized):
            continue
        normalized_tokens.add(normalized)
        if SIGNED_PERCENT_TOKEN_PATTERN.fullmatch(normalized) and _has_directional_word(
            source_text,
            token,
        ):
            normalized_tokens.add(normalized.lstrip("+-"))
        if SIGNED_BASIS_POINT_TOKEN_PATTERN.fullmatch(normalized) and _has_directional_word(
            source_text,
            token,
        ):
            normalized_tokens.add(normalized.lstrip("+-"))
    return normalized_tokens


def _is_temporal_numeric_candidate(source_text: str, token: str, normalized_token: str) -> bool:
    """투자 metric으로 보면 안 되는 일정/시간성 숫자를 탐지한다.

    필요한 이유:
    - "30일", "12차", "3주 후" 같은 값은 대개 운영 일정이다.
    - 이를 metric으로 취급하면 `missing_metric_candidate`와 fact->metric 승격이
      불필요하게 많이 발생한다.

    목적:
    - 숫자 토큰 주변 문맥에서 시간/일정 표현을 감지해 metric 후보에서 제외한다.
    """
    if normalized_token.endswith("개"):
        position = source_text.find(token)
        if position < 0:
            position = source_text.find(token.replace("+", "").replace("-", ""))
        if position >= 0:
            trailing = source_text[position + len(token) : position + len(token) + 1]
            if trailing in {"년", "월", "일", "시", "분", "초", "차", "회", "기"}:
                return True

    if normalized_token.endswith("주"):
        position = source_text.find(token)
        if position < 0:
            position = source_text.find(token.replace("+", "").replace("-", ""))
        if position >= 0:
            trailing = source_text[position + len(token) : position + len(token) + 6].lstrip()
            if trailing.startswith(("후", "뒤", "내", "간", "동안", "째")):
                return True

    return False


def _metric_candidate_set(source_text: str) -> set[str]:
    """metric처럼 취급할 숫자 토큰의 정규화 집합을 만든다.

    필요한 이유:
    - 다음 두 로직이 같은 숫자 기준을 써야 QA 일관성이 유지된다.
      1) evidence `fact -> metric` 승격
      2) `missing_metric_candidate` 경고 판단

    목적:
    - 정규화 + 시간성 노이즈 제거를 거친 유의미 숫자 집합을 반환한다.
    """
    normalized_tokens: set[str] = set()
    for token in _extract_numeric_tokens(source_text):
        normalized = _normalize_numeric_token(token)
        if not _is_meaningful_numeric_token(normalized):
            continue
        if _is_temporal_numeric_candidate(source_text, token, normalized):
            continue
        normalized_tokens.add(normalized)
        if SIGNED_PERCENT_TOKEN_PATTERN.fullmatch(normalized) and _has_directional_word(
            source_text,
            token,
        ):
            normalized_tokens.add(normalized.lstrip("+-"))
        if SIGNED_BASIS_POINT_TOKEN_PATTERN.fullmatch(normalized) and _has_directional_word(
            source_text,
            token,
        ):
            normalized_tokens.add(normalized.lstrip("+-"))
    return normalized_tokens


def _has_directional_word(text: str, token: str) -> bool:
    if not token:
        return False
    position = text.find(token)
    if position < 0:
        position = text.find(token.replace("+", "").replace("-", ""))
    if position < 0:
        return False
    window = text[max(0, position - 20) : position + len(token) + 20]
    if token.startswith("-"):
        return any(
            word in window for word in ("하락", "하향", "감소", "축소", "악화", "내림", "조정")
        )
    if token.startswith("+"):
        return any(word in window for word in ("상승", "상향", "증가", "확대", "개선", "오름"))
    return False


def _append_warning(
    warnings: list[QAWarning],
    code: str,
    detail: str | None = None,
    evidence_index: int | None = None,
) -> None:
    warning = QAWarning(code=code, detail=detail, evidence_index=evidence_index)
    if warning not in warnings:
        warnings.append(warning)


def _normalize_evidence_items(
    raw_unit: SemanticUnitDraft,
) -> tuple[list[EvidenceItem], list[QAWarning]]:
    warnings: list[QAWarning] = []

    source_items = raw_unit.evidence_items
    if source_items:
        items = list(source_items)
        legacy_facts = _dedupe_preserve_order(
            raw_unit.supporting_facts, limit=SUPPORTING_FACT_LIMIT
        )
        typed_texts = _dedupe_preserve_order(
            [item.text for item in items], limit=SUPPORTING_FACT_LIMIT
        )
        if legacy_facts and legacy_facts != typed_texts:
            _append_warning(
                warnings,
                "legacy_facts_diverged",
                "Typed evidence won over materially different legacy supporting_facts.",
            )
    else:
        items = [
            EvidenceItem(kind="fact", text=fact)
            for fact in _dedupe_preserve_order(
                raw_unit.supporting_facts, limit=SUPPORTING_FACT_LIMIT
            )
        ]

    normalized: list[EvidenceItem] = []
    seen_texts: set[str] = set()
    for item in items:
        if item.raw_kind:
            _append_warning(
                warnings,
                "unknown_evidence_kind",
                f"Unknown evidence kind normalized to fact: {item.raw_kind}",
            )
        text = item.text.strip()
        if not text:
            _append_warning(warnings, "empty_evidence")
            continue
        if text in seen_texts:
            continue
        seen_texts.add(text)
        kind = item.kind
        if kind == "fact":
            evidence_numbers = _metric_candidate_set(text)
            if evidence_numbers:
                kind = "metric"
        normalized.append(EvidenceItem(kind=kind, text=text))
        if len(normalized) >= SUPPORTING_FACT_LIMIT:
            break

    if not normalized:
        _append_warning(warnings, "empty_evidence")
    return normalized, warnings


def _compute_evidence_quality_warnings(
    *,
    row: NormalizedMessage,
    structure_type: str,
    raw_message_type: str,
    normalized_message_type: str,
    canonical_summary: str,
    ticker_tags: list[str],
    evidence_items: list[EvidenceItem],
) -> list[QAWarning]:
    """evidence 품질 관련 결정적 QA 경고를 계산한다.

    필요한 이유:
    - LLM 추출 품질은 메시지 타입마다 흔들릴 수 있으므로
      실행 간 일관된 DB 모니터링용 가드레일이 필요하다.

    목적:
    - 숫자 근거 지원 여부, evidence 길이, admin/content 충돌을 검증한다.
    - 구조 타입별 숫자 범위를 달리 적용해 오탐을 줄인다.
    """
    warnings: list[QAWarning] = []
    source_numbers = _source_numeric_set(f"{row.raw_text}\n{row.clean_text}")
    local_numbers = _metric_candidate_set(
        "\n".join([canonical_summary, *[item.text for item in evidence_items], *ticker_tags])
    )
    # single_topic_deep는 보통 단일 논지를 다루므로 원문 전체 숫자 범위를 사용한다.
    # digest/wrap는 무관한 숫자가 섞이기 쉬워 unit 로컬 텍스트로 범위를 제한한다.
    candidate_numbers = source_numbers if structure_type == "single_topic_deep" else local_numbers
    has_metric = any(item.kind == "metric" for item in evidence_items)

    if candidate_numbers and not has_metric:
        _append_warning(
            warnings,
            "missing_metric_candidate",
            "Metric numeric candidates exist but the unit has no metric evidence.",
        )

    for index, item in enumerate(evidence_items):
        if len(item.text) > LONG_EVIDENCE_CHAR_LIMIT:
            _append_warning(
                warnings,
                "long_evidence",
                f"Evidence item exceeds {LONG_EVIDENCE_CHAR_LIMIT} characters.",
                evidence_index=index,
            )
        for token in _extract_numeric_tokens(item.text):
            normalized_token = _normalize_numeric_token(token)
            if not _is_meaningful_numeric_token(normalized_token):
                continue
            if normalized_token not in source_numbers:
                _append_warning(
                    warnings,
                    "unsupported_numeric",
                    f"Evidence contains numeric token not found in source: {token}",
                    evidence_index=index,
                )

    if raw_message_type == "admin" and normalized_message_type != "admin":
        _append_warning(
            warnings,
            "admin_contradiction",
            "Raw message_type=admin but unit contains investment content.",
        )

    return warnings


def _count_source_blocks(text: str) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0
    bullet_count = sum(1 for line in lines if BULLET_LINE_PATTERN.match(line))
    section_count = sum(
        1 for line in lines if ":" in line and 1 <= len(line.split(":", 1)[0].strip()) <= 24
    )
    if bullet_count:
        return bullet_count
    if section_count:
        return section_count
    if len(lines) >= 5:
        return len(lines) - 1
    return 1


def _looks_digest_like_message(
    *,
    source_text: str,
    structure_type: str,
    source_block_count: int,
) -> bool:
    """원문이 digest/wrap 형태인지 추정하는 휴리스틱이다.

    필요한 이유:
    - under-split 경고는 원문 포맷이 실제로 digest에 가까울 때만 의미가 있다.
    - LLM의 structure_type만 보면 원문 포맷 신호를 놓칠 수 있다.
    """
    lowered = source_text.lower()
    has_keyword = any(keyword in lowered for keyword in DIGEST_SOURCE_KEYWORDS)
    if has_keyword and source_block_count >= 3:
        return True
    return structure_type in {"multi_item_digest", "market_wrap"} and source_block_count >= 5


def _unit_topic_signature(text: str) -> str | None:
    for token in TOKEN_PATTERN.findall(text.lower()):
        if len(token) < 2 or token.isdigit() or token in TOPIC_STOPWORDS:
            continue
        return token
    return None


def _unit_token_set(unit: ClassifiedMessage) -> set[str]:
    merged = " ".join([unit.canonical_summary, *unit.supporting_facts, *unit.ticker_tags])
    tokens = {
        token
        for token in TOKEN_PATTERN.findall(merged.lower())
        if len(token) >= 2 and not token.isdigit() and token not in TOPIC_STOPWORDS
    }
    return tokens


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _list_like_signals(text: str) -> list[str]:
    lowered = text.lower()
    return [keyword for keyword in OVER_MERGED_LIST_LIKE_KEYWORDS if keyword.lower() in lowered]


def _format_over_merged_detail(
    *,
    source_text: str,
    structure_type: str,
    source_block_count: int,
    digest_like: bool,
    unit: ClassifiedMessage,
    ticker_count: int,
    evidence_count: int,
    topic_count: int,
) -> str:
    """`over_merged_unit_candidate`를 위한 사람이 읽기 쉬운 진단 문자열을 만든다.

    필요한 이유:
    - over-merged는 자동 분할이 아니라 경고로 유지하는 전략이다.
    - 운영자가 원문 재탐색 없이도 split_needed / broad_list / extraction_noise를
      빠르게 라벨링할 수 있어야 한다.
    """
    unit_text = "\n".join(
        [
            source_text,
            unit.canonical_summary,
            *[item.text for item in unit.evidence_items],
            *unit.ticker_tags,
        ]
    )
    list_signals = _list_like_signals(unit_text)
    sample_tickers = [ticker.strip() for ticker in unit.ticker_tags if ticker.strip()][:5]
    return (
        "Single unit appears broad: "
        f"structure={structure_type}, "
        f"source_blocks={source_block_count}, "
        f"digest_like={_bool_text(digest_like)}, "
        f"list_like={_bool_text(bool(list_signals))}, "
        f"tickers={ticker_count}, "
        f"evidence={evidence_count}, "
        f"topics={topic_count}, "
        f"sample_tickers={','.join(sample_tickers) if sample_tickers else '-'}, "
        f"list_signals={','.join(list_signals) if list_signals else '-'}."
    )


def _jaccard_similarity(first: set[str], second: set[str]) -> float:
    if not first or not second:
        return 0.0
    intersection = len(first & second)
    union = len(first | second)
    if union == 0:
        return 0.0
    return intersection / union


def _apply_digest_split_qa_warnings(
    *,
    row: NormalizedMessage,
    structure_type: str,
    units: list[ClassifiedMessage],
) -> None:
    """unit 정규화 이후 구조적 QA 경고를 부착한다.

    필요한 이유:
    - LLM은 under-split(여러 블록을 1 unit으로 축약) 또는
      over-merge(여러 주제/티커를 1 unit에 과도 결합) 오류를 낼 수 있다.
    - 이 단계에서는 unit을 변경하지 않고 경고만 남겨 운영 루프가 판단하게 한다.

    목적:
    - 결정적 휴리스틱으로 `under_split_candidate`,
      `over_merged_unit_candidate`, `duplicate_unit_candidate`를 발생시킨다.
    """
    if not units:
        return

    source_text = (row.clean_text or row.raw_text).strip()
    source_block_count = _count_source_blocks(source_text)
    digest_like = _looks_digest_like_message(
        source_text=source_text,
        structure_type=structure_type,
        source_block_count=source_block_count,
    )
    if len(units) == 1 and source_block_count >= 4 and digest_like:
        _append_warning(
            units[0].qa_warnings,
            "under_split_candidate",
            f"Digest/wrap-like source has {source_block_count} blocks but only 1 unit.",
        )

    for unit in units:
        ticker_count = len({ticker.lower() for ticker in unit.ticker_tags if ticker.strip()})
        evidence_count = len(unit.evidence_items)
        topic_signatures = {
            signature
            for signature in [_unit_topic_signature(unit.canonical_summary)]
            if signature is not None
        }
        topic_signatures.update(
            signature
            for signature in (_unit_topic_signature(item.text) for item in unit.evidence_items)
            if signature is not None
        )
        topic_count = len(topic_signatures)

        if (ticker_count >= 5 and evidence_count >= 5 and topic_count >= 4) or (
            ticker_count >= 4 and evidence_count >= 7 and topic_count >= 5
        ):
            _append_warning(
                unit.qa_warnings,
                "over_merged_unit_candidate",
                _format_over_merged_detail(
                    source_text=source_text,
                    structure_type=structure_type,
                    source_block_count=source_block_count,
                    digest_like=digest_like,
                    unit=unit,
                    ticker_count=ticker_count,
                    evidence_count=evidence_count,
                    topic_count=topic_count,
                ),
            )

    for left_index, left in enumerate(units):
        left_tickers = {ticker.lower() for ticker in left.ticker_tags if ticker.strip()}
        left_tokens = _unit_token_set(left)
        if not left_tickers or len(left_tokens) < 6:
            continue
        for right_index in range(left_index + 1, len(units)):
            right = units[right_index]
            right_tickers = {ticker.lower() for ticker in right.ticker_tags if ticker.strip()}
            right_tokens = _unit_token_set(right)
            if not right_tickers or len(right_tokens) < 6:
                continue
            overlap_tickers = left_tickers & right_tickers
            if not overlap_tickers:
                continue
            ticker_overlap_ratio = len(overlap_tickers) / min(len(left_tickers), len(right_tickers))
            text_overlap_ratio = _jaccard_similarity(left_tokens, right_tokens)
            if ticker_overlap_ratio >= 0.6 and text_overlap_ratio >= 0.55:
                detail = (
                    f"High overlap with unit {right_index}: ticker_overlap={ticker_overlap_ratio:.2f}, "
                    f"text_overlap={text_overlap_ratio:.2f}"
                )
                _append_warning(left.qa_warnings, "duplicate_unit_candidate", detail)
                _append_warning(
                    right.qa_warnings,
                    "duplicate_unit_candidate",
                    detail.replace(f"unit {right_index}", f"unit {left_index}"),
                )


def _fallback_canonical_summary(clean_text: str) -> str:
    if not clean_text:
        return ""
    line = clean_text.split("\n", 1)[0]
    line = MULTISPACE_PATTERN.sub(" ", line).strip()
    return line[:80].rstrip()


def _build_fallback_message(row: NormalizedMessage) -> ClassifiedMessage | None:
    canonical_summary = _fallback_canonical_summary(row.clean_text)
    if not canonical_summary:
        return None

    return ClassifiedMessage(
        telegram_message_id=row.telegram_message_id,
        source_date=row.source_date,
        channel_key=row.channel_key,
        source_channel_key=row.source_channel_key,
        processing_mode=row.processing_mode,
        structure_type="single_topic_deep",
        unit_index=0,
        message_type="signal",
        event_type=None,
        category_key="unclassified",
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        canonical_summary=canonical_summary,
        supporting_facts=[],
        evidence_items=[],
        qa_warnings=[QAWarning(code="llm_extraction_failed", detail="Semantic extraction failed.")],
    )


def _build_overlay_text(*parts: str) -> str:
    joined = " ".join(part.strip() for part in parts if part and part.strip())
    return MULTISPACE_PATTERN.sub(" ", joined).lower()


def _is_valid_overlay_alias(alias: str) -> bool:
    stripped = alias.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if ASCII_WORD_PATTERN.fullmatch(lowered):
        return len(lowered.replace(" ", "")) >= 3
    return len(stripped) >= 2


def _score_overlay_alias(
    *,
    alias: str,
    summary_text: str,
    facts_text: str,
    clean_text: str,
    raw_text: str,
) -> int:
    if not _is_valid_overlay_alias(alias):
        return 0
    needle = alias.lower()
    score = 0
    if needle in summary_text:
        score += 3
    if needle in facts_text:
        score += 2
    if needle in raw_text:
        score += 2
    if needle in clean_text:
        score += 1
    return score


def _match_category_overlay(
    *,
    taxonomy: TaxonomyRegistry,
    summary_text: str,
    facts_text: str,
    clean_text: str,
    raw_text: str,
) -> str | None:
    best_category: str | None = None
    best_score = 0
    for category in taxonomy.categories:
        aliases = [category.key, *category.aliases]
        score = sum(
            _score_overlay_alias(
                alias=alias,
                summary_text=summary_text,
                facts_text=facts_text,
                clean_text=clean_text,
                raw_text=raw_text,
            )
            for alias in aliases
        )
        if score > best_score:
            best_category = category.key
            best_score = score
    if best_score < 3:
        return None
    return best_category


def _match_theme_overlay(
    *,
    taxonomy: TaxonomyRegistry,
    summary_text: str,
    facts_text: str,
    clean_text: str,
    raw_text: str,
    category_key: str | None,
) -> tuple[str | None, str | None]:
    categories: list[CategoryNode]
    if category_key:
        categories = [node for node in taxonomy.categories if node.key == category_key]
    else:
        categories = list(taxonomy.categories)

    best_theme: str | None = None
    best_category: str | None = category_key
    best_score = 0
    for category in categories:
        for theme in category.themes:
            aliases = [theme.key, *theme.aliases]
            score = sum(
                _score_overlay_alias(
                    alias=alias,
                    summary_text=summary_text,
                    facts_text=facts_text,
                    clean_text=clean_text,
                    raw_text=raw_text,
                )
                for alias in aliases
            )
            if score > best_score:
                best_theme = theme.key
                best_category = category.key
                best_score = score
    if best_score < 3:
        return category_key, None
    return best_category, best_theme


def _normalize_message_type(
    raw_message_type: str,
    *,
    canonical_summary: str,
    supporting_facts: list[str],
) -> str:
    merged_text = f"{canonical_summary} {' '.join(supporting_facts)}".strip()
    lowered = merged_text.lower()

    has_investment_content = any(
        keyword in merged_text or keyword in lowered
        for keyword in SIGNAL_HINT_KEYWORDS + DATA_HINT_KEYWORDS + OPINION_HINT_KEYWORDS
    )
    if any(keyword in merged_text for keyword in REPORT_DISCLOSURE_KEYWORDS):
        has_investment_content = True

    if (
        any(keyword in merged_text for keyword in ADMIN_HINT_KEYWORDS)
        and not has_investment_content
    ):
        return "admin"
    if raw_message_type == "admin":
        if has_investment_content:
            return "opinion"
        return "admin"

    if raw_message_type == "opinion":
        return "opinion"
    if any(keyword in merged_text for keyword in OPINION_HINT_KEYWORDS) and not any(
        keyword in merged_text for keyword in SIGNAL_HINT_KEYWORDS
    ):
        return "opinion"

    signal_score = sum(1 for keyword in SIGNAL_HINT_KEYWORDS if keyword in merged_text)
    data_score = sum(1 for keyword in DATA_HINT_KEYWORDS if keyword in lowered)
    has_numeric = bool(NUMERIC_PATTERN.search(merged_text))

    if raw_message_type == "data":
        if signal_score >= 2:
            return "signal"
        if signal_score >= 1 and data_score <= 2:
            return "signal"
        return "data"

    if raw_message_type == "signal":
        if signal_score == 0 and data_score >= 3 and has_numeric:
            return "data"
        return "signal"

    return "signal"


def _normalize_unit(
    *,
    row: NormalizedMessage,
    taxonomy: TaxonomyRegistry,
    structure_type: str,
    unit_index: int,
    raw_unit: SemanticUnitDraft,
    category_map: dict[str, str],
    theme_map: dict[str, tuple[str, str]],
) -> ClassifiedMessage | None:
    """LLM semantic unit 1개를 파이프라인 표준 레코드로 정규화한다.

    필요한 이유:
    - LLM 출력은 의미는 풍부하지만 저장/조회 관점의 엄격한 스키마와 다를 수 있다.
    - downstream 저장/리포팅은 정규화된 category/theme/message_type과
      결정적 QA 메타데이터를 기대한다.

    목적:
    - taxonomy 키 정규화, evidence/event/message_type 정규화,
      provisional overlay 매칭, QA 경고 계산을 한 지점에서 수행한다.
    """
    canonical_summary = raw_unit.canonical_summary.strip()
    if not canonical_summary:
        return None

    category_key = _normalize_category_key(raw_unit.category_key, category_map)

    theme_category, main_theme = _normalize_theme(raw_unit.main_theme, theme_map)
    if theme_category:
        category_key = theme_category

    sub_themes: list[str] = []
    pending_theme_categories: list[str] = []
    for theme in raw_unit.sub_themes:
        sub_category, normalized_theme = _normalize_theme(theme, theme_map)
        if not normalized_theme:
            continue
        pending_theme_categories.append(sub_category)
        if normalized_theme == main_theme:
            continue
        if category_key != "unclassified" and sub_category != category_key:
            continue
        sub_themes.append(normalized_theme)

    if main_theme is None and sub_themes:
        first_sub_theme = sub_themes.pop(0)
        main_theme = first_sub_theme
        if category_key == "unclassified" and pending_theme_categories:
            category_key = pending_theme_categories[0]

    sub_themes = _dedupe_preserve_order(sub_themes, limit=2)
    ticker_tags = _dedupe_preserve_order(raw_unit.ticker_tags, limit=5)
    evidence_items, qa_warnings = _normalize_evidence_items(raw_unit)
    supporting_facts = [item.text for item in evidence_items]
    event_type = _normalize_event_type(raw_unit.event_type)

    provisional_category: str | None = None
    provisional_theme: str | None = None
    if category_key == "unclassified" or main_theme is None:
        summary_text = _build_overlay_text(canonical_summary)
        facts_text = _build_overlay_text(" ".join(supporting_facts))
        clean_text = _build_overlay_text(row.clean_text)
        raw_text = _build_overlay_text(
            canonical_summary,
            raw_unit.category_key or "",
            raw_unit.main_theme or "",
            " ".join(raw_unit.sub_themes),
        )
        if category_key == "unclassified":
            provisional_category = _match_category_overlay(
                taxonomy=taxonomy,
                summary_text=summary_text,
                facts_text=facts_text,
                clean_text=clean_text,
                raw_text=raw_text,
            )
        overlay_category = category_key if category_key != "unclassified" else provisional_category
        overlay_theme_category, overlay_theme = _match_theme_overlay(
            taxonomy=taxonomy,
            summary_text=summary_text,
            facts_text=facts_text,
            clean_text=clean_text,
            raw_text=raw_text,
            category_key=overlay_category,
        )
        if main_theme is None:
            provisional_theme = overlay_theme
            if category_key == "unclassified" and provisional_category is None:
                provisional_category = overlay_theme_category

    message_type = _normalize_message_type(
        raw_unit.message_type,
        canonical_summary=canonical_summary,
        supporting_facts=supporting_facts,
    )
    qa_warnings.extend(
        _compute_evidence_quality_warnings(
            row=row,
            structure_type=structure_type,
            raw_message_type=raw_unit.message_type,
            normalized_message_type=message_type,
            canonical_summary=canonical_summary,
            ticker_tags=ticker_tags,
            evidence_items=evidence_items,
        )
    )

    return ClassifiedMessage(
        telegram_message_id=row.telegram_message_id,
        source_date=row.source_date,
        channel_key=row.channel_key,
        source_channel_key=row.source_channel_key,
        processing_mode=row.processing_mode,
        structure_type=structure_type,
        unit_index=unit_index,
        message_type=message_type,
        event_type=event_type,
        category_key=category_key,
        main_theme=main_theme,
        provisional_category=provisional_category,
        provisional_theme=provisional_theme,
        is_provisional=bool(provisional_category),
        sub_themes=sub_themes,
        ticker_tags=ticker_tags,
        canonical_summary=canonical_summary,
        supporting_facts=supporting_facts,
        raw_message_type=raw_unit.message_type,
        evidence_items=evidence_items,
        qa_warnings=qa_warnings,
    )


@lru_cache(maxsize=4)
def _get_llm_runtime(llm_config: StageLLMConfig):
    logger.info(
        "Semantic extraction runtime initialized: provider=%s model=%s temperature=%.2f",
        llm_config.provider,
        llm_config.model,
        llm_config.temperature,
    )
    return llm_config.create_llm()


async def _extract_message_semantics(
    *,
    row: NormalizedMessage,
    taxonomy: TaxonomyRegistry,
    llm_config: StageLLMConfig,
    system_prompt: str,
) -> SemanticExtractionDraft:
    llm = _get_llm_runtime(llm_config)
    taxonomy_outline = render_taxonomy_outline(taxonomy)
    user_prompt = build_semantic_extraction_user_prompt(
        row,
        taxonomy_outline=taxonomy_outline,
    )
    messages = llm_config.build_messages(
        system_prompt,
        user_prompt,
    )
    config = {
        "run_name": f"StockReport Semantic Extraction - {row.telegram_message_id}",
        "tags": [
            "stock_report",
            "semantic_extraction",
            f"provider:{llm_config.provider}",
            f"channel:{row.channel_key}",
        ],
        "metadata": {
            "stage": "semantic_extraction",
            "telegram_message_id": row.telegram_message_id,
            "provider": llm_config.provider,
            "model": llm_config.model,
            "channel_key": row.channel_key,
            "channel_message_id": row.channel_message_id,
            "source_date": str(row.source_date),
            "processing_mode": row.processing_mode,
            "content_chars": len(row.clean_text or ""),
        },
    }
    llm_output = await invoke_llm_with_retry(
        llm,
        SemanticExtractionLLMOutput,
        messages,
        config,
        max_retries=SEMANTIC_EXTRACTION_MAX_RETRIES,
        timeout_seconds=SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    )
    return SemanticExtractionDraft(
        structure_type=llm_output.structure_type,
        units=[
            SemanticUnitDraft(**unit.model_dump(exclude_none=False)) for unit in llm_output.units
        ],
    )


async def _classify_single_message(
    *,
    row: NormalizedMessage,
    taxonomy: TaxonomyRegistry,
    llm_config: StageLLMConfig,
    category_map: dict[str, str],
    theme_map: dict[str, tuple[str, str]],
    semaphore: asyncio.Semaphore,
    system_prompt: str,
) -> list[ClassifiedMessage]:
    """메시지 1건에 대해 semantic 추출 + 정규화를 수행하고 실패 시 안전 복구한다.

    필요한 이유:
    - 배치 분류는 개별 메시지 LLM 실패에 견고해야 한다.
    - 단일 메시지 오류가 일일 배치 전체 실패로 번지면 안 된다.
    """
    if row.processing_mode == "skip" or not row.clean_text.strip():
        return []

    try:
        async with semaphore:
            extraction = await _extract_message_semantics(
                row=row,
                taxonomy=taxonomy,
                llm_config=llm_config,
                system_prompt=system_prompt,
            )
    except Exception as exc:
        logger.warning(
            "Semantic extraction failed for telegram_message_id=%s: %s",
            row.telegram_message_id,
            exc,
        )
        fallback = _build_fallback_message(row)
        return [fallback] if fallback else []

    classified_units: list[ClassifiedMessage] = []
    for unit_index, raw_unit in enumerate(extraction.units):
        normalized = _normalize_unit(
            row=row,
            taxonomy=taxonomy,
            structure_type=extraction.structure_type,
            unit_index=unit_index,
            raw_unit=raw_unit,
            category_map=category_map,
            theme_map=theme_map,
        )
        if normalized is None:
            continue
        classified_units.append(normalized)
    _apply_digest_split_qa_warnings(
        row=row,
        structure_type=extraction.structure_type,
        units=classified_units,
    )
    return classified_units


async def _classify_messages_async(
    normalized_messages: list[NormalizedMessage],
    *,
    taxonomy: TaxonomyRegistry,
    llm_config: StageLLMConfig,
    system_prompt: str,
) -> list[ClassifiedMessage]:
    """메시지 배치를 동시 분류하고 메시지별 unit 결과를 평탄화한다.

    필요한 이유:
    - 일일 실행은 메시지 수가 많아 안정적인 제한 동시성이 필요하다.
    - 실행 시간/로그/처리량 제어를 한 곳에서 관리해야 운영이 쉽다.
    """
    started_at = time.perf_counter()
    category_map, theme_map = build_match_dictionary(taxonomy)
    logger.info(
        "Semantic extraction batch started: provider=%s messages=%d max_concurrency=%d",
        llm_config.provider,
        len(normalized_messages),
        SEMANTIC_EXTRACTION_MAX_CONCURRENCY,
    )
    semaphore = asyncio.Semaphore(SEMANTIC_EXTRACTION_MAX_CONCURRENCY)
    tasks = [
        _classify_single_message(
            row=row,
            taxonomy=taxonomy,
            llm_config=llm_config,
            category_map=category_map,
            theme_map=theme_map,
            semaphore=semaphore,
            system_prompt=system_prompt,
        )
        for row in normalized_messages
    ]
    results = await asyncio.gather(*tasks)
    flattened = [item for batch in results for item in batch]
    logger.info(
        "Semantic extraction batch completed: provider=%s messages=%d units=%d elapsed=%.2fs",
        llm_config.provider,
        len(normalized_messages),
        len(flattened),
        time.perf_counter() - started_at,
    )
    return flattened


def classify_messages(
    normalized_messages: list[NormalizedMessage],
    *,
    taxonomy: TaxonomyRegistry,
    system_prompt: str | None = None,
    llm_config: StageLLMConfig | None = None,
) -> list[ClassifiedMessage]:
    """pipeline/CLI가 사용하는 동기 엔트리포인트다.

    목적:
    - 외부 호출부는 단순하게 유지하고, 실제 분류 작업은 async 구현에 위임한다.
    - llm_config 미지정 시 config.yaml(llm.daily_v2.extraction)을 따른다.
      실험(tuning)에서는 명시 주입으로 오버라이드한다.
    """
    if not normalized_messages:
        return []
    resolved_llm_config = llm_config or get_semantic_extraction_llm_config()
    resolved_system_prompt = system_prompt or SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    return asyncio.run(
        _classify_messages_async(
            normalized_messages,
            taxonomy=taxonomy,
            llm_config=resolved_llm_config,
            system_prompt=resolved_system_prompt,
        )
    )
