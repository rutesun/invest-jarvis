"""기본 화면은 현재 상태 한 곳과 중요한 불확실성만 펼친다."""

import re

from tests.pipelines.test_check_html import Resources, render, result_for
from tests.pipelines.test_check_lower_html import Document
from tests.pipelines.test_observation_story import BREACH, TODAY, alab, analysis_for, observation


def visible_text(node):
    if node.folded:
        return ""
    return "".join(
        child if isinstance(child, str) else visible_text(child) for child in node.children
    )


def test_current_once_and_dates_only_in_details():
    document = Document(render([result_for()]))
    current = document.by_class("current")[0]
    assert len(document.by_class("current")) == 1
    assert "현재 상태" in current.text and "현재 유효 상태" not in visible_text(current)
    assert re.findall(r"2026-\d\d-\d\d", visible_text(current)) == [str(TODAY)]
    assert "청산 조건 충족 후 미회복" in visible_text(current)
    assert "다음 확인: 150일선 회복 여부" in visible_text(current)
    histories = document.by_class("current-history")
    assert histories and all(item.folded for item in histories)
    assert str(BREACH) in current.text
    lower = document.by_class("lower-observation")[0]
    assert lower.folded and "지난 관찰 전체 보기" in lower.parent.text
    assert "현재 결론" not in lower.text and "청산 조건 충족 후 미회복" not in lower.text
    assert not document.by_class("observation-current")


def test_extra_states_fold_but_their_uncertainty_is_visible():
    analysis = alab()
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.observation_history += [
        observation("SUPPORT_BREAK", BREACH, anchor="SMA50"),
        observation("MOMENTUM_DECELERATION", BREACH, anchor=None),
    ]
    # Existing models require evidence; make the momentum evidence unavailable for current reading.
    bundle.observation_history[-1].evidence = bundle.observation_history[0].evidence
    document = Document(render([result_for(analysis)]))
    current = document.by_class("current")[0]
    states = document.by_class("current-state")
    assert sum(not item.folded for item in states) == 3
    assert any(item.folded for item in states)
    assert document.by_class("current-more")[0].folded
    assert "실측/기준값 미평가" in visible_text(current)


def test_projection_html_escapes_context_and_has_no_external_resources():
    analysis = analysis_for([observation("SUPPORT_BREAK", BREACH)])
    analysis.strategy_run.signal_bundles[0].strategy_id = '<script src="https://evil.test/">'
    output = render([result_for(analysis)])
    assert "<script" not in output and "&lt;script" in output
    assert all(
        str(value).startswith(("#", "data:image/png;base64,"))
        for _, value in Resources(output).resources
    )
    assert 'class="current-down"' in output
    assert "-20.97% 아래" in Document(output).by_class("current")[0].text


def test_missing_analysis_has_explicit_current_fallback():
    output = render(
        [{"success": True, "ticker": "ALAB", "price": 233.62, "change_pct": 0.0, "total_score": 0}]
    )
    current = Document(output).by_class("current")[0]
    assert "현재 상태 미평가" in current.text
    assert "정상" not in current.text


def test_warning_summary_keeps_risk_without_repeating_dated_nested_evidence():
    from src.pipelines.check_html import _markdown
    from src.pipelines.check_lower_html import render_lower_sections

    raw = (
        "### 전략별 대응\n"
        "- SWING_W150 보조 위험: 높음 (잠정) · 진입 구조의 참고 진단 · 현재 평가일 2026-11-05\n"
        "  - 출처: 신호 A · 진입 신호일 2026-10-20\n"
        "  - 최초 지지선 이탈 · 발생일 2026-10-29 · 최초 확정일 2026-10-30 · 현재 실측 미평가\n"
        "- OTHER 보조 위험: 미평가\n"
    )
    document = Document(render_lower_sections(result_for(), [("전략별 대응", raw)], _markdown))
    warning = document.by_class("lower-warnings")[0]
    assert "높음 (잠정)" in warning.text and "OTHER 보조 위험: 미평가" in warning.text
    assert "2026-" not in warning.text and "출처:" not in warning.text
    details = [
        node for node in document.elements if node.tag == "details" and "최초 확정일" in node.text
    ]
    assert details and all(node.folded for node in details)


