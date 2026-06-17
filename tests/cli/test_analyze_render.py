def test_render_module_exposes_format_deep_dive_output():
    from src.cli.analyze_render import format_deep_dive_output

    assert callable(format_deep_dive_output)


def test_main_reexports_format_deep_dive_output():
    # 기존 import 경로 호환 유지
    from src.cli.main import format_deep_dive_output

    assert callable(format_deep_dive_output)


# ── Task 10: Summary 섹션 ─────────────────────────────────────────────────────


def test_format_summary_section():
    from src.cli.analyze_render import _format_summary_section
    from src.tools.criteria.models import CriteriaCheck, RelativeStrengthResult

    rs = RelativeStrengthResult(
        mansfield_rs=2.1, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC"
    )
    checks = [
        CriteriaCheck(name="A", required=True, met=True, reason="시장환경=상승"),
        CriteriaCheck(name="B", required=True, met=False, reason="is_stage2=0.0 (6/7)"),
        CriteriaCheck(name="C", required=True, met=True, reason="RS=True, 업종강세=True"),
        CriteriaCheck(name="E", required=True, met=False, reason="breakout=False"),
    ]
    out = _format_summary_section(
        checks=checks,
        quality_grade=None,
        relative_strength=rs,
        high_52w=160.5,
        price=155.3,
        ud_volume_ratio=1.8,
        atr=3.2,
        perf_3m=18.0,
        perf_1y=45.0,
    )
    assert "Summary" in out
    assert "핵심 기준" in out and "A✅" in out and "B❌" in out  # 체크리스트 렌더
    assert "B: is_stage2=0.0 (6/7)" in out  # 부연 사유
    assert "2.1" in out
    assert "-3.2%" in out or "-3.24%" in out
    assert "18" in out


# ── Task 11: CAN SLIM 섹션 ────────────────────────────────────────────────────


def test_format_canslim_section_shows_unmet():
    from src.cli.analyze_render import _format_canslim_section
    from src.tools.criteria.models import CanslimResult, ElementVerdict

    canslim = CanslimResult(
        c=ElementVerdict(met=True, detail="분기 EPS +42% (기준 25%)"),
        a=ElementVerdict(met=True, detail="연간 CAGR +28%"),
        n=ElementVerdict(met=True, detail="신제품"),
        s=ElementVerdict(met=True, detail="거래량 +180%"),
        l=ElementVerdict(met=True, detail="RS 강세"),
        i=ElementVerdict(met=False, detail="매집비율 0.38 (기준 0.50)"),
        m=ElementVerdict(met=True, detail="상승장"),
    )
    out = _format_canslim_section(canslim)
    assert "CAN SLIM" in out
    assert "6 / 7" in out
    assert "미충족" in out and "I" in out
    assert "0.38" in out and "+42%" in out


# ── Task 12: Stage2 섹션 ─────────────────────────────────────────────────────


def test_format_stage2_section_with_supertrend():
    from src.cli.analyze_render import _format_stage2_section

    snap = {
        "price": 155.3,
        "sma_20": 148.2,
        "sma_50": 142.1,
        "sma_150": 135.6,
        "sma_200": 128.4,
        "high_52w": 160.5,
        "supertrend_direction": 1,
    }
    out = _format_stage2_section(
        snapshot_dict=snap, gate_b_reason="is_stage2=1.0 (7/7)", supertrend_value=140.0
    )
    assert "Stage 2" in out and "148.2" in out
    assert "Supertrend" in out and "상승" in out
    assert "10.9%" in out or "+10.9" in out


def test_format_stage2_shows_broken_pair_and_slope():
    """비정배열일 때 깨진 쌍 표시 + SMA150/200 기울기(방향·%) 표기."""
    from src.cli.analyze_render import _format_stage2_section

    # ALAB 형태: 마지막 쌍만 역전(SMA150 < SMA200), 둘 다 상승
    snap = {
        "price": 389.2,
        "sma_20": 327.27,
        "sma_50": 242.21,
        "sma_150": 178.75,
        "sma_200": 183.18,
        "supertrend_direction": 1,
    }
    ma_trend = {"sma_150_slope": 5.2, "sma_200_slope": 1.1}
    out = _format_stage2_section(
        snapshot_dict=snap, gate_b_reason=None, supertrend_value=None, ma_trend=ma_trend
    )
    assert "비정배열 (SMA150<SMA200)" in out  # 어느 쌍이 깨졌는지
    assert "5.2" in out and "1.1" in out  # 기울기 %
    assert "상승" in out


