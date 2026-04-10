from pydantic import BaseModel


class UniverseStock(BaseModel):
    """A stock in the screener universe."""
    ticker: str
    name: str
    market: str  # "KOSPI", "KOSDAQ", "NAS", "NYS"
    sources: list[str]  # ["theme", "volume_rank", "rise_rank", "kis_rank", "direct"]
    theme: str | None = None
    theme_change_rate: float | None = None
    price: float | None = None
    change_pct: float | None = None


class ScreenerEvidence(BaseModel):
    """Scored evidence for a stock."""
    stock: UniverseStock
    accumulation_score: float = 0.0
    # Daily net buy (most recent trading day)
    daily_foreign: int = 0
    daily_institution: int = 0
    daily_program: int = 0
    # 10-day aggregated net buy
    foreign_net: int = 0
    institution_net: int = 0
    program_net: int = 0
    # 10-day buy days count (how many days had net buying)
    foreign_days_count: int = 0
    institution_days_count: int = 0
    program_days_count: int = 0
    up_days: int = 0  # collected but not scored
    volume_burst_score: float = 0.0
    source_diversity_bonus: float = 0.0
    momentum_total: float = 0.0
    total_score: float = 0.0  # accumulation + volume_burst + diversity (excludes up_days)
    vol_ratio: float = 0.0
    rank: int = 0
