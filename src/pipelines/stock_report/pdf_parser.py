"""opendataloader-pdf wrapper: PDF -> ParsedDocument (T13).

local 모드 기본. JVM 콜드스타트를 amortize하기 위해 배치 입력(여러 PDF 경로)을 받아
한 번의 ``opendataloader_pdf.convert`` 호출로 처리한다. opendataloader 출력 형식이
바뀌어도 이 wrapper 안에서 흡수하고, 외부에는 ``ParsedDocument``만 노출한다.

CP1(2026-06-04 스파이크) 보완:
- ``text_char_count``는 이미지/링크 마크업을 제거한 **실제 본문 글자 수**다.
  markdown ``![img](...)`` 마크업을 글자로 세면 그림(스캔) 문서가 '정상'으로 오분류된다.
- opendataloader 배치 변환은 all-or-nothing이라 깨진 PDF 1개가 배치 전체 산출을
  0으로 만든다. 0바이트/비PDF를 사전 검증으로 걸러내고, 배치 변환이 실패하면
  per-file로 폴백해 정상 문서를 살린다.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PARSER_VERSION = "opendataloader-pdf-2.4.7"

_WHITESPACE_RE = re.compile(r"\s+")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_PDF_MAGIC = b"%PDF-"


@dataclass(slots=True)
class ParsedDocument:
    source_path: str
    markdown: str
    page_count: int
    text_char_count: int  # 이미지/링크 마크업 제외 실제 본문 글자 수
    image_ref_count: int  # markdown 이미지 참조 수 (rasterization 판정용)
    parse_mode: str  # "local" | "hybrid"
    json_blocks: list | None  # A=None, B에서 사용
    warnings: list[str]


def _load_opendataloader() -> Any:
    try:
        import opendataloader_pdf  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency/runtime guard
        raise RuntimeError(
            "opendataloader-pdf 실행에 Java 11+와 패키지가 필요합니다. "
            "`uv add opendataloader-pdf` 후 다시 실행하세요."
        ) from exc
    return opendataloader_pdf


def _real_text(markdown: str) -> str:
    """이미지 마크업은 제거하고 링크는 표시 텍스트만 남겨 실제 본문만 반환한다."""
    without_images = _IMAGE_RE.sub("", markdown)
    return _LINK_RE.sub(r"\1", without_images)


def _real_text_char_count(markdown: str) -> int:
    """공백·이미지/링크 마크업을 제외한 실제 본문 글자 수."""
    return len(_WHITESPACE_RE.sub("", _real_text(markdown)))


def _image_ref_count(markdown: str) -> int:
    return len(_IMAGE_RE.findall(markdown))


def _page_count(json_data: Any) -> int:
    if isinstance(json_data, dict):
        value = json_data.get("number of pages")
        if isinstance(value, int):
            return value
    return 0


def _validate_pdf(source: Path) -> str | None:
    """변환 전 PDF 유효성 검사. 문제가 있으면 한국어 사유, 없으면 None."""
    if not source.is_file():
        return "파일이 존재하지 않습니다."
    try:
        if source.stat().st_size == 0:
            return "0바이트 빈 파일입니다."
        with source.open("rb") as handle:
            head = handle.read(5)
    except OSError as exc:
        return f"파일 읽기 실패: {exc}"
    if head != _PDF_MAGIC:
        return "PDF 헤더(%PDF-)가 없습니다."
    return None


def _failed_doc(source: Path, parse_mode: str, warning: str) -> ParsedDocument:
    return ParsedDocument(
        source_path=str(source),
        markdown="",
        page_count=0,
        text_char_count=0,
        image_ref_count=0,
        parse_mode=parse_mode,
        json_blocks=None,
        warnings=[warning],
    )


def _build_convert_kwargs(*, use_hybrid: bool, ocr_lang: str | None) -> dict[str, Any]:
    # markdown은 최종 산출물, json은 page_count(+want_json 시 구조 블록) 추출용.
    kwargs: dict[str, Any] = {"format": ["markdown", "json"], "quiet": True}
    if use_hybrid or ocr_lang:
        # OCR은 hybrid 백엔드 경로로만 가능하다 (local 모드엔 ocr_lang 파라미터가 없다).
        kwargs["hybrid"] = "hancom-ai"
        if ocr_lang:
            kwargs["hybrid_hancom_ai_ocr_strategy"] = "force"
    return kwargs


def parse_pdfs(
    paths: list[str],
    *,
    use_hybrid: bool = False,
    ocr_lang: str | None = None,
    want_json: bool = False,
) -> list[ParsedDocument]:
    """PDF 경로 리스트를 ParsedDocument 리스트로 변환한다 (입력 순서 보존).

    배치 입력으로 JVM 콜드스타트를 amortize한다. 단, opendataloader 배치 변환은
    all-or-nothing이라 깨진 PDF 1개가 배치 전체를 실패시킨다. 따라서 0바이트/비PDF는
    사전 검증으로 걸러 failed ParsedDocument로 반환하고, 배치 변환이 실패하면
    per-file로 폴백해 정상 문서를 살린다.
    """
    if not paths:
        return []

    opendataloader_pdf = _load_opendataloader()
    parse_mode = "hybrid" if (use_hybrid or ocr_lang) else "local"
    base_kwargs = _build_convert_kwargs(use_hybrid=use_hybrid, ocr_lang=ocr_lang)

    results: dict[str, ParsedDocument] = {}
    valid: list[str] = []
    for path in paths:
        problem = _validate_pdf(Path(path))
        if problem:
            results[path] = _failed_doc(Path(path), parse_mode, problem)
        else:
            valid.append(path)

    if valid:
        results.update(
            _convert_with_fallback(
                opendataloader_pdf,
                valid,
                base_kwargs,
                parse_mode=parse_mode,
                want_json=want_json,
            )
        )

    return [results[path] for path in paths]


def _convert_batch(
    opendataloader_pdf: Any,
    paths: list[str],
    base_kwargs: dict[str, Any],
    *,
    parse_mode: str,
    want_json: bool,
) -> dict[str, ParsedDocument]:
    tmpdir = tempfile.mkdtemp(prefix="odl_pdf_")
    try:
        opendataloader_pdf.convert(input_path=list(paths), output_dir=tmpdir, **base_kwargs)
        return {
            path: _read_back(Path(path), Path(tmpdir), parse_mode=parse_mode, want_json=want_json)
            for path in paths
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _convert_with_fallback(
    opendataloader_pdf: Any,
    paths: list[str],
    base_kwargs: dict[str, Any],
    *,
    parse_mode: str,
    want_json: bool,
) -> dict[str, ParsedDocument]:
    """배치 변환을 시도하고, all-or-nothing 실패 시 per-file로 폴백한다."""
    try:
        return _convert_batch(
            opendataloader_pdf, paths, base_kwargs, parse_mode=parse_mode, want_json=want_json
        )
    except Exception:  # 배치 all-or-nothing: 한 파일이 실패해도 나머지를 살린다
        results: dict[str, ParsedDocument] = {}
        for path in paths:
            try:
                results.update(
                    _convert_batch(
                        opendataloader_pdf,
                        [path],
                        base_kwargs,
                        parse_mode=parse_mode,
                        want_json=want_json,
                    )
                )
            except Exception as exc:  # 개별 변환 실패 격리
                results[path] = _failed_doc(Path(path), parse_mode, f"변환 실패: {exc}")
        return results


def _read_back(
    source: Path,
    output_dir: Path,
    *,
    parse_mode: str,
    want_json: bool,
) -> ParsedDocument:
    stem = source.stem
    md_path = output_dir / f"{stem}.md"
    json_path = output_dir / f"{stem}.json"
    warnings: list[str] = []

    json_data: Any = None
    if json_path.is_file():
        try:
            json_data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"json 읽기 실패: {exc}")

    if not md_path.is_file():
        warnings.append("opendataloader가 markdown 산출물을 생성하지 않았습니다.")
        return ParsedDocument(
            source_path=str(source),
            markdown="",
            page_count=_page_count(json_data),
            text_char_count=0,
            image_ref_count=0,
            parse_mode=parse_mode,
            json_blocks=None,
            warnings=warnings,
        )

    markdown = md_path.read_text(encoding="utf-8")
    json_blocks: list | None = None
    if want_json and isinstance(json_data, dict):
        kids = json_data.get("kids")
        if isinstance(kids, list):
            json_blocks = kids

    return ParsedDocument(
        source_path=str(source),
        markdown=markdown,
        page_count=_page_count(json_data),
        text_char_count=_real_text_char_count(markdown),
        image_ref_count=_image_ref_count(markdown),
        parse_mode=parse_mode,
        json_blocks=json_blocks,
        warnings=warnings,
    )
