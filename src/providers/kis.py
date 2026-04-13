import asyncio
from functools import lru_cache
import httpx
import pandas as pd
from datetime import datetime, timedelta
from src.core.interfaces import BaseProvider
from src.providers.kis_models import KISToken, KISQuote


class KISProvider(BaseProvider):
    """한국투자증권 API provider for Korean stocks."""

    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self._token: KISToken | None = None
        self._token_expires: datetime | None = None

    async def _get_access_token(self) -> KISToken:
        """Get or refresh access token."""
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        url = f"{self.BASE_URL}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        self._token = KISToken(**data)
        self._token_expires = datetime.now() + timedelta(seconds=data["expires_in"] - 60)
        return self._token

    async def get_quote(self, ticker: str) -> dict:
        """Get current quote for Korean stock."""
        token = await self._get_access_token()

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100",
            "custtype": "P",
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

        output = data["output"]
        return {
            "ticker": ticker,
            "price": float(output["stck_prpr"]),
            "change": float(output["prdy_vrss"]),
            "change_pct": float(output["prdy_ctrt"]),
            "volume": int(output["acml_vol"]),
            "name": output.get("hts_kor_isnm", ""),
        }

    async def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data for Korean stock."""
        period_days_map = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730,
        }
        days = period_days_map.get(period, 365)

        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        headers = {
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010400",
            "custtype": "P",
            "Content-Type": "application/json; charset=utf-8",
        }

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        records = []
        for item in data.get("output", []):
            records.append({
                "Date": pd.to_datetime(item["stck_bsop_date"]),
                "Open": float(item["stck_oprc"]),
                "High": float(item["stck_hgpr"]),
                "Low": float(item["stck_lwpr"]),
                "Close": float(item["stck_clpr"]),
                "Volume": int(item["acml_vol"]),
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df.set_index("Date", inplace=True)
            df.sort_index(inplace=True)

        return df

    async def get_balance(self) -> dict:
        """Get portfolio balance and positions."""
        token = await self._get_access_token()

        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = {
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "TTTC8434R",
            "custtype": "P",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "CANO": "계좌번호",
            "ACNT_PRDT_CD": "01",
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        output1 = data.get("output1", [])
        output2 = data.get("output2", {})

        positions = []
        for item in output1:
            positions.append({
                "ticker": item["pdno"],
                "name": item["prdt_name"],
                "quantity": int(item["hldg_qty"]),
                "avg_price": float(item["pchs_avg_pric"]),
                "current_price": float(item["prpr"]),
                "profit_loss": float(item["evlu_pfls_amt"]),
                "profit_loss_pct": float(item["evlu_pfls_rt"]),
            })

        return {
            "total_assets": float(output2.get("tot_evlu_amt", 0)),
            "cash": float(output2.get("prvs_rcdl_excc_amt", 0)),
            "stock_value": float(output2.get("scts_evlu_amt", 0)),
            "positions": positions,
        }

    async def get_investor_ranking(
        self, investor_type: str = "foreign", top_n: int = 30
    ) -> list[dict]:
        """Get foreign/institution net buy ranking for Korean stocks."""
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        fid_code = "1" if investor_type == "foreign" else "2"
        headers = {
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHPTJ04400000",
            "custtype": "P",
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
        """Get US stock up/down rate ranking.

        Args:
            exchange: Exchange code (NAS=NASDAQ, NYS=NYSE, AMS=AMEX)
            direction: "up" for rise, "down" for fall
            top_n: Number of stocks to return

        Returns:
            List of stocks with ticker, name, change_pct, price, volume
        """
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/overseas-stock/v1/ranking/updown-rate"
        gubn = "1" if direction == "up" else "0"
        headers = {
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "HHDFS76290000",
            "custtype": "P",
            "Content-Type": "application/json; charset=utf-8",
        }
        # NDAY: 0=today, 1=previous day
        # VOL_RANG: 0=all, 1=100+, 2=1K+, 3=10K+, 4=100K+, 5=1M+, 6=10M+
        # Use previous day data if current market is closed
        params = {
            "EXCD": exchange,
            "NDAY": "1",  # Previous day (more reliable than today)
            "GUBN": gubn,
            "VOL_RANG": "0",  # All volume
            "AUTH": "",
            "KEYB": "",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        # Response structure: {"output1": {...}, "output2": [...]}
        # output2 contains the actual stock list
        output2 = data.get("output2", [])
        for item in output2[:top_n]:
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
        """Get US stock volume ranking.

        Args:
            exchange: Exchange code (NAS=NASDAQ, NYS=NYSE, AMS=AMEX)
            top_n: Number of stocks to return

        Returns:
            List of stocks with ticker, name, price, volume
        """
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/overseas-stock/v1/ranking/trade-vol"
        headers = {
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "HHDFS76410000",
            "custtype": "P",
            "Content-Type": "application/json; charset=utf-8",
        }
        # Use previous day data if current market is closed
        params = {
            "EXCD": exchange,
            "NDAY": "1",  # Previous day
            "GUBN": "",
            "VOL_RANG": "0",  # All volume
            "AUTH": "",
            "KEYB": "",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        # Response structure: {"output1": {...}, "output2": [...]}
        # output2 contains the actual stock list
        output2 = data.get("output2", [])
        for item in output2[:top_n]:
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
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010900",
            "custtype": "P",
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
            # Handle empty strings from API
            foreign_val = item.get("frgn_ntby_qty", "0") or "0"
            institution_val = item.get("orgn_ntby_qty", "0") or "0"
            try:
                foreign_net = int(foreign_val.strip()) if isinstance(foreign_val, str) and foreign_val.strip() else int(foreign_val) if foreign_val else 0
            except (ValueError, AttributeError):
                foreign_net = 0
            try:
                institution_net = int(institution_val.strip()) if isinstance(institution_val, str) and institution_val.strip() else int(institution_val) if institution_val else 0
            except (ValueError, AttributeError):
                institution_net = 0
            results.append({
                "date": item.get("stck_bsop_date", ""),
                "foreign_net": foreign_net,
                "institution_net": institution_net,
                "total_net": foreign_net + institution_net,
            })
        return results

    async def get_program_trade(self, ticker: str, days: int = 10) -> list[dict]:
        """Get daily program trading data for a Korean stock.

        Args:
            ticker: Stock ticker code (6 digits)
            days: Number of days to fetch (default 10)

        Returns:
            List of daily program trading data with date and net buy quantity
        """
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/program-trade-by-stock-daily"
        headers = {
            "authorization": f"Bearer {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHPPG04650201",
            "custtype": "P",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": "",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("output", [])[:days]:
            # Handle empty strings from API
            program_val = item.get("whol_smtn_ntby_qty", "0") or "0"
            try:
                program_net = int(program_val.strip()) if isinstance(program_val, str) and program_val.strip() else int(program_val) if program_val else 0
            except (ValueError, AttributeError):
                program_net = 0
            results.append({
                "date": item.get("stck_bsop_date", ""),
                "program_net": program_net,
            })
        return results
