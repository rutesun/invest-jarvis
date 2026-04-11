# Daily Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram 채널 메시지를 수집·저장하고, 매일 시장 전반/테마/특징주를 분석한 Daily Report를 생성한다.

**Architecture:** Part A (Tasks 1-7)는 Telethon 기반 Telegram 수집 파이프라인이며 LLM 없이 독립 동작한다. Part B (Tasks 8-12)는 수집된 CSV + Naver + 매크로 데이터를 LLM Map-Reduce로 분석해 마크다운 리포트를 출력한다.

**Tech Stack:** telethon, pydantic v2, langchain-core, httpx, typer, pyyaml, pytest-asyncio

---

## File Structure

```
src/core/config.py                        MODIFY — TelegramConfig 추가
src/providers/telegram_client.py          CREATE — Telethon 클라이언트 팩토리
src/providers/telegram_state.py           CREATE — monitor_state.json 관리
src/providers/telegram_storage.py         CREATE — CSV 저장 + 경로 유틸
src/providers/telegram_collector.py       CREATE — fetch/catch-up 수집 로직
src/providers/telegram_loader.py          CREATE — CSV 로드 + 검색 + 청킹
src/providers/naver.py                    MODIFY — get_investor_flow 추가
src/llm/daily_report_models.py            CREATE — Map-Reduce Pydantic 모델
src/llm/daily_report_analyzer.py          CREATE — map/reduce/wrapup LLM 함수
src/pipelines/daily_report_v2.py          CREATE — 전체 파이프라인 오케스트레이터
src/cli/main.py                           MODIFY — telegram 서브앱 + daily-report 커맨드

tests/providers/test_telegram_state.py    CREATE
tests/providers/test_telegram_storage.py  CREATE
tests/providers/test_telegram_loader.py   CREATE
tests/llm/test_daily_report_analyzer.py   CREATE
```

---

## Part A: Telegram 수집 파이프라인

---

### Task 1: TelegramConfig + telethon 의존성 추가

**Files:**
- Modify: `src/core/config.py`
- Modify: `pyproject.toml`
- Modify: `config.yaml`

- [ ] **Step 1: telethon 의존성 추가**

```bash
uv add telethon
```

Expected: `pyproject.toml`의 `dependencies`에 `telethon>=1.36` 추가됨.

- [ ] **Step 2: TelegramConfig 모델 작성**

`src/core/config.py`의 기존 import 아래에 추가:

```python
class ChannelRule(BaseModel):
    """단일 채널 수집 규칙."""
    id: str
    include: list[str] = []  # 정규식 — OR 매칭, 비어있으면 전체 허용
    exclude: list[str] = []  # 정규식 — ANY 매칭 시 제외


class TelegramConfig(BaseModel):
    """Telegram 수집 설정."""
    channels: list[ChannelRule] = []
    output_dir: str = "data"
    session_path: str = "~/.cache/invest-jarvis/telegram.session"

    @model_validator(mode="before")
    @classmethod
    def normalize_channels(cls, data: dict) -> dict:
        raw = data.get("channels", [])
        normalized = []
        for ch in raw:
            if isinstance(ch, str):
                normalized.append({"id": ch})
            elif isinstance(ch, dict):
                normalized.append(ch)
        data["channels"] = normalized
        return data
```

`AppConfig`에 필드 추가:

```python
class AppConfig(BaseModel):
    technical: TechnicalConfig = TechnicalConfig()
    cache: CacheConfig = CacheConfig()
    telegram: TelegramConfig = TelegramConfig()  # 추가
```

`config.py` 파일 상단 import 수정:

```python
from pydantic import BaseModel, model_validator
```

- [ ] **Step 3: config.yaml에 telegram 섹션 추가**

기존 `config.yaml` 끝에 추가:

```yaml
telegram:
  output_dir: "data"
  session_path: "~/.cache/invest-jarvis/telegram.session"
  channels:
    - "example_channel"   # 실제 채널 ID로 교체
```

- [ ] **Step 4: 파싱 확인**

```bash
uv run python -c "
from src.core.config import load_config
cfg = load_config()
print(cfg.telegram)
print(cfg.telegram.channels)
"
```

Expected: `TelegramConfig(channels=[...], output_dir='data', ...)` 출력.

- [ ] **Step 5: 커밋**

```bash
git add src/core/config.py pyproject.toml uv.lock config.yaml
git commit -m "feat: add TelegramConfig and telethon dependency"
```

---

### Task 2: Telegram State 관리

**Files:**
- Create: `src/providers/telegram_state.py`
- Create: `tests/providers/test_telegram_state.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_state.py
import json
from pathlib import Path
import pytest
from src.providers.telegram_state import TelegramState


def test_get_last_id_empty(tmp_path):
    state = TelegramState(tmp_path / "state.json")
    assert state.get_last_id("123") == 0


def test_save_and_get(tmp_path):
    state = TelegramState(tmp_path / "state.json")
    state.save("123", 500)
    assert state.get_last_id("123") == 500


def test_save_is_monotonic(tmp_path):
    state = TelegramState(tmp_path / "state.json")
    state.save("123", 500)
    state.save("123", 300)  # 더 작은 값 — 무시돼야 함
    assert state.get_last_id("123") == 500


def test_multiple_channels(tmp_path):
    state = TelegramState(tmp_path / "state.json")
    state.save("aaa", 100)
    state.save("bbb", 200)
    assert state.get_last_id("aaa") == 100
    assert state.get_last_id("bbb") == 200


def test_persisted_to_json(tmp_path):
    path = tmp_path / "state.json"
    state = TelegramState(path)
    state.save("123", 999)

    raw = json.loads(path.read_text())
    assert raw["123"] == 999
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/providers/test_telegram_state.py -v
```

Expected: `ModuleNotFoundError` 또는 `ImportError`.

- [ ] **Step 3: 구현**

```python
# src/providers/telegram_state.py
"""Telegram 채널별 마지막 수집 메시지 ID 상태 관리."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TelegramState:
    """monitor_state.json 기반 채널 상태 추적.
    
    단조 증가(monotonic) 보장: 더 큰 message_id만 저장.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def _load(self) -> dict[str, int]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("상태 파일 로드 실패: %s", e)
            return {}

    def _write(self, data: dict[str, int]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.error("상태 파일 저장 실패: %s", e)

    def get_last_id(self, channel_id: str) -> int:
        """채널의 마지막 수집 message_id 반환. 없으면 0."""
        return self._load().get(str(channel_id), 0)

    def save(self, channel_id: str, message_id: int) -> None:
        """단조 증가 방식으로 message_id 저장."""
        data = self._load()
        key = str(channel_id)
        if message_id > data.get(key, 0):
            data[key] = message_id
            self._write(data)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/providers/test_telegram_state.py -v
```

Expected: 5개 테스트 모두 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_state.py tests/providers/test_telegram_state.py
git commit -m "feat: add TelegramState for channel message ID tracking"
```

---

### Task 3: Telegram Storage (CSV 저장)

**Files:**
- Create: `src/providers/telegram_storage.py`
- Create: `tests/providers/test_telegram_storage.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/providers/test_telegram_storage.py
import csv
from pathlib import Path
from datetime import datetime, timezone
import pytest
from src.providers.telegram_storage import TelegramStorage, CSV_COLUMNS


