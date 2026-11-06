"""Bounded common chart facts, experimental Quality, then consumer decisions."""

from collections.abc import Mapping
from datetime import date, timedelta

from src.pipelines.chart_analysis import ChartAnalysisResult, selected_fact_rows
from src.tools.technical.chart_analysis.models import ChartAnalysis, FactRef, FactSelection


_REASON_COPY = {
    "PROVISIONAL_PREVIEW": "preview: 미완성 봉의 잠정 계산이며 FINAL 확정값이 아닙니다",
    "POLICY_HISTORY_SHORT": "공개에 필요한 연속 FINAL 252봉이 부족합니다",
    "HISTORY_SHORT": "계산에 필요한 220봉이 부족합니다",
    "INCOMPLETE_PREFIX": "입력 기간의 누락 또는 FINAL 확인 부족",
    "INPUT_MISSING": "필수 입력값 또는 지표가 없습니다",
    "ONE_SIDED_SAMPLE": "한 방향 표본: 상승/하락 한쪽 거래량만 있어 Participation이 100/0입니다",
    "CONCENTRATED_VOLUME": "거래량 집중: 방향 거래량 중 하루 비중이 50% 이상입니다",
    "LOW_DIRECTIONAL_SAMPLE": "V>0인 방향 표본이 5개 미만입니다",
    "ZERO_DIRECTIONAL_VOLUME": "보합 제외 방향 거래량의 합이 0입니다",
}


def _value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _evidence_summary(evidence: Mapping) -> str:
    """Current scalar diagnostics only; retained internal arrays are never dumped."""
    parts = []
    for key, value in evidence.items():
        if isinstance(value, (str, int, float, bool, date)) or value is None:
            parts.append(f"{key}={_value(value)}")
        elif isinstance(value, Mapping):
            for nested, scalar in value.items():
                if isinstance(scalar, (str, int, float, bool, date)) or scalar is None:
                    parts.append(f"{key}.{nested}={_value(scalar)}")
        if len(parts) >= 8:
            break
    return ", ".join(parts[:8]) or "계산 근거 보존됨 (내부 시계열 생략)"


def _current_items(analysis: ChartAnalysis):
    finality = analysis.manifest.finality
    sessions = sorted(finality) if isinstance(finality, Mapping) else ()
    cutoff = sessions[-20] if len(sessions) >= 20 else analysis.manifest.as_of - timedelta(days=30)
    return tuple(
        sorted(
            (
                item
                for item in analysis.items
                if item.kind != "EVENT" or (item.confirmed_on or item.occurred_on) >= cutoff
            ),
            key=lambda item: (item.confirmed_on or item.occurred_on, item.rule_id, item.id),
            reverse=True,
        )
    )


def _is_current_fact(item, as_of: date) -> bool:
    """Display validity only; lifecycle EVENTs differ from one-shot EVENTs."""
    if any(
        day is not None and day > as_of
        for day in (item.occurred_on, item.confirmed_on, item.status_as_of)
    ):
        return False
    if item.state in {"UNAVAILABLE", "NOT_SELECTED", "INCOMPLETE_PREFIX"}:
        return item.status_as_of == as_of
    if item.kind == "EVENT" and not item.rule_id.startswith("analysis."):
        return (item.confirmed_on or item.occurred_on) == as_of
    if item.status_as_of != as_of:
        return False
    if item.kind == "EVENT":
        return item.state == "ACTIVE"
    if item.kind == "EPISODE":
        return item.state in {"ACTIVE", "BREACHED"}
    if item.kind == "RISK":
        return item.state == "DETECTED"
    return item.kind == "STATE"


