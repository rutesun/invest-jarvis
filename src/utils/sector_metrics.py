class SectorMetrics:
    """섹터별 우선순위 지표 정의"""

    TECHNOLOGY = [
        "peg_ratio",
        "ps_ratio",
        "revenue_growth",
        "earnings_growth",
        "operating_margin",
        "fcf_yield",
        "debt_to_equity",
    ]

    FINANCIALS = [
        "roe", "roa", "pb_ratio", "debt_to_equity", "earnings_growth"
    ]

    CONSUMER_CYCLICAL = [
        "peg_ratio", "revenue_growth", "gross_margin", "debt_to_equity", "free_cash_flow"
    ]

    CONSUMER_DEFENSIVE = [
        "dividend_yield", "pe_ratio", "gross_margin", "roe", "payout_ratio"
    ]

    HEALTHCARE = [
        "peg_ratio", "revenue_growth", "operating_margin", "roe", "fcf_yield"
    ]

    INDUSTRIALS = [
        "pe_ratio", "roe", "debt_to_equity", "free_cash_flow", "operating_margin"
    ]

    ENERGY = [
        "pb_ratio", "debt_to_equity", "fcf_yield", "operating_margin", "dividend_yield"
    ]

    REAL_ESTATE = [
        "pb_ratio", "dividend_yield", "debt_to_equity", "free_cash_flow"
    ]

    UTILITIES = [
        "dividend_yield", "pe_ratio", "debt_to_equity", "payout_ratio"
    ]

    COMMUNICATION_SERVICES = [
        "pe_ratio", "ev_ebitda", "revenue_growth", "fcf_yield", "operating_margin"
    ]

    DEFAULT = [
        "pe_ratio",
        "roe",
        "revenue_growth",
        "debt_to_equity",
        "free_cash_flow",
    ]

    @classmethod
    def get_priority_metrics(cls, sector: str | None) -> list[str]:
        """주어진 섹터의 우선순위 지표 반환

        yfinance 섹터명 변형을 처리하기 위해 퍼지 매칭 사용.
        섹터가 None이거나 인식되지 않으면 DEFAULT 반환.

        Args:
            sector: yfinance에서 가져온 섹터 문자열

        Returns:
            우선순위 지표 리스트
        """
        if not sector:
            return cls.DEFAULT

        sector_lower = sector.lower()

        if "technolog" in sector_lower:
            return cls.TECHNOLOGY
        elif "financial" in sector_lower:
            return cls.FINANCIALS
        elif "consumer cyclical" in sector_lower or "consumer discretionary" in sector_lower:
            return cls.CONSUMER_CYCLICAL
        elif "consumer defensive" in sector_lower or "consumer staples" in sector_lower:
            return cls.CONSUMER_DEFENSIVE
        elif "healthcare" in sector_lower or "health care" in sector_lower:
            return cls.HEALTHCARE
        elif "industrial" in sector_lower:
            return cls.INDUSTRIALS
        elif "energy" in sector_lower:
            return cls.ENERGY
        elif "real estate" in sector_lower:
            return cls.REAL_ESTATE
        elif "utilit" in sector_lower:
            return cls.UTILITIES
        elif "communication" in sector_lower:
            return cls.COMMUNICATION_SERVICES

        return cls.DEFAULT