def make_msg(msg_id: int = 1, channel: str = "ch1", content: str = "test") -> dict:
    return {
        "message_id": msg_id,
        "timestamp": "2026-04-11T09:00:00+00:00",
        "channel_name": channel,
        "author": "user1",
        "content": content,
        "media_info": None,
        "forward_from": None,
    }


def test_get_csv_path(tmp_path):
    storage = TelegramStorage(str(tmp_path))
    path = storage.get_csv_path("mychannel", "2026-04-11")
    assert path == tmp_path / "2026-04" / "2026-04-11-mychannel.csv"


def test_save_creates_file(tmp_path):
    storage = TelegramStorage(str(tmp_path))
    saved = storage.save_message(make_msg())
    assert saved is True
    path = storage.get_csv_path("ch1", "2026-04-11")
    assert path.exists()


def test_save_has_header(tmp_path):
    storage = TelegramStorage(str(tmp_path))
    storage.save_message(make_msg())
    path = storage.get_csv_path("ch1", "2026-04-11")
    with path.open(encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert header == CSV_COLUMNS


def test_duplicate_skipped(tmp_path):
    storage = TelegramStorage(str(tmp_path))
    storage.save_message(make_msg(msg_id=42))
    saved = storage.save_message(make_msg(msg_id=42))
    assert saved is False
    path = storage.get_csv_path("ch1", "2026-04-11")
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1


def test_get_existing_ids_empty(tmp_path):
    storage = TelegramStorage(str(tmp_path))
    path = tmp_path / "nonexistent.csv"
    assert storage.get_existing_ids(path) == set()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/providers/test_telegram_storage.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: 구현**

```python
# src/providers/telegram_storage.py
"""Telegram 메시지 CSV 저장 및 경로 유틸리티."""
import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "message_id", "timestamp", "channel_name", "author",
    "content", "media_info", "forward_from",
]


class TelegramStorage:
    """날짜별 CSV 파일에 메시지 저장.
    
    파일 구조: {output_dir}/YYYY-MM/YYYY-MM-DD-{channel_name}.csv
    중복 방지: 저장 전 message_id 풀스캔.
    """

    def __init__(self, output_dir: str) -> None:
        self._base = Path(output_dir)

    def get_csv_path(self, channel_name: str, date_str: str) -> Path:
        """CSV 파일 경로 반환. 예: data/2026-04/2026-04-11-mychannel.csv"""
        month = date_str[:7]  # YYYY-MM
        safe_name = _safe_filename(channel_name)
        return self._base / month / f"{date_str}-{safe_name}.csv"

    def get_existing_ids(self, path: Path) -> set[int]:
        """CSV 파일에서 기존 message_id 집합 반환."""
        if not path.exists():
            return set()
        ids: set[int] = set()
        try:
            with path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        ids.add(int(row["message_id"]))
                    except (KeyError, ValueError):
                        pass
        except Exception as e:
            logger.warning("기존 ID 로드 실패 (%s): %s", path, e)
        return ids

    def save_message(self, message_data: dict) -> bool:
        """메시지를 CSV에 저장. 중복이면 False 반환.

        Args:
            message_data: keys — message_id, timestamp(ISO/UTC), channel_name,
                          author, content, media_info(dict|None), forward_from(str|None)
        
        Returns:
            True if saved, False if duplicate.
        """
        ts = message_data.get("timestamp", "")
        date_str = _iso_to_kst_date(ts)
        channel = message_data.get("channel_name", "unknown")
        path = self.get_csv_path(channel, date_str)

        msg_id = int(message_data.get("message_id", 0))
        existing = self.get_existing_ids(path)
        if msg_id in existing:
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.exists()

        try:
            with path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                if write_header:
                    writer.writeheader()
                media = message_data.get("media_info")
                writer.writerow({
                    "message_id": msg_id,
                    "timestamp": ts,
                    "channel_name": channel,
                    "author": message_data.get("author", ""),
                    "content": message_data.get("content", ""),
                    "media_info": json.dumps(media, ensure_ascii=False) if media else "",
                    "forward_from": message_data.get("forward_from", "") or "",
                })
            return True
        except Exception as e:
            logger.error("메시지 저장 실패 (id=%s): %s", msg_id, e, exc_info=True)
            return False


def _safe_filename(name: str) -> str:
    """파일명에 사용 불가한 문자 제거."""
    import re
    return re.sub(r'[^\w가-힣\-]', '_', name)


def _iso_to_kst_date(iso_str: str) -> str:
    """ISO UTC 타임스탬프 → KST 날짜 문자열 (YYYY-MM-DD)."""
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%Y-%m-%d")
    except Exception:
        from datetime import date
        return date.today().isoformat()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/providers/test_telegram_storage.py -v
```

Expected: 5개 테스트 모두 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_storage.py tests/providers/test_telegram_storage.py
git commit -m "feat: add TelegramStorage for CSV message persistence"
```

---

### Task 4: Telegram Collector (필터 + 수집 로직)

**Files:**
- Create: `src/providers/telegram_collector.py`
- Create: `tests/providers/test_telegram_collector.py`

- [ ] **Step 1: 필터 로직 테스트 작성**

```python
# tests/providers/test_telegram_collector.py
import pytest
from src.core.config import ChannelRule
from src.providers.telegram_collector import should_process_message


def test_no_rules_accepts_all():
    rule = ChannelRule(id="ch1")
    assert should_process_message("아무 내용이나", rule) is True


def test_exclude_blocks():
    rule = ChannelRule(id="ch1", exclude=["(?i)광고"])
    assert should_process_message("오늘 광고 대박", rule) is False
    assert should_process_message("시장 분석", rule) is True


def test_include_filters():
    rule = ChannelRule(id="ch1", include=["매수|매도"])
    assert should_process_message("AAPL 매수 추천", rule) is True
    assert should_process_message("오늘 날씨 맑음", rule) is False


def test_exclude_checked_before_include():
    rule = ChannelRule(id="ch1", include=["매수"], exclude=["광고"])
    assert should_process_message("매수 광고", rule) is False


def test_empty_content_rejected():
    rule = ChannelRule(id="ch1")
    assert should_process_message("", rule) is False
    assert should_process_message("   ", rule) is False
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/providers/test_telegram_collector.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: 구현**

```python
# src/providers/telegram_collector.py
"""Telegram 메시지 수집 — fetch(날짜 지정) + catch-up(누락 보충)."""
import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import AsyncIterator

from src.core.config import ChannelRule, TelegramConfig
from src.providers.telegram_state import TelegramState
from src.providers.telegram_storage import TelegramStorage

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def should_process_message(content: str, rule: ChannelRule) -> bool:
    """include/exclude 규칙에 따라 메시지 처리 여부 결정.
    
    1. 빈 메시지 거부
    2. exclude 패턴 매칭 시 거부 (먼저 체크)
    3. include 패턴이 있으면 하나 이상 매칭 시 허용
    4. 규칙 없으면 허용
    """
    if not content or not content.strip():
        return False

    for pattern in rule.exclude:
        if re.search(pattern, content):
            return False

    if rule.include:
        return any(re.search(p, content) for p in rule.include)

    return True


def _find_rule(config: TelegramConfig, channel_id: str, username: str) -> ChannelRule:
    """채널 ID 또는 username으로 ChannelRule 검색. 없으면 기본 규칙 반환."""
    for rule in config.channels:
        if rule.id in (channel_id, username):
            return rule
    return ChannelRule(id=channel_id)


def _kst_day_range_utc(target: date) -> tuple[datetime, datetime]:
    """KST 날짜의 UTC 시작/끝 반환."""
    start_kst = datetime(target.year, target.month, target.day, tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def _build_message_data(message, channel_name: str) -> dict:
    """Telethon Message → dict 변환."""
    ts = message.date
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    content = message.message or ""
    author = ""
    if message.sender:
        author = getattr(message.sender, "username", "") or str(message.sender_id)

    return {
        "message_id": message.id,
        "timestamp": ts.isoformat(),
        "channel_name": channel_name,
        "author": author,
        "content": content,
        "media_info": None,  # 미디어는 이 플랜에서 생략
        "forward_from": str(message.fwd_from.from_id) if message.fwd_from else None,
    }


class TelegramCollector:
    """fetch/catch-up 방식 메시지 수집기."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        storage_dir = config.output_dir
        state_path = f"{storage_dir}/monitor_state.json"
        self._storage = TelegramStorage(storage_dir)
        self._state = TelegramState(state_path)

    async def fetch_date(self, client, target: date | None = None) -> int:
        """특정 날짜(기본: 전날) 메시지 수집.
        
        Returns:
            저장된 메시지 수
        """
        if target is None:
            target = (datetime.now(KST) - timedelta(days=1)).date()

        start_utc, end_utc = _kst_day_range_utc(target)
        total = 0

        for rule in self._config.channels:
            try:
                entity = await client.get_entity(rule.id)
                channel_name = getattr(entity, "title", rule.id) or rule.id
                count = 0

                async for message in client.iter_messages(
                    entity,
                    offset_date=end_utc,
                    reverse=False,
                ):
                    msg_date = message.date
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)

                    if msg_date < start_utc:
                        break

                    if not message.message:
                        continue

                    if not should_process_message(message.message, rule):
                        continue

                    data = _build_message_data(message, channel_name)
                    if self._storage.save_message(data):
                        count += 1
                    self._state.save(str(entity.id), message.id)

                logger.info("fetch_date[%s] %s: %d건", target, rule.id, count)
                total += count

            except Exception as e:
                logger.error("채널 수집 실패 (%s): %s", rule.id, e)

        return total

    async def catch_up(self, client) -> int:
        """마지막 수집 이후 누락분 보충.
        
        Returns:
            저장된 메시지 수
        """
        total = 0

        for rule in self._config.channels:
            try:
                entity = await client.get_entity(rule.id)
                channel_name = getattr(entity, "title", rule.id) or rule.id
                min_id = self._state.get_last_id(str(entity.id))
                count = 0

                async for message in client.iter_messages(
                    entity,
                    min_id=min_id,
                    reverse=True,
                ):
                    if not message.message:
                        continue
                    if not should_process_message(message.message, rule):
                        continue

                    data = _build_message_data(message, channel_name)
                    if self._storage.save_message(data):
                        count += 1
                    self._state.save(str(entity.id), message.id)

                logger.info("catch_up[%s]: %d건", rule.id, count)
                total += count

            except Exception as e:
                logger.error("catch_up 실패 (%s): %s", rule.id, e)

        return total
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/providers/test_telegram_collector.py -v
```

Expected: 5개 테스트 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/providers/telegram_collector.py tests/providers/test_telegram_collector.py
git commit -m "feat: add TelegramCollector with fetch/catch-up and message filtering"
```

---

### Task 5: Telegram Client + Loader

**Files:**
- Create: `src/providers/telegram_client.py`
- Create: `src/providers/telegram_loader.py`
- Create: `tests/providers/test_telegram_loader.py`

- [ ] **Step 1: telegram_client.py 작성**

```python
# src/providers/telegram_client.py
"""Telethon TelegramClient 팩토리."""
import os
from pathlib import Path


def get_client(session_path: str = "~/.cache/invest-jarvis/telegram.session"):
    """TelegramClient 인스턴스 반환.
    
    환경변수:
        TELEGRAM_API_ID: Telegram API ID (필수)
        TELEGRAM_API_HASH: Telegram API Hash (필수)
    
    Raises:
        EnvironmentError: API 자격증명 누락 시
    """
    from telethon import TelegramClient  # 런타임 임포트 (텔레그램 미설치 환경 보호)

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        raise EnvironmentError(
            "TELEGRAM_API_ID, TELEGRAM_API_HASH 환경변수를 설정하세요.\n"
            ".env 파일에 추가하거나 export로 설정하세요."
        )

    resolved = Path(session_path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    return TelegramClient(str(resolved), int(api_id), api_hash)
```

- [ ] **Step 2: loader 테스트 작성**

```python
# tests/providers/test_telegram_loader.py
import csv
from pathlib import Path
import pytest
from src.providers.telegram_loader import TelegramLoader, chunk_messages


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "message_id", "timestamp", "channel_name", "author",
            "content", "media_info", "forward_from",
        ])
        writer.writeheader()
        writer.writerows(rows)


