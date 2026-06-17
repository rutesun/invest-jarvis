"""PDF 메타데이터 추출 + hybrid 라우팅 (T14).

``ParsedDocument`` 한 건(로컬 파싱 결과)에서 문서 메타데이터를 규칙 기반으로 뽑고,
그 문서가 무거운 hybrid 재파싱이 필요한지(``needs_hybrid``)를 결정한다. 이 모듈은
**로컬 전용** 판단이라 런타임에 Java/torch가 필요 없다.

라우팅 핵심 (2026-06-04 스파이크 결정):
- 파일명에 보고서 종류 정보가 없으므로 사전 분류하지 않는다. local로 전부 파싱한 뒤
  **증상 보이는 문서만 hybrid로 승격**한다(needs_ocr와 동일한 local-first 패턴).
- 표 융합 트리거: 로컬 표의 한 셀에 재무 line-item 라벨이 2개 이상 뭉쳐 있으면
  (예: 셀=``"매출액 영업이익 순이익"``) 그 문서엔 융합된 요약표가 있다는 증거 →
  hybrid. 문자열 검사라 비용 ~0. 매크로/전략 리포트는 융합 표가 없어 자동으로
  local-only로 남는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from src.pipelines.stock_report.pdf_parser import ParsedDocument


# 재무제표 line-item 라벨 (tunable). 융합 표(요약 실적추정/목표주가)에서 한 셀에
# 2개 이상 동시 등장하면 그 표가 깨졌다는 신호다. 라벨은 substring 포함관계가
# 있으므로(예: "순이익"⊂"순이익률", "매출액"⊃"매출") 길이 내림차순으로 매칭하고
# 매칭된 구간을 소거해 짧은 라벨이 긴 라벨 안에서 다시 잡히지 않게 한다.
#
# 주의: 단독 "매출"은 의도적으로 제외한다. 예측 컬럼 헤더(예: "26F 매출")나 본문
# 산문에 흔히 나와 false-positive를 만든다. 실제 income-statement line item은
# "매출액"이다.
FINANCIAL_LABELS: frozenset[str] = frozenset(
    {
        "매출액",
        "영업이익",
        "영업손익",
        "영업이익률",
        "순이익",
        "순이익률",
        "지배주주순이익",
        "당기순이익",
        "EBITDA",
        "EPS",
        "BPS",
        "ROE",
    }
)

# 길이 내림차순(긴 라벨 우선) — subsumption-aware 카운트에 사용.
_LABELS_LONGEST_FIRST: tuple[str, ...] = tuple(sorted(FINANCIAL_LABELS, key=len, reverse=True))

# 최소 실제 본문 글자 수. 미만이면 텍스트 레이어가 없는 스캔/이미지 문서로 본다.
_MIN_REAL_TEXT_CHARS = 200
# 이미지가 과다하고(rasterized) 본문이 적으면 스캔 문서로 본다.
_IMAGE_HEAVY_REF_COUNT = 100
_IMAGE_HEAVY_TEXT_CHARS = 500

# 경로의 날짜 폴더(data/files/2026-06-02/...)에서 발행일을 뽑는다.
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# 한국 종목: "종목명 (123456)" -> 6자리 코드.
_KR_TICKER_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<code>\d{6})\)\s*$")
# 해외 종목: "회사명 (HPE.US)" / "(VWS.DC)" / "(300308.CH)" -> TICKER.EX.
# 티커는 영문/숫자로 시작할 수 있다(중국 코드 300308.CH 등 숫자 시작 포함). 거래소
# 접미사(.US/.CH ...)가 반드시 있어야 한국 6자리 코드(_KR_TICKER_RE 담당)와 구분된다.
_FOREIGN_TICKER_RE = re.compile(
    r"^(?P<name>.+?)\s*\((?P<code>[A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,4})\)\s*$"
)

_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<text>.+?)\s*$")


@dataclass(slots=True)
class DocumentMeta:
    broker_key: str
    broker_name: str
    title: str | None
    published_date: date | None
    target_ticker: str | None
    category_key: str | None
    main_theme: str | None
    parse_status: str  # ok | needs_ocr | failed
    needs_hybrid: bool


def load_sources(path: str | Path) -> dict:
    """``stock_report_pdf_sources.yaml``의 ``sources`` 맵을 로드한다."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF sources 파일을 찾을 수 없습니다: {file_path}")
    payload = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    sources = payload.get("sources")
    return sources if isinstance(sources, dict) else {}


def extract_metadata(parsed: ParsedDocument, source_path: str, sources: dict) -> DocumentMeta:
    """로컬 파싱 결과에서 메타데이터를 추출하고 hybrid 필요 여부를 판정한다."""
    broker_key, broker_name = _resolve_broker(Path(source_path).name, sources)
    published_date = _extract_published_date(source_path)
    title, target_ticker = _extract_title_and_ticker(parsed.markdown)
    parse_status = _parse_status(parsed)
    needs_hybrid = parse_status == "ok" and _has_fused_table(parsed)

    return DocumentMeta(
        broker_key=broker_key,
        broker_name=broker_name,
        title=title,
        published_date=published_date,
        target_ticker=target_ticker,
        category_key=None,
        main_theme=None,
        parse_status=parse_status,
        needs_hybrid=needs_hybrid,
    )


