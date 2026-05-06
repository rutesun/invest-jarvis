from types import SimpleNamespace
from typing import TypedDict

from pydantic import BaseModel, Field


class FactorAssessment(BaseModel):
    factor_type: str
    role: str
    freshness_score: int = Field(ge=0, le=5)
    magnitude_score: int = Field(ge=0, le=5)
    actionability_score: int = Field(ge=0, le=5)
    total_score: int = Field(ge=0, le=15)
    headline: str | None = None
    summary: str
    role_reason: str
    evidence: list[str]
    bias: str = "neutral"


class AnalyzeDecisionSummary(BaseModel):
    leader: str
    core_variables: list[str]
    action: str
    timing: str
    action_sentence: str
    defer_reason: str | None = None


class AnalyzeScenario(BaseModel):
    name: str
    trigger_price_levels: list[str]
    confirming_factors: list[str]
    invalidation_conditions: list[str]
    expected_path: str
    recommended_action: str


class AnalyzeDecisionBundle(BaseModel):
    summary: AnalyzeDecisionSummary
    factor_assessments: list[FactorAssessment]
    scenarios: list[AnalyzeScenario]


class FactorScoreEntry(TypedDict):
    factor_type: str
    total_score: int


_POSITIVE_EVENT_KEYWORDS = ("계약", "수주", "승인", "투자", "자사주", "자기주식")
_NEGATIVE_EVENT_KEYWORDS = ("유상증자", "소송", "내부자매도", "횡령", "하향", "리콜")
_MIXED_CORE_PRIORITY = {
    "technical": 0,
    "flow": 1,
    "event": 2,
    "valuation": 3,
}


def classify_leader_label(factor_scores: list[FactorScoreEntry]) -> str:
    ranked = sorted(factor_scores, key=lambda item: item["total_score"], reverse=True)

    if len(ranked) < 2:
        return "판단 보류"

    first = ranked[0]["total_score"]
    second = ranked[1]["total_score"]

    if first < 7:
        return "판단 보류"

    if first - second < 2:
        return "혼합"

    return ranked[0]["factor_type"]


def _compact_summary(text: str, limit: int = 18) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."


def _pick_core_variable_label(assessment: FactorAssessment) -> str:
    return assessment.headline or _compact_summary(assessment.summary)


def _mixed_core_variable_sort_key(assessment: FactorAssessment) -> tuple[int, int, int]:
    weighted_score = assessment.total_score + (
        1 if assessment.factor_type == "technical" and assessment.total_score > 0 else 0
    )
    return (
        -weighted_score,
        _MIXED_CORE_PRIORITY.get(assessment.factor_type, 99),
        -assessment.total_score,
    )


def _technical_headline(total_score: int, rsi: float | None, bias: str) -> str:
    if bias == "bearish":
        return "추세 약화"
    if rsi is not None and rsi >= 80:
        return "단기 과열"
    if total_score >= 100:
        return "신고가 돌파"
    return "가격 모멘텀"


def _event_headline(total_score: int, bias: str, evidence: list[str]) -> str:
    if total_score == 0:
        return "신규 재료 제한적"
    if bias == "bearish":
        return "규제 리스크"
    if any("계약" in item or "수주" in item for item in evidence):
        return "공급계약 재료"
    if any("승인" in item for item in evidence):
        return "승인 모멘텀"
    return "이벤트 부각"


def _flow_headline(score: int, foreign_positive: bool, institution_positive: bool) -> str:
    if score == 0:
        return "수급 약함"
    if foreign_positive and institution_positive:
        return "외인·기관 동행"
    if institution_positive:
        return "기관 매수 우위"
    if foreign_positive:
        return "외인 매수 우위"
    return "수급 엇갈림"


def _valuation_headline(valuation: str, confidence: float) -> str:
    if confidence < 0.45:
        return "재무 데이터 부족"
    if confidence < 0.7:
        return "재무 판단 유보"
    if valuation == "적정":
        return "밸류 중립"
    if valuation == "저평가":
        return "밸류 매력"
    return "고평가 부담"


