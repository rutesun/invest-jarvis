"""차트 브리핑 표시 전용 markup. 수치의 계산·분류는 tools가 책임진다."""

from __future__ import annotations

from html import escape

from src.tools.disclosure import is_korean_ticker


BRIEF_STYLE = """
.jb-up { color:#167044; } .jb-down { color:#bd343d; } .jb-cool { color:#226b9d; }
.jb-hot { color:#b34b19; } .jb-flat,.jb-unavailable { color:#425665; }
.chart-brief { margin:28px 0 20px; padding-top:8px; }
.jb-hero h3 { font-size:clamp(1.3rem,3vw,1.8rem); margin:8px 0 18px; }
.jb-label,.jb-support,.jb-scale { font-size:.82rem; color:#425665; }
.jb-signals { display:grid; grid-template-columns:repeat(5,minmax(0,1fr));
  border-block:1px solid #dfe6ea; }
.jb-signal { min-width:0; padding:16px 12px; overflow-wrap:anywhere; }
.jb-signal:first-child { padding-left:0; } .jb-signal + .jb-signal { border-left:1px solid #dfe6ea; }
.jb-value { font-size:1.05rem; font-weight:600; margin-top:7px; }
.jb-support { margin-top:8px; } .jb-scale { display:flex; justify-content:space-between; gap:8px; }
.jb-crsi-band { position:relative; display:flex; height:7px; margin:18px 0 12px; }
.jb-zone-low { background:#c5dce9; } .jb-zone-middle { background:#dfe6ea; }
.jb-zone-high { background:#f3d8c9; } .jb-crsi-marker { position:absolute; top:-4px;
  width:3px; height:15px; transform:translateX(-50%); background:currentColor; }
.jb-balance { display:flex; height:7px; margin:14px 0 8px; background:#edf1f3; }
.jb-balance .jb-up { background:#167044; } .jb-balance .jb-down { background:#bd343d; }
.jb-ma-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:10px 0 18px; }
.jb-ma { padding:12px; background:#f2f7fa; border-radius:6px; font-size:.9rem; }
.jb-ma .jb-label { display:flex; flex-wrap:wrap; justify-content:space-between; gap:4px; }
.jb-ma p { margin:5px 0 0; font-variant-numeric:tabular-nums; }
.jb-events { border-top:1px solid #dfe6ea; padding-top:12px; }
.jb-event { display:flex; flex-wrap:wrap; gap:6px 12px; font-size:.9rem; margin-top:8px; }
.jb-date,.jb-tag { color:#425665; font-size:.8rem; } .jb-tag { background:#f2f7fa; padding:1px 5px; }
.jb-evidence { font-size:.85rem; } .jb-evidence summary { font-weight:400; }
@media(max-width:850px) { .jb-signals { grid-template-columns:repeat(2,minmax(0,1fr)); }
 .jb-signal:nth-child(odd) { border-left:0; padding-left:0; }
 .jb-signal:nth-child(n+3) { border-top:1px solid #dfe6ea; }
 .jb-signal:last-child { grid-column:1/-1; } .jb-ma-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
"""

_LABELS = {
    "up": "↗ 상승",
    "down": "↘ 하락",
    "flat": "→ 보합",
    "mixed": "혼조",
    "unavailable": "미산출",
}


def _span(text, direction=None):
    css = direction if direction in {"up", "down", "flat", "unavailable", "cool", "hot"} else "flat"
    return f'<span class="jb-{css}">{escape(str(text))}</span>'


def _signed(value):
    if value is None:
        return "미산출"
    return _span(f"{value:+.2f}%", "up" if value > 0 else "down" if value < 0 else "flat")


def _topic(label, value, support=""):
    return f'<section class="jb-signal"><div class="jb-label">{label}</div><div class="jb-value">{value}</div><div class="jb-support">{support}</div></section>'


