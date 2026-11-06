"""check 결과를 재계산 없이 이동 가능한 단일 HTML로 표시한다."""

from __future__ import annotations

import base64
from datetime import datetime
from html import escape

from markdown_it import MarkdownIt

from src.pipelines.check_brief_html import BRIEF_STYLE, render_chart_brief
from src.pipelines.check_current_html import CURRENT_STYLE, render_current_state
from src.pipelines.check_lower_html import LOWER_STYLE, render_lower_sections
from src.pipelines.quick_check import QuickCheckPipeline
from src.tools.disclosure import is_korean_ticker


_STYLE = """
:root { color-scheme: light; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  color:#17252e; background:#edf1f3; font-size:16px; line-height:1.65; }
* { box-sizing:border-box; } body { margin:0; } main { max-width:1440px; margin:auto; padding:32px; }
h1,h2,h3,h4 { line-height:1.35; overflow-wrap:anywhere; } h1 { font-size:2rem; margin:0; }
h2 { font-size:1.6rem; } h3 { font-size:1.2rem; margin:0 0 16px; } h4 { font-size:1rem; }
a { color:#155a80; } p { margin:10px 0; } ul { padding-left:24px; }
li { margin:5px 0; } li p { margin:0; } article { background:#fff; padding:32px; margin:28px 0; }
header.stock { border-bottom:2px solid #dfe6ea; padding-bottom:18px; margin-bottom:24px; }
header.stock h2 { margin:0; } .price { font-size:1.8rem; font-weight:600; margin:6px 0; }
.meta { color:#425665; } .section { margin:28px 0; overflow-wrap:anywhere; }
.current { background:#f2f7fa; padding:20px; border-left:4px solid #326481; }
.warning,.failure { color:#813800; background:#fff4e6; padding:16px; overflow-wrap:anywhere; }
.table-scroll,.chart-scroll { overflow-x:auto; max-width:100%; } table { border-collapse:collapse;
  width:100%; font-size:.94rem; font-variant-numeric:tabular-nums; } th,td { padding:10px 12px;
  border-bottom:1px solid #dfe6ea; vertical-align:top; min-width:100px; } th { text-align:left;
  color:#344b5b; background:#f4f7f9; } table p { margin:0; }
nav { display:flex; flex-wrap:wrap; gap:10px 22px; margin:20px 0; }
details { margin:20px 0; } summary { cursor:pointer; padding:12px 0; color:#164f73;
  font-weight:600; } summary:focus-visible { outline:2px solid #155a80; outline-offset:3px; }
.chart img { display:block; width:100%; height:auto; margin-top:12px; background:#1a1a1a; }
.chart input { margin:8px; } .chart input:checked ~ .chart-scroll img { width:1600px;
  max-width:none; } .quality-chart { width:100%; max-width:560px; height:auto; display:block; }
.quality-chart text { font-size:14px; fill:#344b5b; } .quality-chart .quality-point { fill:#24628c; }
.quality-chart .provisional { fill:#fff; stroke:#995b13; stroke-width:2; }
.quality-chart polyline { fill:none; stroke:#24628c; stroke-width:2; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; } footer { color:#425665; margin-top:32px; }
@media(max-width:700px) { main { padding:16px; } article { padding:18px; margin:20px 0; }
  h1 { font-size:1.6rem; } .price { font-size:1.5rem; } th,td { padding:8px; }
  .current { padding:14px; } }
@media print { :root { background:#fff; } main,article { padding:12px; }
  .chart input { display:none; } .chart .chart-scroll img { width:100% !important; } }
"""