def build_technical_assessment(
    total_score: int,
    rsi: float | None,
    chart_patterns: list[dict],
) -> FactorAssessment:
    detected_patterns = [pattern for pattern in chart_patterns if pattern.get("detected")]
    freshest_pattern = min(
        detected_patterns,
        key=lambda pattern: pattern.get("days_ago", 10**9),
        default=None,
    )

    rsi_evidence = f"RSI {rsi:.1f}" if rsi is not None else "RSI 없음"
    stale_pattern_days = freshest_pattern.get("days_ago", 0) if freshest_pattern else 0
    stale_pattern_name = freshest_pattern.get("pattern_name") if freshest_pattern else None

    absolute_score = abs(total_score)
    if absolute_score >= 100:
        score = 11
        role = "주도"
    elif absolute_score >= 40:
        score = 8
        role = "보조"
    else:
        score = 0
        role = "참고"

    stale_pattern_note = None
    if stale_pattern_days > 120 and score > 0:
        stale_pattern_note = f"{stale_pattern_days}일 전 {stale_pattern_name} 패턴이라 현재 액션은 최근 추세를 더 우선해야 함"
        if absolute_score >= 100:
            score = 8
            role = "보조"
        else:
            score = 6
            role = "참고"

    if freshest_pattern and freshest_pattern.get("days_ago", 0) > 60 and score >= 10:
        score = 8
        role = "보조"

    if total_score < 0:
        summary = "가격과 모멘텀이 현재 약세 흐름을 직접 설명함"
        role_reason = "지지선 이탈/추세 약화가 확인돼 반등보다 방어 판단에 더 가까움"
        bias = "bearish"
    elif score == 0:
        summary = "기술 신호의 방향성이 아직 약함"
        role_reason = "가격과 모멘텀이 액션을 단정할 만큼 강하지 않음"
        bias = "neutral"
    else:
        summary = "가격과 모멘텀이 현재 흐름을 직접 설명함"
        role_reason = "신고가/거래량/추세 지표가 현재 액션과 직접 연결됨"
        bias = "bullish"

    if stale_pattern_note:
        role_reason = stale_pattern_note

    return FactorAssessment(
        factor_type="technical",
        role=role,
        freshness_score=2 if stale_pattern_note else 4 if score > 0 else 1,
        magnitude_score=4 if score > 0 else 1,
        actionability_score=2 if stale_pattern_note else 3 if score > 0 else 1,
        total_score=score,
        headline=_technical_headline(total_score, rsi, bias),
        summary=(
            "기술 신호는 살아 있으나 오래된 패턴은 참고용"
            if stale_pattern_note and score > 0
            else summary
        ),
        role_reason=role_reason,
        evidence=[
            item
            for item in [
                f"technical total_score={total_score}",
                rsi_evidence,
                (
                    f"{stale_pattern_name} {stale_pattern_days}일 전"
                    if stale_pattern_note and stale_pattern_name
                    else None
                ),
            ]
            if item is not None
        ],
        bias=bias,
    )


