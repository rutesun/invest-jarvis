"""LLM-based analysis functions using langchain."""

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from src.llm.models import (
    FundamentalSummaryInput,
    FundamentalSummaryOutput,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


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

Provide summary with:
- summary: brief overall summary in Korean
- key_insights: list of 2-3 key insights
- recommendation: "매수", "매도", or "중립"
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
