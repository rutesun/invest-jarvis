from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.pdf_chunking import (
    MAX_CHARS,
    MIN_CHARS,
    OVERLAP_CHARS,
    PdfChunkDraft,
    build_pdf_chunks,
)
from src.pipelines.stock_report.pdf_metadata import DocumentMeta
from src.pipelines.stock_report.pdf_parser import ParsedDocument


def _parsed(markdown: str) -> ParsedDocument:
    return ParsedDocument(
        source_path="data/files/2026-06-02/shinhanresearch_url_50006_50006.pdf",
        markdown=markdown,
        page_count=4,
        text_char_count=len(markdown),
        image_ref_count=0,
        parse_mode="local",
        json_blocks=None,
        warnings=[],
    )


def _meta(
    *,
    broker_name: str | None = "신한투자증권",
    target_ticker: str | None = "011210",
    category_key: str | None = "자동차부품",
    main_theme: str | None = "멕시코 HEV",
) -> DocumentMeta:
    return DocumentMeta(
        broker_key="shinhanresearch",
        broker_name=broker_name,
        title="현대위아",
        published_date=date(2026, 6, 2),
        target_ticker=target_ticker,
        category_key=category_key,
        main_theme=main_theme,
        parse_status="ok",
        needs_hybrid=False,
    )


def _chunks(markdown: str, **meta_kwargs) -> list[PdfChunkDraft]:
    return build_pdf_chunks(_parsed(markdown), _meta(**meta_kwargs))


def _seqs(chunks: list[PdfChunkDraft]) -> list[int]:
    return [c.chunk_seq for c in chunks]


# --- 헤딩 분할 / section_path -------------------------------------------------


def test_nested_headings_build_hierarchical_section_path() -> None:
    markdown = (
        "# 한미약품\n\n"
        "도입 본문 한 줄. 한미약품의 비만 신약 파이프라인은 국내 1위 수준이다.\n\n"
        "## 릴리 빅딜\n\n"
        "릴리와의 기술수출 계약 규모가 시장 기대를 상회했다는 평가가 이어지고 있다.\n"
    )
    chunks = _chunks(markdown)
    paths = {c.section_path for c in chunks}
    assert "한미약품" in paths
    assert "한미약품 > 릴리 빅딜" in paths


def test_top_level_only_heading_yields_flat_section_path() -> None:
    markdown = (
        "## 릴리 빅딜\n\n"
        "릴리와의 기술수출 계약이 본격화되며 비만 치료제 파이프라인 가치가 부각되었다.\n"
    )
    chunks = _chunks(markdown)
    assert chunks
    assert all(c.section_path == "릴리 빅딜" for c in chunks)


def test_deeper_heading_replaces_same_or_deeper_level_in_path() -> None:
    # h2 -> h3 누적, 이후 다른 h2가 오면 h3는 path에서 빠져야 한다.
    markdown = (
        "## 섹션 A\n\n"
        "섹션 A 본문. 첫 번째 주제에 대한 충분히 긴 산문 문단을 여기에 둔다.\n\n"
        "### 하위 A1\n\n"
        "하위 A1 본문. 세부 주제에 대한 충분히 긴 산문 문단을 여기에 둔다.\n\n"
        "## 섹션 B\n\n"
        "섹션 B 본문. 두 번째 최상위 주제에 대한 충분히 긴 산문 문단을 여기에 둔다.\n"
    )
    paths = {c.section_path for c in _chunks(markdown)}
    assert "섹션 A" in paths
    assert "섹션 A > 하위 A1" in paths
    assert "섹션 B" in paths  # 하위 A1이 섹션 B에 끌려오면 안 된다.
    assert "섹션 A > 하위 A1 > 섹션 B" not in paths


