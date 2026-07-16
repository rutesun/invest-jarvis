"""LLM-based analysis functions using langchain."""

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from src.llm.models import (
    ActionableSignalOutput,
    BriefNarrativesOutput,
    FundamentalSummaryInput,
    FundamentalSummaryOutput,
    IntegratedAnalysisInput,
    IntegratedAnalysisOutput,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)
from src.tools.technical.models import ChartPatternResult, PriceLevels


def format_patterns_for_llm(patterns: dict[str, ChartPatternResult]) -> str:
    """패턴 결과를 LLM용 텍스트로 변환"""
    lines = []
    for _pattern_name, result in patterns.items():
        if result.detected:
            lines.append(
                f"- {result.pattern_name}: 감지됨 (신뢰도 {result.confidence:.0%}, {result.days_ago}일 전 완성)"
            )
            lines.append(f"  {result.description}")
            if result.breakout_level:
                lines.append(f"  돌파 레벨: ${result.breakout_level:.2f}")
        else:
            lines.append(f"- {result.pattern_name}: 미감지")
    return "\n".join(lines) if lines else "패턴 감지 없음"


def format_levels_for_llm(levels: PriceLevels) -> str:
    """가격 레벨을 LLM용 텍스트로 변환"""
    lines = [f"현재가: ${levels.current_price:.2f}\n"]
    if levels.support_levels:
        lines.append("지지선 (가까운 순):")
        for i, support in enumerate(levels.support_levels, 1):
            lines.append(
                f"  {i}. ${support.price:.2f} ({support.description}, {support.distance_pct:+.1f}%)"
            )
        lines.append("")
    if levels.resistance_levels:
        lines.append("저항선 (가까운 순):")
        for i, resistance in enumerate(levels.resistance_levels, 1):
            lines.append(
                f"  {i}. ${resistance.price:.2f} ({resistance.description}, {resistance.distance_pct:+.1f}%)"
            )
        lines.append("")
    if levels.targets:
        lines.append("타겟 (상승 시나리오):")
        for target_name, target_price in levels.targets.items():
            readable_name = target_name.replace("_", " ").title()
            lines.append(f"  - {readable_name}: ${target_price:.2f}")
    return "\n".join(lines)


def _as_dict(item):
    if item is None:
        return None
    return item if isinstance(item, dict) else item.model_dump()


def _format_zone_range(zone: dict) -> str:
    return f"{zone['lower_bound']:.2f}~{zone['upper_bound']:.2f}"


def format_structure_context_for_llm(
    structure_levels,
    execution_levels,
) -> str:
    """구조/실행 레벨을 LLM용 컨텍스트 문자열로 변환"""
    if isinstance(structure_levels, str):
        return structure_levels

    structure_dict = _as_dict(structure_levels)
    if structure_dict and "llm_context" in structure_dict:
        return str(structure_dict["llm_context"])

    lines: list[str] = ["구조 레벨:"]

    if structure_dict:
        support_zones = structure_dict.get("support_zones")
        resistance_zones = structure_dict.get("resistance_zones")
        former_levels = structure_dict.get("former_levels")
        active_box = structure_dict.get("active_box")
        invalidation_value = structure_dict.get("invalidation")
        invalidation = _as_dict(invalidation_value) if invalidation_value else None

        if support_zones is None or resistance_zones is None:
            lines.append("- presenter contract missing (support_zones/resistance_zones)")
            lines.append("")
            lines.append("실행 레벨:")
            if execution_levels:
                for index, level in enumerate(execution_levels, start=1):
                    level_dict = _as_dict(level)
                    lines.append(
                        f"{index}. ${level_dict['price']:.2f} ({level_dict['description']}, {level_dict['distance_pct']:+.1f}%)"
                    )
            else:
                lines.append("- 실행 레벨 데이터 없음")
            return "\n".join(lines)

        support_text = (
            ", ".join(_format_zone_range(zone) for zone in support_zones)
            if support_zones
            else "없음"
        )
        resistance_text = (
            ", ".join(_format_zone_range(zone) for zone in resistance_zones)
            if resistance_zones
            else "없음"
        )
        former_text = (
            ", ".join(_format_zone_range(zone) for zone in former_levels)
            if former_levels
            else "없음"
        )
        active_box_text = _format_zone_range(active_box) if active_box else "없음"

        if structure_dict.get("summary_label"):
            lines.append(f"- summary_label: {structure_dict['summary_label']}")
        if structure_dict.get("headline"):
            lines.append(f"- headline: {structure_dict['headline']}")
        if structure_dict.get("why"):
            lines.append(f"- why: {structure_dict['why']}")
        lines.append(f"- active_box: {active_box_text}")
        lines.append(f"- support_zones: {support_text}")
        lines.append(f"- resistance_zones: {resistance_text}")
        lines.append(f"- former_levels: {former_text}")
        lines.append(f"- invalidation: {invalidation['label'] if invalidation else '없음'}")
    else:
        lines.append("- 구조 존 데이터 없음")

    lines.append("")
    lines.append("실행 레벨:")
    if execution_levels:
        for index, level in enumerate(execution_levels, start=1):
            level_dict = _as_dict(level)
            lines.append(
                f"{index}. ${level_dict['price']:.2f} ({level_dict['description']}, {level_dict['distance_pct']:+.1f}%)"
            )
    else:
        lines.append("- 실행 레벨 데이터 없음")

    return "\n".join(lines)


