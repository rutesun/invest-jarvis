def test_points_grounding_ratio():
    from src.pipelines.debate.grounding import points_grounding_ratio

    ratio = points_grounding_ratio(
        ["게이트 A 통과로 시장환경 양호", "관련 없는 환각 주장"],
        ["게이트 A: 시장환경=상승", "CAN SLIM C 분기 EPS"],
    )
    assert ratio == 0.5
