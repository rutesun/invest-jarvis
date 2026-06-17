"""FMP (Financial Modeling Prep) provider for US sector/industry performance."""

import httpx


_BASE = "https://financialmodelingprep.com/stable"


class FmpProvider:
    """FMP 업종/섹터 perf (미국). 무료 티어 stable 엔드포인트."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def industry_snapshot(self, date: str) -> dict[str, float]:
        """특정일 industry별 평균 등락(%). exchange별 값을 industry 단위로 평균."""
        url = f"{_BASE}/industry-performance-snapshot"
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(url, params={"date": date, "apikey": self.api_key})
            r.raise_for_status()
            rows = r.json()

        agg: dict[str, list[float]] = {}
        for row in rows:
            ind = row.get("industry")
            ch = row.get("averageChange")
            if ind is not None and ch is not None:
                agg.setdefault(ind, []).append(float(ch))

        return {k: sum(v) / len(v) for k, v in agg.items() if v}

    async def historical_industry(self, industry: str) -> list[dict]:
        """industry 시계열 [{date, averageChange}, …] (API 반환 순서 그대로)."""
        url = f"{_BASE}/historical-industry-performance"
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(url, params={"industry": industry, "apikey": self.api_key})
            r.raise_for_status()
            return r.json()