def _markdown(text: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    # html=False만으로 Markdown의 외부 이미지·링크가 차단되지는 않는다.
    parser.add_render_rule(
        "image", lambda self, tokens, idx, options, env: escape(tokens[idx].content)
    )
    parser.add_render_rule("link_open", lambda *args: "")
    parser.add_render_rule("link_close", lambda *args: "")
    parser.add_render_rule("table_open", lambda *args: '<div class="table-scroll"><table>\n')
    parser.add_render_rule("table_close", lambda *args: "</table></div>\n")
    return parser.render(text)


def _sections(document: str) -> list[tuple[str, str]]:
    sections = []
    title = ""
    lines = []
    for line in document.splitlines():
        if line.startswith("## ") and not sections and not lines:
            continue  # 종목 제목은 HTML header에서 escape해 표시한다.
        if line.startswith("### "):
            sections.append((title, "\n".join(lines)))
            title, lines = line[4:], [line]
        else:
            lines.append(line)
    sections.append((title, "\n".join(lines)))
    return sections


def _stock_report(result: dict, index: int, detailed_history: bool, detailed_strategy: bool) -> str:
    ticker = escape(str(result.get("ticker", "UNKNOWN")))
    if not result.get("success", False):
        error = escape(str(result.get("error", "Unknown error")))
        return f'<article id="stock-{index}"><h2>{ticker}</h2><p class="failure">분석 실패: {error}</p></article>'
    formatter = QuickCheckPipeline(technical_tool=None)
    # 숫자 가격 필드만 KRW로 포맷한다. 외부 근거·경고의 USD 원문은 보존한다.
    price_formatter = (
        (lambda value: f"₩{value:,.0f}")
        if is_korean_ticker(str(result.get("ticker", "")))
        else None
    )
    document = formatter.format_output(result, price_formatter=price_formatter)
    sections = _sections(document)
    # 표시 순서만 바꾼다. 계산·전략·수량·관찰의 설명은 기존 formatter가 책임진다.
    order = {
        "": 0,
        "현재 유효 상태": 1,
        "전략별 대응": 2,
        "주요 가격대": 3,
        "관찰 흐름": 4,
        "최근 5거래일": 5,
        "차트 상태 점수(Quality)": 6,
    }
    sections.sort(key=lambda section: order.get(section[0], 7))
    projected_sections = []
    for title, text in sections:
        if title == "현재 유효 상태":
            continue
        if title == "현재 상태":
            # 미평가 fallback의 현재 결론도 새 패널 한 곳에 둔다. 가격·지표는 남긴다.
            parts = text.split("\n\n", 2)
            text = parts[2] if len(parts) > 2 else ""
            title = "기존 기술 참고"
        elif title == "" and text.lstrip().startswith("**분석 기준:"):
            text = "일봉 분석 · 시간외 시세 미포함"
        if text.strip():
            projected_sections.append((title, text))
    sections = projected_sections
    price = result.get("price")
    price_text = (
        "미평가"
        if price is None
        else (
            f"₩{price:,.0f}"
            if is_korean_ticker(str(result.get("ticker", "")))
            else f"${price:,.2f}"
        )
    )
    change = result.get("change_pct")
    change_text = "" if change is None else f" ({change:+.2f}%)"
    price_direction = (
        "up"
        if change is not None and change > 0
        else "down"
        if change is not None and change < 0
        else "flat"
    )
    chunks = [
        f'<article id="stock-{index}"><header class="stock"><h2>{ticker}</h2>',
        f'<p class="price jb-{price_direction}">{price_text}{change_text}</p></header>',
    ]
    chunks.append(
        render_current_state(
            result.get("strategy_analysis"), as_of=getattr(result.get("scorecard"), "as_of", None)
        )
    )
    chart_inserted = False
    for position, (title, text) in enumerate(sections):
        if not chart_inserted and (title == "전략별 대응" or order.get(title, 7) >= 3):
            if result.get("chart_brief_warning"):
                chunks.append(
                    f'<p class="warning">{escape(str(result["chart_brief_warning"]))}</p>'
                )
            elif "chart_brief" in result:
                chunks.append(
                    render_chart_brief(result["chart_brief"], ticker=str(result.get("ticker", "")))
                )
            png = result.get("chart_png")
            if png:
                uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
                alt = f"{ticker} 기술 차트 · 최근 최대 200봉"
                chunks.append(
                    f'<div class="chart"><input type="checkbox" id="chart-zoom-{index}">'
                    f'<label for="chart-zoom-{index}">기술 차트 확대 / 축소 · 최근 최대 200봉</label>'
                    f'<div class="chart-scroll"><img src="{uri}" alt="{alt}"></div></div>'
                )
            else:
                warning = escape(str(result.get("chart_warning") or "차트 데이터 이용 불가"))
                chunks.append(f'<p class="warning">{warning}</p>')
            chart_inserted = True
            chunks.append(render_lower_sections(result, sections[position:], _markdown))
            break
        kind = "section"
        if title == "평가 범위 / 상세":
            # 미평가와 경고는 접지 않고 현재 화면에 남긴다.
            kind += " scope"
        chunks.append(f'<section class="{kind}">')
        chunks.append(_markdown(text))
        chunks.append("</section>")
    detail = formatter.format_output(
        result,
        detailed_history=detailed_history,
        detailed_strategy=True,
        price_formatter=price_formatter,
    )
    opened = " open" if detailed_history or detailed_strategy else ""
    chunks.append(
        f"<details{opened}><summary>상세 근거 · 전체 관찰·전략</summary>{_markdown(detail)}</details>"
    )
    chunks.append("</article>")
    return "\n".join(chunks)


def render_check_html(
    results: list[dict],
    *,
    detailed_history: bool = False,
    detailed_strategy: bool = False,
    generated_at: datetime | None = None,
) -> str:
    """같은 check 결과를 외부 resource·script 없는 UTF-8 문서로 렌더한다."""
    stamp = escape((generated_at or datetime.now().astimezone()).isoformat(timespec="seconds"))
    navigation = "".join(
        f'<a href="#stock-{i}">{escape(str(r.get("ticker", "UNKNOWN")))}'
        + (" · 실패" if not r.get("success", False) else "")
        + "</a>"
        for i, r in enumerate(results)
    )
    reports = "\n".join(
        _stock_report(result, i, detailed_history, detailed_strategy)
        for i, result in enumerate(results)
    )
    return (
        '<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>Quick Check 투자 분석</title>"
        f"<style>{_STYLE}{BRIEF_STYLE}{CURRENT_STYLE}{LOWER_STYLE}</style></head><body><main><h1>Quick Check</h1>"
        f'<p class="meta">생성 시각 {stamp} · 분석 기준일은 종목별 표시</p>'
        f'<nav aria-label="종목 바로가기">{navigation}</nav>{reports}'
        "<footer>각 전략은 같은 입력에 대한 독립 대안입니다. 수량을 합산하지 않습니다. "
        "생성 이후 시세를 자동 갱신하지 않습니다.</footer></main></body></html>\n"
    )
