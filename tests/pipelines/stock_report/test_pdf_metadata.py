from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.pdf_metadata import (
    DocumentMeta,
    extract_metadata,
    load_sources,
)
from src.pipelines.stock_report.pdf_parser import ParsedDocument


SOURCES = {
    "shinhanresearch": {"name": "신한투자증권", "trust_tier": "high"},
    "hana_us_stock": {"name": "하나증권", "trust_tier": "high"},
    "kiwoom_semibat": {"name": "키움증권", "trust_tier": "high"},
    "kwusa": {"name": "kwusa", "trust_tier": "unknown"},
}


def _doc(
    *,
    source_path: str = "data/files/2026-06-02/shinhanresearch_url_50006_50006.pdf",
    markdown: str = "# 제목\n\n본문 " * 100,
    text_char_count: int = 5000,
    image_ref_count: int = 5,
    json_blocks: list | None = None,
    warnings: list[str] | None = None,
) -> ParsedDocument:
    return ParsedDocument(
        source_path=source_path,
        markdown=markdown,
        page_count=4,
        text_char_count=text_char_count,
        image_ref_count=image_ref_count,
        parse_mode="local",
        json_blocks=json_blocks,
        warnings=warnings or [],
    )


def _json_table(rows: list[list[str]]) -> list:
    """rows[i][j] 문자열을 opendataloader JSON 표 스키마로 감싼다."""
    return [
        {
            "type": "table",
            "rows": [
                {"cells": [{"kids": [{"type": "paragraph", "content": cell}]} for cell in row]}
                for row in rows
            ],
        }
    ]


def _meta(**kwargs) -> DocumentMeta:
    doc = _doc(**kwargs)
    return extract_metadata(doc, doc.source_path, SOURCES)


# --- broker 매핑 ---------------------------------------------------------


def test_broker_known_prefix_maps_to_korean_name() -> None:
    meta = _meta(source_path="data/files/2026-06-02/shinhanresearch_url_50006_50006.pdf")
    assert meta.broker_key == "shinhanresearch"
    assert meta.broker_name == "신한투자증권"


def test_broker_longest_prefix_wins_for_multitoken_key() -> None:
    # "hana_us_stock_..."는 첫 토큰("hana")이 아니라 가장 긴 매칭 key로 잡혀야 한다.
    meta = _meta(source_path="data/files/2026-06-02/hana_us_stock_url_9339_9339.pdf")
    assert meta.broker_key == "hana_us_stock"
    assert meta.broker_name == "하나증권"


def test_broker_unknown_prefix_falls_back_to_identity() -> None:
    meta = _meta(source_path="data/files/2026-06-02/jeilstock_url_44294_x.pdf")
    assert meta.broker_key == "jeilstock"
    assert meta.broker_name == "jeilstock"


# --- 발행일 --------------------------------------------------------------


def test_published_date_parsed_from_path() -> None:
    meta = _meta(source_path="data/files/2026-06-02/x.pdf")
    assert meta.published_date == date(2026, 6, 2)


def test_published_date_none_when_absent() -> None:
    meta = _meta(source_path="data/files/inbox/x.pdf")
    assert meta.published_date is None


# --- 제목 / 티커 ---------------------------------------------------------


def test_ticker_korean_six_digit_code() -> None:
    meta = _meta(markdown="# 한미약품 (128940)\n\n## 비만 신약\n본문")
    assert meta.target_ticker == "128940"
    assert meta.title == "한미약품"


def test_ticker_us_suffix() -> None:
    meta = _meta(markdown="# H.P. Enterprise Co. (HPE.US)\n\n## 노트\n본문")
    assert meta.target_ticker == "HPE.US"
    assert meta.title == "H.P. Enterprise Co."


def test_ticker_none_for_macro_report() -> None:
    meta = _meta(markdown="# 2분기 주식시장 전망\n\n### Yellow Flag\n매크로 본문")
    assert meta.target_ticker is None
    assert meta.title == "2분기 주식시장 전망"


