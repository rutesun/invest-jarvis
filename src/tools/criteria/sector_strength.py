"""Sector strength evaluation (Plan 5 — CAN SLIM L / Gate C★).

FMP: US sector via industry-performance-snapshot (rank percentile + trend).
KIS: Korean sector index vs KOSPI relative strength + trend.
"""

from abc import ABC, abstractmethod

import pandas as pd

from src.tools.criteria.models import SectorStrengthResult


# ---------------------------------------------------------------------------
# yfinance industry name → FMP industry name normalization map.
# Derived from 2026-06-10 live API call (129 FMP industries vs yfinance names).
# Only entries where yfinance and FMP names differ are listed.
# ---------------------------------------------------------------------------
YF_TO_FMP_INDUSTRY: dict[str, str] = {
    "Auto Manufacturers": "Auto - Manufacturers",
    "Auto Parts": "Auto - Parts",
    "Auto Dealerships": "Auto - Dealerships",
    "Banks - Diversified": "Banks",
    "Internet Retail": "Retail - Specialty",  # FMP has no 'Internet Retail'
    "Specialty Retail": "Retail - Specialty",
    "Grocery Stores": "Grocery Stores",
    "Residential Construction": "Residential Construction",
    "Telecom Services": "Communication Services",
    "Broadcasting": "Broadcasting",
    "Electronic Components": "Electronic Components",
    "Scientific & Technical Instruments": "Scientific & Technical Instruments",
}

# ---------------------------------------------------------------------------
# KIS: Korean stock industry name (bstp_kor_isnm) → sector index code.
# Confirmed via 2026-06-11 live API call (inquire-daily-indexchartprice, MRKT_DIV=U).
# ---------------------------------------------------------------------------
KOSPI_SECTOR_CODE: dict[str, str] = {
    "종합": "0001",
    "대형주": "0002",
    "중형주": "0003",
    "소형주": "0004",
    "음식료·담배": "0005",
    "섬유·의류": "0006",
    "종이·목재": "0007",
    "화학": "0008",
    "제약": "0009",
    "비금속": "0010",
    "금속": "0011",
    "기계·장비": "0012",
    "전기·전자": "0013",
    "의료·정밀기기": "0014",
    "운송장비·부품": "0015",
    "유통": "0016",
    "전기·가스": "0017",
    "건설": "0018",
    "운송·창고": "0019",
    "통신": "0020",
    "금융": "0021",
    "증권": "0024",
    "보험": "0025",
    "일반서비스": "0026",
    "제조": "0027",
    "부동산": "0028",
    "IT 서비스": "0029",
    "오락·문화": "0030",
}


# ---------------------------------------------------------------------------
# Pure helper functions (testable without I/O)
# ---------------------------------------------------------------------------


def _rank_pct(snapshot: dict[str, float], industry: str) -> float | None:
    """업종 rank percentile. 0=최강(최고 등락), 1=최약."""
    if industry not in snapshot:
        return None
    vals = sorted(snapshot.values(), reverse=True)
    pos = vals.index(snapshot[industry])
    return pos / max(1, len(vals) - 1)


def _trend_from_hist(hist: list[dict], lookback: int = 60) -> str:
    """히스토리 averageChange 합산으로 추세 판단."""
    chs = [float(h["averageChange"]) for h in hist[:lookback] if h.get("averageChange") is not None]
    if not chs:
        return "unknown"
    s = sum(chs)
    if s > 0:
        return "up"
    if s < 0:
        return "down"
    return "flat"


def _relative_price_slope(sector_df: pd.DataFrame, kospi_df: pd.DataFrame) -> float | None:
    """업종지수 / 코스피 상대가격선의 기울기 (양수 = 업종 강세). None = 데이터 부족."""
    if sector_df.empty or kospi_df.empty:
        return None
    common = sector_df.index.intersection(kospi_df.index)
    if len(common) < 2:
        return None
    s_close = sector_df.loc[common, "Close"]
    k_close = kospi_df.loc[common, "Close"]
    if (k_close == 0).any():
        return None
    rp = s_close / k_close
    # 단순 기울기: 끝값 - 시작값
    return float(rp.iloc[-1] - rp.iloc[0])


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class SectorStrengthProvider(ABC):
    @abstractmethod
    async def evaluate(self, ticker: str) -> SectorStrengthResult: ...