def test_content_before_first_heading_uses_intro_section() -> None:
    markdown = (
        "헤딩 이전의 도입 본문이다. 이 문단은 어떤 헤딩에도 속하지 않는 전문이다.\n\n"
        "# 본문 시작\n\n"
        "첫 헤딩 아래의 본문 문단으로 충분히 긴 산문을 둔다.\n"
    )
    chunks = _chunks(markdown)
    assert chunks[0].section_path == "intro"


# --- 산문 small chunk + chunk_seq --------------------------------------------


def test_prose_section_splits_into_multiple_small_chunks_with_contiguous_seq() -> None:
    # 각 문단이 MIN_CHARS를 넘되 합치면 MAX_CHARS를 넘도록 구성 -> 여러 청크.
    para = "현대위아의 멕시코 법인은 가동률 개선으로 고정비 절감 효과가 기대된다. " * 24
    markdown = f"# 현대위아 (011210)\n\n{para.strip()}\n\n{para.strip()}\n\n{para.strip()}\n"
    chunks = _chunks(markdown)
    assert len(chunks) >= 2
    # chunk_seq는 0,1,2.. 로 엄격 증가 + 연속.
    assert _seqs(chunks) == list(range(len(chunks)))
    assert all(not c.is_table for c in chunks)
    assert all(len(c.content_clean) <= MAX_CHARS for c in chunks)


def test_global_chunk_seq_is_contiguous_across_sections() -> None:
    body = "충분히 긴 본문 문단으로 섹션마다 한 개 이상의 청크를 만들기 위한 산문이다. " * 4
    markdown = (
        f"# 섹션1\n\n{body.strip()}\n\n## 섹션2\n\n{body.strip()}\n\n## 섹션3\n\n{body.strip()}\n"
    )
    chunks = _chunks(markdown)
    assert _seqs(chunks) == list(range(len(chunks)))


# --- 표 원자성 ----------------------------------------------------------------


def test_table_block_is_single_atomic_chunk_with_numbers_preserved() -> None:
    markdown = (
        "# 현대위아 (011210)\n\n"
        "## 1Q26 Preview\n\n"
        "1분기 영업이익은 시장 기대치를 소폭 하회할 전망이라는 분석이 제시되었다.\n\n"
        "|(십억원, %)|1Q26F|1Q25|\n"
        "|---|---|---|\n"
        "|매출액|2,157.6|2,061.8|\n"
        "|영업이익|49.6|48.5|\n\n"
        "표 다음의 산문 문단으로 표와 합쳐지면 안 되는 별도 본문이다.\n"
    )
    chunks = _chunks(markdown)
    tables = [c for c in chunks if c.is_table]
    assert len(tables) == 1
    table = tables[0]
    # 숫자가 살아있어야 한다.
    assert "2,157.6" in table.content_clean
    assert "2,061.8" in table.content_clean
    assert "49.6" in table.content_clean
    # 표는 산문과 섞이지 않는다.
    assert "1분기 영업이익" not in table.content_clean
    assert "표 다음의 산문" not in table.content_clean
    # 인접 산문은 표가 아닌 별도 청크로 남는다.
    prose_texts = [c.content_clean for c in chunks if not c.is_table]
    assert any("표 다음의 산문" in t for t in prose_texts)
    assert all("매출액" not in t for t in prose_texts)


def test_table_separator_row_dropped_but_data_rows_kept() -> None:
    markdown = "## 표 섹션\n\n|구분|값|\n|---|---|\n|매출액|2,157.6|\n"
    table = next(c for c in _chunks(markdown) if c.is_table)
    assert "---" not in table.content_clean
    assert "매출액" in table.content_clean
    assert "2,157.6" in table.content_clean


def test_empty_skeleton_table_row_is_skipped() -> None:
    markdown = "## 표 섹션\n\n|구분|값|\n|---|---|\n| | |\n|매출액|2,157.6|\n| | |\n"
    table = next(c for c in _chunks(markdown) if c.is_table)
    # 데이터 행만 남고 빈 스켈레톤 행은 사라진다.
    lines = table.content_clean.splitlines()
    assert all(set(line) != {"|", " "} for line in lines)
    assert "매출액" in table.content_clean


