from __future__ import annotations

import re


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[\s:=,()/]+", text) if len(t) >= 2}


def points_grounding_ratio(points: list[str], evidence_headlines: list[str]) -> float:
    """각 point 가 증거 headline 토큰을 1개 이상 포함하는 비율 (환각 검출)."""
    if not points:
        return 1.0
    ev: set[str] = set()
    for h in evidence_headlines:
        ev |= _tokens(h)
    grounded = sum(1 for p in points if _tokens(p) & ev)
    return round(grounded / len(points), 4)