def test_top_metadata_does_not_repeat_current_date_or_fallback_heading():
    document = Document(render([result_for()]))
    introductory = [
        node
        for node in document.elements
        if node.tag == "section" and node.parent.tag == "article" and not node.folded
    ]
    assert sum(str(TODAY) in visible_text(node) for node in introductory) == 1
    fallback = Document(
        render(
            [
                {
                    "success": True,
                    "ticker": "ALAB",
                    "price": 233.62,
                    "change_pct": 0.0,
                    "total_score": 0,
                }
            ]
        )
    )
    headings = [node.text for node in fallback.elements if node.tag == "h3" and not node.folded]
    assert headings.count("현재 상태") == 1


def test_unconfirmed_today_recovery_warning_is_unfolded_beside_confirmed_structure():
    from src.strategies.models import SignalFinality
    from tests.pipelines.test_observation_story import event

    analysis = analysis_for(
        [
            event("SUPPORT_RECLAIM", TODAY, finality=SignalFinality.PROVISIONAL),
            event("LOWER_HIGH", TODAY, anchor=None),
        ]
    )
    document = Document(render([result_for(analysis)]))
    current = document.by_class("current")[0]
    assert "당일 회복 미평가" in visible_text(current)
    assert "PROVISIONAL" in visible_text(current)
    assert "최근 확인된 고점 하락" in visible_text(current)
    assert not any(
        "당일 회복 확인" in state.text
        for state in document.by_class("current-state")
        if not state.folded
    )


def test_terminal_entry_risk_stays_folded_while_current_risk_and_unknown_remain_visible():
    from src.pipelines.check_html import _markdown
    from src.pipelines.check_lower_html import render_lower_sections

    raw = (
        "### 전략별 대응\n"
        "- PAST 보조 위험: 높음 (확정) · 종료된 진입 구조의 참고 진단 · 현재 평가일 2026-11-05\n"
        "- CURRENT 보조 위험: 높음 (확정) · 진입 구조의 참고 진단 · 현재 평가일 2026-11-05\n"
        "- UNKNOWN 보조 위험: 미평가\n"
    )
    document = Document(render_lower_sections(result_for(), [("전략별 대응", raw)], _markdown))
    warning = document.by_class("lower-warnings")[0]
    assert "PAST 보조 위험" not in warning.text
    assert "CURRENT 보조 위험: 높음 (확정)" in warning.text
    assert "UNKNOWN 보조 위험: 미평가" in warning.text
    historical = [
        node for node in document.elements if node.tag == "li" and "PAST 보조 위험" in node.text
    ]
    assert historical and all(node.folded for node in historical)


def test_real_detector_reacceleration_is_visible_in_default_html_without_price_warning():
    from tests.pipelines.test_observation_current import detector_reacceleration_analysis

    current = Document(render([result_for(detector_reacceleration_analysis())])).by_class(
        "current"
    )[0]
    assert "상승 모멘텀 재가속 · 당일 확인" in visible_text(current)
    assert "FINAL" in visible_text(current)
    assert "미평가" not in visible_text(current)
    assert "주가는" not in visible_text(current)


def test_provisional_general_event_and_signal_keep_header_and_warnings_consistent():
    from tests.pipelines.test_observation_current import provisional_change_analysis

    for kind in ("event", "signal"):
        document = Document(render([result_for(provisional_change_analysis(kind))]))
        current = document.by_class("current")[0]
        assert "PROVISIONAL" in visible_text(current)
        assert "최근 확인된 고점 하락" in visible_text(current)
        assert any(
            "잠정" in warning.text and not warning.folded
            for warning in document.by_class("current-warnings")
        )
        structure = next(
            state for state in document.by_class("current-state") if "최근 확인된" in state.text
        )
        assert "잠정" not in visible_text(structure)