def test_load_date_returns_messages(tmp_path):
    _write_csv(
        tmp_path / "2026-04" / "2026-04-11-ch1.csv",
        [{"message_id": 1, "timestamp": "...", "channel_name": "ch1",
          "author": "u", "content": "hello", "media_info": "", "forward_from": ""}]
    )
    loader = TelegramLoader(str(tmp_path))
    msgs = loader.load_date("2026-04-11")
    assert len(msgs) == 1
    assert msgs[0]["content"] == "hello"


def test_load_date_no_file(tmp_path):
    loader = TelegramLoader(str(tmp_path))
    msgs = loader.load_date("2026-04-11")
    assert msgs == []


def test_search_messages_keyword(tmp_path):
    _write_csv(
        tmp_path / "2026-04" / "2026-04-11-ch1.csv",
        [
            {"message_id": 1, "timestamp": "2026-04-11T01:00:00+00:00", "channel_name": "ch1",
             "author": "u", "content": "NVDA 매수 추천", "media_info": "", "forward_from": ""},
            {"message_id": 2, "timestamp": "2026-04-11T02:00:00+00:00", "channel_name": "ch1",
             "author": "u", "content": "날씨 맑음", "media_info": "", "forward_from": ""},
        ]
    )
    loader = TelegramLoader(str(tmp_path))
    result = loader.search("NVDA", date_str="2026-04-11")
    assert len(result) == 1
    assert "NVDA" in result[0]["content"]