def _fact_lines(analyses, selections, *, own=(), detail=True, as_of=None):
    """Resolve only explicit refs plus the strict result's bounded current facts."""
    valid, missing = [], []
    for selection in selections:
        analysis = analyses.get(selection.ref.analysis_id)
        if analysis is not None and any(i.id == selection.ref.item_id for i in analysis.items):
            valid.append(selection)
        else:
            missing.append(selection)
    rows = selected_fact_rows(analyses, (*own, *valid))
    lines = []
    if not detail:
        if as_of is None:
            as_of = max((analysis.manifest.as_of for analysis in analyses.values()), default=None)
        rows = tuple(
            row
            for row in rows
            if any(analyses[ref.analysis_id].manifest.as_of == as_of for ref in row.refs)
            and _is_current_fact(row.item, as_of)
        )
        grouped = {}
        for row in rows:
            item = row.item
            key = (item.kind, item.rule_id, item.state, item.finality)
            previous = grouped.get(key)
            if previous is None or (item.confirmed_on or item.occurred_on) > (
                previous.item.confirmed_on or previous.item.occurred_on
            ):
                grouped[key] = row
        omitted = len(rows) - len(grouped)
        rows = tuple(grouped.values())
        if omitted:
            lines.append(f"- 동일 규칙·상태 {omitted}건의 상세 근거: --detail-strategy")
    for row in rows:
        item = row.item
        confirmation = "확정 확인일" if item.finality == "FINAL" else "가용일"
        preview = " preview (미완성 봉)" if item.finality == "PROVISIONAL" else ""
        lines.append(
            f"- {item.kind} {item.rule_id}: {item.state} [{item.finality}]{preview}"
            f"; 발생일={item.occurred_on}, {confirmation}={item.confirmed_on or '없음'}, 평가일={item.status_as_of}"
        )
        lines.append(f"  - {_evidence_summary(item.evidence)}")
        if detail:
            lines.extend(f"  - FactRef={ref.analysis_id}/{ref.item_id}" for ref in row.refs)
    if not rows:
        lines.append("- 관측 결과 없음")
    if detail:
        for selection in missing:
            lines.append(f"- 근거 참조 불가: {selection.ref.analysis_id}/{selection.ref.item_id}")
    elif missing:
        lines.append(f"- 근거 참조 불가: {len(missing)}건 (--detail-strategy)")
    return lines


def _selection_lines(selections, *, standalone=True):
    lines = ["", "### 전략 선택 근거"]
    if not selections:
        lines.append(
            "- 공통 분석 단독 조회; 전략 매매판정 없음" if standalone else "- 선택 근거 없음"
        )
    for selection in selections:
        state = "선택" if selection.selected else "거절"
        lines.append(
            f"- {state}: {selection.reason_code}; FactRef={selection.ref.analysis_id}/{selection.ref.item_id}"
        )
    return lines


def render_chart_analysis(
    result: ChartAnalysisResult,
    *,
    analyses: dict[str, ChartAnalysis],
    selections: tuple[FactSelection, ...] = (),
    detail: bool = True,
) -> str:
    """Resolve exact refs independently so an invalid ref cannot hide valid facts."""
    available = dict(analyses)
    available[result.analysis.analysis_id] = result.analysis
    own = tuple(
        FactSelection(FactRef(result.analysis.analysis_id, item.id), True, "COMMON_ANALYSIS")
        for item in (_current_items(result.analysis) if detail else result.analysis.items)
    )
    manifest = result.analysis.manifest
    coverage = manifest.coverage
    period_start = (
        coverage.get("input_start", manifest.origin)
        if isinstance(coverage, Mapping)
        else manifest.origin
    )
    lines = [
        "### 공통 차트 사실",
        f"- {manifest.ticker}: 요청일={result.requested_as_of or manifest.as_of}, 해석 세션={manifest.as_of}",
        f"- 입력 기간: {period_start}~{manifest.as_of}; profile={manifest.input_profile}",
        "- EVENT는 조건 발생, OBSERVATION/EPISODE는 상태 관측, RISK는 위험 조건입니다",
        (
            "- 기본 EVENT는 최근 20세션(세션 목록이 없으면 30일); 명시 선택한 과거 근거는 함께 표시합니다"
            if detail
            else "- 현재 유효 상태·ACTIVE EPISODE·당일 EVENT; 과거/종료 근거는 --detail-strategy"
        ),
    ]
    lines.extend(_fact_lines(available, selections, own=own, detail=detail, as_of=manifest.as_of))
    lines.extend(_quality_lines(result.quality))
    if detail:
        lines.extend(_selection_lines(selections))
    else:
        lines.append("- FactRef·전략 선택 audit: --detail-strategy에서 확인")
    return "\n".join(lines)