def build_event_assessment(
    news_titles: list[str],
    disclosure_items: list[dict] | None,
) -> FactorAssessment:
    usable_disclosures = [
        item
        for item in (disclosure_items or [])
        if isinstance(item.get("description"), str) and item["description"].strip()
    ]
    has_disclosure = bool(usable_disclosures)
    evidence_texts = news_titles + [item["description"] for item in usable_disclosures]
    positive_signal = any(
        keyword in text for text in evidence_texts for keyword in _POSITIVE_EVENT_KEYWORDS
    )
    negative_signal = any(
        keyword in text for text in evidence_texts for keyword in _NEGATIVE_EVENT_KEYWORDS
    )
    directional_disclosure = has_disclosure and (positive_signal or negative_signal)
    total_score = (
        10 if news_titles and has_disclosure else 7 if news_titles or directional_disclosure else 0
    )
    role = "주도" if total_score >= 10 else "보조" if total_score >= 7 else "참고"
    if news_titles and has_disclosure:
        reason = "뉴스와 공시 메타데이터가 같은 방향으로 확인됨"
    elif directional_disclosure:
        reason = "공시 메타데이터만으로도 신규 이벤트가 확인됨"
    elif has_disclosure:
        reason = "공시는 있으나 현재 액션으로 연결할 방향성은 제한적임"
    elif news_titles:
        reason = "뉴스는 있으나 신규 공시 확인은 제한적임"
    else:
        reason = "유의미한 이벤트 부재"

    disclosure_evidence = [item["description"] for item in usable_disclosures[:1]]
    summary = (
        news_titles[0]
        if news_titles
        else disclosure_evidence[0]
        if disclosure_evidence
        else "유의미한 이벤트 부재"
    )
    if negative_signal and not positive_signal:
        bias = "bearish"
    elif total_score > 0:
        bias = "bullish"
    else:
        bias = "neutral"

    return FactorAssessment(
        factor_type="event",
        role=role,
        freshness_score=5 if (news_titles or has_disclosure) else 0,
        magnitude_score=4 if (positive_signal or negative_signal) else 2 if total_score > 0 else 0,
        actionability_score=4 if has_disclosure else 2 if news_titles else 0,
        total_score=total_score,
        headline=_event_headline(total_score, bias, news_titles[:2] + disclosure_evidence),
        summary=summary,
        role_reason=reason,
        evidence=news_titles[:2] + disclosure_evidence,
        bias=bias,
    )


def build_flow_assessment(flow_data) -> FactorAssessment:
    if flow_data is None or not getattr(flow_data, "entries", None):
        return FactorAssessment(
            factor_type="flow",
            role="참고",
            freshness_score=0,
            magnitude_score=0,
            actionability_score=0,
            total_score=0,
            summary="유의미한 수급 부재",
            role_reason="수급 데이터가 없거나 방향성이 약함",
            evidence=[],
        )

    foreign_positive = flow_data.foreign_direction_5d == "매수"
    institution_positive = flow_data.institution_direction_5d == "매수"

    if foreign_positive and institution_positive:
        score = 10
        role = "주도"
        reason = "외인과 기관이 같은 방향으로 수급을 밀어줌"
    elif foreign_positive or institution_positive:
        score = 7
        role = "보조"
        reason = "한 축의 수급은 우호적이지만 일치도는 제한적임"
    else:
        score = 0
        role = "참고"
        reason = "외인과 기관 수급이 모두 약함"

    return FactorAssessment(
        factor_type="flow",
        role=role,
        freshness_score=4,
        magnitude_score=4 if foreign_positive and institution_positive else 2,
        actionability_score=4 if score >= 7 else 1,
        total_score=score,
        headline=_flow_headline(score, foreign_positive, institution_positive),
        summary="외인/기관 수급이 현재 흐름을 뒷받침함" if score >= 7 else "수급 뒷받침이 약함",
        role_reason=reason,
        evidence=[
            f"외인 5일: {flow_data.foreign_direction_5d}",
            f"기관 5일: {flow_data.institution_direction_5d}",
            f"외인 순매수 {flow_data.foreign_buy_days}일",
            f"기관 순매수 {flow_data.institution_buy_days}일",
        ],
        bias="bullish" if score >= 7 else "neutral",
    )


