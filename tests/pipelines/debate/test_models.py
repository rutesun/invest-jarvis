def test_ledger_weight_sums():
    from src.pipelines.debate.models import BullBearLedger, Evidence

    ledger = BullBearLedger(
        mode="entry",
        bull=[
            Evidence(
                side="bull", key="gate_A", weight=4.0, headline="h", detail="d", source="criteria"
            )
        ],
        bear=[
            Evidence(
                side="bear", key="gate_E", weight=3.0, headline="h", detail="d", source="criteria"
            )
        ],
        neutral=[],
        bull_weight=4.0,
        bear_weight=3.0,
        action_space=["매수", "관망"],
    )
    assert ledger.bull_weight == 4.0
    assert ledger.action_space == ["매수", "관망"]
