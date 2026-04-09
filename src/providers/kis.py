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
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
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
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100",
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
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010400",
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
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "TTTC8434R",
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