def test_chunk_messages():
    msgs = [{"content": str(i)} for i in range(130)]
    chunks = chunk_messages(msgs, chunk_size=50)
    assert len(chunks) == 3
    assert len(chunks[0]) == 50
    assert len(chunks[2]) == 30
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
uv run pytest tests/providers/test_telegram_loader.py -v
```

Expected: `ImportError`.

- [ ] **Step 4: loader 구현**

```python
# src/providers/telegram_loader.py
"""Telegram CSV 파일 로드 + 검색 + 청킹."""
import csv
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class TelegramLoader:
    """저장된 Telegram CSV를 읽어 분석에 제공."""

    def __init__(self, output_dir: str) -> None:
        self._base = Path(output_dir)

    def load_date(self, date_str: str) -> list[dict]:
        """날짜의 모든 채널 CSV 로드.
        
        Args:
            date_str: YYYY-MM-DD
            
        Returns:
            메시지 dict 리스트 (전체 채널 합산)
        """
        month = date_str[:7]
        pattern = f"{date_str}-*.csv"
        csv_files = list((self._base / month).glob(pattern))

        if not csv_files:
            logger.debug("CSV 없음: %s", date_str)
            return []

        messages: list[dict] = []
        for path in csv_files:
            messages.extend(_read_csv(path))

        logger.debug("load_date[%s]: %d건 로드", date_str, len(messages))
        return messages

    def search(self, query: str, date_str: str) -> list[dict]:
        """특정 날짜 CSV에서 키워드 검색 (대소문자 무관).
        
        Args:
            query: 검색어 (정규식 사용 가능)
            date_str: YYYY-MM-DD
            
        Returns:
            매칭된 메시지 리스트
        """
        messages = self.load_date(date_str)
        pattern = re.compile(query, re.IGNORECASE)
        return [m for m in messages if pattern.search(m.get("content", ""))]


def chunk_messages(messages: list[dict], chunk_size: int = 50) -> list[list[dict]]:
    """메시지 리스트를 chunk_size 크기로 분할."""
    return [messages[i:i + chunk_size] for i in range(0, len(messages), chunk_size)]


def _read_csv(path: Path) -> list[dict]:
    """단일 CSV 파일을 dict 리스트로 읽기."""
    rows = []
    try:
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
    except Exception as e:
        logger.warning("CSV 읽기 실패 (%s): %s", path, e)
    return rows
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
uv run pytest tests/providers/test_telegram_loader.py -v
```

Expected: 4개 테스트 PASS.

- [ ] **Step 6: 커밋**

```bash
git add src/providers/telegram_client.py src/providers/telegram_loader.py tests/providers/test_telegram_loader.py
git commit -m "feat: add TelegramClient factory and TelegramLoader (CSV load/search/chunk)"
```

---

### Task 6: Telegram CLI 서브앱

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: `telegram_app` 서브앱 추가**

`src/cli/main.py`에서 기존 `cache_app` 선언 아래에 추가:

```python
# src/cli/main.py 에 추가할 코드

telegram_app = typer.Typer(help="Telegram 메시지 수집")
app.add_typer(telegram_app, name="telegram")


@telegram_app.command("fetch")
def telegram_fetch(
    date: str = typer.Argument(
        None,
        help="수집할 날짜 (YYYY-MM-DD). 기본값: 전날",
    ),
):
    """특정 날짜 Telegram 메시지 수집 (기본: 전날)."""
    import asyncio
    from datetime import date as date_type, datetime, timedelta, timezone
    from src.core.config import load_config
    from src.providers.telegram_client import get_client
    from src.providers.telegram_collector import TelegramCollector

    cfg = load_config()

    if not cfg.telegram.channels:
        console.print("[yellow]config.yaml에 telegram.channels가 비어있습니다.[/yellow]")
        raise typer.Exit(1)

    target: date_type | None = None
    if date:
        try:
            target = date_type.fromisoformat(date)
        except ValueError:
            console.print(f"[red]날짜 형식 오류: {date} (YYYY-MM-DD 형식 사용)[/red]")
            raise typer.Exit(1)

    display_date = str(target) if target else "전날"
    console.print(f"[bold]Telegram 메시지 수집 중 ({display_date})...[/bold]")

    async def _run():
        client = get_client(cfg.telegram.session_path)
        async with client:
            await client.start()
            collector = TelegramCollector(cfg.telegram)
            count = await collector.fetch_date(client, target)
        return count

    try:
        count = asyncio.run(_run())
        console.print(f"[green]✓ {count}개 메시지 저장 완료[/green]")
    except EnvironmentError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]수집 오류: {e}[/red]")
        raise typer.Exit(1)


@telegram_app.command("catch-up")
def telegram_catch_up():
    """마지막 수집 이후 누락된 메시지 보충."""
    import asyncio
    from src.core.config import load_config
    from src.providers.telegram_client import get_client
    from src.providers.telegram_collector import TelegramCollector

    cfg = load_config()

    if not cfg.telegram.channels:
        console.print("[yellow]config.yaml에 telegram.channels가 비어있습니다.[/yellow]")
        raise typer.Exit(1)

    console.print("[bold]Telegram catch-up 수집 중...[/bold]")

    async def _run():
        client = get_client(cfg.telegram.session_path)
        async with client:
            await client.start()
            collector = TelegramCollector(cfg.telegram)
            count = await collector.catch_up(client)
        return count

    try:
        count = asyncio.run(_run())
        console.print(f"[green]✓ {count}개 누락 메시지 저장 완료[/green]")
    except EnvironmentError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]수집 오류: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 2: CLI 등록 확인**

```bash
uv run jarvis telegram --help
```

Expected:
```
Usage: jarvis telegram [OPTIONS] COMMAND [ARGS]...
  Telegram 메시지 수집

Commands:
  catch-up  마지막 수집 이후 누락된 메시지 보충.
  fetch     특정 날짜 Telegram 메시지 수집 (기본: 전날).
```

- [ ] **Step 3: 커밋**

```bash
git add src/cli/main.py
git commit -m "feat: add jarvis telegram fetch/catch-up CLI commands"
```

---

## Part B: Daily Report 파이프라인

---

### Task 7: Naver 투자자 수급 데이터

**Files:**
- Modify: `src/providers/naver.py`

- [ ] **Step 1: `get_investor_flow` 메서드 추가**

`src/providers/naver.py`의 `NaverProvider` 클래스에 추가:

```python
async def get_investor_flow(
    self, top_n: int = 20
) -> dict[str, list[dict]]:
    """KOSPI/KOSDAQ 외인·기관 순매수 상위 종목 조회.
    
    Returns:
        {"KOSPI": [...], "KOSDAQ": [...]}
        각 항목: {code, name, market, foreign_net, institution_net}
    """
    results: dict[str, list[dict]] = {"KOSPI": [], "KOSDAQ": []}

    for market, sosok in (("KOSPI", 0), ("KOSDAQ", 1)):
        # 외국인 순매수 상위
        url = (
            f"{self.FINANCE_BASE}/sise/sise_deal_rank_iframe.naver"
            f"?sosok={sosok}&type=1"
        )
        rows = await self._parse_flow_html(url, market)
        results[market] = rows[:top_n]

    return results

async def _parse_flow_html(self, url: str, market: str) -> list[dict]:
    """투자자별 매매 동향 HTML 파싱."""
    headers = {"Referer": self.FINANCE_BASE}
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text

            table_match = re.search(
                r"<table[^>]*class=['\"][^'\"]*type_2[^'\"]*['\"][^>]*>(.*?)</table>",
                html, re.S | re.I,
            )
            if not table_match:
                return []

            table_html = table_match.group(1)
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)
            results = []

            for row in rows:
                link_match = re.search(
                    r"code=(\d{6})[^'\"]*['\"][^>]*>(.*?)</a>",
                    row, re.S | re.I,
                )
                if not link_match:
                    continue

                code = link_match.group(1)
                name = self._strip_tags(link_match.group(2))
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
                if len(cells) < 5:
                    continue

                # 열 순서: 순위, 종목명, 현재가, 외인순매수, 기관순매수(추정)
                foreign_net = self._to_float(self._strip_tags(cells[3])) if len(cells) > 3 else 0.0
                institution_net = self._to_float(self._strip_tags(cells[4])) if len(cells) > 4 else 0.0

                if code and name:
                    results.append({
                        "code": code,
                        "name": name,
                        "market": market,
                        "foreign_net": foreign_net,
                        "institution_net": institution_net,
                    })

            return results

        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                return []
            await asyncio.sleep(1)

    return []
```

