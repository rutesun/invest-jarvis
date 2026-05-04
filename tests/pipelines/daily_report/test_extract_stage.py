from datetime import datetime

from src.pipelines.daily_report.models import IngestedMessage, MessageType
from src.pipelines.daily_report.stages.extract_stage import extract_stage


def test_extract_stage_splits_broker_claim_and_fact():
    messages = [
        IngestedMessage(
            source_id="kwusa-155",
            channel_id="kwusa",
            message_id="155",
            timestamp=datetime.fromisoformat("2026-04-29T01:46:11+00:00"),
            raw_text="마이크론 목표주가 550달러에서 660달러로 상향. 장기 공급계약 증가.",
            message_type=MessageType.BROKER_SUMMARY,
            source_file="data/2026-04/2026-04-29-kwusa.csv",
        )
    ]

    result = extract_stage(messages, date="2026-04-29")

    assert len(result.claims) == 1
    assert result.claims[0].claim_type.value == "broker_view"
    assert result.facts[0].label == "target_price"
    assert result.facts[0].value == "550->660"
