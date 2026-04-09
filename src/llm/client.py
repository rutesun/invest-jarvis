import json
import httpx
from typing import Literal
from src.llm.models import (
    LLMRequest,
    LLMResponse,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


class LLMClient:
    """Multi-provider LLM client with purpose-specific methods."""

    def __init__(
        self,
        provider: Literal["openai", "anthropic"] = "openai",
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.provider = provider
        self.api_key = api_key
        self.model = model or self._get_default_model()
        self.base_url = base_url

    def _get_default_model(self) -> str:
        """Get default model for provider."""
        if self.provider == "openai":
            return "gpt-4-turbo-preview"
        elif self.provider == "anthropic":
            return "claude-3-5-sonnet-20241022"
        return "gpt-4-turbo-preview"

    async def _call_api(self, request: LLMRequest) -> LLMResponse:
        """Call LLM API."""
        if self.provider == "openai":
            return await self._call_openai(request)
        elif self.provider == "anthropic":
            return await self._call_anthropic(request)
        raise ValueError(f"Unsupported provider: {self.provider}")

    async def _call_openai(self, request: LLMRequest) -> LLMResponse:
        """Call OpenAI API."""
        base = self.base_url or "https://api.openai.com/v1"
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "seed": request.seed,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage=data["usage"],
        )

    async def _call_anthropic(self, request: LLMRequest) -> LLMResponse:
        """Call Anthropic API."""
        base = self.base_url or "https://api.anthropic.com/v1"
        url = f"{base}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # Convert OpenAI format to Anthropic format
        system_msg = None
        messages = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                messages.append(msg)

        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data["content"][0]["text"],
            model=data["model"],
            usage=data["usage"],
        )

    async def analyze_news(self, input_data: NewsAnalysisInput) -> NewsAnalysisOutput:
        """Analyze news sentiment and impact."""
        news_text = "\n".join(
            [f"- {n['title']}: {n.get('summary', '')}" for n in input_data.news]
        )

        prompt = f"""Analyze the following news for {input_data.ticker} ({input_data.company_name}):

{news_text}

Provide analysis in JSON format:
{{
  "sentiment": "긍정|부정|중립",
  "confidence": 0.0-1.0,
  "key_themes": ["theme1", "theme2"],
  "summary": "brief summary in Korean",
  "impact_assessment": "impact analysis in Korean"
}}"""

        request = LLMRequest(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a financial news analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            seed=42,
        )

        response = await self._call_api(request)
        data = json.loads(response.content)
        return NewsAnalysisOutput(**data)

    async def generate_technical_summary(
        self, input_data: TechnicalSummaryInput
    ) -> TechnicalSummaryOutput:
        """Generate technical analysis summary."""
        strategies_text = "\n".join(
            [
                f"- {s['name']}: {s['status']} (신뢰도: {s['confidence']:.0f}%)\n  시그널: {', '.join(s['signals'])}\n  근거: {', '.join(s['evidence'])}"
                for s in input_data.strategies
            ]
        )

        indicators_text = "\n".join(
            [f"- {k}: {v:.2f}" for k, v in input_data.indicators.items()]
        )

        prompt = f"""Analyze the following technical data for {input_data.ticker}:

**Current Price**: ${input_data.price:.2f} ({input_data.change_pct:+.2f}%)

**Strategy Results**:
{strategies_text}

**Key Indicators**:
{indicators_text}

Provide summary in JSON format:
{{
  "summary": "brief overall summary in Korean",
  "key_insights": ["insight1", "insight2"],
  "recommendation": "매수|매도|중립",
  "confidence": 0.0-1.0,
  "rationale": "reasoning in Korean"
}}"""

        request = LLMRequest(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a technical analysis expert.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            seed=42,
        )

        response = await self._call_api(request)
        data = json.loads(response.content)
        return TechnicalSummaryOutput(**data)