def test_two_separate_tables_yield_two_table_chunks() -> None:
    markdown = (
        "## 섹션\n\n"
        "|구분|값|\n|---|---|\n|1|2|\n\n"
        "중간 산문 문단으로 두 표 사이를 의미적으로 구분하는 본문이다.\n\n"
        "|항목|결과|\n|---|---|\n|3|4|\n"
    )
    tables = [c for c in _chunks(markdown) if c.is_table]
    assert len(tables) == 2
    assert "1" in tables[0].content_clean
    assert "3" in tables[1].content_clean


# --- 긴 문단 hard-split + overlap, 작은 조각 병합 ------------------------------


def test_oversized_paragraph_hard_split_with_overlap() -> None:
    # 단일 문단이 MAX_CHARS를 크게 초과 -> overlap 겹침으로 분할.
    long_para = "가" * (MAX_CHARS * 2)
    markdown = f"# 섹션\n\n{long_para}\n"
    chunks = _chunks(markdown)
    assert len(chunks) >= 2
    assert all(len(c.content_clean) <= MAX_CHARS for c in chunks)
    # 인접 청크 끝/시작이 OVERLAP_CHARS만큼 겹친다.
    tail = chunks[0].content_clean[-OVERLAP_CHARS:]
    head = chunks[1].content_clean[:OVERLAP_CHARS]
    assert tail == head
    # 전체 글자는 (중복 제외) 원문을 모두 보존한다.
    assert "".join(dict.fromkeys(c.content_clean for c in chunks))


def test_tiny_fragment_merged_into_adjacent_chunk_in_same_section() -> None:
    # 두 정상 문단(각각 단독 청크) 뒤에 tiny 꼬리를 붙여, 어떤 청크도 MIN_CHARS
    # 미만으로 남지 않고 tiny가 인접 청크로 흡수되는 결과를 검증한다.
    para = "충분히 큰 본문 문단으로 단독 청크가 되기에 충분한 길이의 산문을 둔다. " * 24
    tiny = "짧은 꼬리."  # MIN_CHARS 미만
    markdown = f"# 섹션\n\n{para.strip()}\n\n{para.strip()}\n\n{tiny}\n"
    chunks = _chunks(markdown)
    assert len(chunks) >= 2
    # 작은 꼬리는 단독 청크로 남지 않는다(어떤 청크도 MIN 미만이 아님).
    assert all(len(c.content_clean) >= MIN_CHARS for c in chunks)
    assert tiny in chunks[-1].content_clean


def test_leading_tiny_fragment_merges_into_following_chunk() -> None:
    tiny = "짧은 머리."
    big = "뒤따르는 큰 본문 문단으로 단독 청크가 되기에 충분한 길이의 산문을 둔다. " * 24
    markdown = f"# 섹션\n\n{tiny}\n\n{big.strip()}\n\n{big.strip()}\n"
    chunks = _chunks(markdown)
    # 머리 조각은 단독 청크로 남지 않고 첫 본문 청크에 흡수된다.
    assert all(len(c.content_clean) >= MIN_CHARS for c in chunks)
    assert tiny in chunks[0].content_clean


# --- 이미지/노이즈 제거 -------------------------------------------------------


def test_image_markup_stripped_from_content() -> None:
    markdown = (
        "# 섹션\n\n"
        "![image 1](<shinhanresearch_images/imageFile1.png>)\n\n"
        "이미지 마크업은 제거되고 본문만 남아야 한다는 것을 검증하는 충분한 산문이다.\n"
    )
    chunks = _chunks(markdown)
    assert chunks
    joined = "\n".join(c.content_clean for c in chunks)
    assert "imageFile1" not in joined
    assert "![" not in joined
    assert "이미지 마크업은 제거되고" in joined


def test_image_only_block_emits_no_chunk() -> None:
    markdown = "![image 1](<x/imageFile1.png>)\n\n![image 2](<x/imageFile2.png>)\n"
    assert _chunks(markdown) == []


