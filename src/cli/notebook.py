"""Notebook sync CLI. Default execution only reads Notion."""

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from src.integrations.notebook_notion.apply import apply_plan, write_private_json
from src.integrations.notebook_notion.plan import (
    build_plan,
    local_fingerprint,
    manifest_digest,
    projection,
    stock_groups,
)
from src.integrations.notebook_notion.remote import Remote, SyncError
from src.providers.stock_search import StockSearch, StockSearchError
from src.tools.notebook.parser import parse_notebook_dir
from src.tools.notebook.stocks import resolve_stock_entries


notebook_app = typer.Typer(help="투자 notebook의 항목별 Notion 동기화")
DEFAULT_DATABASE = "eee67e454ce4478b9f1749e8e92a1b42"


@notebook_app.callback()
def notebook():
    """항목 동기화 명령 그룹."""


def _protect_source(path, source):
    if path is not None and path.resolve().is_relative_to(source.resolve()):
        raise SyncError("원본 notebook 내부에는 artifact를 쓸 수 없습니다.")


@notebook_app.command("sync")
def sync(
    notebook_dir: Annotated[
        Path, typer.Option("--notebook-dir", help="읽기 전용 원본 경로")
    ] = Path("notebook"),
    database_id: Annotated[
        str, typer.Option("--database-id", help="대상 Database ID")
    ] = DEFAULT_DATABASE,
    offline: Annotated[bool, typer.Option("--offline", help="로컬 파싱만; 적용 불가능")] = False,
    manifest: Annotated[
        Path | None, typer.Option("--manifest", help="본문 없는 JSON 계획 저장 경로")
    ] = None,
    stock_cache: Annotated[
        Path,
        typer.Option("--stock-cache", help="종목 검색 결과 cache; offline은 조회 결과만 재사용"),
    ] = Path("data/notebook-notion/stock-search-cache.json"),
    only_key: Annotated[
        list[str] | None, typer.Option("--only-key", help="적용 후보 Key 선택; 반복 가능")
    ] = None,
    include_updates: Annotated[
        bool, typer.Option("--include-updates", help="hash가 있는 변경 항목도 후보에 포함")
    ] = False,
    apply: Annotated[
        Path | None, typer.Option("--apply", help="별도 승인 후 검토한 manifest 적용")
    ] = None,
    journal: Annotated[
        Path | None, typer.Option("--journal", help="apply 복구 journal; 필수")
    ] = None,
    resume: Annotated[
        bool, typer.Option("--resume", help="같은 manifest/journal의 부분 실패 복구")
    ] = False,
):
    """기본값: 현재 schema/page를 조회하는 remote-aware dry-run."""
    try:
        if apply and (offline or not journal or manifest or only_key or include_updates):
            raise SyncError(
                "--apply는 --journal이 필요하며 offline/manifest/후보 선택과 함께 쓸 수 없습니다."
            )
        if resume and not apply:
            raise SyncError("--resume은 --apply와 함께 사용하세요.")
        if journal and not apply:
            raise SyncError("--journal은 --apply와 함께 사용하세요.")
        for path in (manifest, journal, stock_cache):
            _protect_source(path, notebook_dir)
        if any(
            path and path.resolve() == stock_cache.resolve() for path in (manifest, journal, apply)
        ):
            raise SyncError("종목 cache와 manifest/journal은 다른 파일이어야 합니다.")
        if manifest and manifest.exists():
            raise SyncError("기존 manifest를 보존합니다. 새 --manifest 경로를 사용하세요.")
        if apply and journal.resolve() == apply.resolve():
            raise SyncError("manifest와 journal은 다른 파일이어야 합니다.")
        entries = parse_notebook_dir(notebook_dir)
        if not entries:
            raise SyncError("월별 항목이 없습니다. 원본 경로를 확인하세요.")
        reviewed = None
        if apply:
            reviewed = json.loads(apply.read_text(encoding="utf-8"))
            cache = reviewed.get("stock_resolution")
            if not cache:
                raise SyncError("검색 근거가 없는 과거 manifest입니다. 새 미리보기를 생성하세요.")
        else:
            cache = (
                json.loads(stock_cache.read_text(encoding="utf-8")) if stock_cache.exists() else {}
            )
        if not isinstance(cache, dict):
            raise SyncError("종목 검색 cache 형식이 잘못되었습니다.")
        if offline or apply:
            entries, resolution, _ = resolve_stock_entries(
                entries, cache, allow_expired=bool(apply and resume)
            )
        else:
            if not os.getenv("NOTION_TOKEN"):
                raise SyncError("NOTION_TOKEN이 설정되지 않았습니다.")
            typer.echo("종목 검색 API로 metadata를 확인합니다. 원본 본문은 전송하지 않습니다.")
            with StockSearch() as search:
                entries, resolution, updated_cache = resolve_stock_entries(
                    entries,
                    cache,
                    search=search.search,
                    on_cache_update=lambda progress: write_private_json(stock_cache, progress),
                )
            write_private_json(stock_cache, updated_cache)
        if apply and resolution["blockers"]:
            raise SyncError("종목 검색 근거가 만료되거나 미확정입니다. 새 미리보기를 생성하세요.")
        excluded = sorted(
            str(p.relative_to(notebook_dir))
            for p in notebook_dir.rglob("*.md")
            if p.parent.name not in ("trades", "thoughts", "research")
            or not re.fullmatch(r"\d{4}-\d{2}\.md", p.name)
        )
        if offline:
            if only_key or include_updates:
                raise SyncError("offline에서는 remote 적용 후보를 선택할 수 없습니다.")
            plan = {
                "mode": "OFFLINE",
                "local_count": len(entries),
                "types": dict(Counter(e.type for e in entries)),
                "local_fingerprint": local_fingerprint(entries),
                "excluded_files": excluded,
                "stock_groups": stock_groups(entries),
                "entries": [
                    {
                        "key": e.key,
                        "source_path": e.source_path,
                        "hash": projection(e, entries)[0]["Content Hash"]["rich_text"][0]["text"][
                            "content"
                        ],
                    }
                    for e in entries
                ],
            }
        else:
            token = os.getenv("NOTION_TOKEN")
            if not token:
                raise SyncError("NOTION_TOKEN이 설정되지 않았습니다.")
            if apply:
                if reviewed.get("database_id") != database_id.replace("-", ""):
                    raise SyncError("manifest의 Database ID와 CLI 대상이 다릅니다.")
                with Remote(token, write_enabled=True) as remote:
                    result = apply_plan(remote, entries, reviewed, journal, resume=resume)
                typer.echo(f"read-back 검증 완료: {len(result['completed'])}개. journal: {journal}")
                return
            with Remote(token) as remote:
                snapshot = remote.snapshot(database_id)
                plan = build_plan(
                    entries,
                    snapshot,
                    only_keys=only_key,
                    include_updates=include_updates,
                    read_blocks=remote.blocks,
                )
            plan["excluded_files"] = excluded
        plan["stock_resolution"] = resolution
        plan["blockers"] = sorted(set(plan.get("blockers", []) + resolution["blockers"]))
        if not offline:
            plan["manifest_id"] = manifest_digest(plan)
        if manifest:
            if manifest.exists():
                raise SyncError("기존 manifest를 보존합니다. 새 --manifest 경로를 사용하세요.")
            write_private_json(manifest, plan)
        typer.echo(f"로컬 항목: {len(entries)} / 제외 문서: {len(excluded)} / 실제 쓰기: 0")
        if offline:
            typer.echo("OFFLINE: remote 상태를 확인하지 않았습니다.")
        else:
            typer.echo(json.dumps(plan["counts"], ensure_ascii=False))
            typer.echo(
                f"선택 후보: {len(plan['selected'])} / 경고: {len(plan['warnings'])} / blocker: {len(plan['blockers'])}"
            )
            typer.echo(
                "schema 변경 필요"
                if "SCHEMA_CHANGE_REQUIRED" in plan["blockers"]
                else "schema 자동 변경 없음"
            )
        typer.echo(
            f"종목 분류 검토: {len(resolution['issues'])}건 / 검색 미확정 차단: {len(resolution['blockers'])}건"
        )
        if manifest:
            typer.echo(f"manifest: {manifest}")
        if plan.get("blockers"):
            raise typer.Exit(2)
    except (ValueError, OSError, KeyError, StockSearchError) as error:
        # Do not expose API bodies, credentials, or source text in tracebacks.
        # SyncError and parser diagnostics are deliberately content-free.
        message = (
            str(error)
            if isinstance(error, (SyncError, ValueError, StockSearchError))
            and not isinstance(error, json.JSONDecodeError)
            else "입력 파일 또는 응답 구조 오류"
        )
        typer.echo(f"동기화 중단: {message}", err=True)
        raise typer.Exit(1) from None
