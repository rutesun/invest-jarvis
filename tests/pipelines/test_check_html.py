"""Standalone report preserves display contracts without active external resources."""

import base64
from datetime import date, datetime
from html.parser import HTMLParser

from tests.pipelines.test_observation_story import alab, recovered_today
from tests.pipelines.test_readable_quality import case, quality_on


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def result_for(analysis=None, **extra):
    analysis = analysis or alab()
    return dict(
        success=True,
        ticker="ALAB",
        price=233.62,
        change_pct=1.72,
        total_score=-62,
        scorecard=analysis.scorecard,
        strategy_analysis=analysis,
        **extra,
    )


class Resources(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.resources = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "iframe", "link", "object", "embed"}:
            self.resources.append((tag, attrs))
        for key in ("src", "href", "srcset"):
            if key in attrs:
                self.resources.append((key, attrs[key]))


def render(results, **kwargs):
    from src.pipelines.check_html import render_check_html

    return render_check_html(results, **kwargs)


def test_standalone_chart_report_keeps_current_state_quantity_and_20_session_flow():
    output = render([result_for(chart_png=PNG)], generated_at=datetime(2026, 11, 4, 16, 0))
    assert '<html lang="ko">' in output and 'name="viewport"' in output
    assert "2026-11-04" in output and "2026-11-03" in output
    assert "청산 조건 충족 후 미회복" in output and "2026-10-30" in output
    assert "최근 20개 반환 거래일" in output and "전략별 수량" in output
    assert "수량 미산정" in output and "합산하지 않습니다" in output
    assert "data:image/png;base64," in output and "<details" in output
    assert output.index("전략별 대응") < output.index("주요 가격대")
    assert output.index("현재 상태") < output.index("관찰 흐름")
    assert all(
        str(value).startswith(("data:image/png;base64,", "#"))
        for _key, value in Resources(output).resources
    )


def test_untrusted_markdown_html_links_and_images_cannot_load_resources():
    attack = '<script>alert(1)</script> ![bad](https://evil.test/image.png) [bad](https://evil.test/) & "'
    output = render(
        [
            result_for() | {"ticker": attack, "warnings": [attack]},
            {"success": False, "ticker": "<bad>", "error": attack},
        ]
    )
    assert "<script>" not in output and "&lt;script&gt;" in output
    assert "&lt;bad&gt;" in output and "분석 실패" in output
    assert not any(str(v).startswith(("http", "//")) for _, v in Resources(output).resources)
    assert "alert(1)" in output and "&amp;" in output


def test_multiple_results_keep_input_order_failure_and_chart_warning():
    output = render(
        [
            result_for(chart_warning="raw 데이터 없음"),
            {"success": False, "ticker": "BROKEN", "error": "입력 실패"},
            result_for() | {"ticker": "161890.KS"},
        ]
    )
    assert output.index("ALAB") < output.index("BROKEN") < output.index("161890.KS")
    assert "raw 데이터 없음" in output and "입력 실패" in output
    assert "₩234" in output and "$233.62" in output


def test_quality_sparkline_keeps_missing_gap_and_provisional_distinct():
    days = (date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2))
    current = quality_on(days[2], None, finality="PROVISIONAL", reasons=("PROVISIONAL_PREVIEW",))
    analysis = case(current, (quality_on(days[0], 40), current))
    analysis.exchange_sessions = days
    output = render([result_for(analysis)])
    assert "<svg" in output and "Quality 추이" in output
    assert "장중 잠정" in output and "Technical Score" in output and "미평가" in output
    assert output.count('class="quality-point provisional"') == 1
    assert "<polyline" not in output  # the missing middle session must break the line
    assert "거래량 방향" in output and "최근 확정" in output


def test_detailed_options_are_available_in_open_details_without_losing_base_state():
    output = render([result_for()], detailed_history=True, detailed_strategy=True)
    assert "청산 조건 충족 후 미회복" in output
    assert "<details open" in output and "상세 근거" in output


def korean_result(*, with_analysis):
    from dataclasses import replace

    result = {
        "success": True,
        "ticker": "161890.KS",
        "price": 120000.0,
        "change_pct": 1.0,
        "total_score": 0,
        "indicators": {
            "sma_20": 119000.0,
            "sma_50": 118000.0,
            "sma_100": 117000.0,
            "sma_100_slope_pct": 0.8,
            "sma_150": 116000.0,
            "sma_200": 115000.0,
            "sma_200_slope_pct": -0.7,
        },
        "warnings": ["외부 원문 USD: $1,000"],
    }
    if with_analysis:
        analysis = alab()
        scorecard = analysis.scorecard.model_copy(update={"ticker": "161890.KS"})
        result.update(
            scorecard=scorecard,
            strategy_analysis=replace(analysis, scorecard=scorecard, current_close=120000.0),
        )
    return result


