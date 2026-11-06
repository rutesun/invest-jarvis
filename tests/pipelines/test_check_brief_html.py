"""브리핑은 단일 HTML에서 의미 있는 방향 수치만 색상화한다."""

from tests.tools.technical.test_chart_brief import build, technical


def render(brief, ticker="ALAB"):
    from src.pipelines.check_brief_html import render_chart_brief

    return render_chart_brief(brief, ticker=ticker)


def test_brief_renders_five_topics_ma_values_bands_and_currency_without_sample_ui():
    brief = build(technical())
    output = render(brief)
    for text in (
        "추세",
        "가격 위치",
        "가격 구조",
        "과열·과매도",
        "거래량",
        "현재 배열",
        "50일선",
        "200일선",
        "최근 핵심 변화",
        "FINAL",
        "보합 제외",
    ):
        assert text in output
    assert "$110.00" in output and "$90.00" in output
    assert 'class="jb-down">$105.00' in output
    assert 'class="jb-cool">24.0' in output
    assert 'class="jb-up">50.0%' in output
    assert 'class="jb-down">50.0%' in output
    assert "₩110" in render(brief, "161890.KS")
    assert "SAMPLE" not in output and "<script" not in output and "Tweak" not in output
    assert 'class="jb-crsi-band"' in output
    assert 'class="jb-crsi-marker jb-cool"' in output
    assert "left:24" in output and "width:30" in output
    assert "<meter" not in output
    assert "50일선 &gt; 200일선" in output


def test_brief_escapes_all_external_text_and_handles_unavailable():
    brief = build(technical())
    brief["headline"] = '<img src="https://evil.test/">'
    brief["events"] = [
        {"date": "<bad>", "label": "<script>x</script>", "finality": "UNKNOWN", "direction": "down"}
    ]
    output = render(brief)
    assert "<script>" not in output and "<img" not in output
    assert "&lt;script&gt;" in output and "&lt;bad&gt;" in output
    assert "UNKNOWN" in output
    assert "브리핑 미산출" in render(None)


def test_structure_leads_with_short_status_and_moves_prices_dates_to_support():
    tech = technical()
    tech.raw_dataframe.iloc[4, tech.raw_dataframe.columns.get_loc("High")] = 130.0
    tech.raw_dataframe.iloc[14, tech.raw_dataframe.columns.get_loc("High")] = 120.0
    output = render(build(tech))
    structure = output.split('<div class="jb-label">가격 구조</div>', 1)[1].split("</section>", 1)[
        0
    ]
    value, support = structure.split('<div class="jb-support">', 1)
    assert "고점" in value and "↘ 하락" in value
    assert "$120.00" not in value and "확인" not in value
    assert "$130.00" in support and "$120.00" in support and "확인" in support


def test_unavailable_ma_exposes_reason_instead_of_a_valid_looking_slope():
    tech = technical()
    tech.snapshot.sma_200 = None
    output = render(build(tech))
    assert "기준일 MA 값 부재 또는 snapshot 불일치" in output
