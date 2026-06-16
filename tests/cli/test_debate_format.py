from datetime import datetime

from src.llm.models import DebateCase, DebateVerdictOutput
from src.pipelines.debate.models import BullBearLedger, DebateBundle, Evidence


def _bundle(action="매수"):
    ledger = BullBearLedger(
        mode="entry",
        bull=[
            Evidence(
                side="bull",
                key="gate_A",
                weight=4.0,
                headline="게이트 A",
                detail="상승장",
                source="playbook",
            )
        ],
        bear=[
            Evidence(
                side="bear",
                key="gate_E",
                weight=3.0,
                headline="게이트 E",
                detail="미돌파",
                source="playbook",
            )
        ],
        neutral=[],
        bull_weight=4.0,
        bear_weight=3.0,
        action_space=["매수", "관망"],
    )
    return DebateBundle(
        ledger=ledger,
        bull_case=DebateCase(stance="bull", thesis="강세 우위", points=["게이트 A 통과"]),
        bear_case=DebateCase(stance="bear", thesis="VCP 미돌파", points=["E 미충족"]),
        verdict=DebateVerdictOutput(
            action=action, confidence=0.72, swing_factor="시장환경", reconciliation="bull 우위."
        ),
    )


def test_format_debate_section():
    from src.cli.analyze_render import _format_debate_section

    out = _format_debate_section(_bundle())
    assert "종합 판정" in out and "매수" in out and "72%" in out
    assert "Bull 논거" in out and "Bear 논거" in out and "판결 사유" in out


def test_format_ledger_fallback():
    from src.cli.analyze_render import _format_ledger_fallback

    out = _format_ledger_fallback(_bundle().ledger)
    assert "증거" in out and "게이트 A" in out


def test_deep_dive_output_includes_verdict():
    """플랜 A 출력에 debate 가 있으면 종합 판정이 최상단에 들어간다."""
    from src.cli.analyze_render import format_deep_dive_output
    from src.tools.technical.events_models import MomentumEvents
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult

    snap = IndicatorSnapshot(price=155.3, change_pct=1.2)
    tech = TechnicalResult(
        ticker="T", timestamp=datetime(2026, 6, 15), snapshot=snap, components={}, total_score=0
    )

    class _Sum:
        summary = "s"
        recommendation = "보유"
        confidence = 0.5
        rationale = "r"
        key_insights = []

    result = {
        "ticker": "T",
        "technical": tech,
        "technical_summary": _Sum(),
        "momentum_events": MomentumEvents(),
        "criteria_verdict": None,
        "chart_patterns": {},
        "factor_assessments": [],
        "scenarios": [],
        "debate": _bundle(),
        "debate_ledger": _bundle().ledger,
    }
    out = format_deep_dive_output(result)
    assert "## 🧭 종합 판정" in out
    assert out.index("종합 판정") < out.index("## 📊 Summary")
