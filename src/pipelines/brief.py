"""BriefPipeline — 일일 포트 액션 종합 (스펙: docs/superpowers/specs/2026-07-14-jarvis-brief-design.md).

사실은 코드가, 해석은 LLM이: 액션·순위·근거는 규칙이 확정하고
LLM은 배치 1콜 문장화만 담당한다. 개별 종목·소스 실패는 전체를 막지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.llm.analyzer import generate_brief_narratives
from src.tools.brief.models import BriefItem
from src.tools.brief.render import render_markdown
from src.tools.brief.scoring import (
    BONUS_STOP_PROXIMITY,
    BONUS_SURGE,
    bucket_for,
    classify_watch,
    is_stop_proximate,
    rank,
    surge_reason,
)
from src.tools.disclosure import extract_kr_code, is_korean_ticker
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig


logger = logging.getLogger(__name__)


class BriefPipeline:
    """playbook.yaml(보유+워치) 전 종목 풀 평가 → 버킷 랭킹 → 마크다운 브리핑."""

    def __init__(
        self,
        technical_tools: dict[str, Any],  # {"KR": TechnicalAnalysisTool, "US": ...}
        playbook_engine,
        macro_tool,
        news_tool,
        disclosure_tool,
        flow_tool,
        llm: BaseChatModel | None = None,
    ):
        self.technical_tools = technical_tools
        self.playbook_engine = playbook_engine
        self.macro_tool = macro_tool
        self.news_tool = news_tool
        self.disclosure_tool = disclosure_tool
        self.flow_tool = flow_tool
        self.llm = llm

    async def run(self, config: HoldingsConfig) -> dict[str, Any]:
        date = datetime.now()

        macro = None
        macro_result = await self.macro_tool.execute()
        if macro_result.success:
            macro = macro_result.data
        else:
            logger.warning("매크로 스냅샷 실패 — 시장 환경 섹션 생략: %s", macro_result.error)

        targets: list[tuple[str, HoldingEntry | None, str | None]] = [
            (h.ticker, h, None) for h in config.holdings
        ] + [(w.ticker, None, w.note) for w in config.watchlist]

        items: list[BriefItem] = []
        for ticker, holding, note in targets:  # KIS 동시 호출 금지 → 순차 루프
            items.append(await self._analyze_target(ticker, holding, note))

        ranked = rank(items)

        if self.llm is not None and any(i.action != "error" for i in ranked):
            await self._attach_narratives(ranked)

        return {"date": date, "macro": macro, "items": ranked}

    async def _analyze_target(
        self, ticker: str, holding: HoldingEntry | None, note: str | None
    ) -> BriefItem:
        kind = "holding" if holding is not None else "watch"
        try:
            tool = self.technical_tools["KR" if is_korean_ticker(ticker) else "US"]
            tech_result = await tool.execute(ticker)
            if not tech_result.success:
                raise RuntimeError(f"기술분석 실패: {tech_result.error}")
            technical = tech_result.data

            flow = None
            if is_korean_ticker(ticker) and self.flow_tool is not None:
                flow_result = await self.flow_tool.execute(extract_kr_code(ticker))
                flow = flow_result.data if flow_result.success else None

            verdict = await self.playbook_engine.evaluate(
                ticker=ticker,
                technical_result=technical,
                fundamental=None,  # v1: 펀더멘털 미포함 (스펙 §2) — sector는 graceful None
                flow=flow,
                zone_set=None,  # v1: 구조 zone 미포함 — 사이징은 ATR/-8% 기반
                holding=holding,
            )

            news, disclosures = await self._fetch_evidence(ticker)

            price = technical.snapshot.price
            change_pct = technical.snapshot.change_pct

            remaining_condition = None
            if holding is not None:
                action = verdict.exit_verdict.action if verdict.exit_verdict else "hold"
                has_warn = bool(verdict.exit_verdict and verdict.exit_verdict.signals)
            else:
                action, remaining_condition = classify_watch(verdict.gate)
                has_warn = False

            markers: list[str] = []
            bonus = 0
            stop_price = holding.stop_price if holding else None
            if is_stop_proximate(price, stop_price):
                markers.append("스탑 근접")
                bonus += BONUS_STOP_PROXIMITY
            surge = surge_reason(kind, change_pct)
            if surge:
                markers.append(surge)
                bonus += BONUS_SURGE

            return BriefItem(
                ticker=ticker,
                kind=kind,
                action=action,
                bucket=bucket_for(kind, action, has_warn_signals=has_warn),
                bonus=bonus,
                markers=markers,
                note=note,
                holding=holding,
                verdict=verdict,
                news=news,
                disclosures=disclosures,
                flow=flow,
                price=price,
                change_pct=change_pct,
                technical_verdict=(
                    technical.technical_verdict.model_dump()
                    if technical.technical_verdict is not None
                    else None
                ),
                score_history=[point.model_dump() for point in technical.score_history],
                score_history_warning=technical.score_history_warning,
                remaining_condition=remaining_condition,
            )
        except Exception as e:
            logger.warning("brief 종목 분석 실패 %s: %s", ticker, e)
            return BriefItem(
                ticker=ticker,
                kind=kind,
                action="error",
                bucket=bucket_for(kind, "error"),
                note=note,
                holding=holding,
                error=str(e),
            )

    async def _fetch_evidence(self, ticker: str) -> tuple[list, list]:
        """뉴스·공시 — 표기 전용, 실패해도 판정에 영향 없음."""
        results = await asyncio.gather(
            self.news_tool.execute(ticker, limit=3),
            self.disclosure_tool.execute(ticker),
            return_exceptions=True,
        )
        news_r, disc_r = results
        news = news_r.data if not isinstance(news_r, Exception) and news_r.success else []
        disclosures = disc_r.data if not isinstance(disc_r, Exception) and disc_r.success else []
        return news, disclosures

    async def _attach_narratives(self, items: list[BriefItem]) -> None:
        """LLM 배치 1콜. 실패 시 narrative 없이 진행 — 렌더러가 규칙 원문으로 fallback."""
        try:
            facts = [self._facts_for(i) for i in items if i.action != "error"]
            output = await generate_brief_narratives(
                json.dumps({"items": facts}, ensure_ascii=False), llm=self.llm
            )
            by_ticker = {n.ticker: n for n in output.narratives}
            for item in items:
                item.narrative = by_ticker.get(item.ticker)
        except Exception as e:
            logger.warning("LLM 문장화 실패 — 규칙 원문으로 진행: %s", e)

    @staticmethod
    def _facts_for(item: BriefItem) -> dict[str, Any]:
        exit_v = item.verdict.exit_verdict if item.verdict else None
        gate = item.verdict.gate if item.verdict else None
        return {
            "ticker": item.ticker,
            "kind": item.kind,
            "action": item.action,
            "price": item.price,
            "change_pct": item.change_pct,
            "technical_verdict": item.technical_verdict,
            "score_history": item.score_history,
            "score_history_warning": item.score_history_warning,
            "markers": item.markers,
            "exit_detail": exit_v.detail if exit_v else None,
            "exit_signals": [f"{s.code}: {s.detail}" for s in exit_v.signals] if exit_v else [],
            "gate_veto": gate.veto_reason if gate else None,
            "remaining_condition": item.remaining_condition,
            "flow": (
                f"외인5일 {item.flow.foreign_direction_5d}, 기관5일 {item.flow.institution_direction_5d}"
                if item.flow
                else None
            ),
            "news_titles": [n.title for n in item.news[:3]],
        }

    def format_output(self, result: dict[str, Any]) -> str:
        return render_markdown(result["date"], result["macro"], result["items"])

    def save_report(self, result: dict[str, Any]) -> Path:
        """reports/YYYY-MM/brief_YYYY-MM-DD.md 저장 (ScreenerPipeline.save_report 패턴)."""
        date: datetime = result["date"]
        dir_path = Path("reports") / date.strftime("%Y-%m")
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"brief_{date.strftime('%Y-%m-%d')}.md"
        file_path.write_text(self.format_output(result), encoding="utf-8")
        return file_path