# ── Task 13: 모멘텀 섹션 ─────────────────────────────────────────────────────


def test_format_momentum_section():
    from src.cli.analyze_render import _format_momentum_section
    from src.tools.technical.events_models import MacdCross, MomentumEvents

    events = MomentumEvents(
        macd_cross=MacdCross(
            cross_type="golden", date="2026-05-29", days_ago=10, macd=1.85, signal=1.42
        ),
        ud_volume_ratio=1.6,
        volume_trend="증가",
    )
    snap = {
        "rsi": 68.2,
        "macd": 1.85,
        "macd_signal": 1.42,
        "macd_histogram": 0.43,
        "adx": 28.5,
    }
    out = _format_momentum_section(snapshot_dict=snap, events=events)
    assert "모멘텀" in out and "68.2" in out
    assert "골든" in out and "2026-05-29" in out
    assert "1.6" in out and "28.5" in out


# ── Task 14: Event 섹션 ──────────────────────────────────────────────────────


def test_format_event_section():
    from src.cli.analyze_render import _format_event_section
    from src.tools.technical.events_models import MomentumEvents, PriceEvent, RsEvent

    events = MomentumEvents(
        price_events=[
            PriceEvent(
                code="NEW_HIGH_BREAKOUT",
                side="bull",
                headline="52주 신고가 돌파",
                detail="종가 155.3 > 152.5",
                date="2026-06-12",
                days_ago=0,
            )
        ],
        rs_event=RsEvent(
            cross_type="양전환",
            date="2026-06-01",
            days_ago=10,
            detail="Mansfield RS +2.1 (양전환)",
        ),
    )
    patterns = {
        "vcp": {
            "pattern_name": "VCP",
            "detected": True,
            "confidence": 0.8,
            "completed_date": "2026-06-10",
            "days_ago": 3,
            "description": "pivot 152.5",
        }
    }
    out = _format_event_section(events=events, chart_patterns=patterns)
    assert "Event" in out and "신고가 돌파" in out
    assert "양전환" in out and "VCP" in out and "2026-06-10" in out


# ── Task 15: 구조 레벨 섹션 ──────────────────────────────────────────────────


def test_format_structure_section_with_pivots():
    from src.cli.analyze_render import _format_structure_section

    snap = {
        "pivot": 150.0,
        "support_s1": 145.0,
        "resistance_r1": 158.0,
        "price": 155.3,
    }
    out = _format_structure_section(
        structure_levels=None, presented_structure=None, snapshot_dict=snap
    )
    assert "구조 레벨" in out
    assert "150.0" in out and "145.0" in out and "158.0" in out


# ── Task 16: format_deep_dive_output 통합 섹션 순서 ──────────────────────────


def test_format_deep_dive_output_section_order_no_verdict():
    """플랜 A 출력: 판단요약·종합판정 없음. Summary→모멘텀→Event 순서 보장."""
    from datetime import datetime

    from src.cli.analyze_render import format_deep_dive_output
    from src.tools.technical.events_models import MomentumEvents
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult

    snap = IndicatorSnapshot(
        price=155.3,
        change_pct=1.2,
        rsi=68.2,
        sma_20=148.2,
        sma_50=142.1,
        sma_150=135.6,
        sma_200=128.4,
        high_52w=160.5,
    )
    tech = TechnicalResult(
        ticker="TEST",
        timestamp=datetime(2026, 6, 15),
        snapshot=snap,
        components={},
        total_score=0,
    )

    class _Sum:
        summary = "s"
        recommendation = "보유"
        confidence = 0.5
        rationale = "r"
        key_insights = []

    result = {
        "ticker": "TEST",
        "technical": tech,
        "technical_summary": _Sum(),
        "momentum_events": MomentumEvents(),
        "criteria_verdict": None,
        "chart_patterns": {},
        "factor_assessments": [],
        "scenarios": [],
    }
    out = format_deep_dive_output(result)
    assert "## 📊 Summary" in out
    assert "## 모멘텀" in out
    assert "## Event" in out
    assert "판단 요약" not in out
    assert out.index("## 📊 Summary") < out.index("## 모멘텀") < out.index("## Event")
