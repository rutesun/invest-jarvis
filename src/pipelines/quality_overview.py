"""기존 Quality 결과를 읽어 시점과 관측 근거를 설명하는 기본 화면."""

from collections.abc import Mapping
from math import isfinite


AXES = {
    "trend": ("추세", "가격·이동평균선의 위치와 장기선 방향", "추세 상태"),
    "structure": ("구조", "최근 고점·저점의 변화와 가격 위치", "고점·저점 구조"),
    "momentum": ("모멘텀", "5·20·60일 가격 변화의 강도", "가격 변화 강도"),
    "participation": (
        "거래량 방향(Participation)",
        "상승일과 하락일의 거래량 비중",
        "상승일 거래량 비중",
    ),
}
REASONS = {
    "POLICY_HISTORY_SHORT": "공개에 필요한 연속 FINAL(확정) 252봉 부족",
    "HISTORY_SHORT": "계산에 필요한 220봉 부족",
    "INCOMPLETE_PREFIX": "입력 이력 누락 또는 확정 여부 확인 부족",
    "INPUT_MISSING": "필수 가격·거래량 또는 지표 누락",
    "PROFILE_UNSUPPORTED": "지원하는 입력 형식이 아님",
    "STRICT_FEATURE_REQUEST_REQUIRED": "필수 지표 계산 요청 누락",
    "PROVISIONAL_PREVIEW": "미완성 일봉으로 확정 점수 미산출",
    "LOW_DIRECTIONAL_SAMPLE": "방향 거래량 표본 5개 미만",
    "ZERO_DIRECTIONAL_VOLUME": "상승·하락일 거래량 합계가 0",
    "CONCENTRATED_VOLUME": "하루에 방향 거래량의 50% 이상 집중",
    "ONE_SIDED_SAMPLE": "상승·하락 중 한쪽 거래량만 존재",
    "NONPOSITIVE_PRICE": "가격 입력값이 0 이하",
    "NONPOSITIVE_ATR": "가격 변동폭 입력값이 0 이하",
    "ZERO_PRICE_RANGE": "최근 고가·저가 범위가 0",
    "INVALID_PRICE_RANGE": "최근 고가·저가와 현재가격의 범위 불일치",
}
_WARNINGS = {"ONE_SIDED_SAMPLE", "CONCENTRATED_VOLUME", "PROVISIONAL_PREVIEW"}


def number(value):
    return float(value) if isinstance(value, (int, float)) and isfinite(value) else None


def finality(result):
    if result is None:
        return None
    value = result.quality.manifest.finality
    return value.get(result.quality.as_of) if isinstance(value, Mapping) else value


def valid_result(result, day):
    return (
        result is not None
        and result.quality.as_of == day
        and result.quality.manifest.as_of == day
        and result.analysis.manifest.as_of == day
    )


def quality_value(result, *, current_day=None):
    """공개 확정값과 현재일의 완전한 장중 진단값만 노출한다."""
    if result is None or not valid_result(result, result.quality.as_of):
        return None
    quality = result.quality
    if finality(result) == "FINAL":
        return number(quality.quality)
    if quality.as_of != current_day or finality(result) != "PROVISIONAL":
        return None
    if set(quality.reasons) - _WARNINGS:
        return None
    if any(number(quality.axes.get(key)) is None for key in AXES):
        return None
    return number(quality.diagnostics.get("calculated_quality"))


def quality_history_by_day(analysis, day):
    history = {
        result.quality.as_of: result
        for result in getattr(analysis, "quality_history", ())
        if result.quality.as_of <= day and valid_result(result, result.quality.as_of)
    }
    current = getattr(analysis, "chart_analysis", None)
    if valid_result(current, day):
        history[day] = current
    return history


def compatible(before, after):
    return (
        before is not None
        and after is not None
        and before.quality.parameter_id == after.quality.parameter_id
        and before.quality.score_version == after.quality.score_version
        and all(
            getattr(before.quality.manifest, field) == getattr(after.quality.manifest, field)
            for field in (
                "ticker",
                "exchange",
                "feature_version",
                "input_profile",
                "adjustment_policy",
                "calendar_version",
                "provider",
                "revision_if_known",
                "timezone",
            )
        )
    )