def _resolve_broker(filename: str, sources: dict) -> tuple[str, str]:
    """파일명을 source key와 startswith 매칭(가장 긴 key 우선)한다.

    매칭 실패 시 첫 토큰(첫 '_' 앞)을 broker_key/broker_name으로 그대로 쓴다.
    """
    matched_key: str | None = None
    for key in sources:
        if filename.startswith(key) and (matched_key is None or len(key) > len(matched_key)):
            matched_key = key

    if matched_key is not None:
        entry = sources[matched_key]
        name = entry.get("name") if isinstance(entry, dict) else None
        return matched_key, (name or matched_key)

    prefix = filename.split("_", 1)[0]
    return prefix, prefix


def _extract_published_date(source_path: str) -> date | None:
    match = _DATE_RE.search(source_path)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _extract_title_and_ticker(markdown: str) -> tuple[str | None, str | None]:
    """첫 1-2개 헤딩/본문 줄에서 제목과 티커를 뽑는다.

    한국: ``종목명 (123456)`` -> ticker=6자리 코드, title=종목명.
    해외: ``회사명 (HPE.US)`` -> ticker=HPE.US, title=회사명.
    매칭 실패(매크로/전략 리포트 등) -> (첫 의미 있는 헤딩 또는 None, None).
    """
    candidates = _heading_or_lead_lines(markdown)
    for line in candidates:
        kr = _KR_TICKER_RE.match(line)
        if kr:
            return kr.group("name").strip(), kr.group("code")
        foreign = _FOREIGN_TICKER_RE.match(line)
        if foreign:
            return foreign.group("name").strip(), foreign.group("code")

    return (candidates[0] if candidates else None), None


def _heading_or_lead_lines(markdown: str, limit: int = 4) -> list[str]:
    """헤딩 텍스트(우선)와 그 외 첫 본문 줄을 합쳐 앞쪽 후보 줄을 반환한다."""
    headings: list[str] = []
    leads: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or _is_image_line(line):
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            headings.append(heading.group("text").strip())
        else:
            leads.append(line)
        if len(headings) + len(leads) >= limit * 2:
            break
    return (headings + leads)[:limit]


def _is_image_line(line: str) -> bool:
    return line.startswith("![")


def _parse_status(parsed: ParsedDocument) -> str:
    """parse_status: failed | needs_ocr | ok.

    - failed: markdown이 빈 경우. 치명 실패(0바이트/비PDF/변환 실패/산출물 누락)는
      모두 빈 markdown으로 귀결된다. 비치명 경고(json 읽기 실패 등)는 markdown이
      있으면 failed로 보지 않는다.
    - needs_ocr: 실제 본문 글자 < 임계, 또는 이미지 과다 + 본문 적음(스캔 문서).
    - ok: 그 외.
    """
    if not parsed.markdown.strip():
        return "failed"
    if parsed.text_char_count < _MIN_REAL_TEXT_CHARS:
        return "needs_ocr"
    if parsed.image_ref_count >= _IMAGE_HEAVY_REF_COUNT and (
        parsed.text_char_count < _IMAGE_HEAVY_TEXT_CHARS
    ):
        return "needs_ocr"
    return "ok"


def _has_fused_table(parsed: ParsedDocument) -> bool:
    """로컬 표 셀 중 재무 라벨이 2개 이상 뭉친 셀이 하나라도 있으면 True.

    JSON 표(``type=="table"``)가 있으면 그 셀을, 없으면 markdown 파이프 표 행을 본다.
    """
    cell_texts = _json_table_cell_texts(parsed.json_blocks)
    if cell_texts is None:
        cell_texts = _markdown_table_cell_texts(parsed.markdown)

    return any(_distinct_label_count(text) >= 2 for text in cell_texts)


def _json_table_cell_texts(json_blocks: list | None) -> list[str] | None:
    """json_blocks의 모든 표 셀 텍스트를 모은다. 표 블록이 전혀 없으면 None."""
    if not json_blocks:
        return None

    cell_texts: list[str] = []
    saw_table = False
    for block in json_blocks:
        if not isinstance(block, dict) or block.get("type") != "table":
            continue
        saw_table = True
        for row in block.get("rows") or []:
            if not isinstance(row, dict):
                continue
            for cell in row.get("cells") or []:
                if isinstance(cell, dict):
                    cell_texts.append(_cell_text(cell))

    return cell_texts if saw_table else None


def _cell_text(cell: dict) -> str:
    parts = [
        kid.get("content", "")
        for kid in cell.get("kids") or []
        if isinstance(kid, dict) and isinstance(kid.get("content"), str)
    ]
    return " ".join(parts)


def _markdown_table_cell_texts(markdown: str) -> list[str]:
    """markdown 파이프 표 행(``| a | b |``)을 셀 단위로 분해한다.

    구분선(``|---|---|``)과 빈 스켈레톤 행은 건너뛴다.
    """
    cell_texts: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        if "---" in line or set(line) <= {"|", " "}:
            continue
        for cell in line.strip("|").split("|"):
            cell_texts.append(cell.strip())
    return cell_texts


def _distinct_label_count(text: str) -> int:
    """텍스트에 등장하는 서로 다른 재무 라벨 수(subsumption-aware).

    긴 라벨부터 매칭하고 매칭 구간을 공백으로 소거한다. 그래서 ``순이익률``은
    ``순이익``으로 다시 세지 않고, ``매출액``도 (단독 ``매출`` 라벨이 없으므로)
    한 번만 센다.
    """
    if not text:
        return 0
    found = 0
    remaining = text
    for label in _LABELS_LONGEST_FIRST:
        if label in remaining:
            found += 1
            remaining = remaining.replace(label, " ")
    return found
