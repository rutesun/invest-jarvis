from pathlib import Path

import pytest

from src.tools.notebook.models import NotebookEntry
from src.tools.notebook.parser import parse_notebook_dir


def write_note(root: Path, kind: str, text: str, filename: str = "2026-10.md") -> None:
    folder = root / kind
    folder.mkdir(exist_ok=True)
    (folder / filename).write_bytes(text.encode())


def test_monthly_entries_keep_key_properties_and_exact_body(tmp_path):
    body = (
        "\n- **태그**: #NVDA #반도체 #관망 #NVDA\n"
        "- **출처**: [기사](https://example.com/article)\n"
        "- **원문 PDF**: [원문](https://drive.google.com/file/d/example/view)\n\n"
    )
    write_note(
        tmp_path, "research", "---\ntype: research\n---\n# 노트\n## 2026-10-14\n### 연구\n" + body
    )
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.key == "research/2026-10-14#연구"
    assert entry.body_markdown == body
    assert entry.source_path == "notebook/research/2026-10.md#연구"
    assert entry.stocks == []
    assert entry.themes == ["NVDA", "반도체"]
    assert entry.action == "관망"
    assert entry.source_url == "https://example.com/article"
    assert entry.pdf_url == "https://drive.google.com/file/d/example/view"
    properties = entry.properties()
    assert properties["Key"] == {"rich_text": [{"type": "text", "text": {"content": entry.key}}]}
    assert properties["Date"] == {"date": {"start": "2026-10-14"}}
    assert properties["종목"] == {"multi_select": []}
    assert properties["Source Path"]["rich_text"][0]["text"]["content"] == entry.source_path
    assert properties["PDF 원문"] == {"url": entry.pdf_url}
    assert "Content Hash" not in properties


def test_fenced_headings_and_metadata_are_body_only(tmp_path):
    body = "```markdown\n## 2026-99-99\n### 가짜\n- **태그**: #AAPL\n```\n진짜 본문\n"
    write_note(tmp_path, "thoughts", "## 2026-10-14\n### 단상\n" + body)
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.title == "단상"
    assert entry.body_markdown == body
    assert entry.stocks == []


def test_tilde_fence_ignores_shorter_fence_and_quoted_headings(tmp_path):
    body = "~~~~\n~~~\n### 가짜\n~~~~\n> ### 인용\n"
    write_note(tmp_path, "thoughts", "## 2026-10-14\n### 단상\n" + body)
    assert len(parse_notebook_dir(tmp_path)) == 1


@pytest.mark.parametrize(
    "header", ["## 2026-02-30", "## 2026-13-01", "## 2026-1-01", "## 날짜 없음"]
)
def test_invalid_date_headers_fail_closed(tmp_path, header):
    write_note(tmp_path, "research", f"{header}\n### 제목\n본문\n")
    with pytest.raises(ValueError, match="date"):
        parse_notebook_dir(tmp_path)


def test_entry_without_date_fails_closed(tmp_path):
    write_note(tmp_path, "research", "# 노트\n### 날짜 빠짐\n본문\n")
    with pytest.raises(ValueError, match="date"):
        parse_notebook_dir(tmp_path)


def test_duplicate_keys_across_monthly_files_fail_closed(tmp_path):
    text = "## 2026-10-14\n### 중복\n본문\n"
    write_note(tmp_path, "research", text)
    write_note(tmp_path, "research", text, "2026-09.md")
    with pytest.raises(ValueError, match="Duplicate"):
        parse_notebook_dir(tmp_path)


def test_standalone_documents_are_excluded_and_order_is_stable(tmp_path):
    write_note(tmp_path, "research", "### 날짜가 없는 단독 문서", "evergreen.md")
    write_note(
        tmp_path,
        "trades",
        "## 2026-10-14\n### 삼성전자(005930) 매수\n- **태그**: #삼성전자 #005930 #반도체\n- **액션**: #매수\n",
    )
    write_note(tmp_path, "thoughts", "## 2026-10-14\n### 단상\n")
    entries = parse_notebook_dir(tmp_path)
    assert [entry.type for entry in entries] == ["trades", "thoughts"]
    assert entries[0].stocks == ["005930"]
    assert entries[0].themes == ["삼성전자", "005930", "반도체"]
    assert entries[0].action == "매수"