# ---------------------------------------------------------------------------
# FMP implementation (US stocks)
# ---------------------------------------------------------------------------


class FmpSectorStrength:
    """FMP 업종 snapshot 백분위 + historical 추세 기반 미국 업종 강도 판정.

    evaluate_industry()는 순수 판정 (I/O 없음). 데이터 fetch는 호출자 책임.
    FmpSectorStrengthProvider.evaluate()가 I/O를 담당하고 이 클래스를 사용한다.
    """

    def __init__(
        self,
        snapshot: dict[str, float],
        historical: dict[str, list[dict]],
        normalize_map: dict[str, str] | None = None,
    ):
        self._snapshot = snapshot
        self._historical = historical
        self._normalize = normalize_map or YF_TO_FMP_INDUSTRY

    def evaluate_industry(self, yf_industry: str) -> SectorStrengthResult:
        """yfinance industry 이름으로 FMP 업종 강도 판정."""
        fmp_industry = self._normalize.get(yf_industry, yf_industry)

        if fmp_industry not in self._snapshot:
            return SectorStrengthResult(
                industry=yf_industry,
                rank_pct=None,
                trend="unknown",
                is_strong=None,
                source="none",
                detail=f"FMP snapshot에 '{fmp_industry}' 없음",
            )

        rank = _rank_pct(self._snapshot, fmp_industry)
        hist = self._historical.get(fmp_industry, [])
        trend = _trend_from_hist(hist)
        is_strong = (rank is not None and rank <= 0.5) and trend == "up"

        return SectorStrengthResult(
            industry=fmp_industry,
            rank_pct=rank,
            trend=trend,
            is_strong=is_strong,
            source="FMP",
            detail=f"rank_pct={rank:.2f}, trend={trend}",
        )


# ---------------------------------------------------------------------------
# KIS implementation (Korean stocks)
# ---------------------------------------------------------------------------


class KisSectorStrength:
    """KIS 업종지수 vs 코스피 상대강도 기반 한국 업종 강도 판정.

    evaluate_sector_df()는 순수 판정 (I/O 없음). 데이터 fetch는 호출자 책임.
    """

    def evaluate_sector_df(
        self,
        sector_code: str,
        sector_df: pd.DataFrame,
        kospi_df: pd.DataFrame,
    ) -> SectorStrengthResult:
        """업종지수 DataFrame과 코스피 DataFrame으로 강도 판정."""
        if sector_df.empty or kospi_df.empty:
            return SectorStrengthResult(
                industry=None,
                rank_pct=None,
                trend="unknown",
                is_strong=None,
                source="none",
                detail="업종지수 또는 코스피 데이터 없음",
            )

        slope = _relative_price_slope(sector_df, kospi_df)
        if slope is None:
            return SectorStrengthResult(
                industry=sector_code,
                rank_pct=None,
                trend="unknown",
                is_strong=None,
                source="none",
                detail="상대가격 계산 불가 (공통 날짜 부족)",
            )

        # 업종지수 자체 추세
        if len(sector_df) >= 2:
            pct_change = (sector_df["Close"].iloc[-1] - sector_df["Close"].iloc[0]) / sector_df[
                "Close"
            ].iloc[0]
            trend = "up" if pct_change > 0 else ("down" if pct_change < 0 else "flat")
        else:
            trend = "unknown"

        is_strong = slope > 0 and trend == "up"

        return SectorStrengthResult(
            industry=sector_code,
            rank_pct=None,
            trend=trend,
            is_strong=is_strong,
            source="KIS",
            detail=f"rp_slope={slope:.4f}, trend={trend}",
        )

    @staticmethod
    def resolve_sector_code(bstp_kor_isnm: str) -> str | None:
        """bstp_kor_isnm(한글 업종명) → KOSPI 업종지수 코드. 매핑 없으면 None."""
        return KOSPI_SECTOR_CODE.get(bstp_kor_isnm)
