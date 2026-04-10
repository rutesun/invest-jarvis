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

        Args:
            sector: yfinance에서 가져온 섹터 문자열

        Returns:
            우선순위 지표 리스트
        """
        if not sector:
            return cls.DEFAULT

        if "technolog" in sector.lower():
            return cls.TECHNOLOGY

        return cls.DEFAULT
