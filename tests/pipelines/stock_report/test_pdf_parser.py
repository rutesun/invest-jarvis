from __future__ import annotations

from pathlib import Path

from src.pipelines.stock_report.pdf_parser import (
    _failed_doc,
    _image_ref_count,
    _real_text_char_count,
    _validate_pdf,
)


def test_real_text_char_count_excludes_image_markup() -> None:
    # 그림 마크업은 본문 글자로 세면 안 된다 (CP1: 그림 문서가 '정상'으로 오분류되던 버그).
    markdown = "![img](a.png)\n![img](b.png)\n현대위아 목표주가 99000"
    assert _real_text_char_count(markdown) == len("현대위아목표주가99000")


def test_real_text_char_count_near_zero_for_image_only() -> None:
    markdown = "\n".join(f"![img](p{i}.png)" for i in range(50))
    assert _real_text_char_count(markdown) == 0


def test_real_text_char_count_keeps_link_text() -> None:
    assert _real_text_char_count("[삼성전자](http://x)") == len("삼성전자")


def test_image_ref_count() -> None:
    assert _image_ref_count("![a](1.png) text ![b](2.png)") == 2
    assert _image_ref_count("이미지 없음") == 0


def test_validate_pdf_flags_empty_non_pdf_and_missing(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    assert _validate_pdf(empty) == "0바이트 빈 파일입니다."

    not_pdf = tmp_path / "fake.pdf"
    not_pdf.write_bytes(b"hello not a pdf")
    assert _validate_pdf(not_pdf) is not None

    missing = tmp_path / "nope.pdf"
    assert _validate_pdf(missing) is not None


def test_validate_pdf_accepts_pdf_header(tmp_path: Path) -> None:
    good = tmp_path / "good.pdf"
    good.write_bytes(b"%PDF-1.7\n%rest")
    assert _validate_pdf(good) is None


def test_failed_doc_shape() -> None:
    doc = _failed_doc(Path("x/y.pdf"), "local", "0바이트 빈 파일입니다.")
    assert doc.markdown == ""
    assert doc.text_char_count == 0
    assert doc.image_ref_count == 0
    assert doc.parse_mode == "local"
    assert doc.warnings == ["0바이트 빈 파일입니다."]