def test_chart_axis_noise_lines_dropped_but_prose_kept() -> None:
    # 차트 축 잔해(숫자/축 라벨 단독 줄)는 버리고, 한글이 있는 본문은 유지.
    markdown = (
        "# 섹션\n\n"
        "115,000\n"
        "120\n"
        "좌축\n"
        "현대위아 주가가 의미 있는 본문 한 줄로 충분한 길이를 갖도록 작성한 산문이다.\n\n"
        "투자의견 매수와 목표주가 9만 9천원을 유지한다는 분석이 본문에 담겨 있다.\n"
    )
    chunks = _chunks(markdown)
    joined = "\n".join(c.content_clean for c in chunks)
    assert "115,000" not in joined
    assert "좌축" not in joined
    assert "현대위아 주가가 의미 있는 본문" in joined
    assert "투자의견 매수" in joined


# --- canonical_summary --------------------------------------------------------


def test_canonical_summary_never_empty_and_uses_heading() -> None:
    markdown = (
        "## 1Q26 Preview\n\n"
        "1분기 영업이익은 시장 기대치를 소폭 하회할 전망이라는 분석이 제시되었다.\n"
    )
    chunk = _chunks(markdown)[0]
    assert chunk.canonical_summary
    assert chunk.canonical_summary.startswith("1Q26 Preview")


def test_table_canonical_summary_uses_nearest_preceding_heading() -> None:
    markdown = (
        "## Valuation\n\n"
        "밸류에이션 관련 본문 문단으로 표 직전의 충분히 긴 산문을 둔다.\n\n"
        "###### 현대위아 2026년 1분기 실적 전망\n\n"
        "|구분|값|\n|---|---|\n|매출액|2,157.6|\n"
    )
    table = next(c for c in _chunks(markdown) if c.is_table)
    assert table.canonical_summary == "현대위아 2026년 1분기 실적 전망"


def test_intro_chunk_summary_falls_back_to_first_line() -> None:
    markdown = "헤딩 없는 전문 본문이며 이 첫 문장이 요약으로 쓰여야 한다.\n"
    chunk = _chunks(markdown)[0]
    assert chunk.canonical_summary
    assert "헤딩 없는 전문 본문" in chunk.canonical_summary


# --- embed_payload ------------------------------------------------------------


def test_embed_payload_reuses_build_embed_payload_format() -> None:
    markdown = (
        "# 현대위아 (011210)\n\n"
        "## 1Q26 Preview\n\n"
        "1분기 영업이익은 시장 기대치를 소폭 하회할 전망이라는 분석이 제시되었다.\n"
    )
    chunk = _chunks(markdown)[0]
    payload = chunk.embed_payload
    assert payload.startswith("채널: 신한투자증권\n")
    assert "카테고리: 자동차부품\n" in payload
    assert "메인테마: 멕시코 HEV\n" in payload
    assert "티커: 011210\n" in payload
    assert chunk.canonical_summary in payload
    assert chunk.content_clean in payload


def test_embed_payload_defaults_when_meta_missing() -> None:
    markdown = "# 매크로 전망\n\n주식시장 전반의 매크로 환경에 대한 충분히 긴 본문 산문이다.\n"
    chunk = _chunks(markdown, broker_name=None, target_ticker=None, category_key=None)[0]
    assert chunk.embed_payload.startswith("채널: -\n")
    assert "카테고리: unclassified\n" in chunk.embed_payload
    assert "티커: -\n" in chunk.embed_payload
    assert chunk.ticker_tags == []


def test_ticker_tags_propagated_to_draft() -> None:
    markdown = "# 현대위아 (011210)\n\n충분히 긴 본문 산문을 한 문단 둔다.\n"
    chunk = _chunks(markdown)[0]
    assert chunk.ticker_tags == ["011210"]


# --- 부모 복원 (small-to-big) -------------------------------------------------


