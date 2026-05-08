from datetime import datetime

from src.cli.main import format_deep_dive_output
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


def test_format_deep_dive_output_prefers_presented_structure_blocks():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)
    technical = TechnicalResult(
        ticker="ALAB",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=70,
        strategies=[],
        overall_assessment="관망",
        confidence_score=0.5,
        key_insights=[],
        warnings=[],
    )
    result = {
        "ticker": "ALAB",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {
                "summary": "중립",
                "key_insights": [],
                "recommendation": "관망",
                "confidence": 0.5,
                "rationale": "r",
            },
        )(),
        "presented_structure": {
            "top_judgment": "현재 핵심 구조: support_zone",
            "headline": "핵심 지지 존 우위",
            "why": "최근 지지 터치 집중",
            "cli_blocks": [
                "## 구조 레벨",
                "- **요약**: 핵심 지지 존 우위",
                "- **지지 존**: 95.00~97.00",
                "",
                "## 실행 레벨",
                "- **핵심 실행 레벨**: 피봇 S1 $98.00 (-2.0%)",
                "",
            ],
            "llm_context": "구조 레벨",
        },
    }

    output = format_deep_dive_output(result)

    assert "## 구조 레벨" in output
    assert "핵심 지지 존 우위" in output
    assert "피봇 S1 $98.00" in output
