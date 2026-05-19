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
    - `market_wrap`이라도 서로 다른 핵심 내러티브가 2개 이상이면 unit을 분리한다.
      예: 반도체 랠리 / 유가 급등 / 한국 증시 반응은 각각 별도 unit 후보다.
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
    - 숫자가 있다고 항상 `data`로 두지 말고, 사건성이 강하면 `signal`을 우선한다.

    출력 규칙:
    - `event_type`은 아래 canonical set 중 하나를 우선 사용한다.
      `자본조달`, `수주/계약`, `실적`, `정책`, `인증/승인`, `M&A`, `출시/제품`, `가격/마진`, `통계/지표`, `해석/전망`, `공지`.
      모호하면 null 허용.
    - `canonical_summary`는 report unit 기준의 한글 요약문이다.
    - `canonical_summary`는 20~60자 정도의 factual summary로 작성한다.
    - `canonical_summary`는 원문 첫 줄 복사나 prefix truncation이 아니어야 한다.
    - `supporting_facts`는 최종 리포트가 근거를 선별할 수 있도록 충분히 넓게 보존한다.
    - `supporting_facts`는 중복을 제거하되, 원문에 있는 투자 논리와 핵심 수치를 빠뜨리지 않는다.
    - `supporting_facts`는 원문에 근거가 있는 짧은 추출형 문장으로 작성한다.
      원문보다 더 길게 확장하거나, 원문에 없는 시장 영향/수혜/리스크를 새로 추론하지 않는다.
    - 각 `supporting_facts` 항목은 가능하면 80자 이내로 쓴다.
    - 제목, 채널명, 날짜, 작성자명, 링크, 컴플라이언스/배포 고지는 투자 근거가 아니면 제외한다.
    - 본문 앞부분의 작성자 코멘트/해석/추가 메모는 기사 본문보다 우선적으로 검토한다.
      별도 수치, 주주 관점, 투자 포인트, 리스크 코멘트가 있으면 `supporting_facts`에 반드시 보존한다.
    - `single_topic_deep`에서는 특히 아래 성격의 근거를 우선 보존한다.
      아래 항목은 새 출력 필드가 아니라, `supporting_facts`에 문장형 근거로 녹여서 보존해야 하는 판단 기준이다.
      - thesis: 이 뉴스가 왜 투자적으로 중요한지.
        예: 단순 발전자산 인수가 아니라 북버지니아 데이터센터 전력 수요와 규제자산 성장 경로를 확보한다.
      - risk: 이 투자 논리가 깨지는 조건.
        예: FERC/PJM 가격 통제, 규제 승인 실패, break fee, 고객 요금 부담.
      - regulatory_context: 숫자만 보면 안 보이는 제도/가격/규제 배경.
        예: 허용 ROE와 규제자산 기반 요금 회수 구조가 유틸리티 실적에 영향을 준다.
    - `supporting_facts`는 일반 메시지는 5~8개, 단건 심층 메시지는 필요하면 12~20개까지 허용한다.
    - 원문에 수치(%, 금액, 물량, 성장률)가 있다면 `supporting_facts`에 최소 1개 이상 반드시 포함한다.
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
        - `market_wrap`에서도 반도체 랠리, 유가/지정학, 국내 증시 반응처럼 주제가 다르면 unit을 나눈다
        - `notice`: 운영 공지, 채널 안내, 구독 유도
        - 사건성 기사형 아이템(상장/수주/협약/인증/정책발표 등)은 기본적으로 `signal` 우선
        - `category_key`는 내러티브/섹터, `event_type`은 촉발 이벤트 축으로 분리한다

        message:
        {row.clean_text}
        """
    ).strip()
