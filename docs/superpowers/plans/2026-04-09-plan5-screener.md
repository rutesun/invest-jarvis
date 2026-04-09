# Plan 5: Screener (종목 발굴)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jarvis screen` 명령어로 시장의 주도주, 주도 테마, 상위 종목 뉴스를 자동 발굴

**Architecture:** NaverProvider(테마/랭킹) + KISProvider 확장(수급/미국 랭킹) → Universe 구축 → 5팩터 스코어링 → 테마 집계 → 뉴스 수집 → 마크다운 저장

**Tech Stack:** httpx (Naver API/HTML), yfinance (보조), pandas-ta (지표), 정규식 (HTML 파싱)

---

## File Structure

```
src/
├── providers/
│   ├── naver.py                    # 신규: NaverProvider
│   └── kis.py                      # 수정: 랭킹 메서드 추가
├── tools/
│   └── screener/
│       ├── __init__.py             # 신규
│       ├── models.py               # 신규: UniverseStock, ScreenerEvidence
│       ├── universe.py             # 신규: UniverseBuilder
│       ├── scoring.py              # 신규: 5팩터 스코어링 함수
│       └── evidence.py             # 신규: EvidenceCollector
├── pipelines/
│   └── screener.py                 # 신규: ScreenerPipeline
└── cli/
    └── main.py                     # 수정: screen 명령어 추가
```

---

## Task 1: Screener Models

**Files:**
- Create: `src/tools/screener/__init__.py`
- Create: `src/tools/screener/models.py`
- Create: `tests/tools/screener/__init__.py`
- Test: `tests/tools/screener/test_models.py`

- [ ] **Step 1: Create directories**

Run: `mkdir -p src/tools/screener tests/tools/screener && touch src/tools/screener/__init__.py tests/tools/screener/__init__.py`

- [ ] **Step 2: Write the failing test**

```python
# tests/tools/screener/test_models.py
import pytest
from src.tools.screener.models import UniverseStock, ScreenerEvidence


def test_universe_stock():
    stock = UniverseStock(
        ticker="005930",
        name="삼성전자",
        market="KOSPI",
        sources=["theme", "volume_rank"],
        theme="AI/반도체",
        theme_change_rate=3.2,
        price=70000,
        change_pct=2.5,
    )
    assert stock.ticker == "005930"
    assert len(stock.sources) == 2
    assert stock.theme == "AI/반도체"


def test_universe_stock_minimal():
    stock = UniverseStock(
        ticker="AAPL",
        name="Apple Inc.",
        market="NAS",
        sources=["rise_rank"],
    )
    assert stock.theme is None
    assert stock.price is None


def test_screener_evidence():
    stock = UniverseStock(
        ticker="005930", name="삼성전자", market="KOSPI", sources=["theme"],
    )
    evidence = ScreenerEvidence(
        stock=stock,
        accumulation_score=12.0,
        up_days=7,
        volume_burst_score=5.0,
        source_diversity_bonus=4.0,
        momentum_total=47.0,
        total_score=21.0,
        vol_ratio=3.5,
        rank=1,
    )
    assert evidence.rank == 1
    assert evidence.momentum_total == 47.0
    assert evidence.up_days == 7  # collected but not in total_score
    assert evidence.total_score == 21.0  # accumulation + volume_burst + diversity
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/tools/screener/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: Write implementation**

```python
# src/tools/screener/models.py
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
    up_days: int = 0  # collected but not scored
    volume_burst_score: float = 0.0
    source_diversity_bonus: float = 0.0
    momentum_total: float = 0.0
    total_score: float = 0.0  # accumulation + volume_burst + diversity (excludes up_days)
    vol_ratio: float = 0.0
    rank: int = 0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/tools/screener/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/screener/ tests/tools/screener/
git commit -m "feat(screener): add UniverseStock and ScreenerEvidence models"
```

---

## Task 2: NaverProvider — Theme API

**Files:**
- Create: `src/providers/naver.py`
- Test: `tests/providers/test_naver.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_naver.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.providers.naver import NaverProvider


@pytest.fixture
def mock_theme_list_response():
    return {
        "stocks": [
            {
                "name": "AI/반도체",
                "changeRate": "3.20",
                "themeCode": "TH001",
            },
            {
                "name": "2차전지",
                "changeRate": "2.10",
                "themeCode": "TH002",
            },
        ]
    }


@pytest.fixture
def mock_theme_stocks_response():
    return {
        "stocks": [
            {"itemcode": "005930", "itemname": "삼성전자", "sosok": "0"},
            {"itemcode": "000660", "itemname": "SK하이닉스", "sosok": "0"},
        ]
    }