- [ ] **Step 2: 수동 동작 확인**

```bash
uv run python -c "
import asyncio
from src.providers.naver import NaverProvider
async def test():
    naver = NaverProvider()
    flow = await naver.get_investor_flow(top_n=5)
    for market, items in flow.items():
        print(f'{market}: {len(items)}건')
        for item in items[:2]:
            print(f'  {item}')
asyncio.run(test())
"
```

Expected: KOSPI/KOSDAQ 각 5개 이내 종목 출력. 파싱 실패 시 빈 리스트도 허용 (HTML 구조 변경 가능성).

- [ ] **Step 3: 커밋**

```bash
git add src/providers/naver.py
git commit -m "feat: add NaverProvider.get_investor_flow for foreign/institution flow"
```

---

### Task 8: Daily Report LLM 모델 정의

**Files:**
- Create: `src/llm/daily_report_models.py`

- [ ] **Step 1: 모델 파일 작성**

```python
# src/llm/daily_report_models.py
"""Daily Report Map-Reduce LLM 입출력 Pydantic 모델."""
from pydantic import BaseModel


SECTORS = [
    "거시경제/매크로",
    "반도체/하드웨어",
    "소프트웨어/인터넷/AI",
    "에너지/원자재",
    "금융/은행",
    "헬스케어/바이오",
    "산업재/제조",
    "소비재/유통",
]


class MappedIssue(BaseModel):
    """Map 단계에서 추출한 단일 시장 이슈."""
    sector: str        # SECTORS 중 하나
    category: str      # "Company" | "Industry" | "Macroeconomy"
    topic: str         # 기업명, 산업명, 또는 이슈명
    summary: str       # 2-3문장 요약 (한국어)
    impact: str        # 시장 영향 한 줄 (한국어)
    market_impact: str # "Bull" | "Bear" | "Neutral"
    keywords: list[str]
    message_refs: list[str]  # "channel_name:message_id" 형식


class MapChunkOutput(BaseModel):
    """Map 단계 단일 청크 출력 — 여러 이슈 포함."""
    issues: list[MappedIssue] = []


class SectorReduceOutput(BaseModel):
    """Reduce 단계 섹터별 통합 출력."""
    summary: str              # 섹터 종합 요약 (한국어)
    key_developments: list[str]   # 주요 동향 3-5개
    connected_themes: list[str]   # 타 섹터 연결 고리
    market_direction: str     # "Bull" | "Bear" | "Neutral" | "Mixed"


class KeyTheme(BaseModel):
    """Wrapup 단계 핵심 테마."""
    title: str
    description: str          # 2-3문장
    impact_points: list[str]  # 핵심 포인트 2-4개
    action_level: str         # "관심" | "모니터" | "즉시대응"
    connected_themes: list[str]


class DailyReportOutput(BaseModel):
    """Wrapup 단계 최종 출력."""
    market_narrative: str     # 오늘 시장 스토리 3-4문장
    key_themes: list[KeyTheme]  # 5개
    major_issues: list[str]   # 반드시 알아야 할 이슈 7개
```

- [ ] **Step 2: import 확인**

```bash
uv run python -c "from src.llm.daily_report_models import DailyReportOutput, SECTORS; print('OK', SECTORS[:2])"
```

Expected: `OK ['거시경제/매크로', '반도체/하드웨어']`

- [ ] **Step 3: 커밋**

```bash
git add src/llm/daily_report_models.py
git commit -m "feat: add DailyReport LLM Pydantic models (Map-Reduce-Wrapup)"
```

---

### Task 9: Daily Report LLM Analyzer (Map-Reduce-Wrapup)

**Files:**
- Create: `src/llm/daily_report_analyzer.py`
- Create: `tests/llm/test_daily_report_analyzer.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/llm/test_daily_report_analyzer.py
from unittest.mock import AsyncMock, MagicMock
import pytest
from src.llm.daily_report_models import (
    MapChunkOutput, MappedIssue, SectorReduceOutput, KeyTheme, DailyReportOutput,
)
from src.llm.daily_report_analyzer import (
    map_chunk, reduce_sector, wrapup, analyze_messages,
    _extract_top_keywords,
)


def make_issue(sector="반도체/하드웨어", market_impact="Bull", keywords=None) -> MappedIssue:
    return MappedIssue(
        sector=sector, category="Company", topic="SK하이닉스",
        summary="HBM 수요 급증", impact="반도체 수혜",
        market_impact=market_impact,
        keywords=keywords or ["HBM", "반도체"],
        message_refs=["ch1:123"],
    )


def make_llm_mock(return_value):
    """with_structured_output().ainvoke() 를 모킹하는 LLM mock."""
    chain_mock = MagicMock()
    chain_mock.ainvoke = AsyncMock(return_value=return_value)
    llm_mock = MagicMock()
    llm_mock.with_structured_output = MagicMock(return_value=chain_mock)
    return llm_mock


@pytest.mark.asyncio
async def test_map_chunk_returns_issues():
    expected = MapChunkOutput(issues=[make_issue()])
    llm = make_llm_mock(expected)
    messages = [{"channel_name": "ch1", "message_id": "1", "content": "HBM 수요 증가"}]
    result = await map_chunk(messages, llm)
    assert len(result) == 1
    assert result[0].sector == "반도체/하드웨어"


@pytest.mark.asyncio
async def test_map_chunk_empty_messages():
    llm = make_llm_mock(MapChunkOutput(issues=[]))
    result = await map_chunk([], llm)
    assert result == []


@pytest.mark.asyncio
async def test_reduce_sector():
    expected = SectorReduceOutput(
        summary="반도체 강세",
        key_developments=["HBM 수요 증가"],
        connected_themes=["AI 서버 수혜"],
        market_direction="Bull",
    )
    llm = make_llm_mock(expected)
    issues = [make_issue()]
    result = await reduce_sector("반도체/하드웨어", issues, llm)
    assert result.market_direction == "Bull"


def test_extract_top_keywords():
    issues = [
        make_issue(keywords=["HBM", "반도체", "AI"]),
        make_issue(keywords=["HBM", "엔비디아"]),
    ]
    top = _extract_top_keywords(issues, top_n=3)
    assert top[0] == "HBM"  # 가장 빈번
    assert len(top) <= 3


@pytest.mark.asyncio
async def test_analyze_messages_end_to_end():
    map_output = MapChunkOutput(issues=[make_issue()])
    reduce_output = SectorReduceOutput(
        summary="반도체 강세", key_developments=["HBM"],
        connected_themes=[], market_direction="Bull",
    )
    wrapup_output = DailyReportOutput(
        market_narrative="오늘 시장의 핵심은 반도체입니다.",
        key_themes=[KeyTheme(
            title="HBM 수요 급증", description="...",
            impact_points=["수혜"], action_level="즉시대응",
            connected_themes=[],
        )],
        major_issues=["SK하이닉스 HBM 수요 급증"],
    )

    call_count = 0

    async def mock_ainvoke(_):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return map_output
        elif call_count == 2:
            return reduce_output
        return wrapup_output

    chain_mock = MagicMock()
    chain_mock.ainvoke = mock_ainvoke
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=chain_mock)

    messages = [{"channel_name": "ch1", "message_id": "1", "content": "HBM 수요 증가"}]
    result = await analyze_messages(messages, llm)
    assert "반도체" in result.market_narrative
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/llm/test_daily_report_analyzer.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: analyzer 구현**

```python
# src/llm/daily_report_analyzer.py
"""Daily Report LLM Map-Reduce-Wrapup 분석기."""
import logging
from collections import Counter

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from src.llm.daily_report_models import (
    DailyReportOutput,
    MapChunkOutput,
    MappedIssue,
    SectorReduceOutput,
)

