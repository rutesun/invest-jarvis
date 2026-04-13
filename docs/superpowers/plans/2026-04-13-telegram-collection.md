# Telegram 수집 파이프라인 구현 계획

> **에이전트 작업자용:** 필수 서브스킬: superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 태스크별로 구현할 것. 체크박스(`- [ ]`) 형식으로 진행 추적.

**목표:** Telegram 채널 메시지를 날짜별 CSV로 수집·저장하는 파이프라인을 구축한다. Daily Report V2의 핵심 데이터 소스.

**아키텍처:** config.yaml에서 채널 목록을 읽고, Telethon으로 메시지를 수집하여, 날짜별 CSV(`data/YYYY-MM/YYYY-MM-DD-{channel}.csv`)에 저장한다. `monitor_state.json`으로 채널별 마지막 수집 지점을 추적하여 catch-up 수집을 지원한다. CLI는 `jarvis telegram fetch [DATE]` / `jarvis telegram catch-up` 두 커맨드를 제공한다.

**기술 스택:** telethon, pydantic v2, typer, pyyaml, pandas (CSV 처리)

**설계서:** `docs/superpowers/specs/2026-04-12-telegram-collection-design.md`

---

## 파일 구조

```
src/
  providers/
    telegram_config.py              # TelegramConfig: config.yaml 텔레그램 섹션 로더
    telegram_client.py              # TelegramClientWrapper: Telethon 클라이언트 래퍼
    telegram_collector.py           # TelegramCollector: fetch/catch-up 수집 로직
    telegram_media.py               # TelegramMediaDownloader: 사진/PDF 다운로드
    telegram_storage.py             # TelegramStorage: CSV 저장 + 중복 방지
    telegram_state.py               # TelegramState: monitor_state.json 관리
    telegram_loader.py              # TelegramLoader: CSV 로더 (Daily Report V2 연동용)
  cli/
    main.py                         # 수정: telegram 서브커맨드 그룹 추가

tests/
  providers/
    test_telegram_config.py
    test_telegram_media.py
    test_telegram_storage.py
    test_telegram_state.py
    test_telegram_loader.py
    test_telegram_collector.py
```

---

### Task 1: 의존성 추가

**파일:**
- 수정: `pyproject.toml`

- [ ] **Step 1: telethon 의존성 추가**

`pyproject.toml`의 `dependencies` 리스트에 `telethon` 추가:

```toml
dependencies = [
    "typer>=0.9.0",
    "pydantic>=2.0.0",
    "pandas>=2.0.0",
    "pandas-ta>=0.3.14b",
    "yfinance>=0.2.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "httpx>=0.25.0",
    "langchain-openai>=1.1.12",
    "langchain-anthropic>=1.4.0",
    "langchain-core>=1.2.28",
    "scipy>=1.17.1",
    "ddgs>=9.0.0",
    "telethon>=1.36.0",
]
```

- [ ] **Step 2: 의존성 설치 확인**

실행: `uv sync`
예상: 정상 완료, telethon 설치됨

- [ ] **Step 3: 커밋**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add telethon dependency for telegram collection"
```

---

### Task 2: Telegram 설정 모델

**파일:**
- 생성: `src/providers/telegram_config.py`
- 테스트: `tests/providers/test_telegram_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_config.py
import pytest
from pathlib import Path
from src.providers.telegram_config import TelegramConfig, ChannelConfig


