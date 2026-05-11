from __future__ import annotations

from textwrap import dedent

from src.pipelines.stock_report.models import NormalizedMessage


SEMANTIC_EXTRACTION_SYSTEM_PROMPT = dedent(
    """
    당신은 텔레그램 증시 메시지를 report unit으로 구조화하는 분석기다.

    핵심 원칙:
    - formatting marker(▶, *, -, 숫자)만 보고 자르지 말고 의미 단위를 기준으로 판단한다.
    - 하나의 중심 토픽을 여러 supporting section이 설명하는 메시지는 `single_topic_deep`으로 두고 unit 1개만 만든다.
    - 여러 독립 기사/헤드라인 digest는 `multi_item_digest`로 보고 item별 unit을 만든다.
    - 장 마감 시황/섹터 wrap은 `market_wrap`으로 처리한다.
    - 공지/채널 운영/홍보는 `notice`로 처리한다.

    출력 규칙:
    - `canonical_summary`는 report unit 기준의 한글 요약문이다.
    - `canonical_summary`는 20~60자 정도의 factual summary로 작성한다.
    - `canonical_summary`는 원문 첫 줄 복사나 prefix truncation이 아니어야 한다.
    - `supporting_facts`는 핵심 근거만 짧게 최대 5개까지 넣는다.
    - `ticker_tags`는 회사명 또는 ticker를 최대 5개까지 넣는다.
    - category/theme는 제공된 taxonomy를 우선 사용하되, 확신이 없으면 null로 둔다.
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
        - `notice`: 운영 공지, 채널 안내, 구독 유도

        message:
        {row.clean_text}
        """
    ).strip()