logger = logging.getLogger(__name__)

_MAP_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "당신은 한국 금융시장 전문 애널리스트입니다. 텔레그램 메시지에서 주요 시장 이슈를 추출합니다."),
    ("user", """다음 텔레그램 메시지들에서 주요 시장 이슈를 추출하세요.

메시지:
{chunk_text}

각 이슈에 대해 다음을 추출하세요:
- sector: [거시경제/매크로, 반도체/하드웨어, 소프트웨어/인터넷/AI, 에너지/원자재, 금융/은행, 헬스케어/바이오, 산업재/제조, 소비재/유통] 중 하나
- category: "Company"(특정 기업), "Industry"(산업 전반), "Macroeconomy"(거시경제) 중 하나
- topic: 기업명, 산업명, 이슈명
- summary: 2-3문장 한국어 요약
- impact: 시장 영향 한 줄 (한국어)
- market_impact: "Bull", "Bear", "Neutral" 중 하나
- keywords: 핵심 키워드 최대 5개
- message_refs: 관련 메시지 레퍼런스 (channel_name:message_id 형식)

중요하지 않거나 광고성 메시지는 제외하세요. 이슈가 없으면 빈 리스트를 반환하세요."""),
])

_REDUCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "당신은 한국 금융시장 섹터 전문 애널리스트입니다."),
    ("user", """다음 {sector} 섹터 이슈들을 종합 분석하세요.

이슈 목록:
{issues_text}

다음을 제공하세요:
- summary: 섹터 종합 요약 (한국어, 3-4문장)
- key_developments: 주요 동향 3-5가지 (한국어 리스트)
- connected_themes: 다른 섹터와의 연결 고리 (예: "금리 인상 → 성장주 압박")
- market_direction: "Bull", "Bear", "Neutral", "Mixed" 중 하나"""),
])

_WRAPUP_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "당신은 한국 금융시장 수석 애널리스트입니다."),
    ("user", """오늘의 시장 분석을 종합하여 핵심 인사이트를 도출하세요.

섹터별 요약:
{sector_summaries}

주요 키워드: {keywords}

다음을 제공하세요:
- market_narrative: 오늘 시장의 전체 스토리 (한국어, 3-4문장, "오늘 시장의 핵심은..." 으로 시작)
- key_themes: 가장 중요한 테마 5가지
  - title: 테마 제목
  - description: 2-3문장 설명
  - impact_points: 핵심 포인트 2-4개
  - action_level: "관심", "모니터", "즉시대응" 중 하나
  - connected_themes: 연관 테마들
- major_issues: 오늘 반드시 알아야 할 이슈 7가지 (한국어 짧은 문장)"""),
])


async def map_chunk(messages: list[dict], llm: BaseChatModel) -> list[MappedIssue]:
    """50개 메시지 청크에서 시장 이슈 추출."""
    if not messages:
        return []

    chunk_text = "\n\n".join(
        f"[{m.get('channel_name', 'unknown')} ({m.get('message_id', '')})] "
        f"{m.get('content', '').strip()}"
        for m in messages
        if m.get("content", "").strip()
    )

    if not chunk_text.strip():
        return []

    chain = _MAP_PROMPT | llm.with_structured_output(MapChunkOutput)
    try:
        result: MapChunkOutput = await chain.ainvoke({"chunk_text": chunk_text})
        return result.issues
    except Exception as e:
        logger.warning("map_chunk 실패: %s", e)
        return []


async def reduce_sector(
    sector: str, issues: list[MappedIssue], llm: BaseChatModel
) -> SectorReduceOutput:
    """섹터별 이슈를 통합 분석."""
    issues_text = "\n\n".join(
        f"- [{i.category}] {i.topic}: {i.summary} (영향방향: {i.market_impact})"
        for i in issues
    )

    chain = _REDUCE_PROMPT | llm.with_structured_output(SectorReduceOutput)
    try:
        return await chain.ainvoke({"sector": sector, "issues_text": issues_text})
    except Exception as e:
        logger.warning("reduce_sector[%s] 실패: %s", sector, e)
        return SectorReduceOutput(
            summary="분석 실패",
            key_developments=[],
            connected_themes=[],
            market_direction="Neutral",
        )


async def wrapup(
    sector_outputs: dict[str, SectorReduceOutput],
    top_keywords: list[str],
    llm: BaseChatModel,
) -> DailyReportOutput:
    """섹터별 분석을 종합하여 최종 리포트 생성."""
    sector_summaries = "\n\n".join(
        f"## {sector}\n{output.summary}\n"
        f"주요 동향: {', '.join(output.key_developments[:3])}"
        for sector, output in sector_outputs.items()
    )

    chain = _WRAPUP_PROMPT | llm.with_structured_output(DailyReportOutput)
    return await chain.ainvoke({
        "sector_summaries": sector_summaries,
        "keywords": ", ".join(top_keywords[:10]),
    })


def _extract_top_keywords(issues: list[MappedIssue], top_n: int = 10) -> list[str]:
    """이슈 키워드 빈도 상위 추출."""
    counter: Counter = Counter()
    for issue in issues:
        for kw in issue.keywords:
            normalized = kw.strip().lower()
            if normalized:
                counter[normalized] += 1
    return [kw for kw, _ in counter.most_common(top_n)]