def test_load_simple_channel(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        '    - "12345"\n'
        "  output_dir: data\n",
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    assert len(config.channels) == 1
    assert config.channels[0].id == "12345"
    assert config.channels[0].include == []
    assert config.channels[0].exclude == []
    assert config.output_dir == Path("data")


def test_load_channel_with_filters(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        "    - id: chan1\n"
        "      include:\n"
        '        - "Breaking|Urgent"\n'
        "      exclude:\n"
        '        - "(?i)ad"\n',
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    ch = config.channels[0]
    assert ch.id == "chan1"
    assert ch.include == ["Breaking|Urgent"]
    assert ch.exclude == ["(?i)ad"]


def test_load_mixed_channels(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        '    - "simple_id"\n'
        "    - id: filtered_id\n"
        "      include:\n"
        '        - "pattern"\n',
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    assert len(config.channels) == 2
    assert config.channels[0].id == "simple_id"
    assert config.channels[1].id == "filtered_id"
    assert config.channels[1].include == ["pattern"]


def test_missing_telegram_section(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("technical:\n  strategies: [trend]\n", encoding="utf-8")
    config = TelegramConfig.from_yaml(config_file)
    assert config.channels == []
    assert config.output_dir == Path("data")


def test_missing_file_returns_defaults():
    config = TelegramConfig.from_yaml(Path("/nonexistent/config.yaml"))
    assert config.channels == []


def test_channel_config_should_include():
    ch = ChannelConfig(id="test", include=["Breaking|Urgent"], exclude=["(?i)ad"])
    assert ch.should_include("Breaking news today") is True
    assert ch.should_include("일반 메시지") is False
    assert ch.should_include("Breaking Ad campaign") is False


def test_channel_config_no_filters_includes_all():
    ch = ChannelConfig(id="test")
    assert ch.should_include("아무 메시지") is True
    assert ch.should_include("") is True


def test_channel_config_exclude_only():
    ch = ChannelConfig(id="test", exclude=["(?i)spam"])
    assert ch.should_include("좋은 정보") is True
    assert ch.should_include("이건 SPAM 입니다") is False


def test_summarize_links_channels(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "telegram:\n"
        "  channels:\n"
        '    - "ch1"\n'
        "  link_processing:\n"
        "    summarize_links_channels:\n"
        "      - kiwoom_semibat\n",
        encoding="utf-8",
    )
    config = TelegramConfig.from_yaml(config_file)
    assert "kiwoom_semibat" in config.summarize_links_channels
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/providers/test_telegram_config.py -v`
예상: `ModuleNotFoundError: No module named 'src.providers.telegram_config'`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/providers/telegram_config.py
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel


class ChannelConfig(BaseModel):
    """개별 채널의 수집 설정."""

    id: str
    include: list[str] = []
    exclude: list[str] = []

    def should_include(self, text: str) -> bool:
        """메시지가 include/exclude 필터를 통과하는지 확인한다."""
        if self.include:
            if not any(re.search(p, text) for p in self.include):
                return False
        if self.exclude:
            if any(re.search(p, text) for p in self.exclude):
                return False
        return True


class TelegramConfig(BaseModel):
    """config.yaml의 telegram 섹션을 파싱한 설정."""

    channels: list[ChannelConfig] = []
    output_dir: Path = Path("data")
    summarize_links_channels: list[str] = []

    @classmethod
    def from_yaml(cls, config_path: Path) -> TelegramConfig:
        if not config_path.exists():
            return cls()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        tg = raw.get("telegram", {})
        if not tg:
            return cls()

        channels: list[ChannelConfig] = []
        for ch in tg.get("channels", []):
            if isinstance(ch, str):
                channels.append(ChannelConfig(id=ch))
            elif isinstance(ch, dict):
                channels.append(ChannelConfig(
                    id=str(ch["id"]),
                    include=ch.get("include", []),
                    exclude=ch.get("exclude", []),
                ))

        output_dir = Path(tg.get("output_dir", "data"))
        link_proc = tg.get("link_processing", {})
        summarize = link_proc.get("summarize_links_channels", [])

        return cls(
            channels=channels,
            output_dir=output_dir,
            summarize_links_channels=summarize,
        )
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/providers/test_telegram_config.py -v`
예상: 9개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_config.py tests/providers/test_telegram_config.py
git commit -m "feat: add TelegramConfig for channel list and filter settings"
```

---

### Task 3: 상태 추적 (TelegramState)

**파일:**
- 생성: `src/providers/telegram_state.py`
- 테스트: `tests/providers/test_telegram_state.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_state.py
import json
import pytest
from pathlib import Path
from src.providers.telegram_state import TelegramState


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
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/providers/test_telegram_state.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/providers/telegram_state.py
from __future__ import annotations

import json
from pathlib import Path


class TelegramState:
    """채널별 마지막 수집 메시지 ID를 추적한다.

    data/monitor_state.json에 {channel_id: max_msg_id} 형태로 저장.
    단조 증가(monotonic): 더 큰 ID만 업데이트한다.
    """

    def __init__(self, state_path: Path) -> None:
        self._path = state_path
        self._data: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        if self._path.exists():
            return json.loads(self._path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2),
            encoding="utf-8",
        )

    def get_last_message_id(self, channel_id: str) -> int:
        return self._data.get(channel_id, 0)

    def update(self, channel_id: str, message_id: int) -> None:
        current = self._data.get(channel_id, 0)
        if message_id > current:
            self._data[channel_id] = message_id
            self._save()
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/providers/test_telegram_state.py -v`
예상: 7개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_state.py tests/providers/test_telegram_state.py
git commit -m "feat: add TelegramState for tracking last collected message IDs"
```

---

### Task 4: CSV 저장소 (TelegramStorage)

**파일:**
- 생성: `src/providers/telegram_storage.py`
- 테스트: `tests/providers/test_telegram_storage.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_storage.py
import csv
import json
import pytest
from pathlib import Path
from src.providers.telegram_storage import TelegramStorage


@pytest.fixture
def storage(tmp_path):
    return TelegramStorage(output_dir=tmp_path)


def _make_message(msg_id: int, channel: str = "test_chan", text: str = "hello") -> dict:
    return {
        "message_id": msg_id,
        "timestamp": "2026-04-13T09:00:00+00:00",
        "channel_name": channel,
        "author": "user1",
        "content": text,
        "media_info": json.dumps(None),
        "forward_from": "",
    }


def test_save_creates_csv(storage, tmp_path):
    messages = [_make_message(1), _make_message(2)]
    storage.save("test_chan", "2026-04-13", messages)

    csv_path = tmp_path / "2026-04" / "2026-04-13-test_chan.csv"
    assert csv_path.exists()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["message_id"] == "1"
    assert rows[1]["message_id"] == "2"


def test_save_appends_without_duplicates(storage, tmp_path):
    storage.save("ch", "2026-04-13", [_make_message(1), _make_message(2)])
    storage.save("ch", "2026-04-13", [_make_message(2), _make_message(3)])

    csv_path = tmp_path / "2026-04" / "2026-04-13-ch.csv"
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    ids = [int(r["message_id"]) for r in rows]
    assert sorted(ids) == [1, 2, 3]


def test_csv_columns(storage, tmp_path):
    storage.save("ch", "2026-04-13", [_make_message(1)])
    csv_path = tmp_path / "2026-04" / "2026-04-13-ch.csv"
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    expected_cols = {"message_id", "timestamp", "channel_name", "author", "content", "media_info", "forward_from"}
    assert set(row.keys()) == expected_cols


def test_get_existing_ids_empty_file(storage, tmp_path):
    ids = storage.get_existing_ids("ch", "2026-04-13")
    assert ids == set()


def test_get_existing_ids_from_csv(storage, tmp_path):
    storage.save("ch", "2026-04-13", [_make_message(10), _make_message(20)])
    ids = storage.get_existing_ids("ch", "2026-04-13")
    assert ids == {10, 20}


def test_csv_path_format(storage, tmp_path):
    path = storage.csv_path("my_channel", "2026-01-05")
    assert path == tmp_path / "2026-01" / "2026-01-05-my_channel.csv"


def test_save_empty_messages(storage, tmp_path):
    storage.save("ch", "2026-04-13", [])
    csv_path = tmp_path / "2026-04" / "2026-04-13-ch.csv"
    assert not csv_path.exists()
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/providers/test_telegram_storage.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/providers/telegram_storage.py
from __future__ import annotations

import csv
from pathlib import Path

CSV_COLUMNS = [
    "message_id",
    "timestamp",
    "channel_name",
    "author",
    "content",
    "media_info",
    "forward_from",
]


class TelegramStorage:
    """텔레그램 메시지를 날짜별 CSV로 저장한다.

    파일 경로: {output_dir}/YYYY-MM/YYYY-MM-DD-{channel_name}.csv
    저장 전 기존 message_id를 스캔하여 중복을 방지한다.
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def csv_path(self, channel_name: str, date_str: str) -> Path:
        """YYYY-MM-DD 형식의 날짜와 채널명으로 CSV 경로를 생성한다."""
        month_dir = date_str[:7]  # YYYY-MM
        return self._output_dir / month_dir / f"{date_str}-{channel_name}.csv"

    def get_existing_ids(self, channel_name: str, date_str: str) -> set[int]:
        """해당 CSV에 이미 저장된 message_id 집합을 반환한다."""
        path = self.csv_path(channel_name, date_str)
        if not path.exists():
            return set()
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return {int(row["message_id"]) for row in reader}

    def save(self, channel_name: str, date_str: str, messages: list[dict]) -> None:
        """메시지 목록을 CSV에 저장한다. 중복은 스킵."""
        if not messages:
            return

        path = self.csv_path(channel_name, date_str)
        existing_ids = self.get_existing_ids(channel_name, date_str)
        new_messages = [m for m in messages if int(m["message_id"]) not in existing_ids]

        if not new_messages:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()

        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if not file_exists:
                writer.writeheader()
            for msg in new_messages:
                writer.writerow({col: msg.get(col, "") for col in CSV_COLUMNS})
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/providers/test_telegram_storage.py -v`
예상: 7개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_storage.py tests/providers/test_telegram_storage.py
git commit -m "feat: add TelegramStorage for CSV saving with deduplication"
```

---

### Task 5: CSV 로더 (TelegramLoader)

**파일:**
- 생성: `src/providers/telegram_loader.py`
- 테스트: `tests/providers/test_telegram_loader.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_loader.py
import csv
import pytest
from pathlib import Path
from src.providers.telegram_loader import TelegramLoader


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path


def _write_csv(data_dir: Path, date_str: str, channel: str, rows: list[dict]):
    month = date_str[:7]
    csv_dir = data_dir / month
    csv_dir.mkdir(parents=True, exist_ok=True)
    path = csv_dir / f"{date_str}-{channel}.csv"
    fieldnames = ["message_id", "timestamp", "channel_name", "author", "content", "media_info", "forward_from"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_load_returns_messages_for_date(data_dir):
    _write_csv(data_dir, "2026-04-13", "chan1", [
        {"message_id": "1", "timestamp": "2026-04-13T09:00:00", "channel_name": "chan1",
         "author": "user1", "content": "테스트 메시지", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert len(messages) == 1
    assert messages[0]["id"] == 1
    assert messages[0]["channel"] == "chan1"
    assert messages[0]["text"] == "테스트 메시지"
    assert messages[0]["timestamp"] == "2026-04-13T09:00:00"


def test_load_merges_multiple_channels(data_dir):
    _write_csv(data_dir, "2026-04-13", "chan1", [
        {"message_id": "1", "timestamp": "2026-04-13T09:00:00", "channel_name": "chan1",
         "author": "a", "content": "msg1", "media_info": "", "forward_from": ""},
    ])
    _write_csv(data_dir, "2026-04-13", "chan2", [
        {"message_id": "2", "timestamp": "2026-04-13T09:30:00", "channel_name": "chan2",
         "author": "b", "content": "msg2", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert len(messages) == 2
    channels = {m["channel"] for m in messages}
    assert channels == {"chan1", "chan2"}


def test_load_no_files_returns_empty(data_dir):
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert messages == []


def test_load_default_date_is_yesterday(data_dir):
    """date 미지정 시 전날 데이터를 로드한다."""
    from datetime import datetime, timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    _write_csv(data_dir, yesterday, "ch", [
        {"message_id": "1", "timestamp": f"{yesterday}T10:00:00", "channel_name": "ch",
         "author": "a", "content": "yesterday", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load()
    assert len(messages) == 1
    assert messages[0]["text"] == "yesterday"


def test_load_sorted_by_timestamp(data_dir):
    _write_csv(data_dir, "2026-04-13", "ch", [
        {"message_id": "2", "timestamp": "2026-04-13T10:00:00", "channel_name": "ch",
         "author": "a", "content": "later", "media_info": "", "forward_from": ""},
        {"message_id": "1", "timestamp": "2026-04-13T09:00:00", "channel_name": "ch",
         "author": "a", "content": "earlier", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert messages[0]["text"] == "earlier"
    assert messages[1]["text"] == "later"
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/providers/test_telegram_loader.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/providers/telegram_loader.py
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path


class TelegramLoader:
    """날짜별 CSV에서 텔레그램 메시지를 로드한다.

    Daily Report V2의 IngestStage에서 사용.
    인터페이스: load(date) -> list[dict] (동기, asyncio.to_thread로 호출됨)
    반환 형식: [{"id": int, "channel": str, "text": str, "timestamp": str}, ...]
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def load(self, date_str: str | None = None) -> list[dict]:
        """지정 날짜의 모든 채널 메시지를 로드한다.

        Args:
            date_str: YYYY-MM-DD 형식. None이면 전날.
        """
        if date_str is None:
            date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        month_dir = self._data_dir / date_str[:7]
        if not month_dir.exists():
            return []

        messages: list[dict] = []
        for csv_file in month_dir.glob(f"{date_str}-*.csv"):
            with open(csv_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    messages.append({
                        "id": int(row["message_id"]),
                        "channel": row["channel_name"],
                        "text": row["content"],
                        "timestamp": row["timestamp"],
                    })

        messages.sort(key=lambda m: m["timestamp"])
        return messages
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/providers/test_telegram_loader.py -v`
예상: 5개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_loader.py tests/providers/test_telegram_loader.py
git commit -m "feat: add TelegramLoader for reading collected CSV messages"
```

---

### Task 6: Telethon 클라이언트 래퍼

**파일:**
- 생성: `src/providers/telegram_client.py`

이 모듈은 Telethon 세션을 관리하며 외부 API 의존성이 있어 단위 테스트 없이 통합 테스트로 검증한다.

- [ ] **Step 1: 구현 작성**

```python
# src/providers/telegram_client.py
from __future__ import annotations

import os
import logging

from telethon import TelegramClient

logger = logging.getLogger(__name__)


class TelegramClientWrapper:
    """Telethon 클라이언트를 래핑하여 세션 관리를 담당한다.

    환경 변수:
        TELEGRAM_API_ID: Telegram API ID
        TELEGRAM_API_HASH: Telegram API Hash
        TELETHON_SESSION_NAME: 세션 파일명 (기본값: 'anon')
    """

    def __init__(self) -> None:
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            raise ValueError(
                "TELEGRAM_API_ID와 TELEGRAM_API_HASH 환경 변수가 필요합니다. "
                ".env 파일을 확인하세요."
            )
        session_name = os.getenv("TELETHON_SESSION_NAME", "anon")
        self._client = TelegramClient(session_name, int(api_id), api_hash)

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def start(self) -> None:
        """클라이언트를 시작한다. 첫 실행 시 인증이 필요할 수 있다."""
        await self._client.start()
        logger.info("Telegram 클라이언트 연결됨")

    async def stop(self) -> None:
        """클라이언트 연결을 종료한다."""
        await self._client.disconnect()
        logger.info("Telegram 클라이언트 연결 해제됨")
```

- [ ] **Step 2: import 확인**

실행: `uv run python -c "from src.providers.telegram_client import TelegramClientWrapper; print('OK')"`
예상: `OK` 출력 (환경 변수 미설정이어도 import 자체는 성공)

- [ ] **Step 3: 커밋**

```bash
git add src/providers/telegram_client.py
git commit -m "feat: add TelegramClientWrapper for Telethon session management"
```

---

### Task 7: 메시지 수집기 (TelegramCollector)

**파일:**
- 생성: `src/providers/telegram_collector.py`
- 테스트: `tests/providers/test_telegram_collector.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_collector.py
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from src.providers.telegram_collector import TelegramCollector
from src.providers.telegram_config import ChannelConfig


def _make_tg_message(msg_id: int, text: str, date: datetime, sender_id: int = 123):
    """Telethon Message 객체를 모사하는 mock."""
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.date = date
    msg.sender_id = sender_id
    msg.media = None
    msg.forward = None
    return msg


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_entity = AsyncMock()
    return client


@pytest.fixture
def channel_config():
    return ChannelConfig(id="test_channel")


@pytest.fixture
def channel_config_with_filter():
    return ChannelConfig(id="test_channel", include=["중요|Breaking"])


@pytest.mark.asyncio
async def test_fetch_messages_for_date(mock_client, channel_config):
    target_date = datetime(2026, 4, 13, tzinfo=timezone.utc)
    messages = [
        _make_tg_message(1, "첫 번째 메시지", datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),
        _make_tg_message(2, "두 번째 메시지", datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)),
    ]

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter(messages))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert len(result) == 2
    assert result[0]["message_id"] == 1
    assert result[0]["content"] == "첫 번째 메시지"
    assert result[0]["channel_name"] == "test_channel"


@pytest.mark.asyncio
async def test_fetch_applies_include_filter(mock_client, channel_config_with_filter):
    messages = [
        _make_tg_message(1, "중요한 소식입니다", datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),
        _make_tg_message(2, "일반 잡담", datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)),
        _make_tg_message(3, "Breaking: 속보", datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc)),
    ]

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter(messages))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config_with_filter, "2026-04-13")

    assert len(result) == 2
    texts = [r["content"] for r in result]
    assert "일반 잡담" not in texts


@pytest.mark.asyncio
async def test_fetch_skips_none_text_and_no_media(mock_client, channel_config):
    """text=None이고 media도 None이면 스킵."""
    messages = [
        _make_tg_message(1, None, datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),
        _make_tg_message(2, "유효한 메시지", datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)),
    ]

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter(messages))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert len(result) == 1
    assert result[0]["content"] == "유효한 메시지"


@pytest.mark.asyncio
async def test_fetch_keeps_media_only_message(mock_client, channel_config):
    """text=None이지만 media가 있으면 수집한다."""
    msg_with_media = _make_tg_message(1, None, datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc))
    msg_with_media.media = MagicMock()  # media 존재

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter([msg_with_media]))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert len(result) == 1
    assert result[0]["content"] == ""


@pytest.mark.asyncio
async def test_fetch_includes_forward_info(mock_client, channel_config):
    msg = _make_tg_message(1, "포워드 메시지", datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc))
    fwd = MagicMock()
    fwd.chat_id = 99999
    msg.forward = fwd

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter([msg]))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert result[0]["forward_from"] == "99999"


@pytest.mark.asyncio
async def test_message_dict_format(mock_client, channel_config):
    msg = _make_tg_message(42, "테스트", datetime(2026, 4, 13, 9, 30, tzinfo=timezone.utc))

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter([msg]))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    row = result[0]
    assert set(row.keys()) == {
        "message_id", "timestamp", "channel_name", "author", "content", "media_info", "forward_from",
    }
    assert row["message_id"] == 42
    assert row["author"] == "123"
    assert row["timestamp"] == "2026-04-13T09:30:00+00:00"


async def _async_iter(items):
    """동기 리스트를 async iterator로 변환하는 헬퍼."""
    for item in items:
        yield item
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/providers/test_telegram_collector.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/providers/telegram_collector.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.providers.telegram_config import ChannelConfig

logger = logging.getLogger(__name__)


class TelegramCollector:
    """Telethon 클라이언트를 사용하여 채널 메시지를 수집한다.

    두 가지 모드:
    - fetch_channel: 특정 날짜의 메시지 일괄 수집
    - fetch_since: 특정 message_id 이후 메시지 수집 (catch-up용)

    미디어 다운로더가 설정되면 사진/PDF를 자동 다운로드한다.
    """

    def __init__(self, client: Any, media_downloader: Any = None) -> None:
        self._client = client
        self._media_downloader = media_downloader

    async def fetch_channel(
        self,
        channel_config: ChannelConfig,
        date_str: str,
    ) -> list[dict]:
        """특정 날짜의 채널 메시지를 수집한다.

        Args:
            channel_config: 채널 설정 (ID + 필터)
            date_str: YYYY-MM-DD (UTC 기준)

        Returns:
            CSV 저장용 dict 리스트
        """
        entity = await self._client.get_entity(channel_config.id)
        channel_name = getattr(entity, "title", str(channel_config.id))

        target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        offset_date = target_date + timedelta(days=1)

        messages: list[dict] = []
        async for msg in self._client.iter_messages(
            entity,
            offset_date=offset_date,
            reverse=True,
        ):
            if msg.date < target_date:
                continue
            if msg.date >= offset_date:
                break

            if msg.text is None and msg.media is None:
                continue

            if msg.text and not channel_config.should_include(msg.text):
                continue

            messages.append(await self._to_dict(msg, channel_name, date_str))

        logger.info(
            "%s에서 %s일자 메시지 %d건 수집",
            channel_name, date_str, len(messages),
        )
        return messages

    async def fetch_since(
        self,
        channel_config: ChannelConfig,
        min_id: int,
    ) -> list[dict]:
        """특정 message_id 이후의 메시지를 수집한다 (catch-up용).

        Args:
            channel_config: 채널 설정
            min_id: 이 ID 이후의 메시지만 수집

        Returns:
            CSV 저장용 dict 리스트
        """
        entity = await self._client.get_entity(channel_config.id)
        channel_name = getattr(entity, "title", str(channel_config.id))

        messages: list[dict] = []
        async for msg in self._client.iter_messages(entity, min_id=min_id, reverse=True):
            if msg.text is None and msg.media is None:
                continue
            if msg.text and not channel_config.should_include(msg.text):
                continue
            date_str = msg.date.strftime("%Y-%m-%d")
            messages.append(await self._to_dict(msg, channel_name, date_str))

        logger.info(
            "%s에서 min_id=%d 이후 메시지 %d건 수집",
            channel_name, min_id, len(messages),
        )
        return messages

    async def _to_dict(self, msg: Any, channel_name: str, date_str: str) -> dict:
        """Telethon Message를 CSV 저장용 dict로 변환한다."""
        forward_from = ""
        if msg.forward:
            forward_from = str(getattr(msg.forward, "chat_id", ""))

        media_info = json.dumps(None)
        if msg.media and self._media_downloader:
            media_info = json.dumps(
                await self._media_downloader.download(msg, channel_name, date_str)
            )
        elif msg.media:
            media_info = json.dumps({"type": type(msg.media).__name__})

        return {
            "message_id": msg.id,
            "timestamp": msg.date.isoformat(),
            "channel_name": channel_name,
            "author": str(msg.sender_id or ""),
            "content": msg.text or "",
            "media_info": media_info,
            "forward_from": forward_from,
        }
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/providers/test_telegram_collector.py -v`
예상: 5개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_collector.py tests/providers/test_telegram_collector.py
git commit -m "feat: add TelegramCollector for channel message fetching"
```

---

### Task 8: 미디어 다운로더 (TelegramMediaDownloader)

**파일:**
- 생성: `src/providers/telegram_media.py`
- 테스트: `tests/providers/test_telegram_media.py`

기존 `telegram` 프로젝트(`C:\Users\rutes\Develop\telegram\src\utils\media.py`)의 패턴을 계승.
사진은 `data/images/YYYY-MM-DD/`, PDF는 `data/files/YYYY-MM-DD/`에 저장한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_media.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock


from src.providers.telegram_media import TelegramMediaDownloader


@pytest.fixture
def downloader(tmp_path):
    client = AsyncMock()
    return TelegramMediaDownloader(client=client, base_dir=tmp_path)


def _make_photo_message(msg_id: int):
    msg = MagicMock()
    msg.id = msg_id
    msg.media = MagicMock()
    msg.media.photo = MagicMock()
    msg.media.document = None
    type(msg.media).__name__ = "MessageMediaPhoto"
    return msg


def _make_pdf_message(msg_id: int, filename: str = "report.pdf"):
    msg = MagicMock()
    msg.id = msg_id
    msg.media = MagicMock()
    msg.media.photo = None
    doc = MagicMock()
    doc.mime_type = "application/pdf"
    attr = MagicMock()
    attr.file_name = filename
    doc.attributes = [attr]
    msg.media.document = doc
    type(msg.media).__name__ = "MessageMediaDocument"
    return msg


def _make_video_message(msg_id: int):
    msg = MagicMock()
    msg.id = msg_id
    msg.media = MagicMock()
    msg.media.photo = None
    doc = MagicMock()
    doc.mime_type = "video/mp4"
    doc.attributes = []
    msg.media.document = doc
    type(msg.media).__name__ = "MessageMediaDocument"
    return msg


@pytest.mark.asyncio
async def test_download_photo(downloader, tmp_path):
    msg = _make_photo_message(42)
    # download_media가 파일을 생성하는 것을 시뮬레이션
    expected_path = tmp_path / "images" / "2026-04-13" / "test_chan_42.jpg"

    async def fake_download(message, file):
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        Path(file).write_bytes(b"fake_jpg")
        return str(file)

    downloader._client.download_media = fake_download

    result = await downloader.download(msg, "test_chan", "2026-04-13")

    assert result["type"] == "photo"
    assert result["local_path"] == str(expected_path)
    assert expected_path.exists()


@pytest.mark.asyncio
async def test_download_pdf(downloader, tmp_path):
    msg = _make_pdf_message(99, "analysis.pdf")
    expected_path = tmp_path / "files" / "2026-04-13" / "test_chan_99_analysis.pdf"

    async def fake_download(message, file):
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        Path(file).write_bytes(b"fake_pdf")
        return str(file)

    downloader._client.download_media = fake_download

    result = await downloader.download(msg, "test_chan", "2026-04-13")

    assert result["type"] == "document"
    assert result["mime_type"] == "application/pdf"
    assert result["local_path"] == str(expected_path)


@pytest.mark.asyncio
async def test_skip_video_no_download(downloader):
    msg = _make_video_message(10)

    result = await downloader.download(msg, "ch", "2026-04-13")

    assert result["type"] == "MessageMediaDocument"
    assert result["mime_type"] == "video/mp4"
    assert "local_path" not in result
    downloader._client.download_media.assert_not_called()


@pytest.mark.asyncio
async def test_download_failure_returns_type_only(downloader):
    msg = _make_photo_message(50)
    downloader._client.download_media = AsyncMock(side_effect=Exception("network error"))

    result = await downloader.download(msg, "ch", "2026-04-13")

    assert result["type"] == "photo"
    assert "local_path" not in result


@pytest.mark.asyncio
async def test_download_url_pdf(downloader, tmp_path):
    content = "좋은 리포트입니다 https://example.com/doc/report.pdf 참고하세요"

    async def fake_fetch(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"url_pdf_content")
        return True

    downloader._fetch_url_pdf = fake_fetch

    result = await downloader.download_url_pdfs(content, "ch", "2026-04-13", 77)

    assert len(result) == 1
    assert "report.pdf" in result[0]
    assert (tmp_path / "files" / "2026-04-13").exists()


@pytest.mark.asyncio
async def test_download_url_pdf_no_urls(downloader):
    result = await downloader.download_url_pdfs("URL 없는 메시지", "ch", "2026-04-13", 1)
    assert result == []


@pytest.mark.asyncio
async def test_download_url_pdf_non_pdf_url_skipped(downloader):
    content = "https://example.com/page.html 참조"

    async def fake_fetch(url, path):
        return False  # PDF가 아님

    downloader._fetch_url_pdf = fake_fetch

    result = await downloader.download_url_pdfs(content, "ch", "2026-04-13", 1)
    assert result == []
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/providers/test_telegram_media.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/providers/telegram_media.py
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 메시지 본문에서 URL 추출용 정규식
URL_PATTERN = re.compile(r"(https?://\S+\.pdf(?:\?\S*)?)", re.IGNORECASE)


class TelegramMediaDownloader:
    """텔레그램 메시지의 사진/PDF를 로컬에 다운로드한다.

    기존 telegram 프로젝트의 패턴을 계승:
    - 사진: {base_dir}/images/YYYY-MM-DD/{channel}_{msg_id}.jpg
    - PDF:  {base_dir}/files/YYYY-MM-DD/{channel}_{msg_id}_{filename}.pdf
    - URL PDF: {base_dir}/files/YYYY-MM-DD/{channel}_url_{msg_id}_{filename}.pdf
    """

    def __init__(self, client: Any, base_dir: Path) -> None:
        self._client = client
        self._base_dir = base_dir

    async def download(self, msg: Any, channel_name: str, date_str: str) -> dict:
        """메시지의 미디어를 다운로드하고 media_info dict를 반환한다.

        사진/PDF만 다운로드하고, 그 외 미디어는 type만 기록한다.
        """
        media = msg.media

        # 사진
        if getattr(media, "photo", None):
            return await self._download_photo(msg, channel_name, date_str)

        # 문서 (PDF만 다운로드)
        if getattr(media, "document", None):
            doc = media.document
            mime = getattr(doc, "mime_type", "")
            if mime == "application/pdf":
                return await self._download_pdf(msg, channel_name, date_str)
            return {"type": type(media).__name__, "mime_type": mime}

        return {"type": type(media).__name__}

    async def _download_photo(self, msg: Any, channel: str, date_str: str) -> dict:
        dir_path = self._base_dir / "images" / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{channel}_{msg.id}.jpg"
        try:
            await self._client.download_media(msg, str(file_path))
            return {"type": "photo", "local_path": str(file_path)}
        except Exception as e:
            logger.warning("사진 다운로드 실패 (msg=%d): %s", msg.id, e)
            return {"type": "photo"}

    async def _download_pdf(self, msg: Any, channel: str, date_str: str) -> dict:
        dir_path = self._base_dir / "files" / date_str
        dir_path.mkdir(parents=True, exist_ok=True)

        # 원본 파일명 추출
        filename = f"{msg.id}.pdf"
        doc = msg.media.document
        for attr in getattr(doc, "attributes", []):
            if hasattr(attr, "file_name") and attr.file_name:
                filename = f"{msg.id}_{attr.file_name}"
                break

        file_path = dir_path / f"{channel}_{filename}"
        try:
            await self._client.download_media(msg, str(file_path))
            return {
                "type": "document",
                "mime_type": "application/pdf",
                "local_path": str(file_path),
            }
        except Exception as e:
            logger.warning("PDF 다운로드 실패 (msg=%d): %s", msg.id, e)
            return {"type": "document", "mime_type": "application/pdf"}

    async def download_url_pdfs(
        self, content: str, channel: str, date_str: str, msg_id: int,
    ) -> list[str]:
        """메시지 본문에서 PDF URL을 찾아 다운로드한다.

        Returns:
            다운로드된 파일 경로 리스트
        """
        urls = URL_PATTERN.findall(content)
        if not urls:
            return []

        dir_path = self._base_dir / "files" / date_str
        downloaded: list[str] = []

        for url in urls:
            # URL에서 파일명 추출
            url_filename = url.split("/")[-1].split("?")[0]
            if not url_filename.lower().endswith(".pdf"):
                url_filename = f"{msg_id}.pdf"
            file_path = dir_path / f"{channel}_url_{msg_id}_{url_filename}"

            if await self._fetch_url_pdf(url, file_path):
                downloaded.append(str(file_path))

        return downloaded

    async def _fetch_url_pdf(self, url: str, path: Path) -> bool:
        """URL에서 PDF를 다운로드한다. 성공 시 True."""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                # HEAD로 Content-Type 확인
                head = await client.head(url)
                if "application/pdf" not in head.headers.get("content-type", ""):
                    return False

                # 스트림 다운로드
                resp = await client.get(url)
                resp.raise_for_status()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(resp.content)
                logger.info("URL PDF 다운로드 완료: %s", path)
                return True
        except Exception as e:
            logger.warning("URL PDF 다운로드 실패 (%s): %s", url, e)
            return False
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/providers/test_telegram_media.py -v`
예상: 7개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_media.py tests/providers/test_telegram_media.py
git commit -m "feat: add TelegramMediaDownloader for photo and PDF downloads"
```

---

### Task 9: CLI 커맨드 — telegram fetch / catch-up

**파일:**
- 수정: `src/cli/main.py`

- [ ] **Step 1: 구현 작성**

`src/cli/main.py`의 끝부분(`cache_app` 블록 뒤)에 다음을 추가:

```python
# --- Telegram 서브커맨드 ---

telegram_app = typer.Typer(help="Telegram 채널 메시지 수집")
app.add_typer(telegram_app, name="telegram")


async def run_telegram_fetch(date_str: str, config_path: str):
    """지정 날짜의 텔레그램 메시지를 수집한다."""
    from src.providers.telegram_config import TelegramConfig
    from src.providers.telegram_client import TelegramClientWrapper
    from src.providers.telegram_collector import TelegramCollector
    from src.providers.telegram_media import TelegramMediaDownloader
    from src.providers.telegram_storage import TelegramStorage
    from src.providers.telegram_state import TelegramState

    config = TelegramConfig.from_yaml(Path(config_path))
    if not config.channels:
        return {"success": False, "error": "config.yaml에 telegram.channels가 설정되지 않았습니다."}

    wrapper = TelegramClientWrapper()
    await wrapper.start()

    try:
        media_downloader = TelegramMediaDownloader(
            client=wrapper.client, base_dir=config.output_dir,
        )
        collector = TelegramCollector(
            client=wrapper.client, media_downloader=media_downloader,
        )
        storage = TelegramStorage(output_dir=config.output_dir)
        state = TelegramState(config.output_dir / "monitor_state.json")

        total = 0
        for ch_config in config.channels:
            messages = await collector.fetch_channel(ch_config, date_str)
            storage.save(ch_config.id, date_str, messages)
            for msg in messages:
                state.update(ch_config.id, msg["message_id"])
            total += len(messages)

        return {"success": True, "total": total, "date": date_str}
    finally:
        await wrapper.stop()


async def run_telegram_catchup(config_path: str):
    """마지막 수집 이후 누락분을 보충한다."""
    from datetime import datetime
    from src.providers.telegram_config import TelegramConfig
    from src.providers.telegram_client import TelegramClientWrapper
    from src.providers.telegram_collector import TelegramCollector
    from src.providers.telegram_media import TelegramMediaDownloader
    from src.providers.telegram_storage import TelegramStorage
    from src.providers.telegram_state import TelegramState

    config = TelegramConfig.from_yaml(Path(config_path))
    if not config.channels:
        return {"success": False, "error": "config.yaml에 telegram.channels가 설정되지 않았습니다."}

    wrapper = TelegramClientWrapper()
    await wrapper.start()

    try:
        media_downloader = TelegramMediaDownloader(
            client=wrapper.client, base_dir=config.output_dir,
        )
        collector = TelegramCollector(
            client=wrapper.client, media_downloader=media_downloader,
        )
        storage = TelegramStorage(output_dir=config.output_dir)
        state = TelegramState(config.output_dir / "monitor_state.json")

        total = 0
        for ch_config in config.channels:
            min_id = state.get_last_message_id(ch_config.id)
            messages = await collector.fetch_since(ch_config, min_id)
            # 날짜별로 그룹핑하여 저장
            by_date: dict[str, list[dict]] = {}
            for msg in messages:
                msg_date = msg["timestamp"][:10]
                by_date.setdefault(msg_date, []).append(msg)
            for date_str, date_msgs in by_date.items():
                storage.save(ch_config.id, date_str, date_msgs)
            for msg in messages:
                state.update(ch_config.id, msg["message_id"])
            total += len(messages)

        return {"success": True, "total": total}
    finally:
        await wrapper.stop()


@telegram_app.command("fetch")
def telegram_fetch(
    date: str = typer.Argument(
        None,
        help="수집할 날짜 (YYYY-MM-DD). 미지정 시 전날.",
    ),
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="config.yaml 경로"),
):
    """특정 날짜의 텔레그램 메시지를 일괄 수집한다."""
    from datetime import datetime as dt, timedelta

    if date is None:
        date = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    console.print(f"[bold]Telegram 메시지 수집 중... (날짜: {date})[/bold]\n")

    try:
        result = asyncio.run(run_telegram_fetch(date, config_path))
        if result["success"]:
            console.print(f"[green]완료: {result['total']}건 수집됨 ({result['date']})[/green]")
        else:
            console.print(f"[red]오류: {result['error']}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1)


@telegram_app.command("catch-up")
def telegram_catchup(
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="config.yaml 경로"),
):
    """마지막 수집 이후 누락분을 보충 수집한다."""
    console.print("[bold]Telegram catch-up 수집 중...[/bold]\n")

    try:
        result = asyncio.run(run_telegram_catchup(config_path))
        if result["success"]:
            console.print(f"[green]완료: {result['total']}건 보충 수집됨[/green]")
        else:
            console.print(f"[red]오류: {result['error']}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 2: CLI 헬프 확인**

실행: `uv run jarvis telegram --help`
예상: `fetch`와 `catch-up` 서브커맨드가 표시됨

실행: `uv run jarvis telegram fetch --help`
예상: `DATE` 인자와 `--config` 옵션이 표시됨

- [ ] **Step 3: 커밋**

```bash
git add src/cli/main.py
git commit -m "feat: add telegram fetch and catch-up CLI commands"
```

---

### Task 10: config.yaml에 telegram 섹션 추가

**파일:**
- 수정: `config.yaml`

- [ ] **Step 1: telegram 섹션 추가**

`config.yaml` 끝에 다음을 추가:

```yaml
telegram:
  channels: []
  # 예시:
  # channels:
  #   - "channel_username_or_id"
  #   - id: "filtered_channel"
  #     include:
  #       - "Breaking|Urgent"
  #     exclude:
  #       - "(?i)ad"
  output_dir: "data"
  # link_processing:
  #   summarize_links_channels:
  #     - "kiwoom_semibat"
```

- [ ] **Step 2: 커밋**

```bash
git add config.yaml
git commit -m "feat: add telegram section to config.yaml"
```

---

### Task 11: 문서 업데이트

**파일:**
- 수정: `README.md` — Telegram 커맨드 추가
- 수정: `docs/CLI_USAGE.md` — telegram 섹션 추가
- 수정: `CLAUDE.md` — Architecture, Commands 섹션 업데이트

- [ ] **Step 1: README.md에 Telegram 커맨드 추가**

Features/Commands 섹션에 다음을 추가:

```markdown
uv run jarvis telegram fetch     # 텔레그램 채널 메시지 수집 (기본: 전날)
uv run jarvis telegram catch-up  # 누락분 보충 수집
```

- [ ] **Step 2: docs/CLI_USAGE.md에 telegram 섹션 추가**

명령어 상세 섹션에 다음을 추가:

```markdown
### 7. telegram - 텔레그램 채널 수집

**특징:**
- Telethon 기반 채널 메시지 수집
- include/exclude 정규식 필터링
- 날짜별 CSV 저장 (중복 방지)
- catch-up 모드로 누락분 자동 보충

**요구사항:**
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` 필요
- `config.yaml`에 `telegram.channels` 설정 필요
- 첫 실행 시 Telegram 인증 (전화번호/코드) 필요

**사용법:**
```bash
# 전날 메시지 수집 (기본)
uv run jarvis telegram fetch

# 특정 날짜 수집
uv run jarvis telegram fetch 2026-04-12

# 누락분 보충 수집
uv run jarvis telegram catch-up

# 커스텀 설정 파일
uv run jarvis telegram fetch --config my_config.yaml
```

**데이터 저장:**
- CSV: `data/YYYY-MM/YYYY-MM-DD-{channel}.csv`
- 상태: `data/monitor_state.json`
```

- [ ] **Step 3: CLAUDE.md 업데이트**

Architecture 섹션의 Providers 행에 Telegram 추가:

```markdown
| **Providers** | `src/providers/` | Raw data fetching (yfinance, KIS API, Naver, Telegram) |
```

Common Commands 섹션에 추가:

```markdown
uv run jarvis telegram fetch     # 텔레그램 채널 메시지 수집
uv run jarvis telegram catch-up  # 누락분 보충 수집
```

환경 변수 섹션에 추가:

```
TELEGRAM_API_ID=...            # Telegram message collection
TELEGRAM_API_HASH=...
```

- [ ] **Step 4: 커밋**

```bash
git add README.md docs/CLI_USAGE.md CLAUDE.md
git commit -m "docs: add telegram collection commands to documentation"
```
