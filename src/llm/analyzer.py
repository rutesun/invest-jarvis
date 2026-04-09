"""LLM-based analysis functions using langchain."""
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from src.llm.models import (
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
    news_text = "\n".join(
        [f"- {n['title']}: {n.get('summary', '')}" for n in input_data.news]
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a financial news analyst."),
        ("user", """Analyze the following news for {ticker} ({company_name}):

{news_text}

Provide analysis with:
- sentiment: "긍정", "부정", or "중립"
- confidence: 0.0-1.0
- key_themes: list of main themes
- summary: brief summary in Korean
- impact_assessment: impact analysis in Korean""")
    ])

    chain = prompt | llm.with_structured_output(NewsAnalysisOutput)

    result = await chain.ainvoke({
        "ticker": input_data.ticker,
        "company_name": input_data.company_name,
        "news_text": news_text,
    })

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

    indicators_text = "\n".join(
        [f"- {k}: {v:.2f}" for k, v in input_data.indicators.items()]
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a technical analysis expert."),
        ("user", """Analyze the following technical data for {ticker}:

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
- rationale: reasoning in Korean""")
    ])

    chain = prompt | llm.with_structured_output(TechnicalSummaryOutput)

    result = await chain.ainvoke({
        "ticker": input_data.ticker,
        "price": input_data.price,
        "change_pct": input_data.change_pct,
        "strategies_text": strategies_text,
        "indicators_text": indicators_text,
    })

    return result