def build_valuation_assessment(fundamental_summary) -> FactorAssessment:
    if fundamental_summary is None:
        return FactorAssessment(
            factor_type="valuation",
            role="참고",
            freshness_score=0,
            magnitude_score=0,
            actionability_score=0,
            total_score=0,
            summary="유의미한 밸류에이션 신호 부재",
            role_reason="펀더멘털 요약이 없거나 신뢰도가 낮음",
            evidence=[],
            bias="neutral",
        )

    confidence = fundamental_summary.confidence
    valuation = fundamental_summary.valuation_assessment

    if confidence < 0.7 or valuation == "적정":
        score = 0
        role = "참고"
        reason = "밸류에이션 우위가 크지 않거나 신뢰도가 낮음"
        bias = "neutral"
    elif valuation == "저평가":
        score = 7
        role = "보조"
        reason = "밸류에이션 매력이 보조 근거로 작동함"
        bias = "bullish"
    else:
        score = 7
        role = "보조"
        reason = "고평가 해석이라 공격적 추격을 경계해야 함"
        bias = "bearish"

    return FactorAssessment(
        factor_type="valuation",
        role=role,
        freshness_score=3 if score > 0 else 0,
        magnitude_score=3 if score > 0 else 0,
        actionability_score=2 if score > 0 else 0,
        total_score=score,
        headline=_valuation_headline(valuation, confidence),
        summary=fundamental_summary.summary,
        role_reason=reason,
        evidence=[
            f"valuation={valuation}",
            f"confidence={confidence:.2f}",
        ],
        bias=bias,
    )


def build_decision_summary(
    leader_label: str,
    assessments: list[FactorAssessment],
) -> AnalyzeDecisionSummary:
    if leader_label == "판단 보류":
        return AnalyzeDecisionSummary(
            leader="판단 보류",
            core_variables=["계산 가능한 팩터 부족"],
            action="관망",
            timing="보류",
            action_sentence="지금은 강한 단정보다 관망이 낫다",
            defer_reason="계산 가능한 팩터가 부족하거나 점수 우위가 없음",
        )

    prioritized_assessments = assessments
    leader_assessment = None
    if leader_label != "혼합":
        leader_assessments = [
            assessment for assessment in assessments if assessment.factor_type == leader_label
        ]
        other_assessments = [
            assessment for assessment in assessments if assessment.factor_type != leader_label
        ]
        prioritized_assessments = leader_assessments + other_assessments
        leader_assessment = leader_assessments[0] if leader_assessments else None
    else:
        prioritized_assessments = sorted(assessments, key=_mixed_core_variable_sort_key)

    core_variables = [
        _pick_core_variable_label(assessment) for assessment in prioritized_assessments[:2]
    ]

    if leader_label == "혼합":
        action = "관망"
        timing = "조정_대기"
        action_sentence = "지금 추격보다 핵심 레벨 확인 후 접근이 유리"
    elif leader_assessment and leader_assessment.bias == "bearish":
        action = "매도"
        timing = "지금" if leader_label == "event" else "조정_대기"
        if leader_label == "technical":
            action_sentence = "가격 약세가 주도라 반등 시 비중 축소가 우선"
        elif leader_label == "valuation":
            action_sentence = "밸류 부담이 커 공격적 진입보다 보수적 대응이 우선"
        else:
            action_sentence = "악재가 주도하는 구간이라 보수적 대응이 우선"
    elif leader_assessment is None:
        action = "관망"
        timing = "보류"
        action_sentence = "주도 팩터를 특정하기 어려워 관망이 낫다"
    else:
        action = "매수"
        timing = "조정_대기" if leader_label in {"technical", "flow", "혼합"} else "지금"
        action_sentence = "현재 주도 팩터를 따라 대응 가능"

    return AnalyzeDecisionSummary(
        leader=leader_label,
        core_variables=core_variables,
        action=action,
        timing=timing,
        action_sentence=action_sentence,
        defer_reason=None,
    )


