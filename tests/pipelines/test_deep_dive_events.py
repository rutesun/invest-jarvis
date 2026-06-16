def test_rs_event_from_verdict():
    from src.pipelines.deep_dive import _rs_event_from_verdict
    from src.tools.criteria.models import RelativeStrengthResult

    rs = RelativeStrengthResult(
        mansfield_rs=2.1,
        outperform_6m=10.0,
        rp_slope_4w=0.5,
        index_symbol="^GSPC",
        rs_cross_type="양전환",
        rs_cross_date="2026-06-01",
        rs_cross_days_ago=10,
    )
    event = _rs_event_from_verdict(rs)
    assert event is not None
    assert event.cross_type == "양전환"
    assert event.date == "2026-06-01"


def test_rs_event_none_when_no_cross():
    from src.pipelines.deep_dive import _rs_event_from_verdict
    from src.tools.criteria.models import RelativeStrengthResult

    rs = RelativeStrengthResult(
        mansfield_rs=2.1, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC"
    )
    assert _rs_event_from_verdict(rs) is None
