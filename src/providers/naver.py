import asyncio
import re
import httpx


class NaverProvider:
    """Naver Finance data provider for Korean market."""

    STOCK_API_BASE = "https://stock.naver.com"
    FINANCE_BASE = "https://finance.naver.com"

    async def get_themes(self, top_n: int = 10) -> list[dict]:
        """Get top themes by change rate with their stocks.

        Returns:
            list[dict]: List of themes, each with keys:
                - name: str
                - change_rate: float
                - theme_id: str
                - stocks: list[dict] with keys (code, name, market)
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch theme list
            url = f"{self.STOCK_API_BASE}/api/domestic/market/theme/list"
            params = {"startIdx": 0, "pageSize": 200, "sortType": "changeRate"}
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # API returns array directly, not {"stocks": [...]}
            themes_raw = data[:top_n] if isinstance(data, list) else []
            themes = []

            for theme in themes_raw:
                theme_id = theme.get("no", "")
                stocks = await self._fetch_theme_stocks(client, theme_id)
                themes.append({
                    "name": theme.get("name", ""),
                    "change_rate": float(theme.get("changeRate", 0)),
                    "theme_id": theme_id,
                    "stocks": stocks,
                })

            return themes

    async def _fetch_theme_stocks(self, client: httpx.AsyncClient, theme_id: str) -> list[dict]:
        """Fetch stocks for a specific theme."""
        url = f"{self.STOCK_API_BASE}/api/domestic/market/theme/{theme_id}/stocklist"
        params = {"startIdx": 0, "pageSize": 200, "marketType": "ALL"}
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # API returns array directly
        stocks_raw = data if isinstance(data, list) else []
        stocks = []
        for item in stocks_raw:
            sosok = item.get("sosok", "0")
            market = "KOSPI" if sosok == "0" else "KOSDAQ"
            stocks.append({
                "code": item.get("itemcode", ""),
                "name": item.get("itemname", ""),
                "market": market,
            })
        return stocks

    async def get_volume_ranking(self, top_n: int = 30) -> list[dict]:
        """Get KOSPI+KOSDAQ volume ranking by HTML parsing.

        Returns:
            list[dict]: List of stocks, each with keys:
                - code: str
                - name: str
                - market: str
                - price: float
                - change_pct: float
                - volume: int
        """
        results = []
        for sosok in [0, 1]:  # 0=KOSPI, 1=KOSDAQ
            market = "KOSPI" if sosok == 0 else "KOSDAQ"
            url = f"{self.FINANCE_BASE}/sise/sise_quant.naver?sosok={sosok}"
            items = await self._parse_ranking_html(url, market)
            results.extend(items[:top_n])
        return results[:top_n * 2]  # top_n from KOSPI + top_n from KOSDAQ

    async def get_rise_ranking(self, top_n: int = 30) -> list[dict]:
        """Get KOSPI+KOSDAQ rise ranking by HTML parsing.

        Returns:
            list[dict]: List of stocks, each with keys:
                - code: str
                - name: str
                - market: str
                - price: float
                - change_pct: float
                - volume: int
        """
        results = []
        for sosok in [0, 1]:
            market = "KOSPI" if sosok == 0 else "KOSDAQ"
            url = f"{self.FINANCE_BASE}/sise/sise_rise.naver?sosok={sosok}"
            items = await self._parse_ranking_html(url, market)
            results.extend(items[:top_n])
        return results[:top_n * 2]  # top_n from KOSPI + top_n from KOSDAQ

    async def _parse_ranking_html(self, url: str, market: str, retries: int = 3) -> list[dict]:
        """Parse Naver ranking HTML table."""
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    html = response.text

                return self._extract_table_rows(html, market)
            except (httpx.HTTPError, ValueError):
                if attempt == retries - 1:
                    return []
                await asyncio.sleep(1)
        return []

    def _extract_table_rows(self, html: str, market: str) -> list[dict]:
        """Extract rows from Naver type_2 table."""
        # Find type_2 table
        table_match = re.search(
            r"<table[^>]*class=['\"][^'\"]*type_2[^'\"]*['\"][^>]*>(.*?)</table>",
            html, re.S | re.I,
        )
        if not table_match:
            return []

        table_html = table_match.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)

        results = []
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
            if len(cells) < 6:
                continue

            # Extract code and name from link
            link_match = re.search(
                r"<a[^>]*href=['\"][^'\"]*code=(\d{6})[^'\"]*['\"][^>]*>(.*?)</a>",
                row, re.S | re.I,
            )
            if not link_match:
                continue

            code = link_match.group(1)
            name = self._strip_tags(link_match.group(2))

            price = self._to_float(self._strip_tags(cells[2]))
            change_pct = self._to_float(self._strip_tags(cells[4]))
            volume = self._to_int(self._strip_tags(cells[5]))

            if code and name:
                results.append({
                    "code": code,
                    "name": name,
                    "market": market,
                    "price": price,
                    "change_pct": change_pct,
                    "volume": volume,
                })

        return results

    @staticmethod
    def _strip_tags(text: str) -> str:
        s = re.sub(r"<[^>]+>", " ", text)
        s = re.sub(r"&nbsp;?", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def _to_float(text: str) -> float:
        try:
            return float(text.replace(",", "").replace("%", "").strip())
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _to_int(text: str) -> int:
        try:
            return int(text.replace(",", "").strip())
        except (ValueError, AttributeError):
            return 0