def build_default_scenarios(
    summary: AnalyzeDecisionSummary,
    price_levels,
    assessments: list[FactorAssessment],
    snapshot=None,
) -> list[AnalyzeScenario]:
    support_levels = list(getattr(price_levels, "support_levels", []) or [])
    resistance_levels = list(getattr(price_levels, "resistance_levels", []) or [])
    all_levels = support_levels + resistance_levels

    def pick_level(levels, preferred_types: tuple[str, ...], *, allow_fallback: bool = True):
        for level_type in preferred_types:
            for level in levels:
                if getattr(level, "type", "") == level_type:
                    return level
        if allow_fallback:
            return levels[0] if levels else None
        return None

    def format_level(label: str, level):
        if level is None:
            return None
        description = getattr(level, "description", "레벨")
        price = getattr(level, "price", None)
        if price is None:
            return f"{label}: {description}"
        return f"{label}: {description} ({float(price):,.0f})"

    def add_unique(items: list[str], value: str | None):
        if value and value not in items:
            items.append(value)

    recent_support_level = pick_level(support_levels, ("swing_low", "pivot_s1", "sma_20", "sma_50"))
    recent_resistance_level = pick_level(
        resistance_levels, ("swing_high", "pivot_r1", "sma_20", "sma_50")
    )
    ma50_level = pick_level(all_levels, ("sma_50",), allow_fallback=False)
    ma150_level = pick_level(all_levels, ("sma_150",), allow_fallback=False)
    if (
        ma50_level is None
        and snapshot is not None
        and getattr(snapshot, "sma_50", None) is not None
    ):
        ma50_level = SimpleNamespace(
            type="sma_50",
            description="50일 이평선",
            price=float(snapshot.sma_50),
        )
    if (
        ma150_level is None
        and snapshot is not None
        and getattr(snapshot, "sma_150", None) is not None
    ):
        ma150_level = SimpleNamespace(
            type="sma_150",
            description="150일 이평선",
            price=float(snapshot.sma_150),
        )

    trigger_levels: list[str] = []
    add_unique(trigger_levels, format_level("최근 지지", recent_support_level))
    add_unique(trigger_levels, format_level("최근 저항", recent_resistance_level))
    add_unique(trigger_levels, format_level("50일선", ma50_level))
    add_unique(trigger_levels, format_level("150일선", ma150_level))

    support_description = getattr(recent_support_level, "description", "주요 지지선 유지")
    resistance_description = getattr(recent_resistance_level, "description", "주요 저항선 돌파")
    if not trigger_levels:
        trigger_levels = [support_description, resistance_description]

    bullish_invalidation_level = ma150_level or pick_level(
        support_levels,
        ("sma_150", "sma_200", "swing_low", "pivot_s1"),
    )
    bearish_invalidation_level = ma50_level or pick_level(
        resistance_levels,
        ("sma_50", "sma_150", "swing_high", "pivot_r1"),
    )
    bullish_invalidation = (
        f"무효화 레벨: {getattr(bullish_invalidation_level, 'description', '주요 지지')} "
        f"({float(bullish_invalidation_level.price):,.0f}) 하향 이탈"
        if bullish_invalidation_level is not None
        and getattr(bullish_invalidation_level, "price", None) is not None
        else f"{support_description} 무효화"
    )
    bearish_invalidation = (
        f"무효화 레벨: {getattr(bearish_invalidation_level, 'description', '주요 저항')} "
        f"({float(bearish_invalidation_level.price):,.0f}) 상향 돌파"
        if bearish_invalidation_level is not None
        and getattr(bearish_invalidation_level, "price", None) is not None
        else f"{resistance_description} 무효화"
    )

    confirming_factors = [
        assessment.summary for assessment in assessments if assessment.total_score >= 7
    ]
    if not confirming_factors:
        confirming_factors = ["추가 확인 신호 부족"]

    if summary.action == "매도":
        return [
            AnalyzeScenario(
                name="기본 시나리오",
                trigger_price_levels=trigger_levels,
                confirming_factors=confirming_factors[:2],
                invalidation_conditions=[
                    bearish_invalidation,
                    f"{support_description} 회복 시 재평가",
                ],
                expected_path="반등 실패 후 하락 압력 확대",
                recommended_action=summary.action_sentence,
            ),
            AnalyzeScenario(
                name="반대 시나리오",
                trigger_price_levels=trigger_levels,
                confirming_factors=["주도 약세 요인 완화"],
                invalidation_conditions=[bullish_invalidation, f"{resistance_description} 무효화"],
                expected_path="약세 완화 또는 추세 반전",
                recommended_action="가격 회복과 약세 요인 완화를 함께 확인하면 대응을 재평가",
            ),
        ]

    return [
        AnalyzeScenario(
            name="기본 시나리오",
            trigger_price_levels=trigger_levels,
            confirming_factors=confirming_factors[:2],
            invalidation_conditions=[bullish_invalidation, f"{resistance_description} 돌파 실패"],
            expected_path="눌림 후 재확인",
            recommended_action=summary.action_sentence,
        ),
        AnalyzeScenario(
            name="반대 시나리오",
            trigger_price_levels=trigger_levels,
            confirming_factors=["주도 팩터 약화"],
            invalidation_conditions=[bearish_invalidation, support_description],
            expected_path="기존 판단 약화 또는 반전",
            recommended_action="기본 시나리오와 다른 흐름이 확인되면 대응을 재평가",
        ),
    ]