async def analyze_news(
    input_data: NewsAnalysisInput,
    llm: BaseChatModel,
) -> NewsAnalysisOutput:
    """
    Analyze news sentiment and impact using LLM.

    Args:
        input_data: News analysis input data
        llm: LangChain chat model to use for analysis

    Returns:
        News analysis output with sentiment and insights
    """
    news_text = "\n".join([f"- {n['title']}: {n.get('summary', '')}" for n in input_data.news])

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a financial news analyst."),
            (
                "user",
                """Analyze the following news for {ticker} ({company_name}):

{news_text}

Provide analysis with:
- sentiment: "긍정", "부정", or "중립"
- confidence: 0.0-1.0
- key_themes: list of main themes
- summary: brief summary in Korean
- impact_assessment: impact analysis in Korean""",
            ),
        ]
    )

    chain = prompt | llm.with_structured_output(NewsAnalysisOutput)

    result = await chain.ainvoke(
        {
            "ticker": input_data.ticker,
            "company_name": input_data.company_name,
            "news_text": news_text,
        }
    )

    return result


async def generate_technical_summary(
    input_data: TechnicalSummaryInput,
    llm: BaseChatModel,
) -> TechnicalSummaryOutput:
    """
    Generate technical analysis summary using LLM.

    Args:
        input_data: Technical analysis input data
        llm: LangChain chat model to use for analysis

    Returns:
        Technical summary with recommendations
    """
    strategies_text = "\n".join(
        [
            f"- {s['name']}: {s['status']} (신뢰도: {s['confidence']:.0f}%)\n  시그널: {', '.join(s['signals'])}\n  근거: {', '.join(s['evidence'])}"
            for s in input_data.strategies
        ]
    )

    indicators_text = "\n".join([f"- {k}: {v:.2f}" for k, v in input_data.indicators.items()])

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a technical analysis expert."),
            (
                "user",
                """Analyze the following technical data for {ticker}:

**Current Price**: ${price:.2f} ({change_pct:+.2f}%)

**Strategy Results**:
{strategies_text}

**Key Indicators**:
{indicators_text}

**Rule-based technical verdict**:
{technical_verdict}

**Recent score history**:
{score_history}

**Score history warning**:
{score_history_warning}

**Aggregation trace**:
{aggregation_trace}

Treat the rule-based technical verdict, score history, and aggregation trace as fixed rule output.
Do not change the score or action. Do not derive a new recommendation.
Explain these facts in Korean only; recommendation must describe the provided verdict when it exists.

Provide summary with:
- summary: brief overall summary in Korean
- key_insights: list of 2-3 key insights
- recommendation: Korean wording that explains the provided verdict action; if no verdict is provided, use "매수", "매도", or "중립"
- confidence: 0.0-1.0
- rationale: reasoning in Korean""",
            ),
        ]
    )

    chain = prompt | llm.with_structured_output(TechnicalSummaryOutput)

    result = await chain.ainvoke(
        {
            "ticker": input_data.ticker,
            "price": input_data.price,
            "change_pct": input_data.change_pct,
            "strategies_text": strategies_text,
            "indicators_text": indicators_text,
            "technical_verdict": input_data.technical_verdict,
            "score_history": input_data.score_history,
            "score_history_warning": input_data.score_history_warning,
            "aggregation_trace": input_data.aggregation_trace,
        }
    )

    return result


