"""Chart provenance and shared strategy presentation boundaries."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.pipelines.strategy_analysis import AnalysisStrategyService, ChartBundleLoader
from src.pipelines.strategy_render import render_strategy_sections
from src.position.execution import check_entry_execution
from src.position.models import (
    AccountSnapshot,
    MarketOpenSnapshot,
    PositionSnapshot,
    QuantityStatus,
)
from src.storage.canonical import canonical_bytes
from src.strategies.models import (
    EntryIntent,
    EntryVerdict,
    ExitIntent,
    ExitVerdict,
    StrategyVerdict,
)
from src.tools.technical.scorecard_models import (
    AnalysisTriggerEvent,
    DataStatus,
    Direction,
    Evidence,
    Importance,
    Observation,
    ScoreDimension,
    TechnicalScorecard,
    TriggerStatus,
)


class MarketProvider:
    def __init__(self, frame):
        self.frame = frame
        self.requests = []

    async def get_price_history(self, ticker, period):
        self.requests.append((ticker, period))
        return self.frame


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ticker", "market_ticker"),
    [("AAPL", "SPY"), ("005930.KS", "^KS11"), ("035720.KQ", "^KQ11"), ("0167A0", "^KS11")],
)
async def test_loader_records_market_identity_and_unverified_listing(ticker, market_ticker):
    sessions = pd.date_range("2025-01-01", periods=5, freq="B")
    frame = pd.DataFrame(
        {
            "Open": [10] * 5,
            "High": [11] * 5,
            "Low": [9] * 5,
            "Close": [10] * 5,
            "Volume": [100] * 5,
        },
        index=sessions,
    )
    provider = MarketProvider(frame)
    bundle = await ChartBundleLoader(provider).load(
        ticker=ticker,
        technical=SimpleNamespace(raw_dataframe=frame.iloc[2:]),
        as_of=sessions[-1].date(),
    )

    assert provider.requests == [(market_ticker, "2y")]
    assert bundle.market_ticker == market_ticker
    assert bundle.instrument.coverage.listing_first_session is None
    assert bundle.instrument.coverage.complete is False
    assert bundle.instrument.coverage.actual_start == sessions[2].date()
    assert bundle.exchange_sessions[-4:] == (
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 1, 6),
        date(2025, 1, 7),
    )
    assert date(2025, 1, 1) not in bundle.exchange_sessions


@pytest.mark.asyncio
async def test_loader_marks_current_bar_provisional_from_observed_at():
    from src.strategies.models import BarFinality

    sessions = pd.date_range("2026-10-06", periods=3, freq="B")
    frame = pd.DataFrame(
        {
            "Open": [10] * 3,
            "High": [11] * 3,
            "Low": [9] * 3,
            "Close": [10] * 3,
            "Volume": [100] * 3,
        },
        index=sessions,
    )
    observed_at = datetime(2026, 10, 8, 15, tzinfo=ZoneInfo("America/New_York"))
    bundle = await ChartBundleLoader(MarketProvider(frame)).load(
        ticker="AAPL",
        technical=SimpleNamespace(raw_dataframe=frame),
        as_of=sessions[-1].date(),
        observed_at=observed_at,
    )

    assert bundle.instrument.bars[-1].finality is BarFinality.PROVISIONAL
    assert all(bar.finality is BarFinality.FINAL for bar in bundle.instrument.bars[:-1])


def test_renderer_keeps_new_section_order_and_detail_evidence():
    high = Evidence(
        code="risk",
        message="high risk evidence",
        observed_value=1,
        reference_value=None,
        importance=Importance.HIGH,
        source="test",
    )
    medium = Evidence(
        code="detail",
        message="medium detail evidence",
        observed_value=2,
        reference_value=None,
        importance=Importance.MEDIUM,
        source="test",
    )
    dimension = ScoreDimension(
        code="trend",
        score=60,
        raw_state_points=1,
        minimum_points=0,
        maximum_points=2,
        calculation_version="test",
        data_status=DataStatus.COMPLETE,
        coverage_pct=100,
        metrics={"slope": 2.4},
        observations=[
            Observation(
                code="risk",
                message="high risk",
                direction=Direction.RISING,
                importance=Importance.HIGH,
                source_metrics=["slope"],
                evidence=[high, medium],
            )
        ],
        score_contributions=[],
    )
    scorecard = TechnicalScorecard(
        version="test",
        ticker="AAPL",
        as_of=date(2025, 1, 7),
        trend=dimension,
        structure=dimension.model_copy(update={"code": "structure", "observations": []}),
        momentum=dimension.model_copy(update={"code": "momentum", "observations": []}),
        demand=dimension.model_copy(update={"code": "demand", "observations": []}),
        safety=dimension.model_copy(update={"code": "safety", "observations": []}),
        legacy_raw_total=None,
        legacy_adjusted_score=None,
    )

    compact = render_strategy_sections(scorecard, None, warning="market unavailable")
    detail = render_strategy_sections(scorecard, None, detail=True)

    headings = [
        "Technical Scorecard",
        "중요 상태 / Evidence",
        "최근 Analysis Trigger",
        "현재 Observation",
        "최근 Observation history",
        "최근 Signal history",
        "전략",
        "오늘 EntryOpportunity",
    ]
    assert [compact.index(heading) for heading in headings] == sorted(
        compact.index(heading) for heading in headings
    )
    assert "high risk" in compact
    assert "high risk evidence" in compact
    assert "medium detail evidence" not in compact
    assert "market unavailable" in compact
    assert "trend.slope: 2.4" in detail
    assert "high risk (rising)" in detail
    assert "medium detail evidence" in detail


def test_renderer_orders_recent_events_by_session():
    dimension = ScoreDimension(
        code="trend",
        score=50,
        raw_state_points=0,
        minimum_points=0,
        maximum_points=100,
        calculation_version="test",
        data_status=DataStatus.COMPLETE,
        coverage_pct=100,
        metrics={},
        observations=[],
        score_contributions=[],
    )
    scorecard = TechnicalScorecard(
        version="test",
        ticker="AAPL",
        as_of=date(2025, 1, 7),
        trend=dimension,
        structure=dimension,
        momentum=dimension,
        demand=dimension,
        safety=dimension,
        legacy_raw_total=None,
        legacy_adjusted_score=None,
    )
    scorecard.triggers = [
        AnalysisTriggerEvent(
            code=code,
            trigger_version="test",
            occurred_on=day,
            bars_ago=age,
            direction=None,
            source="test",
            observed_value=None,
            reference_value=None,
            status=TriggerStatus.ACTIVE,
            status_as_of=date(2025, 1, 7),
            status_changed_on=day,
            status_reason="active",
            expires_after_bars=None,
            invalidated_on=None,
            expired_on=None,
            evidence=[],
        )
        for code, day, age in [
            ("OLD_TRIGGER", date(2025, 1, 6), 1),
            ("NEW_TRIGGER", date(2025, 1, 7), 0),
        ]
    ]
    verdicts = [
        SimpleNamespace(
            strategy_id=name,
            entry=SimpleNamespace(
                intent=EntryIntent.WATCH,
                data_status=DataStatus.COMPLETE,
                reasons=[],
                opportunity=None,
            ),
            exit=SimpleNamespace(
                intent=ExitIntent.HOLD,
                data_status=DataStatus.COMPLETE,
                reasons=[],
            ),
            events=[SimpleNamespace(occurred_on=day, code=code, evidence=[])],
        )
        for name, day, code in [
            ("NEWER", date(2025, 1, 7), "NEW"),
            ("OLDER", date(2025, 1, 6), "OLD"),
        ]
    ]
    analysis = SimpleNamespace(
        exchange_sessions=(date(2025, 1, 6), date(2025, 1, 7)),
        strategy_run=SimpleNamespace(verdicts=verdicts, errors=[]),
        current_close=10,
        position_plan=None,
    )

    output = render_strategy_sections(scorecard, analysis)
    assert output.index("NEW_TRIGGER") < output.index("OLD_TRIGGER")
    assert "최근 Strategy Event" not in output


def _position_service(entry: EntryIntent, exit: ExitIntent):
    dimension = ScoreDimension(
        code="trend",
        score=50,
        raw_state_points=0,
        minimum_points=0,
        maximum_points=100,
        calculation_version="test",
        data_status=DataStatus.COMPLETE,
        coverage_pct=100,
        metrics={},
        observations=[],
        score_contributions=[],
    )
    scorecard = TechnicalScorecard(
        version="test",
        ticker="AAPL",
        as_of=date(2025, 1, 7),
        trend=dimension,
        structure=dimension,
        momentum=dimension,
        demand=dimension,
        safety=dimension,
        legacy_raw_total=None,
        legacy_adjusted_score=None,
    )
    verdict = StrategyVerdict(
        verdict_schema_version="1",
        strategy_id="PLAYBOOK_V1",
        strategy_version="1",
        ticker="AAPL",
        as_of=scorecard.as_of,
        entry=EntryVerdict(
            intent=entry, opportunity=None, data_status=DataStatus.COMPLETE, reasons=[]
        ),
        exit=ExitVerdict(intent=exit, data_status=DataStatus.COMPLETE, reasons=[]),
        events=[],
        strategy_state=None,
    )
    bundle = SimpleNamespace(
        exchange_sessions=(scorecard.as_of,),
        instrument=SimpleNamespace(bars=[SimpleNamespace(close=Decimal("10"))]),
        market=SimpleNamespace(),
    )

    class Loader:
        async def load(self, **kwargs):
            return bundle

    class Runner:
        def production_strategy_registry(self):
            return {"PLAYBOOK_V1": "1"}

        def run(self, bundle, *, legacy_result):
            return SimpleNamespace(scorecard=legacy_result.scorecard, verdicts=[verdict], errors=[])

    service = AnalysisStrategyService(chart_loader=Loader(), strategy_runner=Runner())
    return service, SimpleNamespace(scorecard=scorecard)


@pytest.mark.asyncio
@pytest.mark.parametrize(("exit", "expected_sell"), [(ExitIntent.REDUCE, 3), (ExitIntent.EXIT, 5)])
async def test_playbook_exit_plan_sells_from_real_holding_and_renders_quantity(exit, expected_sell):
    service, technical = _position_service(EntryIntent.ALLOW, exit)
    result = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(5)
    )

    assert result.position_plan.sell_quantity == expected_sell
    assert result.position_plan.buy_quantity == 0
    assert f"sell={expected_sell}" in render_strategy_sections(result.scorecard, result)


@pytest.mark.asyncio
async def test_holding_change_changes_only_position_plan():
    service, technical = _position_service(EntryIntent.WATCH, ExitIntent.REDUCE)
    small = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(1)
    )
    large = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(7)
    )

    assert canonical_bytes(small.scorecard) == canonical_bytes(large.scorecard)
    assert canonical_bytes(small.strategy_run.verdicts) == canonical_bytes(
        large.strategy_run.verdicts
    )
    assert small.position_plan.sell_quantity == 1
    assert large.position_plan.sell_quantity == 4


@pytest.mark.asyncio
async def test_buy_without_account_or_execution_is_unavailable():
    service, technical = _position_service(EntryIntent.ALLOW, ExitIntent.HOLD)
    account = AccountSnapshot(
        capital=Decimal("1000"), risk_budget=Decimal("100"), per_share_risk=Decimal("10")
    )
    missing_account = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(2)
    )
    missing_execution = await service.evaluate(
        "AAPL",
        technical,
        as_of=technical.scorecard.as_of,
        position=PositionSnapshot(2),
        account=account,
    )
    stale_check = check_entry_execution(
        strategy_run_id="stale-run",
        source_event_id=None,
        market_session=technical.scorecard.as_of,
        market=MarketOpenSnapshot(
            session=technical.scorecard.as_of,
            open_price=Decimal("10"),
            snapshot_hash="stale-market",
        ),
        policy_version="v1",
    )
    stale_execution = await service.evaluate(
        "AAPL",
        technical,
        as_of=technical.scorecard.as_of,
        position=PositionSnapshot(2),
        account=account,
        execution_check=stale_check,
    )

    for result in (missing_account, missing_execution, stale_execution):
        assert result.position_plan.quantity_status is QuantityStatus.UNAVAILABLE
        assert result.position_plan.buy_quantity is None
        assert "(unavailable)" in render_strategy_sections(result.scorecard, result)


@pytest.mark.asyncio
async def test_account_change_changes_buy_quantity_only_after_current_session_pass():
    service, technical = _position_service(EntryIntent.ALLOW, ExitIntent.HOLD)
    check = check_entry_execution(
        strategy_run_id="approved-run",
        source_event_id=None,
        market_session=date(2025, 1, 8),
        market=MarketOpenSnapshot(
            session=date(2025, 1, 8), open_price=Decimal("10"), snapshot_hash="market"
        ),
        policy_version="v1",
        checked_at=datetime(2025, 1, 8, 14, tzinfo=UTC),
    )
    small = await service.evaluate(
        "AAPL",
        technical,
        as_of=technical.scorecard.as_of,
        position=PositionSnapshot(0),
        account=AccountSnapshot(
            capital=Decimal("1000"), risk_budget=Decimal("100"), per_share_risk=Decimal("10")
        ),
        execution_check=check,
    )
    large = await service.evaluate(
        "AAPL",
        technical,
        as_of=technical.scorecard.as_of,
        position=PositionSnapshot(0),
        account=AccountSnapshot(
            capital=Decimal("2000"), risk_budget=Decimal("200"), per_share_risk=Decimal("10")
        ),
        execution_check=check,
    )

    assert canonical_bytes(small.scorecard) == canonical_bytes(large.scorecard)
    assert canonical_bytes(small.strategy_run.verdicts) == canonical_bytes(
        large.strategy_run.verdicts
    )
    assert small.position_plan.buy_quantity == 10
    assert large.position_plan.buy_quantity == 20


@pytest.mark.asyncio
async def test_service_evaluates_without_database_even_when_dsn_is_configured(monkeypatch):
    service, technical = _position_service(EntryIntent.WATCH, ExitIntent.HOLD)
    import psycopg

    monkeypatch.setenv("JARVIS_DB_DSN", "postgresql://unreachable")

    def reject_connection(*args, **kwargs):
        pytest.fail("chart-only strategy must not connect to PostgreSQL")

    monkeypatch.setattr(psycopg, "connect", reject_connection)
    result = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, pipeline="brief"
    )

    assert result.strategy_run.verdicts
    assert result.warning is None


@pytest.mark.asyncio
async def test_chart_load_failure_is_reraised_without_database_lifecycle():
    events = []

    class Loader:
        async def load(self, **kwargs):
            events.append("load")
            raise TimeoutError("provider timeout")

    service = AnalysisStrategyService(chart_loader=Loader())
    with pytest.raises(TimeoutError, match="provider timeout"):
        await service.evaluate("AAPL", SimpleNamespace(), as_of=date(2026, 10, 2))

    assert events == ["load"]


def test_analysis_service_has_no_database_lifecycle():
    import inspect

    source = inspect.getsource(AnalysisStrategyService)
    assert "persistence" not in source
    assert "strategy_" + "history" not in source


def test_strategy_history_subsystem_is_absent():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for prefix in ("src/storage", "tests/storage", "migrations"):
        assert not (root / prefix / ("strategy_" + "history")).exists()
    for path in (root / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("src.storage.strategy_" + "history")
            elif isinstance(node, ast.Import):
                assert all(
                    not item.name.startswith("src.storage.strategy_" + "history")
                    for item in node.names
                )


@pytest.mark.asyncio
async def test_production_two_year_chart_runs_v2_without_legacy_warmup():
    from src.strategies.models import EntryOpportunityStatus
    from src.tools.technical.models import ScoreHistoryPoint
    from tests.strategies.test_runner import _legacy_result

    sessions = pd.bdate_range("2024-01-02", periods=520)
    close = [100 + day * 0.1 for day in range(520)]
    frame = pd.DataFrame(
        {
            "Open": close,
            "High": [x + 1 for x in close],
            "Low": [x - 1 for x in close],
            "Close": close,
            "Volume": [1000] * 520,
        },
        index=sessions,
    )
    technical = _legacy_result(scorecard_as_of=sessions[-1].date())
    technical.raw_dataframe = frame
    technical.score_history = [
        ScoreHistoryPoint(
            date=str(sessions[-1].date()),
            close=close[-1],
            component_raw_total=40,
            adjusted_score=55,
            verdict_action="add",
            one_line_reason="상승 구조 유지",
        )
    ]
    technical.score_history_warning = "장중 값"
    result = await AnalysisStrategyService(
        chart_loader=ChartBundleLoader(MarketProvider(frame))
    ).evaluate("AAPL", technical, as_of=sessions[-1].date())
    assert result.warning is None
    assert [v.strategy_id for v in result.strategy_run.verdicts] == [
        "TECHNICAL_LEGACY",
        "PLAYBOOK_V1",
    ]
    signals = result.strategy_run.signal_bundles
    assert len(signals) == 1
    assert signals[0].strategy_version == "SWING_W150_V2"
    assert signals[0].data_status is DataStatus.COMPLETE
    assert signals[0].entry_opportunity.status is not EntryOpportunityStatus.NOT_EVALUATED
    assert result.score_history == tuple(technical.score_history)
    assert result.score_history_warning == "장중 값"


@pytest.fixture
def signal_analysis():
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from src.strategies.models import (
        EntryOpportunityStatus,
        ObservationCode,
        ObservationStatus,
        SignalEntryOpportunity,
        SignalFinality,
        StrategySignal,
        StrategySignalBundle,
        StructureStatus,
    )
    from src.strategies.observations import make_observation
    from src.strategies.observations.parameters import ObservationParameters
    from tests.strategies.test_runner import _legacy_result

    sessions = tuple(day.date() for day in pd.bdate_range("2025-01-01", periods=25))
    today = sessions[-1]
    high = Evidence(
        code="support",
        message="SMA150 support",
        observed_value=110,
        reference_value=110,
        importance=Importance.HIGH,
        source="SWING_W150_V2",
    )
    medium = high.model_copy(
        update={
            "code": "detail",
            "message": "medium signal evidence",
            "importance": Importance.MEDIUM,
        }
    )

    def observation(day, code=ObservationCode.PULLBACK_WATCH, active=False):
        return make_observation(
            ticker="AAPL",
            code=code,
            origin=day,
            params=ObservationParameters(),
            status_as_of=today,
            ended_on=None if active else day,
            status=ObservationStatus.ACTIVE if active else ObservationStatus.RESOLVED_TO_SIGNAL,
            evidence=[high, medium],
        )

    def signal(day, code="PULLBACK_REVERSAL_ENTRY"):
        return StrategySignal(
            signal_id=str(day),
            strategy_id="SWING_W150",
            strategy_version="SWING_W150_V2",
            parameter_set_version="params",
            parameter_fingerprint="fingerprint",
            code=code,
            occurred_on=day,
            finality=SignalFinality.FINAL,
            direction=Direction.RISING,
            signal_price=Decimal("110"),
            evidence=[high, medium],
            data_status=DataStatus.COMPLETE,
        )

    recent_signal = signal(sessions[-2])
    bundle = StrategySignalBundle(
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="params",
        parameter_fingerprint="fingerprint",
        ticker="AAPL",
        as_of=today,
        observation_history=[
            observation(sessions[-21], ObservationCode.POST_OVERHEAT_RECOVERY_WATCH),
            observation(sessions[-20], ObservationCode.POST_OVERHEAT_RECOVERY_WATCH),
            observation(sessions[-2]),
            observation(sessions[-1], active=True),
        ],
        signal_history=[
            signal(sessions[-21], "OLD_ENTRY"),
            signal(sessions[-20], "BOUNDARY_ENTRY"),
            recent_signal,
        ],
        current_signals=[],
        entry_opportunity=SignalEntryOpportunity(
            evaluation_as_of=today,
            finality=SignalFinality.FINAL,
            status=EntryOpportunityStatus.ALLOW,
            entry_signal=recent_signal,
            invalidated_by=None,
            age_bars=1,
            signal_price=Decimal("110"),
            execution_reference_price=None,
            extension_pct=Decimal("0.021"),
            market_regime="bull",
            structure_status=StructureStatus.VALID,
            evidence=[high, medium],
            policy_version="params",
        ),
        data_status=DataStatus.COMPLETE,
    )
    scorecard = _legacy_result(scorecard_as_of=today).scorecard
    run = SimpleNamespace(scorecard=scorecard, verdicts=[], signal_bundles=[bundle], errors=[])
    return AnalysisStrategyResult(scorecard, run, sessions, 111.32)


def _signal_position_service(signal_analysis, code, finality):
    from src.strategies.models import BarFinality
    from tests.strategies.test_playbook import _bundle

    chart = _bundle()
    bar = chart.instrument.bars[-1].model_copy(update={"finality": BarFinality(finality.value)})
    chart = chart.model_copy(
        update={
            "instrument": chart.instrument.model_copy(
                update={"bars": (*chart.instrument.bars[:-1], bar)}
            )
        }
    )
    source = signal_analysis.strategy_run.signal_bundles[0]
    signal = source.signal_history[-1].model_copy(
        update={
            "occurred_on": chart.as_of,
            "code": code,
            "finality": finality,
            "signal_price": bar.close,
        }
    )
    opportunity = source.entry_opportunity.model_copy(
        update={
            "evaluation_as_of": chart.as_of,
            "finality": finality,
            "entry_signal": signal,
            "age_bars": 0,
            "signal_price": bar.close,
            "execution_reference_price": bar.close,
        }
    )
    signals = source.model_copy(
        update={
            "as_of": chart.as_of,
            "signal_history": [signal],
            "current_signals": [signal],
            "entry_opportunity": opportunity,
        }
    )
    service, technical = _position_service(EntryIntent.ALLOW, ExitIntent.EXIT)
    technical.scorecard = technical.scorecard.model_copy(update={"as_of": chart.as_of})
    playbook = service.strategy_runner.run(chart, legacy_result=technical).verdicts

    class Loader:
        async def load(self, **kwargs):
            return chart

    class Runner:
        def run(self, bundle, *, legacy_result):
            return SimpleNamespace(
                scorecard=legacy_result.scorecard,
                verdicts=playbook,
                signal_bundles=[signals],
                errors=[],
            )

    return AnalysisStrategyService(Loader(), Runner()), technical


@pytest.mark.asyncio
@pytest.mark.parametrize("code,sell,target", [("OVERHEAT_CORRECTION", 3, 2), ("SMA150_EXIT", 5, 0)])
async def test_service_uses_current_signal_instead_of_playbook_for_real_position(
    signal_analysis, code, sell, target
):
    from src.strategies.models import SignalFinality

    service, technical = _signal_position_service(signal_analysis, code, SignalFinality.PROVISIONAL)
    result = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(5)
    )
    assert (result.position_plan.sell_quantity, result.position_plan.target_quantity) == (
        sell,
        target,
    )
    assert result.position_plan.signal_finality is SignalFinality.PROVISIONAL


@pytest.mark.asyncio
async def test_service_provisional_entry_uses_supplied_current_snapshot_and_account(
    signal_analysis,
):
    from src.position import models
    from src.strategies.models import SignalFinality

    service, technical = _signal_position_service(
        signal_analysis, "TREND_BREAKOUT_ENTRY", SignalFinality.PROVISIONAL
    )
    snapshot = models.MarketSnapshot(
        session=technical.scorecard.as_of, price=Decimal("200"), snapshot_hash="intraday-market"
    )
    account = AccountSnapshot(
        capital=Decimal("1000"), risk_budget=Decimal("100"), per_share_risk=Decimal("10")
    )
    small = await service.evaluate(
        "AAPL",
        technical,
        as_of=technical.scorecard.as_of,
        position=PositionSnapshot(1),
        account=account,
        market_snapshot=snapshot,
    )
    large = await service.evaluate(
        "AAPL",
        technical,
        as_of=technical.scorecard.as_of,
        position=PositionSnapshot(4),
        account=account,
        market_snapshot=snapshot,
    )
    assert (small.position_plan.buy_quantity, large.position_plan.buy_quantity) == (4, 1)
    assert small.position_plan.signal_finality is SignalFinality.PROVISIONAL
    assert small.position_plan.market_snapshot_hash == "intraday-market"
    assert small.position_plan.calculated_at.tzinfo is not None
    assert canonical_bytes(small.strategy_run.signal_bundles) == canonical_bytes(
        large.strategy_run.signal_bundles
    )


def _analysis_with_position_plan(signal_analysis, finality):
    from dataclasses import replace

    from src.position.models import DirectiveKind, PositionDirective, PositionPlan

    return replace(
        signal_analysis,
        position_plan=PositionPlan(
            directive=PositionDirective(DirectiveKind.REDUCE_CURRENT_BY_FRACTION, 0.5),
            current_quantity=5,
            target_quantity=2,
            buy_quantity=0,
            sell_quantity=3,
            quantity_status=QuantityStatus.AVAILABLE,
            signal_finality=finality,
            calculated_at=datetime(2025, 2, 4, 15, tzinfo=UTC) if finality else None,
            market_snapshot_hash="0123456789abcdef" * 4 if finality else None,
        ),
    )


@pytest.mark.parametrize("detail", [False, True])
@pytest.mark.parametrize("finality", ["provisional", "final"])
def test_position_plan_displays_finality_and_detail_reproduction_metadata(
    signal_analysis, finality, detail
):
    from src.strategies.models import SignalFinality

    analysis = _analysis_with_position_plan(signal_analysis, SignalFinality(finality))
    rendered = render_strategy_sections(analysis.scorecard, analysis, detail=detail)
    position_section = rendered.split("### Position Plan\n", 1)[1]
    assert f"signal_finality={finality.upper()}" in position_section
    assert ("장중 후보" if finality == "provisional" else "확정") in position_section
    assert "current=5, target=2, buy=0, sell=3 (available)" in position_section
    if detail:
        assert "calculated_at=2025-02-04T15:00:00+00:00" in position_section
        assert "market_snapshot_hash=" + "0123456789abcdef" * 4 in position_section
    else:
        assert "calculated_at=" not in position_section
        assert "market_snapshot_hash=" not in position_section
        assert "0123456789abcdef" not in position_section


@pytest.mark.parametrize("detail", [False, True])
def test_position_plan_without_signal_metadata_preserves_playbook_output(signal_analysis, detail):
    analysis = _analysis_with_position_plan(signal_analysis, None)
    rendered = render_strategy_sections(analysis.scorecard, analysis, detail=detail)
    position_section = rendered.split("### Position Plan\n", 1)[1]
    assert position_section == (
        "- reduce_current_by_fraction: current=5, target=2, buy=0, sell=3 (available)"
    )


@pytest.mark.parametrize("detail", [False, True])
@pytest.mark.parametrize("opportunity_evidence", ["mixed", "medium_only", "medium_and_high"])
def test_three_surfaces_show_same_core_strategy_content(
    signal_analysis, detail, opportunity_evidence
):
    from src.cli.main import format_deep_dive_output
    from src.llm.models import TechnicalSummaryOutput
    from src.pipelines.brief import BriefPipeline
    from src.pipelines.quick_check import QuickCheckPipeline
    from src.strategies.models import ObservationCode, ObservationStatus, SignalFinality
    from src.strategies.observations import make_observation
    from src.strategies.observations.parameters import PRODUCT_OBSERVATION_PARAMETERS
    from src.tools.brief.models import BUCKET_HOLD_OK, BriefItem
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult

    signal_analysis = _analysis_with_position_plan(signal_analysis, SignalFinality.PROVISIONAL)
    bundle = signal_analysis.strategy_run.signal_bundles[0]
    bundle.observation_history.extend(
        [
            make_observation(
                ticker="AAPL",
                code=ObservationCode.MOMENTUM_DECELERATION,
                origin=bundle.as_of,
                params=PRODUCT_OBSERVATION_PARAMETERS,
                evidence=[
                    Evidence(
                        code="MOMENTUM_DECELERATION_CURRENT",
                        message="모멘텀 현재 실측",
                        observed_value=109,
                        reference_value=110,
                        importance=Importance.HIGH,
                        source="OBSERVATION_V1",
                    )
                ],
            ),
            make_observation(
                ticker="AAPL",
                code=ObservationCode.HIGHER_HIGH,
                origin=bundle.as_of,
                params=PRODUCT_OBSERVATION_PARAMETERS,
                status=ObservationStatus.RESOLVED,
                confirmed_on=bundle.as_of,
                ended_on=bundle.as_of,
                evidence=bundle.observation_history[-1].evidence,
            ),
        ]
    )

    if opportunity_evidence != "mixed":
        opportunity = signal_analysis.strategy_run.signal_bundles[0].entry_opportunity
        high, medium = opportunity.evidence
        opportunity.evidence = [
            medium.model_copy(update={"message": "opportunity primary evidence"})
        ]
        if opportunity_evidence == "medium_and_high":
            opportunity.evidence.append(
                high.model_copy(update={"message": "opportunity high evidence"})
            )
        opportunity.evidence.append(
            medium.model_copy(update={"message": "opportunity secondary evidence"})
        )

    technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime(2025, 2, 4),
        snapshot=IndicatorSnapshot(price=111.32, change_pct=1.2),
        components={},
        scorecard=signal_analysis.scorecard,
    )
    check = QuickCheckPipeline(None).format_output(
        {
            "ticker": "AAPL",
            "success": True,
            "scorecard": signal_analysis.scorecard,
            "strategy_analysis": signal_analysis,
            "price": 111.32,
            "change_pct": 1.2,
            "total_score": 50,
            "assessment": "hold",
            "confidence": 50,
            "signals": [],
            "warnings": [],
            "components": [],
            "indicators": {},
        },
        detailed_strategy=detail,
    )
    analyze = format_deep_dive_output(
        {
            "ticker": "AAPL",
            "technical": technical,
            "scorecard": signal_analysis.scorecard,
            "strategy_analysis": signal_analysis,
            "technical_summary": TechnicalSummaryOutput(
                summary="hold",
                recommendation="hold",
                confidence=0.5,
                rationale="test",
                key_insights=[],
            ),
        },
        detailed_strategy=detail,
    )
    item = BriefItem(
        ticker="AAPL",
        kind="watch",
        action="rejected",
        bucket=BUCKET_HOLD_OK,
        scorecard=signal_analysis.scorecard,
        strategy_analysis=signal_analysis,
    )
    brief = BriefPipeline.__new__(BriefPipeline).format_output(
        {"date": technical.timestamp, "macro": None, "items": [item]}, detailed_strategy=detail
    )
    common = render_strategy_sections(signal_analysis.scorecard, signal_analysis, detail=detail)
    for rendered in (check, analyze, brief):
        assert common in rendered
        for text in (
            "현재 Observation",
            "최근 Observation history",
            "최근 Signal history",
            "PULLBACK_WATCH",
            "PULLBACK_REVERSAL_ENTRY",
            "오늘 EntryOpportunity",
            "ALLOW",
            "SMA150 support",
            "rising",
            f"{signal_analysis.exchange_sessions[-20]} SWING_W150 POST_OVERHEAT_RECOVERY_WATCH",
            "BOUNDARY_ENTRY",
            "확장 +2.1%",
            "cycle / support",
            "Positive Observations",
            "Risk Observations",
            "당일 EVENT",
            "MOMENTUM_DECELERATION — 상승 모멘텀 약화 지속",
            "HIGHER_HIGH — 직전 고점보다 높은 고점 확인",
            "현재 실측: 모멘텀 현재 실측 (관측값=109, 기준값=110)",
        ):
            assert text in rendered
        old_watch = (
            f"{signal_analysis.exchange_sessions[-21]} SWING_W150 POST_OVERHEAT_RECOVERY_WATCH"
        )
        assert (old_watch in rendered) is detail
        assert ("OLD_ENTRY" in rendered) is detail
        assert "medium signal evidence" in rendered
        position_section = rendered.split("### Position Plan\n", 1)[1]
        assert "signal_finality=PROVISIONAL" in position_section
        assert "장중 후보" in position_section
        assert ("calculated_at=2025-02-04T15:00:00+00:00" in position_section) is detail
        assert ("market_snapshot_hash=" + "0123456789abcdef" * 4 in position_section) is detail
        if opportunity_evidence != "mixed":
            assert rendered.count("opportunity primary evidence") == 1
            assert "opportunity secondary evidence" in rendered
        if opportunity_evidence == "medium_and_high":
            assert rendered.count("opportunity high evidence") == 1


def test_observation_and_signal_history_are_separate(signal_analysis):
    rendered = render_strategy_sections(signal_analysis.scorecard, signal_analysis)
    current = rendered.split("### 현재 Observation\n")[1].split("### 최근 Observation history")[0]
    observations = rendered.split("### 최근 Observation history")[1].split(
        "### 최근 Signal history"
    )[0]
    signals = rendered.split("### 최근 Signal history")[1].split("### 전략")[0]

    assert "ACTIVE" in current
    assert "RESOLVED_TO_SIGNAL" not in current
    assert "PULLBACK_WATCH" in observations
    assert "RESOLVED_TO_SIGNAL" in observations
    assert "PULLBACK_REVERSAL_ENTRY" not in observations
    assert "PULLBACK_REVERSAL_ENTRY [FINAL] (rising)" in signals
    assert "PULLBACK_WATCH" not in signals


def test_default_output_explains_signal_opportunity_and_five_day_score_history(
    signal_analysis,
):
    from dataclasses import replace

    from src.strategies.models import EntryOpportunityStatus
    from src.tools.technical.models import ScoreHistoryPoint

    bundle = signal_analysis.strategy_run.signal_bundles[0]
    signal = bundle.signal_history[-1].model_copy(
        update={
            "evidence": [
                Evidence(
                    code="PULLBACK_REVERSAL_ENTRY",
                    message="pullback reversal entry",
                    observed_value=219.34,
                    reference_value=213.67,
                    importance=Importance.HIGH,
                    source="SWING_W150_V2",
                ),
                Evidence(
                    code="SMA_50",
                    message="sma 50",
                    observed_value=219.34,
                    reference_value=213.67,
                    importance=Importance.HIGH,
                    source="SWING_W150_V2",
                ),
                Evidence(
                    code="SMA_50_SLOPE_DIRECTION_RISING",
                    message="sma 50 slope direction rising",
                    observed_value=1.25,
                    reference_value=0,
                    importance=Importance.HIGH,
                    source="SWING_W150_V2",
                ),
            ]
        }
    )
    bundle.signal_history[-1] = signal
    opportunity = bundle.entry_opportunity.model_copy(
        update={
            "status": EntryOpportunityStatus.WATCH,
            "extension_pct": Decimal("0.051"),
            "evidence": [
                Evidence(
                    code="ENTRY_WATCH",
                    message="entry watch",
                    observed_value=0.051,
                    reference_value=0.05,
                    importance=Importance.MEDIUM,
                    source="SWING_W150_ENTRY_OPPORTUNITY_V2",
                )
            ],
        }
    )
    bundle.entry_opportunity = opportunity
    scores = tuple(
        ScoreHistoryPoint(
            date=f"2025-02-{day:02d}",
            close=100 + day,
            component_raw_total=raw,
            adjusted_score=adjusted,
            verdict_action=action,
            one_line_reason=reason,
            new_entry_allowed=allowed,
            driver_components=[driver],
            change_drivers=[change],
            events=[event],
            cautions=[caution],
        )
        for day, raw, adjusted, action, reason, allowed, driver, change, event, caution in (
            (
                3,
                90,
                103,
                "buy",
                "추세가 강하게 유지",
                True,
                "trend +40",
                "trend +10",
                "돌파",
                "과열 주의",
            ),
            (
                4,
                85,
                95,
                "add",
                "상승 구조 유지",
                True,
                "structure +30",
                "momentum -8",
                "지지 확인",
                "없음",
            ),
            (
                5,
                100,
                115,
                "buy",
                "수급 회복",
                True,
                "demand +35",
                "demand +20",
                "거래량 증가",
                "과열 주의",
            ),
            (
                6,
                60,
                65,
                "watch",
                "단기 조정",
                False,
                "risk -30",
                "risk -50",
                "cRSI 이탈",
                "신규 진입 대기",
            ),
            (
                7,
                65,
                70,
                "add",
                "지지선 반등",
                True,
                "trend +20",
                "trend +5",
                "SMA50 지지",
                "거래량 확인",
            ),
        )
    )
    analysis = replace(
        signal_analysis,
        score_history=scores,
        score_history_warning="5일 중 1일은 장중 값",
    )

    rendered = render_strategy_sections(analysis.scorecard, analysis)
    signal_section = rendered.split("최근 Signal history — 20거래일", 1)[1].split("### 전략", 1)[0]
    opportunity_section = rendered.split("오늘 EntryOpportunity", 1)[1].split(
        "### 최근 5거래일 Technical Score", 1
    )[0]
    score_section = rendered.split("### 최근 5거래일 Technical Score", 1)[1].split(
        "### 중요 상태 / Evidence", 1
    )[0]

    assert "발생 원인: 눌림목 지지 후 반등 진입 조건 충족" in signal_section
    assert "근거: SMA50 지지 확인" in signal_section
    assert "근거: SMA50 기울기 방향 상승" in signal_section
    assert "관측값=219.34" in signal_section
    assert "상태 원인: 상승장·구조 유효, 확장 +5.1%가 허용 상한 +5.0% 초과" in opportunity_section
    assert "근거: 허용 이격 초과 또는 시장 조건 대기" in opportunity_section
    assert "관측값=0.051, 기준값=0.05" in opportunity_section
    assert score_section.count("2025-02-") == 5
    assert "2025-02-07: 70점 (전일 +5) — add" in score_section
    for text in (
        "이유: 지지선 반등",
        "주요 구성: trend +20",
        "변화: trend +5",
        "이벤트: SMA50 지지",
        "주의: 거래량 확인",
        "신규진입: 가능",
        "5일 중 1일은 장중 값",
    ):
        assert text in score_section


@pytest.mark.parametrize("detail", [False, True])
@pytest.mark.parametrize(
    ("age", "label"),
    [(0, "Signal 종가 추정 100"), (1, "다음 실제 거래 가능 시가 104")],
)
def test_real_opportunity_price_basis_matches_all_three_surfaces(age, label, detail):
    from src.cli.main import format_deep_dive_output
    from src.llm.models import TechnicalSummaryOutput
    from src.pipelines.brief import BriefPipeline
    from src.pipelines.quick_check import QuickCheckPipeline
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from src.strategies.entry_opportunity import evaluate_signal_entry_opportunity
    from src.strategies.swing_w150.parameters import SwingW150Parameters
    from src.tools.brief.models import BUCKET_HOLD_OK, BriefItem
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult
    from tests.strategies.test_entry_opportunity import _v2_bundle, _v2_signal
    from tests.strategies.test_runner import _legacy_result

    chart = _v2_bundle(current_open=104)
    source = _v2_signal(chart.instrument.bars[-1 - age].session_date)
    opportunity = evaluate_signal_entry_opportunity([source], chart, SwingW150Parameters())
    assert opportunity.age_bars == age
    assert opportunity.execution_reference_price == Decimal("100" if age == 0 else "104")
    technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.combine(chart.as_of, datetime.min.time()),
        snapshot=IndicatorSnapshot(price=100, change_pct=0),
        components={},
        scorecard=_legacy_result(scorecard_as_of=chart.as_of).scorecard,
    )
    run = SimpleNamespace(
        verdicts=[],
        errors=[],
        signal_bundles=[
            SimpleNamespace(
                strategy_id="SWING_W150",
                signal_history=[source],
                observation_history=[],
                entry_opportunity=opportunity,
            )
        ],
    )
    analysis = AnalysisStrategyResult(technical.scorecard, run, chart.exchange_sessions, 100)
    check = QuickCheckPipeline(None).format_output(
        {
            "ticker": "AAPL",
            "success": True,
            "scorecard": technical.scorecard,
            "strategy_analysis": analysis,
            "price": 100,
            "change_pct": 0,
            "total_score": 50,
            "assessment": "hold",
            "confidence": 50,
            "signals": [],
            "warnings": [],
            "components": [],
            "indicators": {},
        },
        detailed_strategy=detail,
    )
    analyze = format_deep_dive_output(
        {
            "ticker": "AAPL",
            "technical": technical,
            "scorecard": technical.scorecard,
            "strategy_analysis": analysis,
            "technical_summary": TechnicalSummaryOutput(
                summary="hold",
                recommendation="hold",
                confidence=0.5,
                rationale="test",
                key_insights=[],
            ),
        },
        detailed_strategy=detail,
    )
    item = BriefItem(
        ticker="AAPL",
        kind="watch",
        action="rejected",
        bucket=BUCKET_HOLD_OK,
        scorecard=technical.scorecard,
        strategy_analysis=analysis,
    )
    brief = BriefPipeline.__new__(BriefPipeline).format_output(
        {"date": technical.timestamp, "macro": None, "items": [item]},
        detailed_strategy=detail,
    )
    for rendered in (check, analyze, brief):
        section = rendered.split("### 오늘 EntryOpportunity\n", 1)[1]
        assert label in section
        if age == 0:
            assert "거래 가능 시가" not in section
            assert "다음 거래일 시가" not in section


def test_production_output_omits_obsolete_overheat_placeholder(signal_analysis):
    rendered = render_strategy_sections(signal_analysis.scorecard, signal_analysis)

    assert "Planned Strategy" not in rendered
    assert "OVERHEAT_CYCLE_V1 not_implemented" not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize("provisional", [False, True])
async def test_service_evaluates_entry_signal_performance_on_demand(signal_analysis, provisional):
    from src.strategies.models import BarFinality
    from tests.strategies.test_signal_performance import chart

    run = signal_analysis.strategy_run
    signal_bundle = run.signal_bundles[0]
    source = signal_bundle.signal_history[-1]
    today = signal_bundle.as_of
    signal_bundle.signal_history = [
        source,
        source.model_copy(
            update={"signal_id": "exit", "code": "SMA150_EXIT", "occurred_on": today}
        ),
    ]
    bundle = chart(
        [
            (source.occurred_on, "109", "110", BarFinality.FINAL),
            (today, "120", "132", BarFinality.PROVISIONAL if provisional else BarFinality.FINAL),
        ]
    )

    class Loader:
        async def load(self, **kwargs):
            return bundle

    class Runner:
        def run(self, bundle, **kwargs):
            return run

    result = await AnalysisStrategyService(Loader(), Runner()).evaluate(
        "AAPL", SimpleNamespace(), as_of=today
    )
    assert len(result.signal_performances) == 1
    performance = result.signal_performances[0]
    assert performance.signal_id == str(source.occurred_on)
    assert performance.estimated_return_from_signal_close == Decimal("0.2")
    assert performance.executed_return_from_next_tradable_open == Decimal("0.1")
    compact = render_strategy_sections(result.scorecard, result)
    assert "Signal 종가 추정 +20.0%" in compact
    assert "다음 실제 거래 가능 시가 체결 +10.0%" in compact
    assert "signal_close_estimate" in compact
    assert "next_open_actual" in compact
    if provisional:
        assert performance.estimated_data_status is DataStatus.PARTIAL
        assert performance.executed_data_status is DataStatus.PARTIAL
        assert compact.count("PARTIAL (PROVISIONAL_EVALUATION_CLOSE)") == 2
    detailed = render_strategy_sections(result.scorecard, result, detail=True)
    assert f"signal_id={source.signal_id}" in detailed
    assert "parameter_fingerprint=fingerprint" in detailed


def test_renderer_distinguishes_missing_execution_reason(signal_analysis):
    from dataclasses import replace

    from src.strategies.models import BarFinality
    from src.strategies.signal_performance import evaluate_signal_performance
    from tests.strategies.test_signal_performance import chart

    source = signal_analysis.strategy_run.signal_bundles[0].signal_history[-1]
    performance = evaluate_signal_performance(
        source, chart([(source.occurred_on, "109", "110", BarFinality.FINAL)])
    )
    analysis = replace(signal_analysis, signal_performances=(performance,))
    rendered = render_strategy_sections(analysis.scorecard, analysis)
    assert "Signal 종가 추정 +0.0%" in rendered
    assert "다음 실제 거래 가능 시가 체결 NOT_EVALUATED" in rendered
    assert "NEXT_TRADABLE_BAR_UNAVAILABLE" in rendered
    assert "signal_id=" not in rendered
