# src/llm/daily_report_models.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class IngestResult(BaseModel):
    telegram_messages: list[dict]
    ref_lookup: dict[int, str] = Field(default_factory=dict)
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
    source_ids: list[int] = Field(default_factory=list)


class ShuffleResult(BaseModel):
    themes: list[Theme]
    stock_details: dict[str, StockDetail]


class StockCatalyst(BaseModel):
    ticker: str
    themes: list[str]
    news: list[str]
    catalyst_summary: str


class DailyReportInsights(BaseModel):
    market_pulse: str
    featured_analysis: str


class DailyReport(BaseModel):
    date: str
    market_pulse: str
    featured_analysis: str
    themes: list[Theme] = Field(default_factory=list)
    catalysts: list[StockCatalyst] = Field(default_factory=list)
    stock_details: dict[str, StockDetail] = Field(default_factory=dict)
    ref_lookup: dict[int, str] = Field(default_factory=dict)
