"""NH 조회 성공 후 보유 사실만 갱신하고 사용자 설정은 보존한다."""

import fcntl
import os
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from ruamel.yaml import YAML
from ruamel.yaml.events import AliasEvent
from ruamel.yaml.nodes import MappingNode, SequenceNode

from src.providers.nhplug import NHBalanceSnapshot
from src.tools.playbook.holdings import HoldingsConfig


def _ticker(value: str) -> str:
    return value.upper().removesuffix(".KS").removesuffix(".KQ")


def _has_merge(node) -> bool:
    if isinstance(node, MappingNode):
        return any(
            key.tag == "tag:yaml.org,2002:merge" or _has_merge(value) for key, value in node.value
        )
    if isinstance(node, SequenceNode):
        return any(_has_merge(value) for value in node.value)
    return False


def save_broker_holdings(
    config: HoldingsConfig,
    snapshot: NHBalanceSnapshot,
    original: bytes | None,
    path: str | Path = "playbook.yaml",
) -> None:
    """저장 구간을 직렬화하고 같은 원문에서 시작한 경쟁 갱신을 거부한다."""
    target = Path(path)
    private_dir = target.parent / "data/broker"
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        private_dir / "playbook-sync.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        _save_broker_holdings(config, snapshot, original, target)


def _save_broker_holdings(
    config: HoldingsConfig,
    snapshot: NHBalanceSnapshot,
    original: bytes | None,
    target: Path,
) -> None:
    """주석·사용자 필드 보존, 원문 백업, 충돌 확인 후 원자적으로 교체한다."""

    def unchanged():
        if target.is_symlink() or (target.read_bytes() if target.exists() else None) != original:
            raise ValueError(
                "playbook.yaml이 조회 중 변경되었습니다. 파일을 확인한 뒤 다시 실행하세요"
            )

    unchanged()
    if original is not None:
        text = original.decode("utf-8")
        if any(isinstance(event, AliasEvent) for event in YAML().parse(text)) or _has_merge(
            YAML().compose(text)
        ):
            raise ValueError(
                "playbook.yaml에 YAML alias/merge가 있어 자동 갱신을 중단했습니다. 참조 설정을 개별 값으로 작성하세요"
            )
    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(original.decode("utf-8")) if original is not None else {}
    data = data or {}
    settings = data.get("holding_settings")
    if settings is None:
        settings = data["holding_settings"] = {}
    if not isinstance(settings, dict):
        raise ValueError("playbook.yaml holding_settings는 종목별 설정이어야 합니다")
    previous = {_ticker(str(row["ticker"])): row for row in data.get("holdings") or []}
    for ticker, row in previous.items():
        saved = deepcopy(row)
        for field in ("ticker", "quantity", "avg_price"):
            saved.pop(field, None)
        if saved:
            settings[ticker] = saved
        else:
            settings.pop(ticker, None)
    holdings = []
    for holding in config.holdings:
        ticker = _ticker(holding.ticker)
        row = deepcopy(previous.get(ticker, settings.get(ticker, {})))
        row.update(
            ticker=ticker,
            quantity=int(holding.quantity)
            if holding.quantity == int(holding.quantity)
            else str(holding.quantity),
            avg_price=holding.avg_price,
        )
        holdings.append(row)
    data["holdings"] = holdings
    broker = data.get("broker") or {}
    data["broker"] = broker
    broker.update(
        provider="nh", account_id=snapshot.account_id, synced_at=snapshot.as_of.isoformat()
    )
    buffer = StringIO()
    yaml.dump(data, buffer)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=".playbook-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(buffer.getvalue())
            stream.flush()
            os.fsync(stream.fileno())
        unchanged()
        if original is not None:
            backup_dir = target.parent / "data/broker/playbook-backups"
            backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            backup = backup_dir / f"{uuid4().hex}.yaml"
            descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(original)
        unchanged()
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
