"""KIS 분기 재무 / growth-ratio / 수정주가 응답 구조 1회성 검증.
실행: uv run python scripts/verify_kis_quarterly.py 005930
환경변수 KIS_APP_KEY, KIS_APP_SECRET 필요.
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from src.providers.kis import KISProvider


def _load_env() -> None:
    """Load .env from worktree root first, then fall back to main project root."""
    load_dotenv()
    if not os.environ.get("KIS_APP_KEY"):
        candidate = Path(__file__).parent.parent.parent.parent.parent / ".env"
        if candidate.exists():
            load_dotenv(candidate)


async def _fetch_price_range(
    kis: KISProvider, ticker: str, start: str, end: str, adj: str
) -> list[tuple[str, str]]:
    """Fetch price rows for a specific date range, returning (date, close) pairs."""
    token = await kis._get_access_token()
    url = f"{kis.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "Authorization": f"{token.token_type} {token.access_token}",
        "appkey": kis.app_key,
        "appsecret": kis.app_secret,
        "tr_id": "FHKST03010100",
        "Content-Type": "application/json; charset=utf-8",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_DATE_1": start,
        "FID_INPUT_DATE_2": end,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": adj,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        data = resp.json()
    rows = data.get("output2", [])
    return [(r["stck_bsop_date"], r["stck_clpr"]) for r in rows]


async def main(code: str) -> None:
    _load_env()
    kis = KISProvider(os.environ["KIS_APP_KEY"], os.environ["KIS_APP_SECRET"])

    # 1) profit-ratio 연간(0) vs 분기(1) — EPS 필드와 기간(stac_yymm) 확인
    for div in ("0", "1"):
        try:
            rows = await kis._get_finance_data(
                path="/uapi/domestic-stock/v1/finance/profit-ratio",
                tr_id="FHKST66430300",
                ticker=code,
                div_cls_code=div,
            )
            periods = [r.get("stac_yymm") for r in rows[:6]]
            has_eps = bool(rows) and "eps" in rows[0]
            print(f"[profit-ratio div={div}] rows={len(rows)} periods={periods} has_eps={has_eps}")
            if rows:
                print(f"    sample keys: {sorted(rows[0].keys())}")
        except httpx.HTTPStatusError as e:
            print(
                f"[profit-ratio div={div}] ERROR: {e.response.status_code} {e.response.text[:300]}"
            )

    # 2) growth-ratio 존재/필드 확인
    try:
        growth = await kis._get_finance_data(
            path="/uapi/domestic-stock/v1/finance/growth-ratio",
            tr_id="FHKST66430800",
            ticker=code,
            div_cls_code="1",
        )
        print(f"[growth-ratio div=1] rows={len(growth)}")
        if growth:
            print(f"    sample keys: {sorted(growth[0].keys())}")
            print(f"    sample row: {growth[0]}")
    except httpx.HTTPStatusError as e:
        print(f"[growth-ratio div=1] ERROR: {e.response.status_code} {e.response.text[:300]}")

    # 3) 수정주가 코드: 0 vs 1 비교
    #    005930 액면분할: 2018-05-04 (50000원→1000원, 50:1)
    #    분할 전 가격: ~2,600,000원 / 분할 후: ~52,000원 (raw)
    #    수정주가면 분할 전 종가가 ~52,000원 수준으로 표시되어야 함
    print("\n[price adj comparison] Checking 005930 split period (2018-04 to 2018-06):")
    for adj in ("0", "1"):
        try:
            pairs = await _fetch_price_range(kis, "005930", "20180401", "20180630", adj)
            # Sort by date ascending
            pairs.sort(key=lambda x: x[0])
            # Show first 3 (pre-split) and last 3 (post-split)
            pre = [p for p in pairs if p[0] < "20180504"][:3]
            post = [p for p in pairs if p[0] >= "20180504"][:3]
            print(f"  FID_ORG_ADJ_PRC={adj}")
            print(f"    pre-split  (< 20180504): {pre}")
            print(f"    post-split (>= 20180504): {post}")
        except httpx.HTTPStatusError as e:
            print(
                f"  FID_ORG_ADJ_PRC={adj} ERROR: {e.response.status_code} {e.response.text[:200]}"
            )

    # Also show recent 1y for reference
    for adj in ("0", "1"):
        try:
            df = await kis.get_price_history(code, period="1y", _org_adj_prc=adj)
            tail = df["Close"].tail(3).tolist() if not df.empty else []
            oldest = df["Close"].head(3).tolist() if not df.empty else []
            print(
                f"[price 1y FID_ORG_ADJ_PRC={adj}] rows={len(df)} "
                f"last_closes={tail} oldest_closes={oldest}"
            )
        except httpx.HTTPStatusError as e:
            print(
                f"[price 1y FID_ORG_ADJ_PRC={adj}] ERROR: "
                f"{e.response.status_code} {e.response.text[:200]}"
            )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "005930"))