def build_analyze_decision_bundle(
    *,
    technical_data,
    technical_summary,
    news_articles,
    news_analysis,
    fundamental_summary,
    disclosure_items,
    flow_data,
    chart_patterns,
    price_levels,
) -> AnalyzeDecisionBundle:
    snapshot = technical_data.indicators or technical_data.snapshot
    technical_assessment = build_technical_assessment(
        total_score=technical_data.total_score,
        rsi=snapshot.rsi,
        chart_patterns=[
            {
                "pattern_name": result.pattern_name,
                "detected": result.detected,
                "days_ago": result.days_ago or 0,
            }
            for result in chart_patterns.values()
        ],
    )
    if technical_summary is not None:
        technical_summary_text = (
            technical_summary.key_insights[0]
            if technical_summary.key_insights
            else technical_summary.summary
        )
        technical_assessment = technical_assessment.model_copy(
            update={
                "summary": technical_summary_text or technical_assessment.summary,
                "evidence": technical_assessment.evidence + [technical_summary.summary],
            }
        )

    disclosure_payload = [
        {"form_type": item.form_type, "description": item.description}
        for item in disclosure_items or []
    ]
    raw_news_titles = [article.title for article in news_articles]
    strong_analyzed_event = (
        news_analysis is not None
        and news_analysis.confidence >= 0.75
        and news_analysis.sentiment in {"긍정", "부정"}
        and bool(news_analysis.key_themes)
    )
    event_news_titles = raw_news_titles
    if (
        not disclosure_payload
        and not any("계약" in title for title in raw_news_titles)
        and not strong_analyzed_event
    ):
        event_news_titles = []

    event_assessment = build_event_assessment(
        news_titles=event_news_titles,
        disclosure_items=disclosure_payload,
    )
    if news_analysis is not None and event_assessment.total_score > 0:
        update_payload = {
            "summary": news_analysis.summary,
            "evidence": event_assessment.evidence + [news_analysis.impact_assessment],
        }
        if news_analysis.sentiment == "부정":
            update_payload["bias"] = "bearish"
        elif news_analysis.sentiment == "긍정":
            update_payload["bias"] = "bullish"

        event_assessment = event_assessment.model_copy(update=update_payload)

    assessments = [
        technical_assessment,
        event_assessment,
        build_valuation_assessment(fundamental_summary),
    ]
    if flow_data is not None:
        assessments.append(build_flow_assessment(flow_data))

    assessments = sorted(assessments, key=lambda assessment: assessment.total_score, reverse=True)
    score_entries = [
        {"factor_type": assessment.factor_type, "total_score": assessment.total_score}
        for assessment in assessments
        if assessment.total_score > 0
    ]
    leader_label = classify_leader_label(score_entries)
    summary = build_decision_summary(leader_label, assessments)
    scenarios = build_default_scenarios(summary, price_levels, assessments, snapshot=snapshot)
    return AnalyzeDecisionBundle(
        summary=summary,
        factor_assessments=assessments,
        scenarios=scenarios,
    )
