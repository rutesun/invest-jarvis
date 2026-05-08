#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from src.pipelines.stock_report.db import apply_migrations, connect_db, resolve_db_dsn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stock report migrations.")
    parser.add_argument("--dsn", default=None, help="Postgres DSN (optional)")
    parser.add_argument(
        "--migrations-dir",
        default="migrations/stock_report",
        help="Migration directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dsn = resolve_db_dsn(args.dsn)
    migrations_dir = Path(args.migrations_dir)

    with connect_db(dsn) as conn:
        applied = apply_migrations(conn, migrations_dir)

    if applied:
        print("Applied migrations:")
        for filename in applied:
            print(f"- {filename}")
    else:
        print("No migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
