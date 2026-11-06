"""현재 상태 projection을 외부 resource 없이 한 번 표시한다."""

from __future__ import annotations

import re
from datetime import date
from html import escape

from src.pipelines.observation_current import CurrentObservation, build_current_observations
from src.pipelines.strategy_analysis import AnalysisStrategyResult
from src.strategies.models import SignalFinality


CURRENT_STYLE = """
.current-heading { display:flex; align-items:baseline; flex-wrap:wrap; gap:8px 18px; }
.current-heading h3 { margin:0; } .current-as-of,.current-owner { color:#425665; font-size:.9rem; }
.current-state { border-top:1px solid #d6e2e9; padding-top:14px; margin-top:16px; }
.current-state h4 { margin:0 0 4px; font-size:1.08rem; } .current-state p { margin:4px 0; }
.current-measurement { font-variant-numeric:tabular-nums; } .current-up { color:#167044; }
.current-down { color:#bd343d; } .current-flat { color:#425665; }
.current-history { margin:8px 0 0; } .current-history summary { font-size:.9rem; padding:6px 0; }
.current-history li { margin:7px 0; } .current-history time { font-variant-numeric:tabular-nums; }
.current-warnings { background:#fff4e6; color:#813800; padding:10px 14px; margin-top:16px; }
.current-warnings p { margin:5px 0; } .current-more { margin-bottom:0; }
"""


def _measurement_html(value: str) -> str:
    # 거리의 부호가 있는 숫자만 색칠한다. 날짜·기간·기준선 이름은 중립으로 둔다.
    return re.sub(
        r"[+-]\d+(?:\.\d+)?%",
        lambda match: (
            f'<span class="current-{"down" if match[0].startswith("-") else "up" if float(match[0][:-1]) > 0 else "flat"}">{match[0]}</span>'
        ),
        escape(value),
    )


def _state_html(state: CurrentObservation) -> str:
    identity = " · ".join(value for value in state.context if value is not None)
    owner = escape(state.strategy_id + (" · " + identity if identity else ""))
    provisional = " · 잠정" if state.finality is SignalFinality.PROVISIONAL else ""
    history = "".join(
        f'<li data-source="{escape(row.source_id, quote=True)}"><time datetime="{row.day}">{row.day}</time> · {escape(row.text)} · {"잠정" if row.finality is SignalFinality.PROVISIONAL else "확정"}</li>'
        for row in state.history
    )
    measurement = (
        f'<p class="current-measurement">{_measurement_html(state.measurement)}</p>'
        if state.measurement
        else ""
    )
    next_check = f"<p>다음 확인: {escape(state.next_check)}</p>" if state.next_check else ""
    details = (
        f'<details class="current-history"><summary>이 상태가 된 경과 보기</summary><p class="current-owner">{owner}</p><ol>{history}</ol></details>'
        if history
        else ""
    )
    return f'<div class="current-state" data-strategy="{escape(state.strategy_id, quote=True)}"><h4>{escape(state.title)}{provisional}</h4><p class="current-owner">{escape(state.strategy_id)}</p>{measurement}{next_check}{details}</div>'


def render_current_state(
    analysis: AnalysisStrategyResult | None, *, as_of: date | None = None
) -> str:
    """주요 세 상태와 현재 불확실성은 펼치고, 상태별 날짜는 경과에 둔다."""
    if analysis is None:
        stamp = str(as_of) if as_of is not None else "기준일 미평가"
        return f'<section class="section current"><div class="current-heading"><h3>현재 상태</h3><span class="current-as-of">{stamp} · 확정 여부 미평가</span></div><p>현재 상태 미평가 — 분석 결과 없음</p></section>'
    summary = build_current_observations(analysis)
    finality = (
        "PROVISIONAL · 장중 잠정"
        if summary.finality is SignalFinality.PROVISIONAL
        else "FINAL · 확정"
    )
    states = "".join(_state_html(state) for state in summary.states[:3])
    if len(summary.states) > 3:
        states += f'<details class="current-more"><summary>추가 현재 상태 {len(summary.states) - 3}개 보기</summary>{"".join(_state_html(state) for state in summary.states[3:])}</details>'
    warnings = tuple(
        dict.fromkeys(
            (
                *summary.warnings,
                *(warning for state in summary.states for warning in state.warnings),
            )
        )
    )
    warning_html = (
        '<div class="current-warnings">'
        + "".join(f"<p>{escape(warning)}</p>" for warning in warnings)
        + "</div>"
        if warnings
        else ""
    )
    return f'<section class="section current"><div class="current-heading"><h3>현재 상태</h3><span class="current-as-of">{summary.as_of} · {finality}</span></div>{states}{warning_html}</section>'
