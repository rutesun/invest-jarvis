# src/tools/filing/impact.py
"""공시 유형별 임팩트 정량 계산."""

import logging

from src.tools.filing.models import FilingFacts, FilingImpact


logger = logging.getLogger(__name__)


class ImpactCalculator:
    """FilingFacts에서 유형별 임팩트를 계산한다."""

    def calculate(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail

        if detail and detail.detail_type == "유상증자":
            return self._calc_equity_issuance(facts)
        if detail and detail.detail_type == "전환사채":
            return self._calc_convertible_bond(facts)
        if detail and detail.detail_type == "공급계약":
            return self._calc_supply_contract(facts)
        return self._calc_earnings_report(facts)

    def _calc_earnings_report(self, facts: FilingFacts) -> FilingImpact:
        metrics: dict[str, float] = {}
        for key, comp in facts.comparisons.items():
            metrics[key.replace("_yoy", "_yoy_pct")] = comp.change_pct

        oi = facts.financials.get("operating_margin")
        if oi:
            metrics["operating_margin_pct"] = float(oi.value)

        direction = self._infer_direction(facts)
        severity = self._infer_severity(metrics)

        parts = []
        rev_yoy = metrics.get("revenue_yoy_pct")
        if rev_yoy is not None:
            parts.append(f"매출 YoY {rev_yoy:+.1f}%")
        oi_yoy = metrics.get("operating_income_yoy_pct")
        if oi_yoy is not None:
            parts.append(f"영업이익 YoY {oi_yoy:+.1f}%")

        return FilingImpact(
            facts=facts,
            impact_type="실적발표",
            metrics=metrics,
            severity=severity,
            direction=direction,
            summary=", ".join(parts) if parts else "비교 데이터 없음",
            confidence="high" if facts.comparisons else "low",
        )

    def _calc_equity_issuance(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail
        shares = facts.financials.get("shares_outstanding")
        equity = facts.financials.get("total_equity")

        metrics: dict[str, float] = {}
        if detail.new_shares and shares:
            total_after = float(shares.value) + detail.new_shares
            metrics["dilution_pct"] = round(detail.new_shares / total_after * 100, 2)
            metrics["new_shares"] = float(detail.new_shares)
        if detail.issue_price:
            metrics["issue_price"] = float(detail.issue_price)
        if detail.new_shares and detail.issue_price:
            proceeds = detail.new_shares * float(detail.issue_price)
            metrics["proceeds"] = proceeds
            if equity:
                metrics["proceeds_to_equity_pct"] = round(proceeds / float(equity.value) * 100, 2)

        return FilingImpact(
            facts=facts,
            impact_type="유상증자",
            metrics=metrics,
            severity="High" if metrics.get("dilution_pct", 0) > 10 else "Medium",
            direction="부정",
            summary=f"희석률 {metrics.get('dilution_pct', 0):.1f}%, 자금용도 {detail.purpose or '미공개'}",
            confidence="medium",
        )

    def _calc_convertible_bond(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail
        shares = facts.financials.get("shares_outstanding")

        metrics: dict[str, float] = {}
        if detail.conversion_shares and shares:
            metrics["overhang_pct"] = round(detail.conversion_shares / float(shares.value) * 100, 2)
            metrics["conversion_shares"] = float(detail.conversion_shares)
        if detail.conversion_price:
            metrics["conversion_price"] = float(detail.conversion_price)
        if detail.cb_amount:
            metrics["cb_amount"] = float(detail.cb_amount)

        return FilingImpact(
            facts=facts,
            impact_type="전환사채",
            metrics=metrics,
            severity="High" if metrics.get("overhang_pct", 0) > 10 else "Medium",
            direction="부정",
            summary=f"오버행 {metrics.get('overhang_pct', 0):.1f}%, 만기 {detail.maturity_date or '미공개'}",
            confidence="medium",
        )

    def _calc_supply_contract(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail
        revenue = facts.financials.get("revenue")

        metrics: dict[str, float] = {}
        if detail.contract_amount:
            metrics["contract_amount"] = float(detail.contract_amount)
            if revenue and float(revenue.value) > 0:
                metrics["revenue_ratio_pct"] = round(
                    float(detail.contract_amount) / float(revenue.value) * 100, 2
                )

        return FilingImpact(
            facts=facts,
            impact_type="공급계약",
            metrics=metrics,
            severity="High" if metrics.get("revenue_ratio_pct", 0) > 10 else "Medium",
            direction="긍정",
            summary=f"매출 대비 {metrics.get('revenue_ratio_pct', 0):.1f}%, 상대방 {detail.counterparty or '미공개'}",
            confidence="medium",
        )

    def _infer_direction(self, facts: FilingFacts) -> str:
        if not facts.comparisons:
            return "중립"
        positive = sum(1 for c in facts.comparisons.values() if c.change_pct > 0)
        negative = sum(1 for c in facts.comparisons.values() if c.change_pct < 0)
        if positive > negative:
            return "긍정"
        if negative > positive:
            return "부정"
        return "중립"

    def _infer_severity(self, metrics: dict[str, float]) -> str:
        changes = [abs(v) for k, v in metrics.items() if "yoy_pct" in k]
        if not changes:
            return "Low"
        avg = sum(changes) / len(changes)
        if avg > 20:
            return "High"
        if avg > 5:
            return "Medium"
        return "Low"