# --- needs_hybrid (융합 표) ----------------------------------------------


def test_needs_hybrid_true_for_fused_json_cell() -> None:
    blocks = _json_table(
        [
            ["(십억원, %)", "1Q26F", "1Q25"],
            ["매출액 영업이익 순이익", "2,157.6 49.6 42.1", "2,061.8 4.6 48.5"],
        ]
    )
    meta = _meta(json_blocks=blocks)
    assert meta.needs_hybrid is True


def test_needs_hybrid_false_for_clean_json_table() -> None:
    # 각 라벨이 자기 셀에 깔끔히 분리된 표 -> 융합 셀 없음.
    blocks = _json_table(
        [
            ["구분", "1Q26F"],
            ["매출액", "2,157.6"],
            ["영업이익", "49.6"],
            ["순이익", "42.1"],
        ]
    )
    meta = _meta(json_blocks=blocks)
    assert meta.needs_hybrid is False


def test_needs_hybrid_true_from_markdown_table_fallback() -> None:
    markdown = (
        "# 종목 (123456)\n\n"
        "|(십억원)|1Q26F|\n"
        "|---|---|\n"
        "|매출액 영업이익 순이익|2,157.6 49.6 42.1|\n"
    )
    meta = _meta(markdown=markdown, json_blocks=None)
    assert meta.needs_hybrid is True


def test_needs_hybrid_false_when_no_table() -> None:
    meta = _meta(markdown="# 매크로 (no table)\n\n매출액 전망은 본문 산문에만 있다.")
    assert meta.needs_hybrid is False


def test_needs_hybrid_label_subsumption_does_not_double_count() -> None:
    # "순이익률" 한 셀은 "순이익"으로 다시 세지 않으므로 융합(2개)이 아니다.
    blocks = _json_table([["순이익률", "2.0"]])
    meta = _meta(json_blocks=blocks)
    assert meta.needs_hybrid is False


def test_needs_hybrid_false_when_failed_or_needs_ocr() -> None:
    # 융합 셀이 있어도 failed/needs_ocr면 hybrid 대상이 아니다(쓸 만한 로컬 표 없음).
    blocks = _json_table([["매출액 영업이익 순이익", "1 2 3"]])
    failed = _meta(markdown="", warnings=["0바이트 빈 파일입니다."], json_blocks=blocks)
    assert failed.needs_hybrid is False
    ocr = _meta(text_char_count=64, json_blocks=blocks)
    assert ocr.needs_hybrid is False


# --- parse_status --------------------------------------------------------


def test_parse_status_needs_ocr_for_low_text() -> None:
    meta = _meta(text_char_count=64)
    assert meta.parse_status == "needs_ocr"


def test_parse_status_needs_ocr_for_image_heavy_low_text() -> None:
    meta = _meta(text_char_count=400, image_ref_count=200)
    assert meta.parse_status == "needs_ocr"


def test_parse_status_failed_for_empty_or_warning() -> None:
    assert _meta(markdown="", warnings=["0바이트 빈 파일입니다."]).parse_status == "failed"
    assert _meta(markdown="   ").parse_status == "failed"


def test_parse_status_ok_for_normal_doc() -> None:
    meta = _meta(text_char_count=5000, image_ref_count=10)
    assert meta.parse_status == "ok"


def test_parse_status_ok_for_chart_heavy_but_text_rich() -> None:
    # 차트(이미지) 많아도 본문이 충분하면 정상 (50003 유형: image_ref 944, text 76k).
    meta = _meta(text_char_count=76000, image_ref_count=944)
    assert meta.parse_status == "ok"


# --- loader --------------------------------------------------------------


def test_load_sources_reads_yaml_map() -> None:
    sources = load_sources("config/stock_report_pdf_sources.yaml")
    assert sources["shinhanresearch"]["name"] == "신한투자증권"
    assert sources["hana_us_stock"]["name"] == "하나증권"
    # 미확인 prefix는 identity(name == key).
    assert sources["jeilstock"]["name"] == "jeilstock"
