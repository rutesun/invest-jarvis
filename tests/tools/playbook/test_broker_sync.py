"""보유 설정의 삭제 의도와 동시 저장 경계를 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from threading import Barrier, BrokenBarrierError

import pytest
import yaml

import src.tools.playbook.broker_sync as sync_module
from src.pipelines.broker_account import merge_broker_holdings
from src.tools.playbook.holdings import load_holdings
from tests.pipelines.test_broker_account import row, snapshot


BASELINE = 'holdings:\n- ticker: "005930"\n  quantity: 1\n  avg_price: 100\n  stop_price: 80\n'


def apply(path, observed):
    original = path.read_bytes()
    config = merge_broker_holdings(load_holdings(path), observed)
    sync_module.save_broker_holdings(config, observed, original, path)


def test_deleted_stop_is_not_restored_after_sale_and_reentry(tmp_path):
    path = tmp_path / "playbook.yaml"
    path.write_text(BASELINE.replace('"005930"', 'AAPL'))
    apply(path, snapshot(row("AAPL", market="US")))
    data = yaml.safe_load(path.read_text())
    data["holdings"][0].pop("stop_price")
    path.write_text(yaml.safe_dump(data))
    apply(path, snapshot(row("AAPL", market="US")))
    apply(path, snapshot())
    apply(path, snapshot(row("AAPL", market="US")))
    assert load_holdings(path).holdings[0].stop_price is None


def test_two_saves_of_the_same_original_cannot_both_replace_it(tmp_path, monkeypatch):
    path = tmp_path / "playbook.yaml"
    path.write_text(BASELINE)
    original = path.read_bytes()
    gate = Barrier(2)
    replace = sync_module.os.replace

    def synchronized_replace(source, target):
        with suppress(BrokenBarrierError):
            gate.wait(timeout=0.2)
        replace(source, target)

    monkeypatch.setattr(sync_module.os, "replace", synchronized_replace)

    def save(quantity):
        observed = snapshot(row(quantity=quantity))
        config = merge_broker_holdings(load_holdings(path), observed)
        try:
            sync_module.save_broker_holdings(config, observed, original, path)
            return "saved"
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, ("2", "3")))
    assert sorted(outcomes) == ["conflict", "saved"]


@pytest.mark.parametrize("original", [
    'defaults: &risk\n  stop_price: 80\n  note: shared\n'
    'holdings:\n- <<: *risk\n  ticker: AAPL\n  quantity: 1\n  avg_price: 100\n',
    'holdings:\n- <<: {stop_price: 80}\n  ticker: AAPL\n  quantity: 1\n  avg_price: 100\n',
])
def test_yaml_alias_is_not_flattened_or_overwritten(tmp_path, original):
    path = tmp_path / "playbook.yaml"
    path.write_text(original)
    with pytest.raises(ValueError, match="alias"):
        apply(path, snapshot(row("AAPL", market="US")))
    assert path.read_text() == original
    assert not list(tmp_path.glob(".playbook-*.tmp"))


def test_merge_marker_in_a_note_is_preserved_as_plain_text(tmp_path):
    path = tmp_path / "playbook.yaml"
    path.write_text(BASELINE + 'watchlist:\n- ticker: AAPL\n  note: "<<"\n')
    apply(path, snapshot(row()))
    assert yaml.safe_load(path.read_text())["watchlist"][0]["note"] == "<<"