async def generate_fundamental_summary(
    input_data: FundamentalSummaryInput,
    llm: BaseChatModel,
) -> FundamentalSummaryOutput:
    """Generate fundamental analysis summary using LLM."""
    from src.utils.sector_metrics import SectorMetrics

    # 섹터별 우선순위 지표 가져오기
    priority_metrics = SectorMetrics.get_priority_metrics(input_data.sector)

    # 모든 지표를 포함하되, 우선순위 지표는 [핵심] 표시
    all_metrics = [
        ("pe_ratio", "P/E"),
        ("forward_pe", "Forward P/E"),
        ("peg_ratio", "PEG"),
        ("pb_ratio", "P/B"),
        ("ps_ratio", "PSR"),
        ("ev_ebitda", "EV/EBITDA"),
        ("roe", "ROE"),
        ("roa", "ROA"),
        ("revenue_growth", "매출 성장률"),
        ("earnings_growth", "이익 성장률"),
        ("gross_margin", "매출총이익률"),
        ("operating_margin", "영업이익률"),
        ("profit_margin", "순이익률"),
        ("debt_to_equity", "D/E"),
        ("free_cash_flow", "FCF"),
        ("fcf_yield", "FCF Yield"),
        ("dividend_yield", "배당 수익률"),
        ("payout_ratio", "배당 성향"),
    ]

    metrics_text = []
    for metric_name, display_name in all_metrics:
        value = getattr(input_data, metric_name, None)
        if value is not None:
            # 우선순위 지표면 [핵심] 접두사 추가
            prefix = "[핵심] " if metric_name in priority_metrics else ""

            # 포맷팅
            if metric_name in [
                "revenue_growth",
                "earnings_growth",
                "gross_margin",
                "operating_margin",
                "profit_margin",
                "fcf_yield",
                "dividend_yield",
                "roe",
                "roa",
                "payout_ratio",
            ]:
                formatted = f"{value * 100:.1f}%"
            elif metric_name == "free_cash_flow":
                formatted = f"${value / 1e9:.1f}B"
            else:
                formatted = f"{value:.1f}" if abs(value) > 10 else f"{value:.2f}"

            metrics_text.append(f"{prefix}{display_name}: {formatted}")

    if not metrics_text:
        metrics_text.append("No financial metrics available")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a fundamental analysis expert."),
            (
                "user",
                """Analyze the following fundamental data for {ticker}:

**Sector**: {sector} / {industry}

**Key Metrics** (핵심 지표는 [핵심]으로 표시):
{metrics_text}

Provide summary with:
- summary: overall fundamental assessment in Korean
- strengths: list of 2-3 key strengths (핵심 지표를 중심으로)
- weaknesses: list of 2-3 key weaknesses
- valuation_assessment: "저평가", "적정", or "고평가"
- confidence: 0.0-1.0""",
            ),
        ]
    )

    chain = prompt | llm.with_structured_output(FundamentalSummaryOutput)

    result = await chain.ainvoke(
        {
            "ticker": input_data.ticker,
            "sector": input_data.sector or "N/A",
            "industry": input_data.industry or "N/A",
            "metrics_text": "\n".join(f"- {m}" for m in metrics_text),
        }
    )

    return result


async def generate_integrated_analysis(
    input_data: IntegratedAnalysisInput,
    llm: BaseChatModel,
) -> IntegratedAnalysisOutput:
    """기술적·기본적·공시·수급 팩터를 통합한 종합 투자 분석을 생성한다."""
    disclosure_text = (
        "\n".join(
            f"- [{d['form_type']}] {d['date']}: {d['description']}\n  URL: {d['url']}"
            for d in input_data.disclosure_items
        )
        if input_data.disclosure_items
        else "해당 기간 주요 공시 없음"
    )

    flow_text = input_data.flow_summary or "수급 데이터 없음 (미국주식 또는 KIS 미설정)"

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 한국 주식시장 종합 분석 전문가입니다. 실행 가능한 투자 인사이트를 제공하세요.",
            ),
            (
                "user",
                """종합 투자 분석을 제공하세요. 종목: {ticker}

**기술적 분석**: {technical_recommendation} — {technical_rationale}

**기본적 분석 (밸류에이션)**: {fundamental_valuation}

**공시 분석 (최근 3개월)**:
{disclosure_text}

**수급 동향**:
{flow_text}

다음 형식으로 분석하세요:
- recommendation: "매수", "매도", 또는 "중립"
- rationale: 3-4개 근거 (각 항목은 "기술적:", "기본적:", "공시:", "수급:" 중 하나로 시작)
- risks: 2-3개 리스크 요인
- action_summary: 한 줄 요약""",
            ),
        ]
    )

    chain = prompt | llm.with_structured_output(IntegratedAnalysisOutput)

    return await chain.ainvoke(
        {
            "ticker": input_data.ticker,
            "technical_recommendation": input_data.technical_recommendation,
            "technical_rationale": input_data.technical_rationale,
            "fundamental_valuation": input_data.fundamental_valuation or "N/A",
            "disclosure_text": disclosure_text,
            "flow_text": flow_text,
        }
    )