def render_common_strategy_analysis(analysis, *, detail: bool = True) -> str:
    """One shared presentation seam for check/analyze/brief."""
    run = analysis.strategy_run
    analyses = getattr(analysis, "common_analyses", {})
    selections = (
        *getattr(analysis, "technical_fact_selections", ()),
        *tuple(getattr(getattr(analysis, "scorecard", None), "fact_selections", ()) or ()),
        *(
            selection
            for consumer in (*getattr(run, "verdicts", ()), *getattr(run, "signal_bundles", ()))
            for selection in (getattr(consumer, "fact_selections", ()) or ())
        ),
    )
    result = getattr(analysis, "chart_analysis", None)
    if result is not None:
        return render_chart_analysis(
            result, analyses=analyses, selections=selections, detail=detail
        )
    reason = getattr(analysis, "chart_analysis_unavailable", None) or "공통 분석 입력 이용 불가"
    lines = ["### 공통 차트 사실", "- 기존 소비자가 선택한 원래 scope의 사실과 근거입니다"]
    as_of = getattr(getattr(analysis, "scorecard", None), "as_of", None)
    lines.extend(_fact_lines(analyses, selections, detail=detail, as_of=as_of))
    lines.extend(["", "### Quality", f"- Quality: null — {reason}"])
    if detail:
        lines.extend(_selection_lines(selections, standalone=False))
    else:
        lines.append("- FactRef·전략 선택 audit: --detail-strategy에서 확인")
    return "\n".join(lines)


def chart_analysis_context(analysis) -> dict | None:
    """Calculated values for explanation only; no input for rule-action mutation."""
    result = getattr(analysis, "chart_analysis", None)
    if result is None:
        return None
    return {
        "read_only": True,
        "instruction": "계산된 실험적 상태 설명 전용. 점수·축·사실과 기존 매매판정을 변경하지 마세요",
        "as_of": str(result.analysis.manifest.as_of),
        "quality": result.quality.quality,
        "axes": dict(result.quality.axes),
        "reasons": result.quality.reasons,
        "facts": [
            {
                "ref": f"{result.analysis.analysis_id}/{item.id}",
                "kind": item.kind,
                "state": item.state,
                "finality": item.finality,
                "occurred_on": str(item.occurred_on),
                "confirmed_on": str(item.confirmed_on),
                "evidence": _evidence_summary(item.evidence),
            }
            for item in _current_items(result.analysis)
        ],
    }


def _quality_lines(quality) -> list[str]:
    lines = [
        "",
        "### Quality",
        "- 실험적 상태 지수: 매매 임계값·수익률 예측으로 검증되지 않았습니다; 등급 비활성",
        f"- Quality: {_value(quality.quality)} / 100"
        + (" [FINAL]" if quality.quality is not None else ""),
        "- " + " | ".join(f"{key}={_value(value)}" for key, value in quality.axes.items()),
        "- Participation: 보합 제외, V>0 방향 표본≥5; 한 방향 표본은 100/0, 하루 비중≥50%는 집중 경고",
    ]
    if quality.quality is None:
        lines.append("- null: 공개 가능한 FINAL Quality가 없습니다")
        preview = quality.diagnostics.get("calculated_quality")
        if preview is not None:
            lines.append(f"- 진단용 preview 계산값={_value(preview)} (공개 Quality 아님)")
    for reason in quality.reasons:
        lines.append(f"- {reason}: {_REASON_COPY.get(reason, reason)}")
    return lines


def render_quality_summary(analysis) -> str:
    """Read the current Quality without recomputation or mutation."""
    result = getattr(analysis, "chart_analysis", None)
    day = analysis.scorecard.as_of
    if result is None:
        reason = getattr(analysis, "chart_analysis_unavailable", None) or "공통 분석 입력 이용 불가"
        return f"### Quality\n- Quality: null — {reason}"
    if result.analysis.manifest.as_of != day or result.quality.as_of != day:
        return (
            "### Quality\n- Quality: null — 평가일 불일치; 과거 점수를 현재값으로 표시하지 않습니다"
        )
    lines = _quality_lines(result.quality)
    labels = {
        "trend": "추세",
        "structure": "구조",
        "momentum": "모멘텀",
        "participation": "Participation",
    }
    lines[4] = "- " + " · ".join(
        f"{labels.get(key, key)} {_value(float(value)) if value is not None else '미평가'}"
        for key, value in result.quality.axes.items()
    )
    return "\n".join(lines).lstrip("\n")
