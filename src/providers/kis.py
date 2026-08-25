import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import yaml

from src.core.interfaces import BaseProvider
from src.providers.kis_models import KISToken


logger = logging.getLogger(__name__)


# KIS FID_ORG_ADJ_PRC: "0" = 수정주가(split/dividend adjusted), "1" = 원주가(unadjusted).
# Confirmed via Task 1 live call: 005930 had a 50:1 split in May 2018.
# "0" returns split-adjusted closes (pre-split ~48 500 KRW, post-split ~52 000 KRW — continuous).
# "1" returns raw/unadjusted closes (pre-split ~2 400 000 KRW, post-split ~52 000 — chart distortion).
ADJUSTED = "0"


class KISProvider(BaseProvider):
    """한국투자증권 API provider for Korean stocks."""

    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self._token: KISToken | None = None
        self._token_expires: datetime | None = None

        # 토큰 캐시 파일 경로
        cache_dir = Path.home() / ".cache" / "invest-jarvis"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._token_cache_file = cache_dir / "kis_token.yaml"

    def _read_cached_token(self) -> str | None:
        """캐시된 토큰 읽기 (만료 체크 포함)"""
        try:
            if not self._token_cache_file.exists():
                return None

            with open(self._token_cache_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "token" not in data or "valid_date" not in data:
                return None

            # 만료 체크
            valid_date = data["valid_date"]
            now = datetime.now()

            if valid_date > now:
                return data["token"]
            return None
        except Exception:
            return None

    def _save_token_cache(self, token: str, expires_at: datetime) -> None:
        """토큰을 파일에 저장"""
        try:
            with open(self._token_cache_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    {"token": token, "valid_date": expires_at},
                    f,
                    allow_unicode=True,
                )
        except Exception:
            pass  # 캐시 저장 실패해도 진행

    async def _get_access_token(self) -> KISToken:
        """Get or refresh access token."""
        # 1. 메모리 캐시 체크
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        # 2. 파일 캐시 체크
        cached_token = self._read_cached_token()
        if cached_token:
            # KISToken 객체로 변환
            self._token = KISToken(
                access_token=cached_token,
                token_type="Bearer",
                expires_in=86400,
            )
            self._token_expires = datetime.now() + timedelta(hours=23)  # 여유 1시간
            return self._token

        # 3. 새 토큰 발급
        url = f"{self.BASE_URL}/oauth2/tokenP"
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
        }
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        # 공식 KIS API는 json= 대신 data=json.dumps() 사용
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, content=json.dumps(payload))

            if response.status_code == 403:
                raise ValueError(
                    f"KIS API 인증 거부 (403 Forbidden)\n"
                    f"Response: {response.text}\n\n"
                    "가능한 원인:\n"
                    "1. APP KEY 또는 APP SECRET이 잘못되었습니다\n"
                    "2. '국내주식시세' 서비스 승인이 필요합니다\n"
                    "3. IP 제한이 걸려있을 수 있습니다\n"
                    "4. 실전투자 계좌가 아닌 모의투자 계좌일 수 있습니다\n"
                    "5. 모의투자라면 /oauth2/token 엔드포인트를 사용해야 합니다"
                )
            response.raise_for_status()
            data = response.json()

        self._token = KISToken(**data)
        self._token_expires = datetime.now() + timedelta(seconds=data["expires_in"] - 60)

        # 토큰을 파일에 캐시
        try:
            if "access_token_token_expired" in data:
                expires_at = datetime.strptime(
                    data["access_token_token_expired"], "%Y-%m-%d %H:%M:%S"
                )
            else:
                # access_token_token_expired가 없으면 expires_in 사용 (24시간 - 1시간 여유)
                expires_at = datetime.now() + timedelta(seconds=data["expires_in"] - 3600)
            self._save_token_cache(self._token.access_token, expires_at)
        except Exception:
            pass  # 저장 실패해도 진행

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
            # 업종명 (한글) — Task 3b: 업종지수 코드와 다른 체계.
            # bstp_kor_isnm='전기·전자' → sector_code='0013' 변환에는 KOSPI_SECTOR_CODE 매핑 필요.
            "bstp_kor_isnm": output.get("bstp_kor_isnm", ""),
        }

    async def get_price_history(
        self, ticker: str, period: str = "1y", _org_adj_prc: str = ADJUSTED
    ) -> pd.DataFrame:
        """Get historical price data for Korean stock.

        KIS API는 한 번에 100일만 반환하므로, 필요시 여러 번 호출해서 병합합니다.

        _org_adj_prc: ADJUSTED(수정주가) or "0"(원주가). Use the module constant ADJUSTED.
        """
        period_days_map = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730,
            "3y": 1095,
        }
        days = period_days_map.get(period, 365)

        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

        all_records = []
        end_date = datetime.now()

        # KIS API는 100일 제한이 있으므로 필요한 만큼 여러 번 호출
        max_batches = (days // 100) + 1
        for batch in range(max_batches):
            if len(all_records) >= days:
                break

            batch_end = end_date - timedelta(days=batch * 100)
            batch_start = batch_end - timedelta(days=110)  # 여유 10일

            headers = {
                "Authorization": f"{token.token_type} {token.access_token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": "FHKST03010100",
                "Content-Type": "application/json; charset=utf-8",
            }

            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": batch_start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": batch_end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": _org_adj_prc,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

            # output2에서 데이터 추출
            for item in data.get("output2", []):
                all_records.append(
                    {
                        "Date": pd.to_datetime(item["stck_bsop_date"]),
                        "Open": float(item["stck_oprc"]),
                        "High": float(item["stck_hgpr"]),
                        "Low": float(item["stck_lwpr"]),
                        "Close": float(item["stck_clpr"]),
                        "Volume": int(item["acml_vol"]),
                    }
                )

        df = pd.DataFrame(all_records)
        if not df.empty:
            # 중복 제거 (날짜별)
            df = df.drop_duplicates(subset=["Date"])
            df.set_index("Date", inplace=True)
            df.sort_index(inplace=True)
            # Add timezone (Asia/Seoul) to match yfinance format
            df.index = df.index.tz_localize("Asia/Seoul")

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
            positions.append(
                {
                    "ticker": item["pdno"],
                    "name": item["prdt_name"],
                    "quantity": int(item["hldg_qty"]),
                    "avg_price": float(item["pchs_avg_pric"]),
                    "current_price": float(item["prpr"]),
                    "profit_loss": float(item["evlu_pfls_amt"]),
                    "profit_loss_pct": float(item["evlu_pfls_rt"]),
                }
            )

        return {
            "total_assets": float(output2.get("tot_evlu_amt", 0)),
            "cash": float(output2.get("prvs_rcdl_excc_amt", 0)),
            "stock_value": float(output2.get("scts_evlu_amt", 0)),
            "positions": positions,
        }

    async def get_investor_ranking(
        self, investor_type: str = "foreign", top_n: int = 30
    ) -> list[dict]:
        """Get foreign/institution net buy ranking for Korean stocks.

        외국인기관 매매종목가집계(FHPTJ04400000)는 한 응답에 종목별 외국인·기관
        순매수를 모두 담아 준다. 따라서 원하는 투자자(frgn/orgn)의 순매수 금액으로
        클라이언트 정렬해 순매수 상위만 반환한다.

        경계 계약: 이 엔드포인트는 FID_COND_SCR_DIV_CODE="16449"와
        FID_RANK_SORT_CLS_CODE를 요구한다(과거 "16174"/누락은 rt_cd!=0 또는
        빈 output을 유발). rt_cd != "0"이면 조용히 빈 리스트를 내리지 않고
        경고 후 반환한다.
        """
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHPTJ04400000",
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "V",
            "FID_COND_SCR_DIV_CODE": "16449",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_RANK_SORT_CLS_CODE": "0",  # 0: 금액순
            "FID_ETC_CLS_CODE": "0",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        if str(data.get("rt_cd")) != "0":
            logger.warning(
                "get_investor_ranking rt_cd=%s msg=%s (파라미터 계약 위반 가능)",
                data.get("rt_cd"),
                data.get("msg1"),
            )
            return []

        qty_key = "frgn_ntby_qty" if investor_type == "foreign" else "orgn_ntby_qty"
        amount_key = "frgn_ntby_tr_pbmn" if investor_type == "foreign" else "orgn_ntby_tr_pbmn"

        def _to_int(value) -> int:
            try:
                return int(str(value).strip() or 0)
            except (ValueError, AttributeError):
                return 0

        rows = [
            {
                "ticker": item.get("mksc_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "net_buy_volume": _to_int(item.get(qty_key, 0)),
                "net_buy_amount": _to_int(item.get(amount_key, 0)),
            }
            for item in data.get("output", [])
        ]
        # 해당 투자자 순매수(>0)만, 금액 큰 순
        buys = [r for r in rows if r["net_buy_amount"] > 0]
        buys.sort(key=lambda r: r["net_buy_amount"], reverse=True)
        return buys[:top_n]

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
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "HHDFS76290000",
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
            results.append(
                {
                    "ticker": item.get("symb", ""),
                    "name": item.get("name", ""),
                    "change_pct": float(item.get("rate", 0)),
                    "price": float(item.get("last", 0)),
                    "volume": int(item.get("tvol", 0)),
                    "exchange": exchange,
                }
            )
        return results

    async def get_us_ranking_volume(self, exchange: str = "NAS", top_n: int = 30) -> list[dict]:
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
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "HHDFS76410000",
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
            results.append(
                {
                    "ticker": item.get("symb", ""),
                    "name": item.get("name", ""),
                    "price": float(item.get("last", 0)),
                    "volume": int(item.get("tvol", 0)),
                    "exchange": exchange,
                }
            )
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
            # Handle empty strings from API
            foreign_val = item.get("frgn_ntby_qty", "0") or "0"
            institution_val = item.get("orgn_ntby_qty", "0") or "0"
            try:
                foreign_net = (
                    int(foreign_val.strip())
                    if isinstance(foreign_val, str) and foreign_val.strip()
                    else int(foreign_val)
                    if foreign_val
                    else 0
                )
            except (ValueError, AttributeError):
                foreign_net = 0
            try:
                institution_net = (
                    int(institution_val.strip())
                    if isinstance(institution_val, str) and institution_val.strip()
                    else int(institution_val)
                    if institution_val
                    else 0
                )
            except (ValueError, AttributeError):
                institution_net = 0
            results.append(
                {
                    "date": item.get("stck_bsop_date", ""),
                    "foreign_net": foreign_net,
                    "institution_net": institution_net,
                    "total_net": foreign_net + institution_net,
                }
            )
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
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHPPG04650201",
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
                program_net = (
                    int(program_val.strip())
                    if isinstance(program_val, str) and program_val.strip()
                    else int(program_val)
                    if program_val
                    else 0
                )
            except (ValueError, AttributeError):
                program_net = 0
            results.append(
                {
                    "date": item.get("stck_bsop_date", ""),
                    "program_net": program_net,
                }
            )
        return results

    async def _get_finance_data(
        self, path: str, tr_id: str, ticker: str, div_cls_code: str = "0"
    ) -> list[dict]:
        """Get domestic stock finance data from KIS API.

        div_cls_code: "0"=연간, "1"=분기 (confirmed via Task 1 live call).
        """
        token = await self._get_access_token()
        url = f"{self.BASE_URL}{path}"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "FID_DIV_CLS_CODE": div_cls_code,
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker.replace(".KS", "").replace(".KQ", ""),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        return data.get("output", [])

    async def get_financial_ratio(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
        return await self._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/financial-ratio",
            tr_id="FHKST66430100",
            ticker=ticker,
            div_cls_code=div_cls_code,
        )

    async def get_balance_sheet(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
        return await self._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/balance-sheet",
            tr_id="FHKST66430200",
            ticker=ticker,
            div_cls_code=div_cls_code,
        )

    async def get_profit_ratio(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
        return await self._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/profit-ratio",
            tr_id="FHKST66430300",
            ticker=ticker,
            div_cls_code=div_cls_code,
        )

    async def get_income_statement(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
        return await self._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/income-statement",
            tr_id="FHKST66430400",
            ticker=ticker,
            div_cls_code=div_cls_code,
        )

    async def get_other_major_ratios(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
        return await self._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/other-major-ratios",
            tr_id="FHKST66430500",
            ticker=ticker,
            div_cls_code=div_cls_code,
        )

    async def get_growth_ratio(self, ticker: str, div_cls_code: str = "0") -> list[dict]:
        """성장성비율 (매출/영업이익/순이익 증가율).

        EPS증가율은 응답에 없을 수 있음 — Task 1 실호출 검증 결과 참조.
        tr_id FHKST66430800 confirmed via Task 1 live call.
        """
        return await self._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/growth-ratio",
            tr_id="FHKST66430800",
            ticker=ticker,
            div_cls_code=div_cls_code,
        )

    async def get_sector_index_history(self, sector_code: str, period: str = "1y") -> pd.DataFrame:
        """국내 업종지수 일별 OHLCV. sector_code 예: '0001'(코스피종합).

        inquire-daily-indexchartprice (tr FHKUP03500100, FID_COND_MRKT_DIV_CODE='U').
        Plan 5 실호출 검증 — bstp_nmix_oprc/hgpr/lwpr/prpr 필드 사용.
        """
        token = await self._get_access_token()
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKUP03500100",
            "Content-Type": "application/json; charset=utf-8",
        }
        days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
        days = days_map.get(period, 365)
        end = datetime.now()
        start = end - timedelta(days=days)
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": sector_code,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()

        rows = []
        for it in data.get("output2", []):
            if not it.get("stck_bsop_date"):
                continue
            rows.append(
                {
                    "Date": pd.to_datetime(it["stck_bsop_date"]),
                    "Open": float(it.get("bstp_nmix_oprc") or 0),
                    "High": float(it.get("bstp_nmix_hgpr") or 0),
                    "Low": float(it.get("bstp_nmix_lwpr") or 0),
                    "Close": float(it.get("bstp_nmix_prpr") or 0),
                    "Volume": int(it.get("acml_vol") or 0),
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.drop_duplicates("Date").set_index("Date").sort_index()
            df.index = df.index.tz_localize("Asia/Seoul")
        return df