async def analyze_messages(
    messages: list[dict], llm: BaseChatModel, chunk_size: int = 50
) -> DailyReportOutput:
    """전체 메시지 Map-Reduce-Wrapup 분석.
    
    Args:
        messages: 텔레그램 메시지 리스트
        llm: LangChain BaseChatModel
        chunk_size: Map 단계 청크 크기 (기본 50)
        
    Returns:
        DailyReportOutput
    """
    from src.providers.telegram_loader import chunk_messages

    # Map Phase
    chunks = chunk_messages(messages, chunk_size)
    all_issues: list[MappedIssue] = []
    for i, chunk in enumerate(chunks):
        logger.debug("Map [%d/%d]", i + 1, len(chunks))
        issues = await map_chunk(chunk, llm)
        all_issues.extend(issues)

    logger.info("Map 완료: 이슈 %d개 추출", len(all_issues))

    if not all_issues:
        return DailyReportOutput(
            market_narrative="오늘 수집된 메시지에서 주요 이슈를 찾지 못했습니다.",
            key_themes=[],
            major_issues=[],
        )

    # Filter Phase
    top_keywords = _extract_top_keywords(all_issues)

    # Reduce Phase (섹터별)
    from collections import defaultdict
    by_sector: dict[str, list[MappedIssue]] = defaultdict(list)
    for issue in all_issues:
        by_sector[issue.sector].append(issue)

    sector_outputs: dict[str, SectorReduceOutput] = {}
    for sector, sector_issues in by_sector.items():
        logger.debug("Reduce [%s]: %d개 이슈", sector, len(sector_issues))
        sector_outputs[sector] = await reduce_sector(sector, sector_issues, llm)

    # Wrapup Phase
    logger.info("Wrapup 시작 (%d개 섹터)", len(sector_outputs))
    return await wrapup(sector_outputs, top_keywords, llm)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/llm/test_daily_report_analyzer.py -v
```

Expected: 5개 테스트 모두 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/llm/daily_report_analyzer.py tests/llm/test_daily_report_analyzer.py
git commit -m "feat: add DailyReport LLM analyzer (Map-Reduce-Wrapup pipeline)"
```

---

### Task 10: Daily Report V2 파이프라인

**Files:**
- Create: `src/pipelines/daily_report_v2.py`

- [ ] **Step 1: 파이프라인 작성**

```python
# src/pipelines/daily_report_v2.py
"""Daily Report V2 파이프라인 — Telegram + 뉴스 + 매크로 + 테마 + 특징주 통합."""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


class DailyReportV2Pipeline:
    """매일 시장 리포트 생성 파이프라인.
    
    데이터 수집 (병렬):
        - Telegram CSV 로드 + LLM Map-Reduce 분석
        - 매크로 지표 (VIX, Fear&Greed, WTI, 금리, DXY)
        - Naver 상위 테마 + 구성 종목
        - Naver 수급 데이터 (외인/기관 순매수)
        - 거래량/상승 상위 종목
    """

    def __init__(
        self,
        llm: BaseChatModel,
        output_dir: str = "data",
    ) -> None:
        self._llm = llm
        self._output_dir = output_dir

    async def run(self, target_date: date | None = None) -> dict:
        """Daily Report 실행.
        
        Args:
            target_date: 분석 날짜 (기본: 전날 KST)
            
        Returns:
            dict with keys:
                date, macro, telegram_analysis, themes,
                featured_stocks, errors
        """
        if target_date is None:
            target_date = (datetime.now(KST) - timedelta(days=1)).date()

        date_str = target_date.isoformat()
        logger.info("DailyReportV2 시작: %s", date_str)

        # 병렬 데이터 수집
        macro_task = asyncio.create_task(self._collect_macro())
        themes_task = asyncio.create_task(self._collect_themes())
        flow_task = asyncio.create_task(self._collect_flow())
        featured_task = asyncio.create_task(self._collect_featured())
        telegram_task = asyncio.create_task(self._analyze_telegram(date_str))

        results = await asyncio.gather(
            macro_task, themes_task, flow_task, featured_task, telegram_task,
            return_exceptions=True,
        )

        macro, themes, flow, featured, telegram_analysis = results
        errors = []

        for name, result in zip(
            ["macro", "themes", "flow", "featured", "telegram"], results
        ):
            if isinstance(result, Exception):
                logger.error("%s 수집 실패: %s", name, result)
                errors.append(f"{name}: {result}")

        return {
            "date": date_str,
            "macro": macro if not isinstance(macro, Exception) else None,
            "telegram_analysis": (
                telegram_analysis
                if not isinstance(telegram_analysis, Exception)
                else None
            ),
            "themes": themes if not isinstance(themes, Exception) else [],
            "flow": flow if not isinstance(flow, Exception) else {},
            "featured_stocks": featured if not isinstance(featured, Exception) else [],
            "errors": errors,
        }

    async def _collect_macro(self):
        from src.tools.macro import MacroTool
        tool = MacroTool()
        result = await tool.execute()
        if not result.success:
            raise RuntimeError(f"macro 실패: {result.error}")
        return result.data

    async def _collect_themes(self) -> list[dict]:
        from src.providers.naver import NaverProvider
        naver = NaverProvider()
        return await naver.get_themes(top_n=10)

    async def _collect_flow(self) -> dict:
        from src.providers.naver import NaverProvider
        naver = NaverProvider()
        return await naver.get_investor_flow(top_n=20)

    async def _collect_featured(self) -> list[dict]:
        """거래량 상위 + 외인/기관 동시 순매수 Smart Money 필터."""
        from src.providers.naver import NaverProvider
        naver = NaverProvider()

        volume_rank, flow = await asyncio.gather(
            naver.get_volume_ranking(top_n=50),
            naver.get_investor_flow(top_n=50),
        )

        # 종목 코드 기준 flow 인덱스 구축
        flow_index: dict[str, dict] = {}
        for market_items in flow.values():
            for item in market_items:
                flow_index[item["code"]] = item

        featured = []
        for stock in volume_rank:
            code = stock.get("code", "")
            flow_data = flow_index.get(code, {})
            foreign_net = flow_data.get("foreign_net", 0)
            institution_net = flow_data.get("institution_net", 0)
            smart_money = foreign_net > 0 and institution_net > 0

            featured.append({
                **stock,
                "foreign_net": foreign_net,
                "institution_net": institution_net,
                "smart_money": smart_money,
            })

        # Smart Money 우선, 그 다음 거래량 순
        featured.sort(key=lambda x: (x["smart_money"], x.get("volume", 0)), reverse=True)
        return featured[:20]

    async def _analyze_telegram(self, date_str: str):
        from src.providers.telegram_loader import TelegramLoader
        from src.llm.daily_report_analyzer import analyze_messages

        loader = TelegramLoader(self._output_dir)
        messages = loader.load_date(date_str)

        if not messages:
            logger.warning("Telegram 메시지 없음 (%s). fetch 먼저 실행하세요.", date_str)
            return None

        logger.info("Telegram 메시지 %d건 분석 시작", len(messages))
        return await analyze_messages(messages, self._llm)


def format_daily_report_output(result: dict) -> str:
    """파이프라인 결과 → 마크다운 문자열 변환."""
    lines = [f"# 📊 Daily Report — {result.get('date', '날짜 없음')}\n"]

    # 매크로 스냅샷
    macro = result.get("macro")
    if macro:
        lines.append("## 매크로 스냅샷\n")
        lines.append("| 지표 | 값 | 변동 |")
        lines.append("|------|-----|------|")
        lines.append(f"| VIX | {macro.vix:.1f} | {macro.vix_change:+.2f} |")
        lines.append(f"| Fear & Greed | {macro.fear_greed} | {macro.fear_greed_label} |")
        lines.append(f"| WTI | {macro.wti:.2f} | {macro.wti_change:+.2f} |")
        lines.append(f"| US 10Y | {macro.us_10y:.2f}% | — |")
        lines.append(f"| DXY | {macro.dxy:.2f} | {macro.dxy_change:+.2f} |")
        lines.append("")

    # 시장 내러티브 + 핵심 테마
    analysis = result.get("telegram_analysis")
    if analysis:
        lines.append("## 오늘의 시장 스토리\n")
        lines.append(f"{analysis.market_narrative}\n")

        if analysis.key_themes:
            lines.append("## 핵심 테마\n")
            for i, theme in enumerate(analysis.key_themes, 1):
                action_emoji = {"즉시대응": "🔴", "모니터": "🟡", "관심": "🟢"}.get(
                    theme.action_level, "⚪"
                )
                lines.append(f"### {i}. {action_emoji} {theme.title} `{theme.action_level}`")
                lines.append(f"{theme.description}")
                for point in theme.impact_points:
                    lines.append(f"- {point}")
                lines.append("")

        if analysis.major_issues:
            lines.append("## 오늘의 주요 이슈\n")
            for issue in analysis.major_issues:
                lines.append(f"- {issue}")
            lines.append("")
    else:
        lines.append("> ⚠️ Telegram 데이터 없음. `jarvis telegram fetch` 먼저 실행하세요.\n")

    # 테마별 시장 소식
    themes = result.get("themes", [])
    if themes:
        lines.append("## 테마별 시장 소식\n")
        for theme in themes[:5]:
            lines.append(
                f"**{theme.get('name', '')}** "
                f"(등락률: {theme.get('change_rate', 0):+.1f}%)"
            )

    # Smart Money 특징주
    featured = result.get("featured_stocks", [])
    smart_money = [s for s in featured if s.get("smart_money")]
    if smart_money:
        lines.append("\n## Smart Money 특징주 (외인+기관 동시 순매수)\n")
        lines.append("| 종목 | 가격 | 등락률 | 외인순매수 | 기관순매수 |")
        lines.append("|------|------|--------|-----------|-----------|")
        for s in smart_money[:10]:
            lines.append(
                f"| {s.get('name', '')}({s.get('code', '')}) "
                f"| {s.get('price', 0):,} "
                f"| {s.get('change_pct', 0):+.1f}% "
                f"| {s.get('foreign_net', 0)/1e8:+.0f}억 "
                f"| {s.get('institution_net', 0)/1e8:+.0f}억 |"
            )
        lines.append("")

    # 에러 요약
    errors = result.get("errors", [])
    if errors:
        lines.append("\n---\n⚠️ 수집 오류:")
        for err in errors:
            lines.append(f"- {err}")

    return "\n".join(lines)
```

