# src/tools/flow.py
"""
KIS API 수급 툴 — 한국주식의 외인/기관 일별 순매수 데이터를 조회한다.

KISProvider.get_investor_trend()를 래핑하여 10일치 InvestorFlow 모델을 생성한다.
1일·5일·10일 구간별 방향 판단 및 10일 중 순매수 일수를 제공한다.
"""

from dataclasses import dataclass, field

from src.core.models import ToolResult


def _fmt_kis_date(date_str: str) -> str:
    """KIS 날짜 형식 YYYYMMDD → YYYY-MM-DD 변환."""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


def _direction(entries: list, attr: str) -> str:
    """주어진 entries 구간에서 attr(foreign_net or institution_net) 과반 기준 방향 반환."""
    if not entries:
        return "N/A"
    buys = sum(1 for e in entries if getattr(e, attr) > 0)
    return "매수" if buys > len(entries) / 2 else "매도"


def _net_sum(entries: list, attr: str) -> int:
    """주어진 entries 구간의 attr 합계."""
    return sum(getattr(e, attr) for e in entries)


@dataclass
class InvestorFlowEntry:
    """하루치 투자자 순매수 데이터 (KIS API 기준, 단위: 주)."""

    date: str  # "YYYY-MM-DD", 최신일이 index 0
    foreign_net: int  # 양수=순매수, 음수=순매도
    institution_net: int


@dataclass
class InvestorFlow:
    """한국주식 10일 수급 요약. entries[0]이 가장 최신일."""

    code: str
    entries: list[InvestorFlowEntry] = field(default_factory=list)

    # ── 1일 방향 (최신 하루) ────────────────────────────────────────────────────

    @property
    def foreign_direction_1d(self) -> str:
        return _direction(self.entries[:1], "foreign_net")

    @property
    def institution_direction_1d(self) -> str:
        return _direction(self.entries[:1], "institution_net")

    # ── 5일 방향 ────────────────────────────────────────────────────────────────

    @property
    def foreign_direction_5d(self) -> str:
        return _direction(self.entries[:5], "foreign_net")

    @property
    def institution_direction_5d(self) -> str:
        return _direction(self.entries[:5], "institution_net")

    # ── 10일 방향 ───────────────────────────────────────────────────────────────

    @property
    def foreign_direction_10d(self) -> str:
        return _direction(self.entries, "foreign_net")

    @property
    def institution_direction_10d(self) -> str:
        return _direction(self.entries, "institution_net")

    # ── 10일 중 순매수 일수 ─────────────────────────────────────────────────────

    @property
    def foreign_buy_days(self) -> int:
        """10일 중 외인 순매수 일수."""
        return sum(1 for e in self.entries if e.foreign_net > 0)

    @property
    def institution_buy_days(self) -> int:
        """10일 중 기관 순매수 일수."""
        return sum(1 for e in self.entries if e.institution_net > 0)

    # ── 구간별 순매수 합계 ──────────────────────────────────────────────────────

    @property
    def foreign_net_1d(self) -> int:
        return _net_sum(self.entries[:1], "foreign_net")

    @property
    def foreign_net_5d(self) -> int:
        return _net_sum(self.entries[:5], "foreign_net")

    @property
    def foreign_net_10d(self) -> int:
        return _net_sum(self.entries, "foreign_net")

    @property
    def institution_net_1d(self) -> int:
        return _net_sum(self.entries[:1], "institution_net")

    @property
    def institution_net_5d(self) -> int:
        return _net_sum(self.entries[:5], "institution_net")

    @property
    def institution_net_10d(self) -> int:
        return _net_sum(self.entries, "institution_net")


class FlowTool:
    """KISProvider를 통해 한국주식 10일 수급 데이터를 조회한다."""

    def __init__(self, kis_provider) -> None:
        """
        Args:
            kis_provider: KISProvider 인스턴스. KIS 키 미설정 시 None.
        """
        self.kis_provider = kis_provider

    async def execute(self, code: str) -> ToolResult:
        """6자리 KRX 종목코드로 10일 수급 데이터를 조회한다.

        Returns:
            ToolResult[InvestorFlow] on success, ToolResult(success=False) on error.
        """
        if self.kis_provider is None:
            return ToolResult(
                success=False,
                data=None,
                error="KIS provider 미설정 — KIS_APP_KEY, KIS_APP_SECRET 환경변수를 확인하세요",
            )
        try:
            raw = await self.kis_provider.get_investor_trend(code, days=10)
            entries = [
                InvestorFlowEntry(
                    date=_fmt_kis_date(item["date"]),
                    foreign_net=item["foreign_net"],
                    institution_net=item["institution_net"],
                )
                for item in raw
            ]
            return ToolResult(success=True, data=InvestorFlow(code=code, entries=entries))
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))
