# src/tools/filing/concepts.py
"""SEC XBRL 태그 fallback 체인 + DART 계정명 매핑."""

# SEC: metric → XBRL 태그 fallback 체인 (우선순위 순)
SEC_CONCEPT_CHAINS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "cost_of_revenue": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss", "IncomeLossFromOperations"],
    "ebitda": [
        "EarningsBeforeInterestTaxesDepreciationAndAmortization",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps": [
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByOperatingActivities",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
    ],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "total_debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ],
}

# DART: 계정명 → metric key
DART_ACCOUNT_MAPPING: dict[str, str] = {
    "매출액": "revenue",
    "매출원가": "cost_of_revenue",
    "매출총이익": "gross_profit",
    "영업이익": "operating_income",
    "당기순이익": "net_income",
    "기본주당이익": "eps",
    "자산총계": "total_assets",
    "부채총계": "total_liabilities",
    "자본총계": "total_equity",
    "현금및현금성자산": "cash_and_equivalents",
    "영업활동으로인한현금흐름": "operating_cash_flow",
    "영업활동현금흐름": "operating_cash_flow",
    "유형자산의취득": "capex",
    "유형자산취득": "capex",
}


def resolve_sec_metric(metric: str, facts: dict[str, float | int]) -> float | None:
    """SEC XBRL facts에서 metric에 해당하는 값을 fallback 체인으로 검색."""
    chain = SEC_CONCEPT_CHAINS.get(metric)
    if not chain:
        return None
    for tag in chain:
        if tag in facts:
            return float(facts[tag])
    return None


def resolve_dart_metric(account_nm: str) -> str | None:
    """DART 계정명을 metric key로 변환."""
    return DART_ACCOUNT_MAPPING.get(account_nm)
