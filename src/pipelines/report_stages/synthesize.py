# src/pipelines/report_stages/synthesize.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import (
    DailyReport,
    IngestResult,
    ShuffleResult,
    StockCatalyst,
)
from src.llm.daily_report_analyzer import synthesize_report

logger = logging.getLogger(__name__)


@dataclass
class SynthesizeStage:
    llm: BaseChatModel

    async def run(
        self,
        ingest: IngestResult,
        shuffle: ShuffleResult,
        catalysts: list[StockCatalyst],
    ) -> DailyReport:
        macro_str = json.dumps(ingest.macro_snapshot, ensure_ascii=False, indent=2)

        news_lines = []
        for n in ingest.market_news:
            news_lines.append(f"- [{n.get('source', '')}] {n.get('title', '')}: {n.get('summary', '')}")
        news_str = "\n".join(news_lines)

        themes_data = []
        for theme in shuffle.themes:
            stock_infos = []
            for ticker in theme.stocks:
                detail = shuffle.stock_details.get(ticker)
                if detail:
                    stock_infos.append({
                        "ticker": ticker,
                        "market": detail.market,
                        "flow_score": detail.flow_score,
                        "volume_score": detail.volume_score,
                    })
            themes_data.append({
                "name": theme.name,
                "narrative": theme.narrative,
                "sentiment": theme.sentiment,
                "mention_count": theme.mention_count,
                "stocks": stock_infos,
            })
        themes_str = json.dumps(themes_data, ensure_ascii=False, indent=2)

        catalysts_data = [c.model_dump() for c in catalysts]
        catalysts_str = json.dumps(catalysts_data, ensure_ascii=False, indent=2)

        return await synthesize_report(
            llm=self.llm,
            macro=macro_str,
            news=news_str,
            themes=themes_str,
            catalysts=catalysts_str,
            metadata={"stage": "synthesize", "theme_count": len(shuffle.themes)},
        )
