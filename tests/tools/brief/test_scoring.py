"""brief 랭킹/판정 순수 함수 테스트. I/O 없음."""

from src.tools.brief.models import (
    BUCKET_BUY_ELIGIBLE,
    BUCKET_HOLD_OK,
    BUCKET_HOLD_WARN,
    BUCKET_IMMINENT,
    BUCKET_LIQUIDATE,
    BUCKET_REDUCE,
    BUCKET_REJECTED,
    BriefItem,
)
from src.tools.brief.scoring import (
    BONUS_STOP_PROXIMITY,
    BONUS_SURGE,
    bucket_for,
    classify_watch,
    is_stop_proximate,
    rank,
    surge_reason,
)
from src.tools.playbook.models import GateCheck, GateResult


def _gate(met_flags: dict[str, bool | None], passed: bool = False) -> GateResult:
    checklist = [
        GateCheck(name=n, required=True, met=met_flags[n], reason=f"{n} 사유")
        for n in ("A", "B", "C", "E")
    ]
    return GateResult(passed=passed, checklist=checklist, quality_grade=None, veto_reason=None)


# ── classify_watch: 임박 = 필수 4중 정확히 3 충족 ──────────────────────────


def test_classify_watch_eligible():
    gate = _gate({"A": True, "B": True, "C": True, "E": True}, passed=True)
    assert classify_watch(gate) == ("eligible", None)


def test_classify_watch_imminent_3_of_4():
    gate = _gate({"A": True, "B": True, "C": True, "E": False})
    action, remaining = classify_watch(gate)
    assert action == "imminent"
    assert remaining == "E: E 사유"


def test_classify_watch_rejected_2_of_4():
    gate = _gate({"A": True, "B": True, "C": False, "E": False})
    assert classify_watch(gate) == ("rejected", None)


def test_classify_watch_none_counts_as_unmet():
    """met=None(데이터 없음)은 미충족으로 취급 — 3 True + 1 None = 임박."""
    gate = _gate({"A": True, "B": True, "C": True, "E": None})
    action, remaining = classify_watch(gate)
    assert action == "imminent"
    assert remaining.startswith("E:")


# ── bucket_for ──────────────────────────────────────────────────────────────


def test_bucket_mapping():
    assert bucket_for("holding", "liquidate") == BUCKET_LIQUIDATE
    assert bucket_for("watch", "eligible") == BUCKET_BUY_ELIGIBLE
    assert bucket_for("holding", "reduce") == BUCKET_REDUCE
    assert bucket_for("watch", "imminent") == BUCKET_IMMINENT
    assert bucket_for("holding", "hold", has_warn_signals=True) == BUCKET_HOLD_WARN
    assert bucket_for("watch", "rejected") == BUCKET_REJECTED
    assert bucket_for("holding", "hold", has_warn_signals=False) == BUCKET_HOLD_OK
    assert bucket_for("holding", "error") == BUCKET_HOLD_OK
    assert bucket_for("watch", "error") == BUCKET_HOLD_OK


# ── 가산 마커 ───────────────────────────────────────────────────────────────


def test_stop_proximate_within_3pct():
    assert is_stop_proximate(price=102.9, stop_price=100.0) is True
    assert is_stop_proximate(price=103.1, stop_price=100.0) is False
    assert is_stop_proximate(price=99.0, stop_price=100.0) is True  # 이미 이탈 → 근접
    assert is_stop_proximate(price=None, stop_price=100.0) is False
    assert is_stop_proximate(price=100.0, stop_price=None) is False


def test_surge_reason_direction():
    assert surge_reason("holding", -5.2) == "급변: 보유 급락"
    assert surge_reason("holding", 6.0) == "급변: 보유 급등"
    assert surge_reason("watch", 5.5) == "급변: 워치 상승 돌파"
    assert surge_reason("watch", -7.0) == "급변: 워치 급락"
    assert surge_reason("holding", 4.9) is None
    assert surge_reason("holding", None) is None


# ── rank: 버킷 절대 우선, 가산점은 동버킷 내 정렬 전용 ──────────────────────


def _item(ticker: str, bucket: int, bonus: int = 0) -> BriefItem:
    return BriefItem(ticker=ticker, kind="holding", action="hold", bucket=bucket, bonus=bonus)


def test_rank_bucket_absolute_priority():
    """축소(버킷3)+가산 110점이어도 청산(버킷1)을 역전하지 못한다."""
    reduce_boosted = _item("A", BUCKET_REDUCE, bonus=BONUS_STOP_PROXIMITY + BONUS_SURGE)
    liquidate_plain = _item("B", BUCKET_LIQUIDATE, bonus=0)
    ranked = rank([reduce_boosted, liquidate_plain])
    assert [i.ticker for i in ranked] == ["B", "A"]


def test_rank_bonus_breaks_tie_within_bucket():
    a = _item("A", BUCKET_HOLD_WARN, bonus=0)
    b = _item("B", BUCKET_HOLD_WARN, bonus=BONUS_STOP_PROXIMITY)
    ranked = rank([a, b])
    assert [i.ticker for i in ranked] == ["B", "A"]


def test_rank_is_stable_for_equal_keys():
    a = _item("A", BUCKET_HOLD_OK)
    b = _item("B", BUCKET_HOLD_OK)
    assert [i.ticker for i in rank([a, b])] == ["A", "B"]