def test_tags_preserve_raw_candidates_without_classification_or_alias_mapping(tmp_path):
    body = (
        "- **태그**: #삼성전자 #005930 #005930.KS #하이닉스 #SK하이닉스 #000660 #000660.KS #HBM #AI\r\n"
        "```\r\n- **태그**: #삼성전기\r\n```\r\n"
    )
    write_note(tmp_path, "research", "## 2026-10-22\r\n### 반도체 비교\r\n" + body)
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.stocks == []
    assert entry.themes == [
        "삼성전자",
        "005930",
        "005930.KS",
        "하이닉스",
        "SK하이닉스",
        "000660",
        "000660.KS",
        "HBM",
        "AI",
    ]
    assert entry.key == "research/2026-10-22#반도체 비교"
    assert entry.body_markdown == body


def test_only_explicit_stock_metadata_becomes_unresolved_stock_candidates(tmp_path):
    write_note(
        tmp_path,
        "research",
        "## 2026-10-22\n### 비교\n"
        "- **종목**: #미등록기업 #005930.KS\n"
        "- **태그**: #삼성전기 #009150 #엘앤에프 #066970 #한국콜마 #에이피알 #리노공업 #반도체 #미등록테마\n",
    )
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.stocks == ["미등록기업", "005930.KS"]
    assert entry.themes == [
        "삼성전기",
        "009150",
        "엘앤에프",
        "066970",
        "한국콜마",
        "에이피알",
        "리노공업",
        "반도체",
        "미등록테마",
    ]


@pytest.mark.parametrize(
    ("title", "tag", "stock"),
    [
        ("KODEX AI전력핵심설비 매수", "KODEX_AI전력핵심설비", "KODEX AI전력핵심설비"),
        ("SOL 조선TOP3플러스 매수", "SOL조선TOP3플러스", "SOL 조선TOP3플러스"),
    ],
)
def test_observed_etf_trade_titles_preserve_complete_stock_name(tmp_path, title, tag, stock):
    write_note(tmp_path, "trades", f"## 2026-10-22\n### {title}\n- **태그**: #{tag} #ETF\n")
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.stocks == [stock]
    assert entry.themes == [tag, "ETF"]


def test_unregistered_tag_is_not_inferred_from_company_mentions(tmp_path):
    write_note(
        tmp_path,
        "research",
        "## 2026-10-22\n### 삼성전자 공급망\n삼성전자 본문\n- **태그**: #새기업 #CPO\n",
    )
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.stocks == []
    assert entry.themes == ["새기업", "CPO"]


def test_pdf_property_requires_explicit_drive_metadata(tmp_path):
    write_note(
        tmp_path,
        "research",
        "## 2026-10-14\n### 연구\n[PDF](https://drive.google.com/file/d/inferred/view)\n- **원문 PDF**: [파일](https://example.com/not-drive.pdf)\n",
    )
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.pdf_url is None


def test_heading_hash_characters_remain_part_of_compatible_identity(tmp_path):
    write_note(tmp_path, "research", "## 2026-10-14\n### C#\n본문\n")
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.key == "research/2026-10-14#C#"


@pytest.mark.parametrize(
    "fields",
    [
        {"stocks": ["invalid,name"]},
        {"themes": ["😀" * 51]},
        {"themes": [f"theme{i}" for i in range(101)]},
        {"action": "a" * 101},
        {"source_url": "https://example.com/" + "a" * 2000},
        {"pdf_url": "file:///tmp/private.pdf"},
    ],
)
def test_properties_fail_closed_for_invalid_notion_values(fields):
    entry = NotebookEntry(
        "research", "2026-10-14", "제목", "본문", "notebook/research/2026-10.md#제목", **fields
    )
    with pytest.raises(ValueError, match="Notion"):
        entry.properties()


@pytest.mark.parametrize(
    ("title", "candidate"),
    [
        ("삼성전자(005930) 매수", "005930"),
        ("아마존(AMZN) 매수", "AMZN"),
        ("삼성전기 매도 (1/3 부분청산)", "삼성전기"),
        ("새로운 회사 이름 손절", "새로운 회사 이름"),
    ],
)
def test_trade_title_preserves_search_candidate_without_resolving(tmp_path, title, candidate):
    write_note(tmp_path, "trades", f"## 2026-10-22\n### {title}\n본문\n")
    [entry] = parse_notebook_dir(tmp_path)
    assert entry.stocks == [candidate]
    assert entry.key == f"trades/2026-10-22#{title}"
    assert entry.body_markdown == "본문\n"
