"""Daily report 파이프라인 공유 테스트 픽스처."""

from datetime import datetime

import pytest

from src.pipelines.daily_report.models import (
    MacroSnapshot,
    MappedIssue,
    TelegramMessage,
)


@pytest.fixture
def sample_macro():
    """샘플 매크로 스냅샷."""
    return MacroSnapshot(
        date="2026-04-14",
        us_markets={"S&P500": 1.2, "NASDAQ": 1.5, "DOW": 0.8},
        kr_markets={"KOSPI": 2.1, "KOSDAQ": 1.8},
        vix=19.1,
        fear_greed=52,
        krw_usd=1320.0,
    )


@pytest.fixture
def sample_messages():
    """샘플 텔레그램 메시지."""
    return [
        TelegramMessage(
            channel_id="test_channel",
            message_id="msg1",
            timestamp=datetime(2026, 4, 14, 9, 0),
            text="Bloom Energy, Oracle에 연료전지 1.2GW 공급",
        ),
        TelegramMessage(
            channel_id="test_channel",
            message_id="msg2",
            timestamp=datetime(2026, 4, 14, 9, 15),
            text="LS ELECTRIC 북미 DC 배전반 1700억 수주",
        ),
        TelegramMessage(
            channel_id="test_channel",
            message_id="msg3",
            timestamp=datetime(2026, 4, 14, 9, 30),
            text="데이터센터 전력 수요 2030년 1350TWh 전망",
        ),
    ]


@pytest.fixture
def sample_mapped_issue():
    """샘플 매핑된 이슈."""
    return MappedIssue(
        title="AI 데이터센터 전력 인프라 투자 급증",
        summary="Oracle-Bloom Energy 계약, LS 수주 등",
        themes=["AI 데이터센터", "전력 인프라"],
        keywords=["Bloom Energy", "Oracle", "LS ELECTRIC"],
        sentiment="bull",
        source_ids=["msg1", "msg2", "msg3"],
    )