- [ ] **Step 2: 동작 확인 (mock 데이터 없이 구조만)**

```bash
uv run python -c "
from src.pipelines.daily_report_v2 import DailyReportV2Pipeline, format_daily_report_output
print('import OK')
"
```

Expected: `import OK`

- [ ] **Step 3: 커밋**

```bash
git add src/pipelines/daily_report_v2.py
git commit -m "feat: add DailyReportV2Pipeline with parallel data collection and formatter"
```

---

### Task 11: Daily Report CLI 커맨드

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: `daily-report` 커맨드 추가**

`src/cli/main.py`에 기존 `report` 커맨드 아래에 추가:

```python
@app.command("daily-report")
def daily_report_v2(
    date: str = typer.Option(
        None,
        "--date",
        "-d",
        help="분석 날짜 (YYYY-MM-DD). 기본값: 전날",
    ),
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM 제공자"
    ),
):
    """Daily Market Report — Telegram + 뉴스 + 매크로 + 테마 + 특징주 통합 리포트."""
    import asyncio
    from datetime import date as date_type
    from src.llm.provider import LLMProvider
    from src.core.config import load_config
    from src.pipelines.daily_report_v2 import DailyReportV2Pipeline, format_daily_report_output

    cfg = load_config()
    target: date_type | None = None

    if date:
        try:
            target = date_type.fromisoformat(date)
        except ValueError:
            console.print(f"[red]날짜 형식 오류: {date} (YYYY-MM-DD 형식 사용)[/red]")
            raise typer.Exit(1)

    display_date = str(target) if target else "전날"
    console.print(f"[bold]Daily Report 생성 중 ({display_date})...[/bold]\n")

    try:
        llm = LLMProvider.create(provider=provider)
        pipeline = DailyReportV2Pipeline(
            llm=llm,
            output_dir=cfg.telegram.output_dir,
        )
        result = asyncio.run(pipeline.run(target))
        output = format_daily_report_output(result)
        console.print(Markdown(output))

        if result.get("errors"):
            console.print("\n[yellow]⚠️ 일부 데이터 수집 실패 (위 에러 참조)[/yellow]")

    except Exception as e:
        console.print(f"[red]Daily Report 오류: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 2: CLI 등록 확인**

```bash
uv run jarvis daily-report --help
```

Expected:
```
Usage: jarvis daily-report [OPTIONS]
  Daily Market Report — Telegram + 뉴스 + 매크로 + 테마 + 특징주 통합 리포트.

Options:
  -d, --date TEXT        분석 날짜 (YYYY-MM-DD). 기본값: 전날
  -p, --provider TEXT    LLM 제공자  [default: openai]
```

- [ ] **Step 3: 전체 테스트 실행**

```bash
uv run pytest tests/providers/test_telegram_state.py tests/providers/test_telegram_storage.py tests/providers/test_telegram_loader.py tests/providers/test_telegram_collector.py tests/llm/test_daily_report_analyzer.py -v
```

Expected: 전체 PASS.

- [ ] **Step 4: 커밋**

```bash
git add src/cli/main.py
git commit -m "feat: add jarvis daily-report CLI command (Daily Report V2)"
```

---

## Self-Review

**스펙 커버리지 확인:**

| 스펙 요구사항 | 구현 태스크 |
|---|---|
| `jarvis telegram fetch [DATE]` | Task 6 |
| `jarvis telegram catch-up` | Task 6 |
| config.yaml 채널 관리 (id + include/exclude) | Task 1, 4 |
| CSV 저장 (YYYY-MM/YYYY-MM-DD-{channel}.csv) | Task 3 |
| monitor_state.json 상태 관리 | Task 2 |
| 중복 방지 (message_id 풀스캔) | Task 3 |
| `jarvis daily-report` 커맨드 | Task 11 |
| 매크로 스냅샷 (기존 MacroTool 활용) | Task 10 |
| Telegram Map-Reduce LLM 분석 | Task 8, 9 |
| Naver 테마 동적 감지 | Task 7, 10 |
| 수급 분석 (외인/기관 순매수) | Task 7, 10 |
| Smart Money 특징주 필터링 | Task 10 |
| 시장 내러티브 생성 | Task 9 (market_narrative) |
| 테마별 액션 레벨 (관심/모니터/즉시대응) | Task 8 (KeyTheme.action_level) |
| 텔레그램 사전 언급 여부 | ⚠️ 미구현 — 현재 플랜에서 제외, 후속 개선 |

**미디어 다운로드**: 스펙에 언급됐으나 YAGNI 원칙으로 이번 플랜에서 제외. `_build_message_data`에서 `media_info=None` 처리로 확장 여지 남김.

**포트폴리오 연계 섹션**: 스펙의 "포트폴리오 연계" 제안은 Portfolio 점검 파이프라인 구현 후 추가.
