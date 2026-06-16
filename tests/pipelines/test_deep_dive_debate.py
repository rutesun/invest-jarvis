import pytest


@pytest.mark.asyncio
async def test_build_debate_returns_bundle_and_ledger(monkeypatch):
    from src.llm.models import DebateAdvocacyOutput, DebateCase, DebateVerdictOutput
    from src.pipelines import deep_dive

    async def _adv(_i, _l):
        return DebateAdvocacyOutput(
            bull_case=DebateCase(stance="bull", thesis="강세", points=["p"]),
            bear_case=DebateCase(stance="bear", thesis="약세", points=["q"]),
        )

    async def _judge(_i, _l):
        return DebateVerdictOutput(
            action="관망", confidence=0.5, swing_factor="x", reconciliation="y"
        )

    # engine.py의 로컬 이름을 패치해야 함
    monkeypatch.setattr("src.pipelines.debate.engine.run_debate_advocacy", _adv)
    monkeypatch.setattr("src.pipelines.debate.engine.run_debate_judge", _judge)

    bundle, ledger = await deep_dive._build_debate(
        criteria_verdict=None,
        factor_assessments=[],
        snapshot=None,
        flow=None,
        holding=False,
        llm=object(),
        ticker="TEST",
    )
    assert ledger is not None
    assert bundle is not None
    assert bundle.verdict.action in ledger.action_space


@pytest.mark.asyncio
async def test_build_debate_graceful_on_llm_failure(monkeypatch):
    from src.pipelines import deep_dive

    async def _boom(_i, _l):
        raise RuntimeError("llm down")

    monkeypatch.setattr("src.pipelines.debate.engine.run_debate_advocacy", _boom)
    bundle, ledger = await deep_dive._build_debate(
        criteria_verdict=None,
        factor_assessments=[],
        snapshot=None,
        flow=None,
        holding=False,
        llm=object(),
        ticker="TEST",
    )
    assert bundle is None
    assert ledger is not None  # 실패해도 증거 장부는 표시 가능