def previous_result(analysis, day, history):
    sessions = sorted({d for d in analysis.exchange_sessions if d <= day})
    return history.get(sessions[-2]) if len(sessions) >= 2 and sessions[-1] == day else None


def quality_cell(result, previous, *, current_day):
    value = quality_value(result, current_day=current_day)
    if value is None:
        return "미산출" if result is not None else "미평가"
    prior = quality_value(previous, current_day=current_day)
    delta = f"{value - prior:+.2f}" if prior is not None and compatible(previous, result) else "—"
    prefix = "장중 잠정 " if finality(result) == "PROVISIONAL" else ""
    return f"{prefix}{value:.2f} ({delta})"


def _feature(result, key):
    feature = result.analysis.features.get(key)
    if feature is None or feature.status not in {"READY", "PROVISIONAL"}:
        return None
    return number(feature.value)


def quality_close(result):
    return _feature(result, "Close") if result is not None else None


def _axis_evidence(result, axis):
    def read(key):
        return _feature(result, key)

    close = read("Close")
    if axis == "trend" and close is not None:
        parts = []
        for days in (50, 150, 200):
            sma = read(f"SMA_{days}")
            if sma is not None:
                position = "위" if close > sma else "아래" if close < sma else "동일"
                parts.append(f"{days}일선 {position} ({sma:,.2f})")
        return " · ".join(parts)
    if axis == "structure":
        high, low = read("High_20_New"), read("Low_20_New")
        if high is not None and low is not None:
            return f"20일 고가 {high:,.2f} / 저가 {low:,.2f}"
    if axis == "momentum":
        parts = []
        for lag in (5, 20, 60):
            prior = read(f"Close_Lag{lag}")
            if close is not None and prior is not None and prior > 0:
                parts.append(f"{lag}일 수익률 {(close / prior - 1) * 100:+.2f}%")
        return " · ".join(parts)
    if axis == "participation":
        up, down = read("Up_Volume_20"), read("Down_Volume_20")
        if up is not None and down is not None and up + down > 0:
            return f"상승일 거래량 {100 * up / (up + down):.1f}% / 하락일 {100 * down / (up + down):.1f}% (보합 제외)"
    return ""


def axis_change_lines(before, after):
    if not compatible(before, after):
        return ["- 축 점수 변화: 미평가 — 전 거래일 결과 또는 동일 계산 기준 부족"]
    lines = []
    for key, (label, _, meaning) in AXES.items():
        prior, value = number(before.quality.axes.get(key)), number(after.quality.axes.get(key))
        if prior is None or value is None:
            lines.append(f"- {label} 축 점수 변화: 미평가")
            continue
        delta = value - prior
        direction = "상승" if delta > 0 else "하락" if delta < 0 else "유지"
        lines.append(
            f"- {label} 축 점수 변화: {prior:.2f} → {value:.2f} ({delta:+.2f}점) · {meaning} 점수 {direction}"
        )
    return lines


