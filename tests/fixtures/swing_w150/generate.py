"""SWING_W150 v3 정답지 생성기. 테스트 중에는 실행하지 않는다.

기준 동작은 백테스트 스크립트(`src/backtest/universe_transition.simulate`)에 jarvis 지표를 넣은 판
(`universe_jarvis_indicators.prepare_jarvis`)이다. 엔진이 이 결과와 같은 매매를 내야 한다.

사용:
    BT_LONG_CACHE=<가격 캐시 폴더> uv run python tests/fixtures/swing_w150/generate.py
캐시에서 원본 OHLCV를 이 폴더로 복사한 뒤, 복사본만으로 매매 목록을 만든다.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src" / "backtest"))

import pandas as pd  # noqa: E402
from universe_jarvis_indicators import prepare_jarvis  # noqa: E402
from universe_transition import simulate  # noqa: E402
from universe_validate import BASE, CLIMAX  # noqa: E402


TICKERS = ["COIN", "AMAT", "PYPL", "UPST"]


def load(ticker: str) -> pd.DataFrame:
    return pd.read_csv(HERE / f"{ticker}.csv", parse_dates=["Date"]).set_index("Date")


def main() -> None:
    cache = os.environ.get("BT_LONG_CACHE")
    for tk in TICKERS:
        if cache:
            shutil.copyfile(Path(cache) / f"{tk}.csv", HERE / f"{tk}.csv")
        trades = simulate(prepare_jarvis(load(tk), None), **BASE, **CLIMAX)
        rows = [
            {
                "kind": x["kind"],
                "entry_date": x["entry_date"].isoformat(),
                "exit_date": x["exit_date"].isoformat(),
                "entry": float(x["entry"]),
                "exit": float(x["exit"]),
                "R": float(x["R"]),
                "why": x["why"],
                "n_partial": int(x["n_partial"]),
            }
            for x in trades
        ]
        (HERE / f"{tk}.trades.json").write_text(json.dumps(rows, indent=1) + "\n")
        print(f"{tk}: {len(rows)}건")


if __name__ == "__main__":
    main()
