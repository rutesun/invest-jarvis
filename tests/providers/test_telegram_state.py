# tests/providers/test_telegram_state.py
import json
import pytest
from pathlib import Path
from src.providers.telegram.state import TelegramState


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "monitor_state.json"


def test_get_returns_zero_for_unknown_channel(state_file):
    state = TelegramState(state_file)
    assert state.get_last_message_id("unknown_channel") == 0


def test_update_and_get(state_file):
    state = TelegramState(state_file)
    state.update("chan1", 100)
    assert state.get_last_message_id("chan1") == 100


def test_update_persists_to_file(state_file):
    state = TelegramState(state_file)
    state.update("chan1", 200)

    # 새 인스턴스로 로드해도 유지되어야 한다
    state2 = TelegramState(state_file)
    assert state2.get_last_message_id("chan1") == 200


def test_update_only_increases(state_file):
    """단조 증가: 더 작은 ID로 업데이트하면 무시."""
    state = TelegramState(state_file)
    state.update("chan1", 500)
    state.update("chan1", 300)
    assert state.get_last_message_id("chan1") == 500


def test_multiple_channels(state_file):
    state = TelegramState(state_file)
    state.update("chan1", 100)
    state.update("chan2", 200)
    assert state.get_last_message_id("chan1") == 100
    assert state.get_last_message_id("chan2") == 200


def test_state_file_auto_created(tmp_path):
    state_file = tmp_path / "deep" / "nested" / "state.json"
    state = TelegramState(state_file)
    state.update("chan1", 42)
    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["chan1"] == 42


def test_load_existing_state_file(state_file):
    state_file.write_text('{"chan1": 999}', encoding="utf-8")
    state = TelegramState(state_file)
    assert state.get_last_message_id("chan1") == 999