def test_parent_reconstruction_reassembles_section_in_seq_order() -> None:
    para1 = "첫 번째 문단으로 섹션 본문의 앞부분을 이루는 충분히 긴 산문 문단이다. " * 24
    para2 = "두 번째 문단으로 섹션 본문의 뒷부분을 이루는 충분히 긴 산문 문단이다. " * 24
    markdown = (
        "## 1Q26 Preview\n\n"
        f"{para1.strip()}\n\n{para2.strip()}\n\n"
        "## 다른 섹션\n\n"
        "다른 섹션의 본문으로 위 섹션과 섞이면 안 되는 충분히 긴 산문 문단이다.\n"
    )
    chunks = _chunks(markdown)

    target = "1Q26 Preview"
    section_chunks = sorted(
        (c for c in chunks if c.section_path == target),
        key=lambda c: c.chunk_seq,
    )
    assert len(section_chunks) >= 2
    # chunk_seq 순서대로 이어 붙이면 원래 섹션 내용 순서가 복원된다.
    reassembled = "\n\n".join(c.content_clean for c in section_chunks)
    assert reassembled.index(para1.strip()[:20]) < reassembled.index(para2.strip()[:20])
    # 다른 섹션 내용이 섞이지 않는다.
    assert "다른 섹션의 본문" not in reassembled


def test_table_kept_in_section_order_for_reconstruction() -> None:
    markdown = (
        "## 실적\n\n"
        "표 앞 산문 문단으로 섹션 본문의 도입부를 이루는 충분히 긴 산문이다.\n\n"
        "|구분|값|\n|---|---|\n|매출액|2,157.6|\n\n"
        "표 뒤 산문 문단으로 섹션 본문의 마무리를 이루는 충분히 긴 산문이다.\n"
    )
    section_chunks = sorted(
        (c for c in _chunks(markdown) if c.section_path == "실적"),
        key=lambda c: c.chunk_seq,
    )
    kinds = [c.is_table for c in section_chunks]
    # 산문 -> 표 -> 산문 순서가 chunk_seq로 보존된다.
    assert kinds == [False, True, False]
    assert "표 앞 산문" in section_chunks[0].content_clean
    assert "2,157.6" in section_chunks[1].content_clean
    assert "표 뒤 산문" in section_chunks[2].content_clean


# --- 빈 입력 -----------------------------------------------------------------


def test_empty_markdown_yields_no_chunks() -> None:
    assert _chunks("") == []
    assert _chunks("   \n\n  \n") == []


# --- CP2 잡음 필터: 차트 파이프블록 -----------------------------------------


def test_chart_table_filtered() -> None:
    # 숫자·기호·공백만으로 이루어진 파이프 블록은 청크가 생성되지 않아야 한다.
    markdown = "# MSCI 비중\n\n|0|2000|4000|6000|\n|---|---|---|---|\n|100|200|300|400|\n"
    chunks = _chunks(markdown)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 0


def test_real_table_not_filtered() -> None:
    # 한글 헤더가 있는 표는 is_table=True 청크 1개가 반드시 생성되어야 한다.
    markdown = (
        "## 실적 요약\n\n|구분|2025|2026|\n|---|---|---|\n|매출액|1,000|1,200|\n|영업이익|80|100|\n"
    )
    chunks = _chunks(markdown)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "매출액" in table_chunks[0].content_clean


def test_table_br_cleaned() -> None:
    # 표 셀에 <br> 태그가 포함되어 있어도 content_clean에는 남지 않아야 한다.
    markdown = (
        "## 브레이크 테스트\n\n"
        "|구분|내용|\n"
        "|---|---|\n"
        "|매출액<br>증가율|2,157.6<BR/>|\n"
        "|영업이익|49.6<br />|\n"
    )
    chunks = _chunks(markdown)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    content = table_chunks[0].content_clean
    assert "<br>" not in content.lower()
    assert "<br/>" not in content.lower()
    assert "매출액" in content
    assert "2,157.6" in content


