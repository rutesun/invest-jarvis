# LLM Ticker Resolver Design

**Date:** 2026-04-10  
**Status:** Approved

## Overview

Replace the yfinance search fallback and static yml mapping in `TickerResolver` with a GPT-4o + DuckDuckGo Tool Calling Loop (`LLMTickerAgent`). This enables accurate resolution of Korean company names (e.g., "삼성전자" → `005930.KS`) and foreign names (e.g., "로켓랩" → `RKLB`) without maintaining a hand-curated static mapping file.

## Resolution Pipeline

```
resolve(query)
  ├─ 1. Direct ticker detection   → return immediately (AAPL, 005930.KS, etc.)
  ├─ 2. User cache lookup         → return + update usage
  └─ 3. LLMTickerAgent            → search → cache save → return
```

The `config/ticker_names.yaml` static mapping file is removed. Steps that depended on it (`_load_static_mapping`, `_contains_korean`, static mapping lookup, `_search_yfinance`) are all removed from `TickerResolver`.

## Components

### `src/providers/llm_ticker_agent.py` (new file)

```
LLMTickerAgent
  __init__(api_key: str, model: str = "gpt-4o")
  async resolve(query: str) -> tuple[str, str]  # (ticker, display_name)
```

**Tool:**
```python
@tool
def duckduckgo_search(query: str) -> str:
    """Search DuckDuckGo and return top 5 results as text"""
```

**Tool Calling Loop:**
- Uses LangChain `create_react_agent` (or manual loop)
- Max **3 tool calls** per resolution; raises `TickerNotFoundError` if unresolved
- Final LLM response must be JSON: `{"ticker": "005930.KS", "display_name": "Samsung Electronics Co., Ltd."}`

**System prompt requirements:**
- Return exact exchange ticker symbol (e.g., `005930.KS`, `035720.KQ`, `RKLB`)
- Korean KOSPI stocks use `.KS` suffix, KOSDAQ use `.KQ` suffix
- US stocks use plain symbol (e.g., `AAPL`, `RKLB`)
- Response format: JSON `{"ticker": "...", "display_name": "..."}`

### `src/providers/ticker_resolver.py` (modified)

**Remove:**
- `static_mapping_path` constructor parameter
- `self.static_mapping` field
- `self._search_cache` field (in-memory search cache, no longer needed)
- `_load_static_mapping()`
- `_contains_korean()`
- `_search_yfinance()`

**Add:**
- `self.llm_agent = LLMTickerAgent(api_key=...)` initialized in constructor
- Step 3 calls `await self.llm_agent.resolve(query)` and saves result to `user_cache`

**`TickerResolution.resolution_method`** — add `"llm_agent"` to the Literal type in `ticker_models.py`.

### `pyproject.toml` (modified)

Add dependency: `duckduckgo-search>=6.0.0`

### `config/ticker_names.yaml` (deleted)

No longer used.

## Cache Behavior

- `UserMappingCache` at `~/.cache/invest-jarvis/user_mappings.yaml` — unchanged
- After `LLMTickerAgent.resolve()` succeeds, `TickerResolver` calls `user_cache.save(query, ticker, display_name)`
- Subsequent identical queries hit cache (Step 2), skipping LLM entirely

## Error Handling

| Condition | Behavior |
|---|---|
| `OPENAI_API_KEY` not set | `LLMTickerAgent.__init__` raises `ValueError` |
| LLM returns invalid JSON | retry up to max iterations, then `TickerNotFoundError` |
| DuckDuckGo returns no results | LLM tries different search query (within max iterations) |
| Max iterations (3) exceeded | `TickerNotFoundError` raised, propagated to CLI |

## Dependencies

- `langchain-openai` — already in `pyproject.toml`
- `langchain-core` — already in `pyproject.toml`
- `duckduckgo-search>=6.0.0` — to be added

## Out of Scope

- Anthropic/Claude as LLM provider for ticker resolution (OpenAI only, consistent with existing `gpt-4o` default)
- Modifying `UserMappingCache` structure
- Adding ticker resolution to the `report` command (it uses raw tickers already)