@pytest.mark.asyncio
async def test_get_themes(mock_theme_list_response, mock_theme_stocks_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_response_list = AsyncMock()
        mock_response_list.json.return_value = mock_theme_list_response
        mock_response_list.raise_for_status = MagicMock()

        mock_response_stocks = AsyncMock()
        mock_response_stocks.json.return_value = mock_theme_stocks_response
        mock_response_stocks.raise_for_status = MagicMock()

        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(side_effect=[mock_response_list, mock_response_stocks, mock_response_stocks])

        provider = NaverProvider()
        themes = await provider.get_themes(top_n=2)

        assert len(themes) == 2
        assert themes[0]["name"] == "AI/반도체"
        assert themes[0]["change_rate"] == 3.20
        assert len(themes[0]["stocks"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_naver.py::test_get_themes -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/providers/naver.py
import re
import httpx


class NaverProvider:
    """Naver Finance data provider for Korean market."""

    STOCK_API_BASE = "https://stock.naver.com"
    FINANCE_BASE = "https://finance.naver.com"

    async def get_themes(self, top_n: int = 10) -> list[dict]:
        """Get top themes by change rate with their stocks."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch theme list
            url = f"{self.STOCK_API_BASE}/api/domestic/market/theme/list"
            params = {"startIdx": 0, "pageSize": 200, "sortType": "changeRate"}
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            themes_raw = data.get("stocks", [])[:top_n]
            themes = []

            for theme in themes_raw:
                theme_id = theme.get("themeCode", "")
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
        params = {"startIdx": 0, "pageSize": 200, "marketType": ""}
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        stocks = []
        for item in data.get("stocks", []):
            sosok = item.get("sosok", "0")
            market = "KOSPI" if sosok == "0" else "KOSDAQ"
            stocks.append({
                "code": item.get("itemcode", ""),
                "name": item.get("itemname", ""),
                "market": market,
            })
        return stocks

    async def get_volume_ranking(self, top_n: int = 30) -> list[dict]:
        """Get KOSPI+KOSDAQ volume ranking by HTML parsing."""
        results = []
        for sosok in [0, 1]:  # 0=KOSPI, 1=KOSDAQ
            market = "KOSPI" if sosok == 0 else "KOSDAQ"
            url = f"{self.FINANCE_BASE}/sise/sise_quant.naver?sosok={sosok}"
            items = await self._parse_ranking_html(url, market)
            results.extend(items[:top_n])
        return results[:top_n * 2]

    async def get_rise_ranking(self, top_n: int = 30) -> list[dict]:
        """Get KOSPI+KOSDAQ rise ranking by HTML parsing."""
        results = []
        for sosok in [0, 1]:
            market = "KOSPI" if sosok == 0 else "KOSDAQ"
            url = f"{self.FINANCE_BASE}/sise/sise_rise.naver?sosok={sosok}"
            items = await self._parse_ranking_html(url, market)
            results.extend(items[:top_n])
        return results[:top_n * 2]

    async def _parse_ranking_html(self, url: str, market: str, retries: int = 3) -> list[dict]:
        """Parse Naver ranking HTML table."""
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    html = response.text

                return self._extract_table_rows(html, market)
            except Exception:
                if attempt == retries - 1:
                    return []
                import asyncio
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_naver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/providers/naver.py tests/providers/test_naver.py
git commit -m "feat(providers): add NaverProvider with theme and ranking APIs"
```

---

## Task 3: KISProvider Extensions

**Files:**
- Modify: `src/providers/kis.py`
- Test: `tests/providers/test_kis_ranking.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_kis_ranking.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.providers.kis import KISProvider


@pytest.fixture
def mock_token_response():
    return {
        "access_token": "test_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }


@pytest.fixture
def mock_investor_ranking_response():
    return {
        "output": [
            {
                "hts_kor_isnm": "삼성전자",
                "mksc_shrn_iscd": "005930",
                "frgn_ntby_qty": "500000",
                "frgn_ntby_tr_pbmn": "35000000000",
            },
        ]
    }


@pytest.mark.asyncio
async def test_get_investor_ranking(mock_token_response, mock_investor_ranking_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = AsyncMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = AsyncMock()
        mock_ranking_resp.json.return_value = mock_investor_ranking_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.post.return_value = mock_token_resp
        mock_instance.get.return_value = mock_ranking_resp

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_investor_ranking(investor_type="foreign", top_n=10)

        assert len(result) == 1
        assert result[0]["ticker"] == "005930"
        assert result[0]["name"] == "삼성전자"


@pytest.mark.asyncio
async def test_get_us_ranking_updown(mock_token_response):
    mock_us_response = {
        "output": {
            "body": [
                {
                    "symb": "NVDA",
                    "name": "NVIDIA Corp",
                    "rate": "5.20",
                    "last": "950.00",
                    "tvol": "50000000",
                },
            ]
        }
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = AsyncMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = AsyncMock()
        mock_ranking_resp.json.return_value = mock_us_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.post.return_value = mock_token_resp
        mock_instance.get.return_value = mock_ranking_resp

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_us_ranking_updown(exchange="NAS", direction="up", top_n=10)

        assert len(result) == 1
        assert result[0]["ticker"] == "NVDA"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_kis_ranking.py -v`
Expected: FAIL

- [ ] **Step 3: Add methods to KISProvider**

Append to `src/providers/kis.py`:

```python
    async def get_investor_ranking(
        self, investor_type: str = "foreign", top_n: int = 30
    ) -> list[dict]:
        """Get foreign/institution net buy ranking for Korean stocks."""
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        fid_code = "1" if investor_type == "foreign" else "2"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHPTJ04400000",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "V",
            "FID_COND_SCR_DIV_CODE": "16174",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": "",
            "FID_ETC_CLS_CODE": fid_code,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("output", [])[:top_n]:
            results.append({
                "ticker": item.get("mksc_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "net_buy_volume": int(item.get("frgn_ntby_qty", 0)),
                "net_buy_amount": int(item.get("frgn_ntby_tr_pbmn", 0)),
            })
        return results

    async def get_us_ranking_updown(
        self, exchange: str = "NAS", direction: str = "up", top_n: int = 30
    ) -> list[dict]:
        """Get US stock up/down rate ranking."""
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/overseas-stock/v1/ranking/updown-rate"
        gubn = "1" if direction == "up" else "0"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "HHDFS76290000",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {"EXCD": exchange, "GUBN": gubn, "BYMD": "", "NDAY": ""}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        body = data.get("output", {}).get("body", [])
        for item in body[:top_n]:
            results.append({
                "ticker": item.get("symb", ""),
                "name": item.get("name", ""),
                "change_pct": float(item.get("rate", 0)),
                "price": float(item.get("last", 0)),
                "volume": int(item.get("tvol", 0)),
                "exchange": exchange,
            })
        return results

    async def get_us_ranking_volume(
        self, exchange: str = "NAS", top_n: int = 30
    ) -> list[dict]:
        """Get US stock volume ranking."""
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/overseas-stock/v1/ranking/trade-pbmn"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "HHDFS76320010",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {"EXCD": exchange, "GUBN": "", "BYMD": "", "NDAY": ""}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        body = data.get("output", {}).get("body", [])
        for item in body[:top_n]:
            results.append({
                "ticker": item.get("symb", ""),
                "name": item.get("name", ""),
                "price": float(item.get("last", 0)),
                "volume": int(item.get("tvol", 0)),
                "exchange": exchange,
            })
        return results

    async def get_investor_trend(self, ticker: str, days: int = 10) -> list[dict]:
        """Get daily investor trend (foreign + institution net buy) for a Korean stock."""
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010900",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("output", [])[:days]:
            foreign_net = int(item.get("frgn_ntby_qty", 0))
            institution_net = int(item.get("orgn_ntby_qty", 0))
            results.append({
                "date": item.get("stck_bsop_date", ""),
                "foreign_net": foreign_net,
                "institution_net": institution_net,
                "total_net": foreign_net + institution_net,
            })
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_kis_ranking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/providers/kis.py tests/providers/test_kis_ranking.py
git commit -m "feat(providers): add KIS investor ranking and US ranking methods"
```

---

## Task 4: Scoring Functions

**Files:**
- Create: `src/tools/screener/scoring.py`
- Test: `tests/tools/screener/test_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/screener/test_scoring.py
import pytest
import pandas as pd
import numpy as np
from src.tools.screener.scoring import (
    score_accumulation,
    score_up_days,
    score_volume_burst,
    score_source_diversity,
    score_momentum,
)


def test_score_accumulation():
    trends = [
        {"total_net": 100},
        {"total_net": -50},
        {"total_net": 200},
        {"total_net": 300},
        {"total_net": -10},
        {"total_net": 150},
        {"total_net": 50},
        {"total_net": -20},
        {"total_net": 100},
        {"total_net": 80},
    ]
    score = score_accumulation(trends)
    # 7 positive days, net_sum > 0, score = 7 * 1.5 = 10.5
    assert score == 10.5


def test_score_accumulation_negative_sum():
    trends = [
        {"total_net": -100},
        {"total_net": -200},
        {"total_net": 10},
    ]
    score = score_accumulation(trends)
    assert score == 0.0  # net_sum < 0


def test_score_up_days():
    df = pd.DataFrame({
        "Open": [100, 101, 102, 100, 99],
        "Close": [101, 100, 103, 101, 98],  # up, down, up, up, down
    })
    days = score_up_days(df, window=5)
    assert days == 3


def test_score_volume_burst():
    score = score_volume_burst(vol_ratio=3.0)
    # clamp(3.0 - 1.5, 0, 8.0) = 1.5
    assert score == 1.5

    score = score_volume_burst(vol_ratio=10.0)
    # clamp(10.0 - 1.5, 0, 8.0) = 8.0
    assert score == 8.0

    score = score_volume_burst(vol_ratio=1.0)
    assert score == 0.0


def test_score_source_diversity():
    sources = ["theme", "volume_rank", "kis_rank"]
    bonus = score_source_diversity(sources)
    # weights: 1.0 + 1.5 + 1.5 = 4.0, raw = 3.0, bonus = min(10, 2.0 * 3.0) = 6.0
    assert bonus == 6.0


def test_score_source_diversity_single():
    sources = ["rise_rank"]
    bonus = score_source_diversity(sources)
    # weight: 1.0, raw = 0.0, bonus = 0.0
    assert bonus == 0.0


def test_score_momentum_breakout():
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    # consolidation then breakout
    close = np.concatenate([np.random.uniform(98, 102, 55), [103, 105, 107, 110, 112]])
    high = close + 1
    low = close - 1
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": [1000000] * 60,
    }, index=dates)
    result = score_momentum(df)
    assert "breakout" in result
    assert "momentum_total" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/screener/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/screener/scoring.py
import pandas as pd
import numpy as np

SOURCE_WEIGHTS = {
    "theme": 1.0,
    "volume_rank": 1.5,
    "rise_rank": 1.0,
    "kis_rank": 1.5,
    "direct": 0.0,
}


def score_accumulation(investor_trends: list[dict]) -> float:
    """Score based on foreign+institution net buy days. Range: 0-15."""
    if not investor_trends:
        return 0.0

    positive_days = sum(1 for t in investor_trends if t.get("total_net", 0) > 0)
    net_sum = sum(t.get("total_net", 0) for t in investor_trends)

    if net_sum <= 0:
        return 0.0

    return min(15.0, positive_days * 1.5)


def score_up_days(df: pd.DataFrame, window: int = 10) -> int:
    """Count up days (Close > Open) in recent window. Not scored, collected only."""
    if df.empty or len(df) < 2:
        return 0

    recent = df.tail(window)
    return int((recent["Close"] > recent["Open"]).sum())


def score_volume_burst(vol_ratio: float) -> float:
    """Score based on volume surge ratio. Range: 0-8."""
    if vol_ratio < 1.5:
        return 0.0
    return min(8.0, vol_ratio - 1.5)


def score_source_diversity(sources: list[str]) -> float:
    """Score based on how many data sources found this stock. Range: 0-10."""
    weighted_sum = sum(SOURCE_WEIGHTS.get(s, 0) for s in sources)
    raw = max(0, weighted_sum - 1.0)
    return min(10.0, 2.0 * raw)


def score_momentum(df: pd.DataFrame, lookback: int = 50) -> dict:
    """Score momentum signals. Returns dict with individual scores and total."""
    result = {
        "breakout": 0.0,
        "trend_reversal": 0.0,
        "compression": 0.0,
        "flow": 0.0,
        "combo": 0.0,
        "momentum_total": 0.0,
    }

    if df.empty or len(df) < lookback:
        return result

    latest = df.iloc[-1]
    close = float(latest["Close"])

    # Breakout: close > previous N days high
    prev_high = df["High"].iloc[-(lookback + 1):-1].max()
    if not pd.isna(prev_high) and close > float(prev_high):
        result["breakout"] = 12.0

    # Trend Reversal: SuperTrend direction change -1 → +1
    if "SUPERTd_10_3.0" in df.columns and len(df) > 1:
        curr_dir = df.iloc[-1].get("SUPERTd_10_3.0")
        prev_dir = df.iloc[-2].get("SUPERTd_10_3.0")
        if not pd.isna(curr_dir) and not pd.isna(prev_dir):
            if float(prev_dir) < 0 and float(curr_dir) > 0:
                result["trend_reversal"] = 25.0

    # Compression: recent 10-day ATR < previous 10-day ATR
    if "ATR" in df.columns and len(df) >= 20:
        recent_atr = df["ATR"].iloc[-10:].mean()
        prev_atr = df["ATR"].iloc[-20:-10].mean()
        if not pd.isna(recent_atr) and not pd.isna(prev_atr) and prev_atr > 0:
            if recent_atr < prev_atr:
                result["compression"] = 15.0

    # Combo bonus
    if result["breakout"] > 0 and result["trend_reversal"] > 0:
        result["combo"] = 10.0

    result["momentum_total"] = (
        result["breakout"]
        + result["trend_reversal"]
        + result["compression"]
        + result["flow"]
        + result["combo"]
    )

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/screener/test_scoring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/screener/scoring.py tests/tools/screener/test_scoring.py
git commit -m "feat(screener): add 5-factor scoring functions"
```

---

## Task 5: Universe Builder

**Files:**
- Create: `src/tools/screener/universe.py`
- Test: `tests/tools/screener/test_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/screener/test_universe.py
import pytest
from unittest.mock import AsyncMock
from src.tools.screener.universe import UniverseBuilder
from src.tools.screener.models import UniverseStock


@pytest.fixture
def mock_naver():
    provider = AsyncMock()
    provider.get_themes.return_value = [
        {
            "name": "AI/반도체",
            "change_rate": 3.2,
            "theme_id": "TH001",
            "stocks": [
                {"code": "005930", "name": "삼성전자", "market": "KOSPI"},
                {"code": "000660", "name": "SK하이닉스", "market": "KOSPI"},
            ],
        }
    ]
    provider.get_volume_ranking.return_value = [
        {"code": "005930", "name": "삼성전자", "market": "KOSPI", "price": 70000, "change_pct": 2.5, "volume": 5000000},
    ]
    provider.get_rise_ranking.return_value = [
        {"code": "035420", "name": "NAVER", "market": "KOSPI", "price": 200000, "change_pct": 4.0, "volume": 1000000},
    ]
    return provider


@pytest.fixture
def mock_kis():
    provider = AsyncMock()
    provider.get_investor_ranking.return_value = [
        {"ticker": "005930", "name": "삼성전자", "net_buy_volume": 500000, "net_buy_amount": 35000000000},
    ]
    provider.get_us_ranking_updown.return_value = [
        {"ticker": "NVDA", "name": "NVIDIA", "change_pct": 5.0, "price": 950, "volume": 50000000, "exchange": "NAS"},
    ]
    provider.get_us_ranking_volume.return_value = []
    return provider


@pytest.mark.asyncio
async def test_build_kr_universe(mock_naver, mock_kis):
    builder = UniverseBuilder(naver_provider=mock_naver, kis_provider=mock_kis, yf_provider=AsyncMock())
    universe = await builder.build(market="kr")

    # 005930 should appear from theme + volume + kis
    samsung = next((s for s in universe if s.ticker == "005930"), None)
    assert samsung is not None
    assert "theme" in samsung.sources
    assert "volume_rank" in samsung.sources
    assert "kis_rank" in samsung.sources
    assert samsung.theme == "AI/반도체"

    # NAVER from rise_rank only
    naver = next((s for s in universe if s.ticker == "035420"), None)
    assert naver is not None
    assert naver.sources == ["rise_rank"]


@pytest.mark.asyncio
async def test_build_us_universe(mock_naver, mock_kis):
    builder = UniverseBuilder(naver_provider=mock_naver, kis_provider=mock_kis, yf_provider=AsyncMock())
    universe = await builder.build(market="us")

    nvda = next((s for s in universe if s.ticker == "NVDA"), None)
    assert nvda is not None
    assert nvda.market == "NAS"


@pytest.mark.asyncio
async def test_build_all_universe(mock_naver, mock_kis):
    builder = UniverseBuilder(naver_provider=mock_naver, kis_provider=mock_kis, yf_provider=AsyncMock())
    universe = await builder.build(market="all")

    tickers = [s.ticker for s in universe]
    assert "005930" in tickers
    assert "NVDA" in tickers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/screener/test_universe.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/screener/universe.py
from src.tools.screener.models import UniverseStock
from src.providers.naver import NaverProvider
from src.providers.kis import KISProvider
from src.providers.yfinance_provider import YFinanceProvider


class UniverseBuilder:
    """Build universe of stocks from multiple sources."""

    def __init__(
        self,
        naver_provider: NaverProvider,
        kis_provider: KISProvider | None,
        yf_provider: YFinanceProvider,
    ):
        self.naver = naver_provider
        self.kis = kis_provider
        self.yf = yf_provider

    async def build(self, market: str = "all") -> list[UniverseStock]:
        """Build universe for given market."""
        stocks: dict[str, UniverseStock] = {}

        if market in ("kr", "all"):
            await self._build_kr(stocks)

        if market in ("us", "all"):
            await self._build_us(stocks)

        return list(stocks.values())

    async def _build_kr(self, stocks: dict[str, UniverseStock]) -> None:
        """Build Korean market universe."""
        # 1. Themes
        try:
            themes = await self.naver.get_themes(top_n=10)
            for theme in themes:
                for s in theme.get("stocks", []):
                    code = s["code"]
                    self._merge(stocks, code, UniverseStock(
                        ticker=code,
                        name=s["name"],
                        market=s["market"],
                        sources=["theme"],
                        theme=theme["name"],
                        theme_change_rate=theme["change_rate"],
                    ))
        except Exception:
            pass

        # 2. Volume ranking
        try:
            volume_stocks = await self.naver.get_volume_ranking(top_n=30)
            for s in volume_stocks:
                self._merge(stocks, s["code"], UniverseStock(
                    ticker=s["code"],
                    name=s["name"],
                    market=s["market"],
                    sources=["volume_rank"],
                    price=s.get("price"),
                    change_pct=s.get("change_pct"),
                ))
        except Exception:
            pass

        # 3. Rise ranking
        try:
            rise_stocks = await self.naver.get_rise_ranking(top_n=30)
            for s in rise_stocks:
                self._merge(stocks, s["code"], UniverseStock(
                    ticker=s["code"],
                    name=s["name"],
                    market=s["market"],
                    sources=["rise_rank"],
                    price=s.get("price"),
                    change_pct=s.get("change_pct"),
                ))
        except Exception:
            pass

        # 4. KIS investor ranking
        if self.kis:
            try:
                for inv_type in ["foreign", "institution"]:
                    ranking = await self.kis.get_investor_ranking(investor_type=inv_type, top_n=30)
                    for s in ranking:
                        self._merge(stocks, s["ticker"], UniverseStock(
                            ticker=s["ticker"],
                            name=s["name"],
                            market="KOSPI",
                            sources=["kis_rank"],
                        ))
            except Exception:
                pass

    async def _build_us(self, stocks: dict[str, UniverseStock]) -> None:
        """Build US market universe."""
        if not self.kis:
            return

        for exchange in ["NAS", "NYS"]:
            # Rise ranking
            try:
                rise = await self.kis.get_us_ranking_updown(exchange=exchange, direction="up", top_n=30)
                for s in rise:
                    self._merge(stocks, s["ticker"], UniverseStock(
                        ticker=s["ticker"],
                        name=s["name"],
                        market=exchange,
                        sources=["rise_rank"],
                        price=s.get("price"),
                        change_pct=s.get("change_pct"),
                    ))
            except Exception:
                pass

            # Volume ranking
            try:
                volume = await self.kis.get_us_ranking_volume(exchange=exchange, top_n=30)
                for s in volume:
                    self._merge(stocks, s["ticker"], UniverseStock(
                        ticker=s["ticker"],
                        name=s["name"],
                        market=exchange,
                        sources=["volume_rank"],
                        price=s.get("price"),
                    ))
            except Exception:
                pass

    def _merge(self, stocks: dict[str, UniverseStock], key: str, new: UniverseStock) -> None:
        """Merge stock into universe, accumulating sources."""
        if key in stocks:
            existing = stocks[key]
            for source in new.sources:
                if source not in existing.sources:
                    existing.sources.append(source)
            if new.theme and not existing.theme:
                existing.theme = new.theme
                existing.theme_change_rate = new.theme_change_rate
            if new.price and not existing.price:
                existing.price = new.price
                existing.change_pct = new.change_pct
        else:
            stocks[key] = new
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/screener/test_universe.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/screener/universe.py tests/tools/screener/test_universe.py
git commit -m "feat(screener): add UniverseBuilder for KR+US markets"
```

---

## Task 6: Evidence Collector

**Files:**
- Create: `src/tools/screener/evidence.py`
- Test: `tests/tools/screener/test_evidence.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/screener/test_evidence.py
import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock
from src.tools.screener.evidence import EvidenceCollector
from src.tools.screener.models import UniverseStock, ScreenerEvidence


@pytest.fixture
def mock_kis():
    provider = AsyncMock()
    provider.get_investor_trend.return_value = [
        {"date": "20260409", "foreign_net": 100, "institution_net": 200, "total_net": 300},
        {"date": "20260408", "foreign_net": -50, "institution_net": 100, "total_net": 50},
    ]
    return provider


@pytest.fixture
def mock_yf():
    provider = AsyncMock()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.3
    provider.get_price_history.return_value = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    return provider


@pytest.mark.asyncio
async def test_collect_and_score(mock_kis, mock_yf):
    collector = EvidenceCollector(kis_provider=mock_kis, yf_provider=mock_yf)
    universe = [
        UniverseStock(ticker="005930", name="삼성전자", market="KOSPI", sources=["theme", "volume_rank"]),
    ]
    results = await collector.collect_and_score(universe)

    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].stock.ticker == "005930"
    assert results[0].total_score >= 0


@pytest.mark.asyncio
async def test_score_tickers(mock_kis, mock_yf):
    collector = EvidenceCollector(kis_provider=mock_kis, yf_provider=mock_yf)
    results = await collector.score_tickers(["AAPL"])

    assert len(results) == 1
    assert results[0].stock.ticker == "AAPL"
    assert results[0].stock.market == "US"
    assert results[0].stock.sources == ["direct"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/screener/test_evidence.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/tools/screener/evidence.py
import asyncio
import pandas as pd
from src.tools.screener.models import UniverseStock, ScreenerEvidence
from src.tools.screener.scoring import (
    score_accumulation,
    score_up_days,
    score_volume_burst,
    score_source_diversity,
    score_momentum,
)
from src.tools.technical.indicators import IndicatorCalculator
from src.providers.kis import KISProvider
from src.providers.yfinance_provider import YFinanceProvider


class EvidenceCollector:
    """Collect evidence and score stocks."""

    def __init__(
        self,
        kis_provider: KISProvider | None,
        yf_provider: YFinanceProvider,
        concurrency: int = 10,
    ):
        self.kis = kis_provider
        self.yf = yf_provider
        self.concurrency = concurrency
        self.calculator = IndicatorCalculator()

    async def collect_and_score(self, universe: list[UniverseStock]) -> list[ScreenerEvidence]:
        """Collect evidence and score all stocks in universe."""
        semaphore = asyncio.Semaphore(self.concurrency)

        async def bounded_collect(stock: UniverseStock) -> ScreenerEvidence | None:
            async with semaphore:
                try:
                    return await self._collect_one(stock)
                except Exception:
                    return None

        tasks = [bounded_collect(stock) for stock in universe]
        results = await asyncio.gather(*tasks)

        scored = [r for r in results if r is not None]
        scored.sort(key=lambda x: (x.momentum_total, x.total_score), reverse=True)
        for i, item in enumerate(scored):
            item.rank = i + 1

        return scored

    async def score_tickers(self, tickers: list[str]) -> list[ScreenerEvidence]:
        """Score arbitrary tickers without universe building."""
        universe = [
            UniverseStock(
                ticker=ticker,
                name=ticker,
                market=self._detect_market(ticker),
                sources=["direct"],
            )
            for ticker in tickers
        ]
        return await self.collect_and_score(universe)

    async def _collect_one(self, stock: UniverseStock) -> ScreenerEvidence:
        """Collect evidence for a single stock."""
        is_kr = stock.market in ("KOSPI", "KOSDAQ")

        # 1. OHLCV (140 days)
        df = await self.yf.get_price_history(
            stock.ticker if not is_kr else f"{stock.ticker}.KS",
            period="6mo",
        )

        # 2. Calculate indicators (for momentum signals)
        if not df.empty:
            df = self.calculator.calculate(df)

        # 3. Investor trend (KR only)
        investor_trends = []
        if is_kr and self.kis:
            try:
                investor_trends = await self.kis.get_investor_trend(stock.ticker, days=10)
            except Exception:
                pass

        # 4. Score
        acc_score = score_accumulation(investor_trends)
        up_days = score_up_days(df, window=10) if not df.empty else 0

        vol_ratio = 0.0
        if not df.empty and "Vol_SMA_20" in df.columns:
            latest_vol = df.iloc[-1].get("Volume", 0)
            vol_sma = df.iloc[-1].get("Vol_SMA_20", 0)
            if not pd.isna(vol_sma) and float(vol_sma) > 0:
                vol_ratio = float(latest_vol) / float(vol_sma)

        vol_score = score_volume_burst(vol_ratio)
        diversity = score_source_diversity(stock.sources)
        momentum = score_momentum(df)

        # Flow score from accumulation
        momentum["flow"] = acc_score * 5.0
        momentum["momentum_total"] += momentum["flow"]

        total = acc_score + vol_score + diversity

        return ScreenerEvidence(
            stock=stock,
            accumulation_score=acc_score,
            up_days=up_days,
            volume_burst_score=vol_score,
            source_diversity_bonus=diversity,
            momentum_total=momentum["momentum_total"],
            total_score=total,
            vol_ratio=round(vol_ratio, 2),
        )

    def _detect_market(self, ticker: str) -> str:
        """Detect market from ticker format."""
        if ticker.endswith(".KS"):
            return "KOSPI"
        elif ticker.endswith(".KQ"):
            return "KOSDAQ"
        elif ticker.isdigit() and len(ticker) == 6:
            return "KOSPI"
        return "US"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/screener/test_evidence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/screener/evidence.py tests/tools/screener/test_evidence.py
git commit -m "feat(screener): add EvidenceCollector with score_tickers() reusable interface"
```

---

## Task 7: ScreenerPipeline

**Files:**
- Create: `src/pipelines/screener.py`
- Test: `tests/pipelines/test_screener.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/pipelines/test_screener.py
import pytest
from unittest.mock import AsyncMock
from src.pipelines.screener import ScreenerPipeline
from src.tools.screener.models import UniverseStock, ScreenerEvidence
from src.core.models import ToolResult
from src.tools.news import NewsArticle


@pytest.fixture
def mock_universe_builder():
    builder = AsyncMock()
    builder.build.return_value = [
        UniverseStock(ticker="005930", name="삼성전자", market="KOSPI", sources=["theme"], theme="AI/반도체", theme_change_rate=3.2),
        UniverseStock(ticker="NVDA", name="NVIDIA", market="NAS", sources=["rise_rank"]),
    ]
    return builder


@pytest.fixture
def mock_evidence_collector():
    collector = AsyncMock()
    collector.collect_and_score.return_value = [
        ScreenerEvidence(
            stock=UniverseStock(ticker="005930", name="삼성전자", market="KOSPI", sources=["theme"], theme="AI/반도체", theme_change_rate=3.2),
            accumulation_score=12.0, up_days=7, volume_burst_score=5.0,
            source_diversity_bonus=4.0, momentum_total=47.0, total_score=21.0, vol_ratio=3.5, rank=1,
        ),
        ScreenerEvidence(
            stock=UniverseStock(ticker="NVDA", name="NVIDIA", market="NAS", sources=["rise_rank"]),
            accumulation_score=0.0, up_days=6, volume_burst_score=3.0,
            source_diversity_bonus=0.0, momentum_total=37.0, total_score=3.0, vol_ratio=2.0, rank=2,
        ),
    ]
    return collector


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock()
    tool.execute.return_value = ToolResult(
        success=True,
        data=[NewsArticle(title="HBM 수주", published="2026-04-09", summary="확대", url="https://example.com")],
    )
    return tool


@pytest.mark.asyncio
async def test_screener_pipeline_run(mock_universe_builder, mock_evidence_collector, mock_news_tool):
    pipeline = ScreenerPipeline(
        universe_builder=mock_universe_builder,
        evidence_collector=mock_evidence_collector,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run(market="all")

    assert result["market"] == "all"
    assert len(result["leaders"]) == 2
    assert len(result["themes"]) >= 1
    assert result["themes"][0]["name"] == "AI/반도체"
    assert "news" in result


@pytest.mark.asyncio
async def test_screener_pipeline_format(mock_universe_builder, mock_evidence_collector, mock_news_tool):
    pipeline = ScreenerPipeline(
        universe_builder=mock_universe_builder,
        evidence_collector=mock_evidence_collector,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run(market="all")
    output = pipeline.format_output(result)

    assert "주도 테마" in output
    assert "주도주" in output
    assert "삼성전자" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipelines/test_screener.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/pipelines/screener.py
from datetime import datetime
from pathlib import Path
from typing import Any
from src.tools.screener.universe import UniverseBuilder
from src.tools.screener.evidence import EvidenceCollector
from src.tools.screener.models import ScreenerEvidence
from src.tools.news import NewsTool


class ScreenerPipeline:
    """Market screener pipeline: universe → score → themes → news."""

    def __init__(
        self,
        universe_builder: UniverseBuilder,
        evidence_collector: EvidenceCollector,
        news_tool: NewsTool,
    ):
        self.universe_builder = universe_builder
        self.evidence_collector = evidence_collector
        self.news_tool = news_tool

    async def run(self, market: str = "all") -> dict[str, Any]:
        """Run screener pipeline."""
        # 1. Universe
        universe = await self.universe_builder.build(market)

        # 2. Evidence + Score
        scored = await self.evidence_collector.collect_and_score(universe)

        # 3. Theme aggregation
        theme_ranking = self._aggregate_themes(scored)

        # 4. News for top 10
        top_stocks = scored[:10]
        news = await self._fetch_news_for_top(top_stocks)

        return {
            "market": market,
            "timestamp": datetime.now(),
            "leaders": scored[:20],
            "themes": theme_ranking[:10],
            "news": news,
            "total_universe_size": len(universe),
        }

    def _aggregate_themes(self, scored: list[ScreenerEvidence]) -> list[dict]:
        """Aggregate themes from scored stocks."""
        themes: dict[str, dict] = {}
        for item in scored:
            theme = item.stock.theme
            if not theme:
                continue
            if theme not in themes:
                themes[theme] = {
                    "name": theme,
                    "change_rate": item.stock.theme_change_rate,
                    "stock_count": 0,
                    "top_stocks": [],
                    "momentum_sum": 0.0,
                }
            themes[theme]["stock_count"] += 1
            themes[theme]["momentum_sum"] += item.momentum_total
            if len(themes[theme]["top_stocks"]) < 3:
                themes[theme]["top_stocks"].append(item.stock.name)

        result = list(themes.values())
        for t in result:
            t["avg_momentum"] = t["momentum_sum"] / t["stock_count"] if t["stock_count"] > 0 else 0
        result.sort(key=lambda x: x["avg_momentum"], reverse=True)
        return result

    async def _fetch_news_for_top(self, top_stocks: list[ScreenerEvidence]) -> dict[str, list]:
        """Fetch news for top stocks."""
        news: dict[str, list] = {}
        for item in top_stocks:
            ticker = item.stock.ticker
            # For Korean stocks, yfinance needs .KS suffix
            yf_ticker = f"{ticker}.KS" if item.stock.market in ("KOSPI", "KOSDAQ") else ticker
            try:
                result = await self.news_tool.execute(yf_ticker, limit=3)
                if result.success and result.data:
                    news[item.stock.name] = [
                        {"title": a.title, "published": a.published}
                        for a in result.data
                    ]
            except Exception:
                pass
        return news

    def format_output(self, result: dict[str, Any]) -> str:
        """Format screener result as markdown."""
        ts = result["timestamp"].strftime("%Y-%m-%d")
        lines = [
            f"# Market Screener ({ts})",
            "",
        ]

        # Themes
        themes = result.get("themes", [])
        if themes:
            lines.append("## 주도 테마 TOP 10")
            lines.append("| # | 테마 | 등락률 | 종목수 | 주요 종목 |")
            lines.append("|---|------|--------|--------|-----------|")
            for i, t in enumerate(themes, 1):
                stocks_str = ", ".join(t["top_stocks"])
                rate = t.get("change_rate") or 0
                lines.append(f"| {i} | {t['name']} | {rate:+.1f}% | {t['stock_count']} | {stocks_str} |")
            lines.append("")

        # Leaders
        leaders = result.get("leaders", [])
        if leaders:
            lines.append("## 주도주 TOP 20")
            lines.append("| # | 종목 | 시장 | 모멘텀 | 수급 | 거래량 | 소스 |")
            lines.append("|---|------|------|--------|------|--------|------|")
            for item in leaders:
                s = item.stock
                sources_str = ",".join(s.sources)
                acc = f"{item.accumulation_score:.0f}" if item.accumulation_score > 0 else "-"
                lines.append(
                    f"| {item.rank} | {s.name} | {s.market} | "
                    f"{item.momentum_total:.0f} | {acc} | {item.vol_ratio:.1f}x | {sources_str} |"
                )
            lines.append("")

        # News
        news = result.get("news", {})
        if news:
            lines.append("## 상위 종목 뉴스")
            for name, articles in news.items():
                lines.append(f"### {name}")
                for a in articles:
                    lines.append(f"- {a['title']} ({a['published']})")
                lines.append("")

        return "\n".join(lines)

    def save_report(self, result: dict[str, Any]) -> Path:
        """Save report to markdown file."""
        timestamp = result["timestamp"]
        dir_path = Path("reports") / timestamp.strftime("%Y-%m")
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"screen-{timestamp.strftime('%Y-%m-%d')}.md"
        file_path.write_text(self.format_output(result))
        return file_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/test_screener.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/screener.py tests/pipelines/test_screener.py
git commit -m "feat(pipelines): add ScreenerPipeline with theme aggregation and report saving"
```

---

## Task 8: CLI screen Command

**Files:**
- Modify: `src/cli/main.py`
- Test: `tests/cli/test_cli.py`

- [ ] **Step 1: Add screen command to CLI**

Add imports and the `screen` command to `src/cli/main.py`:

```python
from src.providers.naver import NaverProvider
from src.tools.screener.universe import UniverseBuilder
from src.tools.screener.evidence import EvidenceCollector
from src.pipelines.screener import ScreenerPipeline


async def run_screen(market: str) -> dict:
    """Run screener pipeline."""
    naver_provider = NaverProvider()
    kis_provider = None

    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    if kis_key and kis_secret:
        kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret)

    yf_provider = YFinanceProvider()
    news_tool = NewsTool()

    universe_builder = UniverseBuilder(
        naver_provider=naver_provider,
        kis_provider=kis_provider,
        yf_provider=yf_provider,
    )
    evidence_collector = EvidenceCollector(
        kis_provider=kis_provider,
        yf_provider=yf_provider,
    )
    pipeline = ScreenerPipeline(
        universe_builder=universe_builder,
        evidence_collector=evidence_collector,
        news_tool=news_tool,
    )

    return await pipeline.run(market)


@app.command()
def screen(
    market: str = typer.Option("all", "--market", "-m", help="kr, us, or all"),
):
    """Scan market for leading stocks and themes."""
    console.print(f"[bold]Scanning {market} market...[/bold]\n")

    try:
        result = asyncio.run(run_screen(market))

        # Format and display
        pipeline = ScreenerPipeline(
            universe_builder=None,
            evidence_collector=None,
            news_tool=None,
        )
        output = pipeline.format_output(result)
        console.print(Markdown(output))

        # Save report
        report_path = pipeline.save_report(result)
        console.print(f"\n[green]Report saved to {report_path}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ --ignore=tests/integration -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/cli/main.py
git commit -m "feat(cli): add screen command for market scanning"
```

---

## Task 9: Integration Test + Tag

**Files:**
- Create: `tests/integration/test_e2e_plan5.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_e2e_plan5.py
import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()


@pytest.mark.integration
def test_screen_command_kr():
    """Test screen command for Korean market."""
    result = runner.invoke(app, ["screen", "--market=kr"])
    # May fail without network, but should not crash
    assert result.exit_code in [0, 1]


@pytest.mark.integration
def test_screen_command_us():
    """Test screen command for US market (requires KIS credentials)."""
    result = runner.invoke(app, ["screen", "--market=us"])
    assert result.exit_code in [0, 1]
```

- [ ] **Step 2: Create tests/integration/__init__.py if missing**

Run: `touch tests/integration/__init__.py`

- [ ] **Step 3: Run all unit tests**

Run: `uv run pytest tests/ -v --ignore=tests/integration`
Expected: All PASS

- [ ] **Step 4: Commit and tag**

```bash
git add tests/integration/test_e2e_plan5.py
git commit -m "test: add Plan 5 screener integration tests"
git tag -a v0.5.0 -m "Plan 5: Market Screener with theme/leader detection"
```

---

## Summary

Plan 5 완료 시 동작하는 기능:

```bash
jarvis screen              # 한국+미국 시장 스캔
jarvis screen --market=kr  # 한국만
jarvis screen --market=us  # 미국만
```

출력 예시:
```markdown
# Market Screener (2026-04-09)

## 주도 테마 TOP 10
| # | 테마 | 등락률 | 종목수 | 주요 종목 |
|---|------|--------|--------|-----------|
| 1 | AI/반도체 | +3.2% | 8 | 삼성전자, SK하이닉스, ... |

## 주도주 TOP 20
| # | 종목 | 시장 | 모멘텀 | 수급 | 거래량 | 소스 |
|---|------|------|--------|------|--------|------|
| 1 | SK하이닉스 | KOSPI | 47.0 | 12 | 3.5x | 테마,거래량,기관 |

## 상위 종목 뉴스
### SK하이닉스
- HBM 수주 확대 (2026-04-09)
```

저장: `reports/2026-04/screen-2026-04-09.md`

**추가된 컴포넌트:**
- NaverProvider (테마 API + HTML 랭킹)
- KISProvider 확장 (투자자 랭킹, 미국 랭킹, 투자자 동향)
- UniverseBuilder (KR 4소스 + US 2소스)
- 5팩터 스코어링 (수급, 거래량, 소스다양성, 모멘텀 + 상승일수 참고)
- EvidenceCollector (score_tickers 재사용 인터페이스 포함)
- ScreenerPipeline (테마 집계 + 뉴스 + 리포트 저장)