# --- CP2 잡음 필터: 출처줄 병합 ----------------------------------------------


def test_source_line_merged_to_prev() -> None:
    # 출처줄 tiny 청크는 앞 청크의 content_clean에 병합되어야 한다.
    big_para = "현대위아의 멕시코 법인은 가동률 개선으로 고정비 절감 효과가 기대된다. " * 8
    markdown = f"# 본문 섹션\n\n{big_para.strip()}\n\n자료: 신한투자증권\n"
    chunks = _chunks(markdown)
    # "자료: 신한투자증권"이 단독 청크로 남아선 안 된다.
    standalone = [c for c in chunks if c.content_clean.startswith("자료:")]
    assert len(standalone) == 0
    # 앞 청크(big_para 포함)에 출처줄이 병합되어 있어야 한다.
    merged_chunk = next(c for c in chunks if "자료: 신한투자증권" in c.content_clean)
    assert "가동률 개선" in merged_chunk.content_clean


def test_source_line_first_chunk_kept() -> None:
    # 앞 청크가 없으면 출처줄 청크도 그냥 독립 청크로 유지되어야 한다.
    markdown = "출처: Bloomberg\n"
    chunks = _chunks(markdown)
    assert len(chunks) == 1
    assert chunks[0].content_clean == "출처: Bloomberg"


def test_chart_table_mixed_with_real() -> None:
    # 차트 파이프블록과 진짜 표가 같이 있을 때, 차트 블록만 제거되고 진짜 표는 남아야 한다.
    markdown = (
        "# 섹션\n\n"
        "| 0 | 2000 | 4000 |\n"
        "|---|---|---|\n"
        "| 100 | 200 | 300 |\n\n"
        "중간 산문 문단으로 두 표 사이를 의미적으로 구분한다.\n\n"
        "|구분|2025|\n"
        "|---|---|\n"
        "|매출액|1,000|\n"
    )
    chunks = _chunks(markdown)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "매출액" in table_chunks[0].content_clean


# --- CP2 잡음 필터: 노이즈 청크 제거 -----------------------------------------


def test_bullet_only_chunk_filtered() -> None:
    # ▪ 기호만으로 이루어진 청크는 의미 단어가 없어 제거되어야 한다.
    big_para = "현대위아의 멕시코 법인은 가동률 개선으로 고정비 절감 효과가 기대된다. " * 8
    markdown = f"# 섹션A\n\n{big_para.strip()}\n\n# 섹션B\n\n▪ ▪ ▪ ▪\n"
    chunks = _chunks(markdown)
    joined = "\n".join(c.content_clean for c in chunks)
    assert "▪" not in joined
    # 의미 있는 본문은 보존된다.
    assert any("가동률 개선" in c.content_clean for c in chunks)
    # 노이즈만 있던 섹션은 청크를 만들지 않는다.
    assert all(c.section_path != "섹션B" for c in chunks)


def test_br_only_line_dropped_and_br_not_mistaken_as_word() -> None:
    # 산문 줄의 잔여 <br>는 제거되고, 'br'이 영문 단어로 오인돼 기호 청크가 남지 않는다.
    big_para = "현대위아의 멕시코 법인은 가동률 개선으로 고정비 절감 효과가 기대된다. " * 8
    markdown = f"# 섹션A\n\n{big_para.strip()}\n\n# 섹션B\n\n<br><br>|\n"
    chunks = _chunks(markdown)
    joined = "\n".join(c.content_clean for c in chunks)
    assert "<br>" not in joined.lower()
    assert all(c.section_path != "섹션B" for c in chunks)


def test_meaningful_short_prose_chunk_kept() -> None:
    # 의미 단어가 있는 짧은 청크(예: 'Overweight')는 과삭제하지 않고 보존한다.
    markdown = "# 투자의견\n\nOverweight\n"
    chunks = _chunks(markdown)
    assert any("Overweight" in c.content_clean for c in chunks)