async def generate_actionable_signal(
    ticker: str,
    technical_summary: str,
    chart_patterns: dict[str, ChartPatternResult],
    price_levels: PriceLevels,
    structure_context: str | None = None,
    structure_levels=None,
    execution_levels=None,
    structure_summary: str | None = None,
    execution_summary: str | None = None,
    news_analysis: str | None = None,
    fundamental_summary: str | None = None,
    llm: BaseChatModel | None = None,
) -> ActionableSignalOutput:
    """Generate actionable signal with pattern and price insights"""
    if llm is None:
        from src.llm.provider import get_llm_instance

        llm = get_llm_instance()

    patterns_text = format_patterns_for_llm(chart_patterns)
    structure_context_text = structure_context or format_structure_context_for_llm(
        structure_levels,
        execution_levels,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """당신은 프로 트레이더입니다. 구체적인 가격과 패턴으로 명확한 투자 신호를 제공하세요.

**신규 필드 작성 가이드:**

1. **pattern_insight**: 감지된 패턴을 자연스럽게 해석
   - 패턴이 있으면: "Cup & Handle 형성 완료 (8일 전), 돌파 준비 중"
   - 패턴이 없으면: "명확한 차트 패턴 없음, 지지/저항선 중심 분석"

2. **target_price**: 시나리오별 목표가 (자유 서술)
   - 상승 시: "돌파 시 Cup & Handle 목표 $250, 중간 저항 $210"
   - 하락 시: "이탈 시 50일선 $175까지 조정 가능"

3. **entry_zone**: 진입 타이밍과 구간
   - "조정 시 $175-180 (50일선) 분할 매수, 돌파 확인 후 $205 추격 가능"

4. **key_levels**: 핵심 가격 레벨 간결 요약
   - "지지: $187/$175/$160, 저항: $200/$210/$250"

**기존 필드 작성 규칙:**
- primary_reason: 반드시 구체적 숫자 포함
- signal_strength: 1-10, 패턴 신뢰도 포함""",
            ),
            (
                "user",
                """종목: {ticker}

**기술적 분석**:
{technical_summary}

**차트 패턴**:
{patterns_text}

**구조/실행 레벨**:
{structure_summary}
{execution_summary}

**구조/실행 상세**:
{structure_context}

**뉴스**: {news_analysis}
**펀더멘탈**: {fundamental_summary}

위 정보를 종합해서 명확한 투자 신호를 생성하세요.""",
            ),
        ]
    )

    chain = prompt | llm.with_structured_output(ActionableSignalOutput)

    result = await chain.ainvoke(
        {
            "ticker": ticker,
            "technical_summary": technical_summary,
            "patterns_text": patterns_text,
            "structure_context": structure_context_text,
            "structure_summary": structure_summary or "구조 레벨 요약 없음",
            "execution_summary": execution_summary or "실행 레벨 요약 없음",
            "news_analysis": news_analysis or "없음",
            "fundamental_summary": fundamental_summary or "없음",
        }
    )

    return result


async def generate_brief_narratives(
    facts_json: str,
    llm: BaseChatModel,
) -> BriefNarrativesOutput:
    """전 종목 규칙 판정 사실(JSON)을 배치 1콜로 문장화한다.

    액션·순위·근거는 이미 규칙이 확정 — LLM은 서술만 담당하며,
    사실에 없는 수치·사건을 만들면 안 된다 (스펙 §6.1).
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 한국어 투자 브리핑 작성자다. 제공된 '규칙 판정 사실'만 사용해 "
                "각 종목의 서술 슬롯을 채운다. 사실에 없는 수치·사건·전망을 만들지 마라. "
                "모든 종목에 대해 하나씩 narrative를 반환하라.",
            ),
            (
                "user",
                "다음은 종목별 규칙 판정 결과 JSON이다:\n\n{facts_json}\n\n"
                "각 종목에 대해 technical_note(기술적 근거 1-2문장), "
                "flow_note(수급 사실이 있으면 1문장, 없으면 null), "
                "news_note(뉴스가 있으면 해석 1문장, 없으면 null), "
                "next_check(다음 확인 지점 1문장)를 작성하라.",
            ),
        ]
    )
    chain = prompt | llm.with_structured_output(BriefNarrativesOutput)
    return await chain.ainvoke({"facts_json": facts_json})