def render_quality_overview(analysis):
    day = analysis.scorecard.as_of
    result = getattr(analysis, "chart_analysis", None)
    history = quality_history_by_day(analysis, day)
    lines = [
        "### 차트 상태 점수(Quality)",
        "",
        "추세·구조·모멘텀·거래량 방향의 현재 상태를 0~100으로 요약합니다. 각 축도 0~100이며 매매 판단은 전략별 대응에서 확인합니다.",
        "높을수록 해당 축의 상승 방향 조건이 강하다는 뜻입니다. 수익률 예측이나 매수·매도 기준으로 검증된 점수는 아닙니다.",
        "",
    ]
    if not valid_result(result, day):
        reason = (
            "평가일 불일치"
            if result
            else (getattr(analysis, "chart_analysis_unavailable", None) or "계산 입력 이용 불가")
        )
        return "\n".join([*lines, f"- Quality: 미산출 — {reason}"])
    value = quality_value(result, current_day=day)
    provisional = finality(result) == "PROVISIONAL"
    if value is not None:
        state = "장중 잠정 " if provisional else "확정 "
        lines.append(f"- Quality: {state}{value:.2f} / 100 · {day}")
    else:
        reasons = [
            REASONS.get(reason, "입력 또는 계산 조건 미충족; 상세 근거 참조")
            for reason in result.quality.reasons
        ]
        lines.append(
            f"- Quality: 미산출 · {day} — {'; '.join(dict.fromkeys(reasons)) or '계산 조건 미충족'}"
        )
    if provisional:
        finals = [
            r
            for d, r in sorted(history.items())
            if d < day and finality(r) == "FINAL" and quality_value(r) is not None
        ]
        if finals:
            latest = finals[-1]
            lines.append(
                f"- 최근 확정 Quality: {latest.quality.as_of} · {quality_value(latest):.2f} / 100"
            )
        else:
            lines.append("- 최근 확정 Quality: 미평가 — 과거 확정 결과 없음")
        lines.append("- 장중 값은 일봉 마감 전 변할 수 있습니다.")
    previous = previous_result(analysis, day, history)
    lines += ["", "| 축 / 현재 점수 | 무엇을 보는가 | 전 거래일 대비 |", "|---|---|---|"]
    for key, (label, description, _) in AXES.items():
        axis = number(result.quality.axes.get(key))
        prior = number(previous.quality.axes.get(key)) if compatible(previous, result) else None
        change = f"{axis - prior:+.2f}점" if axis is not None and prior is not None else "미평가"
        state = " (장중 잠정)" if provisional and axis is not None else ""
        lines.append(
            f"| {label} {axis:.2f}{state} | {description} | {change} |"
            if axis is not None
            else f"| {label} 미평가 | {description} | 미평가 |"
        )
    lines.append("")
    for key, (label, _, _) in AXES.items():
        evidence = _axis_evidence(result, key)
        lines.append(f"- {label} 근거: {evidence or '실측 근거 미평가'}")
    warnings = [
        REASONS[r] for r in result.quality.reasons if r in _WARNINGS and r != "PROVISIONAL_PREVIEW"
    ]
    if warnings:
        lines.append(f"- 해석 주의: {'; '.join(warnings)}")
    return "\n".join(lines)


def quality_change_lines(analysis, days, day):
    history = quality_history_by_day(analysis, day)
    finals = [
        history[d]
        for d in days
        if d in history
        and finality(history[d]) == "FINAL"
        and quality_value(history[d]) is not None
    ]
    lines = []
    if len(finals) >= 2 and compatible(finals[0], finals[-1]):
        first, last = finals[0], finals[-1]
        a, b = quality_value(first), quality_value(last)
        lines.append(
            f"- 확정 기간 Quality: {first.quality.as_of} {a:.2f} → {last.quality.as_of} {b:.2f} ({b - a:+.2f}점)"
        )
        lines += axis_change_lines(first, last)
    else:
        lines.append("- 확정 기간 Quality 변화: 미평가 — 비교할 확정 결과 부족")
    current = history.get(day)
    previous = previous_result(analysis, day, history)
    if current is not None and finality(current) == "PROVISIONAL":
        value, prior = quality_value(current, current_day=day), quality_value(previous)
        if value is not None and prior is not None and compatible(previous, current):
            lines.append(
                f"- 오늘 장중 Quality: 직전 확정 {prior:.2f} → 장중 잠정 {value:.2f} ({value - prior:+.2f}점) · 마감 전 변동 가능"
            )
            lines += axis_change_lines(previous, current)
        else:
            lines.append(
                "- 오늘 장중 Quality 변화: 미평가 — 잠정 계산 조건 또는 직전 확정 결과 부족"
            )
    warning = getattr(analysis, "quality_history_unavailable", None)
    if warning:
        lines.append(f"- Quality 이력 일부 미평가: {warning}")
    return lines
