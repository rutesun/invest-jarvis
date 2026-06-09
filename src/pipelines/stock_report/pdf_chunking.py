"""PDF markdown -> small-to-big retrieval chunks (T15).

``ParsedDocument.markdown`` (opendataloader 산출 Markdown)을 검색 단위 청크로 자른다.
검색 정밀도를 위해 산문은 **문단 단위 작은 청크**로, 표는 통째로 **원자 청크**로
만든다. 각 청크는 ``section_path`` + ``chunk_seq``로 부모 섹션을 복원할 수 있게
저장한다(small-to-big). merge(부모 확장)는 retrieval(T16) 소관이고, 여기서는 "작게
저장 + 부모 연결 정보"까지만 만든다.

임베딩 텍스트는 텔레그램 청크와 **같은** ``build_embed_payload``로 생성해 두 테이블의
벡터가 같은 좌표계에 있게 한다(Key Decision 5 — UNION ALL 검색 성립).

청킹 파라미터(``MAX_CHARS``/``MIN_CHARS``/``OVERLAP_CHARS``)는 CP2(실데이터 품질
게이트)에서 튜닝 대상인 모듈 상수다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.pipelines.stock_report.chunking import build_embed_payload
from src.pipelines.stock_report.pdf_metadata import DocumentMeta
from src.pipelines.stock_report.pdf_parser import ParsedDocument


# 작은 청크 목표 크기(문자). 한 문단을 넘겨 합칠 때 이 길이를 넘지 않게 모은다.
MAX_CHARS = 1500
# 이 길이 미만 조각은 같은 섹션의 인접 청크로 병합한다(파편 방지).
MIN_CHARS = 200
# MAX_CHARS를 넘는 단일 문단을 hard-split할 때 인접 조각 간 겹치는 길이(~10%).
OVERLAP_CHARS = 150

_DEFAULT_INTRO_SECTION = "intro"

# 이미지 마크업은 노이즈이므로 본문에서 제거한다(pdf_parser._IMAGE_RE와 동일 아이디어).
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*$")
# 표 구분선(``|---|---|``): 데이터가 아니므로 청크 본문에서 제외한다.
_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|?$")
# 차트 축 노이즈: 숫자/부호/단위 토큰만으로 이루어진 짧은 단독 줄(축 눈금·범례 잔해).
# opendataloader가 차트 이미지를 텍스트로 흘릴 때 생긴다. 산문 손실을 막기 위해
# 한글/영문 단어가 하나라도 있으면 노이즈로 보지 않는다.
_AXIS_NOISE_RE = re.compile(r"^[\s\d.,%()$+\-/x×~]+$")
_HANGUL_OR_WORD_RE = re.compile(r"[가-힣]|[A-Za-z]{2,}")
# 차트 축 단독 줄로 흔히 나오는 짧은 라벨 토큰. 한두 글자 단위/축 표기라 의미가 없다.
_AXIS_LABEL_TOKENS = frozenset({"좌축", "우축", "원", "점", "배", "회", "일", "조", "억"})


@dataclass(slots=True)
class PdfChunkDraft:
    section_path: str
    chunk_seq: int
    is_table: bool
    canonical_summary: str
    content_clean: str
    embed_payload: str
    ticker_tags: list[str]


@dataclass(slots=True)
class _Block:
    """reading order 상의 한 블록. 헤딩 / 표 / 산문 문단 중 하나."""

    kind: str  # "heading" | "table" | "prose"
    text: str
    section_path: str
    heading_level: int = 0
    heading_text: str = ""


@dataclass(slots=True)
class _SectionContext:
    """헤딩 스택으로부터 현재 section_path를 추적한다."""

    stack: list[tuple[int, str]] = field(default_factory=list)

    def push(self, level: int, text: str) -> None:
        # 같은 레벨 이상(더 얕거나 같은)의 헤딩은 새 헤딩으로 교체한다.
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, text))

    def path(self) -> str:
        return " > ".join(text for _, text in self.stack)

    def current_heading(self) -> str:
        return self.stack[-1][1] if self.stack else ""


def build_pdf_chunks(parsed: ParsedDocument, meta: DocumentMeta) -> list[PdfChunkDraft]:
    """파싱된 PDF markdown을 small-to-big 청크 리스트로 변환한다(reading order 보존)."""
    blocks = _split_blocks(parsed.markdown)

    ticker_tags = [meta.target_ticker] if meta.target_ticker else []
    channel_name = meta.broker_name or "-"
    category_key = meta.category_key or "unclassified"

    drafts: list[PdfChunkDraft] = []
    seq = 0
    for section_path, heading_text, units in _section_units(blocks):
        for is_table, content in units:
            content_clean = content.strip()
            if not content_clean:
                continue
            canonical_summary = _canonical_summary(heading_text, content_clean, is_table)
            embed_payload = build_embed_payload(
                canonical_summary=canonical_summary,
                clean_text=content_clean,
                channel_name=channel_name,
                category_key=category_key,
                main_theme=meta.main_theme,
                ticker_tags=ticker_tags,
            )
            drafts.append(
                PdfChunkDraft(
                    section_path=section_path,
                    chunk_seq=seq,
                    is_table=is_table,
                    canonical_summary=canonical_summary,
                    content_clean=content_clean,
                    embed_payload=embed_payload,
                    ticker_tags=list(ticker_tags),
                )
            )
            seq += 1

    return drafts


def _split_blocks(markdown: str) -> list[_Block]:
    """markdown을 헤딩/표/산문 문단 블록으로 분해한다(reading order 보존).

    - 헤딩(``#``~``######``): section_path 갱신용. 본문 청크가 되지는 않는다.
    - 표 블록(``|`` 로 시작하는 연속 줄): 통째로 한 블록(원자).
    - 산문: 빈 줄로 구분된 문단. 이미지 마크업/차트 축 노이즈 줄은 제거한다.
    """
    context = _SectionContext()
    blocks: list[_Block] = []
    lines = markdown.splitlines()
    i = 0
    prose_buffer: list[str] = []

    def flush_prose() -> None:
        if not prose_buffer:
            return
        paragraph = "\n".join(prose_buffer).strip()
        prose_buffer.clear()
        if paragraph:
            blocks.append(_Block(kind="prose", text=paragraph, section_path=context.path()))

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        heading = _HEADING_RE.match(line)
        if heading:
            flush_prose()
            level = len(heading.group("hashes"))
            text = heading.group("text").strip()
            context.push(level, text)
            blocks.append(
                _Block(
                    kind="heading",
                    text=text,
                    section_path=context.path(),
                    heading_level=level,
                    heading_text=text,
                )
            )
            i += 1
            continue

        if line.startswith("|"):
            flush_prose()
            table_text, i = _consume_table(lines, i)
            if table_text:
                blocks.append(_Block(kind="table", text=table_text, section_path=context.path()))
            continue

        if not line:
            flush_prose()
            i += 1
            continue

        cleaned = _clean_prose_line(line)
        if cleaned:
            prose_buffer.append(cleaned)
        i += 1

    flush_prose()
    return blocks


def _consume_table(lines: list[str], start: int) -> tuple[str, int]:
    """``start``부터 연속된 표 줄(``|`` 시작)을 모아 본문 텍스트와 다음 인덱스를 반환한다.

    구분선(``|---|``)과 빈 스켈레톤 행(``| | |``)은 건너뛴다. 데이터 행은 숫자가
    살아있도록 원문 그대로 유지한다.
    """
    rows: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        i += 1
        if _TABLE_SEPARATOR_RE.match(line):
            continue
        if _is_empty_table_row(line):
            continue
        rows.append(line)
    return "\n".join(rows), i


def _is_empty_table_row(line: str) -> bool:
    """``| | |``처럼 셀 내용이 전혀 없는 스켈레톤 행이면 True."""
    return set(line) <= {"|", " "}


def _clean_prose_line(line: str) -> str:
    """산문 한 줄에서 이미지 마크업을 제거하고, 차트 축 노이즈 줄은 버린다(빈 문자열 반환).

    의미 있는 본문을 잃지 않도록, 한글/영문 단어가 하나라도 남으면 노이즈로 보지 않는다.
    """
    stripped = _IMAGE_RE.sub("", line).strip()
    if not stripped:
        return ""
    # 단독 축 라벨 토큰(좌축/우축/원 ...)은 한글이어도 노이즈로 본다.
    if stripped in _AXIS_LABEL_TOKENS:
        return ""
    # 그 외에는 한글/영문 단어가 하나라도 있으면 본문으로 보존한다(산문 손실 방지).
    if _HANGUL_OR_WORD_RE.search(stripped):
        return stripped
    if _AXIS_NOISE_RE.match(stripped):
        return ""
    return stripped


def _section_units(
    blocks: list[_Block],
) -> list[tuple[str, str, list[tuple[bool, str]]]]:
    """블록들을 (section_path, heading_text, units) 묶음으로 그룹핑한다.

    units는 (is_table, content) 순서 리스트다. 같은 section_path 안에서 표는 통째
    원자 청크, 산문은 MAX/MIN/overlap 규칙으로 작은 청크들로 쪼갠다. 표는 산문과
    절대 합치지 않는다.
    """
    grouped: list[tuple[str, str, list[tuple[bool, str]]]] = []

    def section_for(path: str, heading: str) -> list[tuple[bool, str]]:
        if grouped and grouped[-1][0] == path:
            return grouped[-1][2]
        units: list[tuple[bool, str]] = []
        grouped.append((path, heading, units))
        return units

    # section_path 별 최신 heading_text 추적(표 캡션 = 가장 가까운 앞 헤딩).
    current_path = ""
    current_heading = ""
    prose_run: list[str] = []
    units_ref: list[tuple[bool, str]] | None = None

    def flush_prose_run() -> None:
        nonlocal prose_run, units_ref
        if prose_run and units_ref is not None:
            for chunk in _chunk_prose(prose_run):
                units_ref.append((False, chunk))
        prose_run = []

    for block in blocks:
        if block.kind == "heading":
            flush_prose_run()
            current_path = block.section_path
            current_heading = block.heading_text
            units_ref = section_for(current_path or _DEFAULT_INTRO_SECTION, current_heading)
            continue

        path = block.section_path or current_path
        if not path:
            path = _DEFAULT_INTRO_SECTION
        if units_ref is None or path != (current_path or _DEFAULT_INTRO_SECTION):
            flush_prose_run()
            current_path = block.section_path
            units_ref = section_for(path, current_heading)

        if block.kind == "table":
            flush_prose_run()
            units_ref.append((True, block.text))
        else:  # prose
            prose_run.append(block.text)

    flush_prose_run()
    return [(path, heading, units) for path, heading, units in grouped if units]


def _chunk_prose(paragraphs: list[str]) -> list[str]:
    """문단 리스트를 작은 청크로 만든다.

    1) MAX_CHARS를 넘는 단일 문단은 OVERLAP_CHARS 겹침으로 hard-split.
    2) 나머지는 MAX_CHARS를 넘지 않게 문단 경계에서 누적.
    3) MIN_CHARS 미만 조각은 인접 청크에 병합.
    """
    expanded: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > MAX_CHARS:
            expanded.extend(_hard_split(para))
        else:
            expanded.append(para)

    accumulated = _accumulate(expanded)
    return _merge_small(accumulated)


def _hard_split(text: str) -> list[str]:
    """긴 텍스트를 MAX_CHARS 윈도우 + OVERLAP_CHARS 겹침으로 분할한다."""
    step = MAX_CHARS - OVERLAP_CHARS
    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + MAX_CHARS, length)
        pieces.append(text[start:end].strip())
        if end >= length:
            break
        start += step
    return [p for p in pieces if p]


def _accumulate(paragraphs: list[str]) -> list[str]:
    """문단을 MAX_CHARS를 넘지 않게 누적해 청크 리스트로 만든다."""
    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if not buffer:
            buffer = para
            continue
        candidate = f"{buffer}\n\n{para}"
        if len(candidate) <= MAX_CHARS:
            buffer = candidate
        else:
            chunks.append(buffer)
            buffer = para
    if buffer:
        chunks.append(buffer)
    return chunks


def _merge_small(chunks: list[str]) -> list[str]:
    """MIN_CHARS 미만 조각을 인접 청크에 병합한다(섹션 내부 한정).

    가능하면 앞 청크 뒤에 붙이고, 첫 청크면 다음 청크 앞에 붙인다. 모든 조각이 작아도
    최소 1개 청크는 남긴다(내용 보존).
    """
    if len(chunks) <= 1:
        return chunks

    merged: list[str] = []
    for chunk in chunks:
        if len(chunk) < MIN_CHARS and merged:
            merged[-1] = f"{merged[-1]}\n\n{chunk}"
        else:
            merged.append(chunk)

    # 첫 청크가 작아 병합 못 한 경우: 다음 청크 앞에 붙인다.
    if len(merged) >= 2 and len(merged[0]) < MIN_CHARS:
        merged[1] = f"{merged[0]}\n\n{merged[1]}"
        merged.pop(0)

    return merged


def _canonical_summary(heading_text: str, content: str, is_table: bool) -> str:
    """NOT NULL canonical_summary 생성.

    - 헤딩이 있으면 헤딩을 기본으로 쓴다. 헤딩이 짧고(표가 아니면) 본문 첫 줄을 덧붙여
      검색 신호를 키운다.
    - 표는 가장 가까운 앞 헤딩(표의 캡션/섹션)을 그대로 쓴다.
    - 헤딩이 없으면(intro/표 캡션 부재) 본문 첫 줄로 대체한다. 절대 비우지 않는다.
    """
    heading = heading_text.strip()
    first_line = _first_sentence(content)

    if is_table:
        return heading or first_line or "표"

    if not heading:
        return first_line or "본문"

    if len(heading) < 40 and first_line and first_line != heading:
        return f"{heading} — {first_line}"
    return heading


def _first_sentence(content: str) -> str:
    """본문의 첫 문장/첫 줄을 ~120자 이내로 뽑는다(canonical_summary 보강용)."""
    for raw in content.splitlines():
        line = raw.strip().lstrip("-•· ").strip()
        if line:
            sentence = re.split(r"(?<=[.!?。])\s", line, maxsplit=1)[0]
            return sentence[:120].strip()
    return ""
