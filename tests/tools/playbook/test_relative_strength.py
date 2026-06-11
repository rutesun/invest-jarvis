from src.tools.playbook.models import RelativeStrengthResult


def test_rs_result_model():
    r = RelativeStrengthResult(
        mansfield_rs=12.3, outperform_6m=18.0, rp_slope_4w=0.5, index_symbol="^GSPC"
    )
    assert r.mansfield_rs == 12.3
    assert r.is_strong is True  # mansfield_rs > 0 and rp_slope_4w >= 0


def test_rs_weak_when_negative():
    r = RelativeStrengthResult(
        mansfield_rs=-3.0, outperform_6m=-5.0, rp_slope_4w=-0.2, index_symbol="^KS11"
    )
    assert r.is_strong is False