def render_chart_brief(brief: dict | None, *, ticker: str) -> str:
    """외부 resource 없이 escape·통화·방향 색상을 적용한다."""
    if not brief:
        return '<p class="warning">차트 브리핑 미산출: 표시 재료 없음</p>'
    day = escape(str(brief.get("as_of") or "미상"))
    state = escape(str(brief.get("finality") or "UNKNOWN"))
    stamp = f'<p class="meta">차트 기준일 {day} · {state}</p>'
    if brief.get("reason"):
        return (
            '<section class="chart-brief">'
            + stamp
            + f'<p class="warning">차트 브리핑 미산출: {escape(str(brief["reason"]))}</p></section>'
        )

    def price(value):
        if value is None:
            return "미산출"
        return f"₩{value:,.0f}" if is_korean_ticker(ticker) else f"${value:,.2f}"

    trends = brief["trends"]
    trend = "<br>".join(
        f"{name} {_span(_LABELS.get(trends[key], '미산출'), trends[key])}"
        for key, name in (("short", "단기"), ("long", "장기"))
    )
    averages = {ma["period"]: ma for ma in brief["moving_averages"]}
    positions = []
    for period in (50, 150):
        distance = averages[period]["distance_pct"]
        relation = (
            "미산출"
            if distance is None
            else "위"
            if distance > 0
            else "아래"
            if distance < 0
            else "일치"
        )
        positions.append(f"{period}일선 {relation} {_signed(distance)}")
    structures = []
    structure_details = []
    for key, label in (("high", "고점"), ("low", "저점")):
        item = brief["structure"].get(key)
        if item is None:
            structures.append(f"{label} 변화 미산출")
        else:
            structures.append(f"{label} {_span(_LABELS[item['direction']], item['direction'])}")
            structure_details.append(
                f'{label} {escape(price(item["previous"]))} → {_span(price(item["value"]), item["direction"])}<br><span class="jb-date">pivot {escape(item["pivot_on"])} · 확인 {escape(item["confirmed_on"])} · {escape(item["finality"])}</span>'
            )
    crsi = brief["crsi"]
    crsi_state = crsi["state"]
    state_label = {
        "oversold": "과매도권",
        "overbought": "과매수권",
        "neutral": "중립",
        "unavailable": "미산출",
    }[crsi_state]
    color = {"oversold": "cool", "overbought": "hot"}.get(crsi_state)
    crsi_support = (
        escape(crsi["reason"])
        if crsi["reason"]
        else (
            f"cRSI {_span(f'{crsi["value"]:.1f}', color)} · 하단 {crsi['low']:.1f} / 상단 {crsi['high']:.1f}"
            f'<div class="jb-crsi-band" role="img" aria-label="cRSI {crsi["value"]:.1f}, 하단 {crsi["low"]:.1f}, 상단 {crsi["high"]:.1f}">'
            f'<span class="jb-zone-low" style="width:{crsi["low"]:g}%"></span>'
            f'<span class="jb-zone-middle" style="width:calc({crsi["high"]:g}% - {crsi["low"]:g}%)"></span>'
            f'<span class="jb-zone-high" style="width:calc(100% - {crsi["high"]:g}%)"></span>'
            f'<span class="jb-crsi-marker jb-{color or "flat"}" style="left:{crsi["value"]:g}%"></span></div>'
            '<div class="jb-scale"><span>0 · 과매도</span><span>과매수 · 100</span></div>'
        )
    )
    volume = brief["volume"]
    if volume["reason"]:
        volume_value, volume_support = "미산출", escape(volume["reason"])
    else:
        up, down = volume["up_pct"], volume["down_pct"]
        volume_value = (
            f"상승일 {_span(f'{up:.1f}%', 'up')}<br>하락일 {_span(f'{down:.1f}%', 'down')}"
        )
        volume_support = (
            f'<div class="jb-balance" role="img" aria-label="상승일 거래량 {up:.1f}%, 하락일 {down:.1f}%">'
            f'<span class="jb-up" style="width:{up:.4f}%"></span><span class="jb-down" style="width:{down:.4f}%"></span></div>'
            f"최근 20개 응답 봉 · 보합 {volume['flat_days']}일 제외"
        )
    array_sign = {"above": "&gt;", "below": "&lt;", "equal": "=", "unavailable": "비교 미산출"}[
        brief["arrays"]["50_200"]
    ]
    trend_support = f"단기 20·50일 / 장기 150·200일<br>현재 배열: 50일선 {array_sign} 200일선"
    topics = (
        _topic("추세", trend, trend_support)
        + _topic("가격 위치", positions[0], positions[1])
        + _topic(
            "가격 구조",
            "<br>".join(structures),
            "<br>".join(
                structure_details
                + [escape(brief["structure"].get("reason") or "우측 3봉으로 확인한 FINAL pivot")]
            ),
        )
        + _topic("과열·과매도", _span(state_label, color), crsi_support)
        + _topic("거래량", volume_value, volume_support)
    )
    cards = []
    for period, ma in averages.items():
        slope = ma["slope_pct"]
        slope_text = (
            "기울기 미산출"
            if slope is None
            else f"21봉 변화 {_span(f'{slope:+.2f}%', ma['direction'])}"
        )
        if ma.get("reason"):
            slope_text = escape(str(ma["reason"]))
        cards.append(
            f'<div class="jb-ma"><div class="jb-label"><span>{period}일선</span>{_span(_LABELS[ma["direction"]], ma["direction"])}</div><p>{_span(price(ma["value"]), ma["direction"])}</p><p>주가 이격 {_signed(ma["distance_pct"])}</p><div class="jb-support">{slope_text}</div></div>'
        )
    arrays = []
    for key, fast, slow in (("20_50", 20, 50), ("50_200", 50, 200)):
        relation = brief["arrays"][key]
        sign = {"above": "&gt;", "below": "&lt;", "equal": "=", "unavailable": "비교 미산출"}[
            relation
        ]
        arrays.append(
            f"{fast}일선 {_span(price(averages[fast]['value']), averages[fast]['direction'])} {sign} {slow}일선 {_span(price(averages[slow]['value']), averages[slow]['direction'])}"
        )
    events = (
        "".join(
            f'<div class="jb-event"><span class="jb-date">{escape(str(event["date"]))}</span>{_span(event["label"], event.get("direction"))}<span class="jb-tag">{escape(str(event["finality"]))}</span></div>'
            for event in brief["events"]
        )
        or '<p class="jb-support">최근 20개 응답 봉 내 확인 가능한 교차·밴드 변화 없음</p>'
    )
    return (
        '<section class="chart-brief" aria-label="차트 상단 브리핑">'
        + stamp
        + f'<div class="jb-hero"><div class="jb-label">현재 차트 상태</div><h3>{escape(str(brief["headline"]))}</h3></div>'
        + f'<div class="jb-signals">{topics}</div><p class="jb-label">이동평균의 방향과 현재 주가 위치</p><div class="jb-ma-grid">{"".join(cards)}</div>'
        + f'<div class="jb-events"><div class="jb-label">최근 핵심 변화</div>{events}</div>'
        + '<details class="jb-evidence"><summary>판정 기준과 현재 배열 보기</summary><ul>'
        + f"<li>현재 배열: {' · '.join(arrays)}. 현재 배열과 최근 교차 발생은 별도로 표시합니다.</li>"
        + "<li>이동평균 방향: 기존 snapshot의 21봉 변화율이 +0.5% 초과 상승, −0.5% 미만 하락, 그 사이는 보합입니다.</li>"
        + "<li>cRSI는 기존 가변 상하단 밴드를 사용합니다. 과매도 상태 자체는 매수 지시가 아닙니다.</li>"
        + "<li>거래량 비중은 전일 종가 대비 상승일·하락일 거래량 합을 분모로 계산하며 보합 제외입니다. 실제 매수·매도 주문량을 뜻하지 않습니다.</li>"
        + "<li>최근 사건은 각 발생일과 비교한 인접 두 봉의 FINAL / PROVISIONAL / UNKNOWN을 함께 확인합니다.</li></ul></details></section>"
    )
