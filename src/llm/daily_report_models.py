# src/llm/daily_report_models.py
from __future__ import annotations

from pydantic import BaseModel
from typing import Literal


class IngestResult(BaseModel):
    telegram_messages: list[dict]
    macro_snapshot: dict
    market_news: list[dict]
    kr_flow: list[dict]
    momentum: list[dict]


class IssueExtract(BaseModel):
    theme: str
    tickers: list[str]
    sentiment: Literal["bull", "bear", "neutral"]
    summary: str
    source_ids: list[int]


class StockDetail(BaseModel):
    ticker: str
    market: Literal["KR", "US"]
    mention_count: int
    flow_score: float | None
    volume_score: float | None
    source: Literal["telegram", "market_data", "both"]
    summaries: list[str]


class Theme(BaseModel):
    name: str
    narrative: str
    sentiment: Literal["bull", "bear", "neutral"]
    mention_count: int
    stocks: list[str]


class ShuffleResult(BaseModel):
    themes: list[Theme]
    stock_details: dict[str, StockDetail]


class StockCatalyst(BaseModel):
    ticker: str
    themes: list[str]
    news: list[str]
    catalyst_summary: str


class DailyReport(BaseModel):
    date: str
    market_pulse: str
    narrative_and_themes: str
    featured_analysis: str