def test_korean_html_fallback_and_folded_details_use_krw_for_every_numeric_price():
    for with_analysis in (False, True):
        output = render([korean_result(with_analysis=with_analysis)])
        for price in (120000, 119000, 118000, 117000, 116000, 115000):
            assert f"${price:.2f}" not in output
            assert f"₩{price:,}" in output
        assert "외부 원문 USD: $1,000" in output
        assert "<details>" in output


def test_korean_html_detail_options_preserve_krw_and_default_text_contract():
    from src.pipelines.quick_check import QuickCheckPipeline

    for with_analysis in (False, True):
        result = korean_result(with_analysis=with_analysis)
        original_detail = QuickCheckPipeline(None).format_output(result, detailed_strategy=True)
        assert "**가격**: $120000.00 (+1.00%)" in original_detail
        assert "SMA 20: $119000.00" in original_detail
        assert "$117000.00 · ↗ 상승 (+0.80%/21일)" in original_detail
        for history, strategy in ((True, False), (False, True), (True, True)):
            output = render([result], detailed_history=history, detailed_strategy=strategy)
            assert "$120000.00" not in output and "$117000.00" not in output
            assert "₩120,000" in output and "₩117,000 · ↗ 상승 (+0.80%/21일)" in output
            assert "₩115,000 · ↘ 하락 (-0.70%/21일)" in output
            assert "외부 원문 USD: $1,000" in output and "<details open>" in output


def test_us_html_keeps_usd_prices_in_summary_and_details():
    result = korean_result(with_analysis=False) | {"ticker": "ALAB", "price": 123.45}
    output = render([result], detailed_strategy=True)
    assert "$123.45" in output and "SMA 20: $119000.00" in output
    assert "$117000.00 · ↗ 상승 (+0.80%/21일)" in output
    assert "₩" not in output


def test_same_day_recovery_is_in_html_current_section_not_only_timeline():
    output = render([result_for(recovered_today()) | {"price": 300.0}])
    current = output.split('<section class="section current">', 1)[1].split("</section>", 1)[0]
    assert "150일선: 당일 회복 확인" in current
    assert "2026-11-03 · FINAL · 확정" in current
    assert "현재 청산 조건 지속 여부 미평가" not in current


def test_brief_is_between_current_state_and_chart_preserving_full_report():
    from tests.tools.technical.test_chart_brief import build, technical

    output = render([result_for(chart_png=PNG, chart_brief=build(technical()))])
    assert output.index("현재 상태") < output.index('class="chart-brief"')
    assert output.index('class="chart-brief"') < output.index("data:image/png;base64,")
    assert output.index("data:image/png;base64,") < output.index("전략별 대응")
    assert 'class="price jb-up"' in output
    assert "청산 조건 충족 후 미회복" in output and "상세 근거" in output
    assert all(
        str(v).startswith(("data:image/png;base64,", "#")) for _, v in Resources(output).resources
    )
    down = render([result_for() | {"change_pct": -1.0}])
    assert 'class="price jb-down"' in down


def test_brief_failure_warning_is_escaped_and_existing_chart_survives():
    output = render([result_for(chart_png=PNG, chart_brief_warning="브리핑 미산출: <bad>")])
    assert "브리핑 미산출: &lt;bad&gt;" in output
    assert "<bad>" not in output and "data:image/png;base64," in output


def test_alab_headline_distinguishes_long_ma_rise_from_price_below_preserving_state_quantity():
    from tests.tools.technical.test_chart_brief import alab_headline_technical, build

    output = render([result_for(chart_png=PNG, chart_brief=build(alab_headline_technical()))])
    assert "단기선 하락 · 장기선 상승 · 주가 150일선 아래" in output
    assert "장기 상승 속 단기 조정" not in output
    assert "청산 조건 충족 후 미회복" in output
    assert "전략별 수량" in output and "수량 미산정" in output
    assert "합산하지 않습니다" in output and "상세 근거" in output
    assert output.index("현재 상태") < output.index("단기선 하락 · 장기선 상승")


def test_scorecard_only_fallback_keeps_known_date_once_with_unknown_finality():
    from tests.pipelines.test_check_current_html import visible_text
    from tests.pipelines.test_check_lower_html import Document
    from tests.pipelines.test_observation_story import TODAY

    result = result_for()
    del result["strategy_analysis"]
    document = Document(render([result]))
    current = document.by_class("current")[0]
    assert str(TODAY) in visible_text(current)
    assert "확정 여부 미평가" in visible_text(current)
    assert "FINAL" not in visible_text(current)
    introductory = [
        node
        for node in document.elements
        if node.tag == "section" and node.parent.tag == "article" and not node.folded
    ]
    assert sum(str(TODAY) in visible_text(node) for node in introductory) == 1


def test_no_scorecard_fallback_marks_date_and_finality_unknown():
    from tests.pipelines.test_check_current_html import visible_text
    from tests.pipelines.test_check_lower_html import Document

    result = result_for()
    del result["strategy_analysis"]
    del result["scorecard"]
    current = Document(render([result])).by_class("current")[0]
    assert "기준일 미평가" in visible_text(current)
    assert "확정 여부 미평가" in visible_text(current)
    assert "FINAL" not in visible_text(current)
