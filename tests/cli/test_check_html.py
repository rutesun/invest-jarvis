"""Offline CLI output and atomic replacement contracts."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

import src.cli.main as cli


runner = CliRunner()


def success(ticker):
    return {"success": True, "ticker": ticker, "price": 100.0, "change_pct": 1.0, "total_score": 0}


def fake_checks(monkeypatch, results=None):
    calls = []

    async def run(queries, **kwargs):
        calls.append((queries, kwargs))
        return results or [success(t) for t in queries]

    monkeypatch.setattr(cli, "run_quick_checks", run)
    return calls


def test_default_check_does_not_generate_or_save_html(monkeypatch, tmp_path):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)
    output = runner.invoke(cli.app, ["check", "ALAB"])
    assert output.exit_code == 0 and "100.00" in output.stdout
    assert calls == [(["ALAB"], {})] and list(tmp_path.iterdir()) == []


def test_bare_html_saves_unique_reports_and_prints_absolute_file_links(monkeypatch, tmp_path):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    outputs = [runner.invoke(cli.app, ["check", "ALAB", "--html"]) for _ in range(2)]

    assert all(output.exit_code == 0 for output in outputs)
    reports = sorted((tmp_path / "tmp" / "reports").glob("check-*.html"))
    assert len(reports) == 2
    assert all('<html lang="ko">' in report.read_text("utf-8") for report in reports)
    for report in reports:
        assert any(str(report) in output.stdout for output in outputs)
        assert any(report.as_uri() in output.stdout for output in outputs)
    assert calls == [(["ALAB"], {"include_chart": True})] * 2


@pytest.mark.parametrize("options", [["--detail-history"], ["--detail-strategy"], ["--force"]])
def test_bare_html_does_not_consume_following_options(monkeypatch, tmp_path, options):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    output = runner.invoke(cli.app, ["check", "ALAB", "--html", *options])

    assert output.exit_code == 0
    assert len(list((tmp_path / "tmp" / "reports").glob("check-*.html"))) == 1
    assert calls == [(["ALAB"], {"include_chart": True})]


@pytest.mark.parametrize("equals", [False, True])
def test_explicit_path_preserves_unicode_spaces_and_prints_encoded_uri(
    monkeypatch, tmp_path, equals
):
    fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)
    relative_path = "reports/한글 보고서.html"
    args = [f"--html={relative_path}"] if equals else ["--html", relative_path]

    output = runner.invoke(cli.app, ["check", "ALAB", *args])

    target = tmp_path / relative_path
    assert output.exit_code == 0 and target.is_file()
    assert str(target) in output.stdout
    assert target.as_uri() in output.stdout
    assert "%ED%95%9C%EA%B8%80%20%EB%B3%B4%EA%B3%A0%EC%84%9C.html" in output.stdout
    assert not (tmp_path / "tmp").exists()


def test_html_path_with_emoji_alias_is_printed_literally(monkeypatch, tmp_path):
    fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "reports" / ":smile:.html"

    output = runner.invoke(cli.app, ["check", "ALAB", "--html", "reports/:smile:.html"])

    assert output.exit_code == 0 and target.is_file()
    assert f"HTML 저장: {target}" in output.stdout
    assert f"HTML 링크: {target.as_uri()}" in output.stdout


@pytest.mark.parametrize("path", ["ALAB", "-"])
def test_html_value_without_extension_remains_an_explicit_path(monkeypatch, tmp_path, path):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    output = runner.invoke(cli.app, ["check", "MSFT", "--html", path])

    assert output.exit_code == 0 and (tmp_path / path).is_file()
    assert calls == [(["MSFT"], {"include_chart": True})]
    assert not (tmp_path / "tmp").exists()


def test_html_after_delimiter_is_a_query_and_does_not_create_files(monkeypatch, tmp_path):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    output = runner.invoke(cli.app, ["check", "--", "ALAB", "--html"])

    assert output.exit_code == 0
    assert calls == [(["ALAB", "--html"], {})]
    assert list(tmp_path.iterdir()) == []


def test_bare_html_before_delimiter_preserves_following_queries(monkeypatch, tmp_path):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    output = runner.invoke(cli.app, ["check", "ALAB", "--html", "--", "--html", "--force"])

    assert output.exit_code == 0
    assert calls == [(["ALAB", "--html", "--force"], {"include_chart": True})]
    assert len(list((tmp_path / "tmp" / "reports").glob("check-*.html"))) == 1


def test_bare_html_does_not_hide_unknown_options(monkeypatch, tmp_path):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    output = runner.invoke(cli.app, ["check", "ALAB", "--html", "--unknown"])

    assert output.exit_code == 2 and calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("args", [["--help"], ["ALAB", "--html", "--help"]])
def test_help_describes_optional_path_and_default_without_running_checks(
    monkeypatch, tmp_path, args
):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    output = runner.invoke(cli.app, ["check", *args])

    assert output.exit_code == 0 and calls == []
    assert "[PATH]" in output.stdout and "tmp/reports/check-<time>-<id>.html" in output.stdout
    assert list(tmp_path.iterdir()) == []


def test_auto_path_never_overwrites_a_collision_even_with_force(monkeypatch, tmp_path):
    calls = fake_checks(monkeypatch)
    monkeypatch.chdir(tmp_path)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 6, 12, 34, 56)

    monkeypatch.setattr(cli, "datetime", FixedDatetime)
    monkeypatch.setattr(cli, "uuid4", lambda: UUID(int=0))
    target = tmp_path / "tmp/reports/check-20261106-123456-00000000000000000000000000000000.html"
    target.parent.mkdir(parents=True)
    target.write_text("original")

    output = runner.invoke(cli.app, ["check", "ALAB", "--html", "--force"])

    assert output.exit_code == 2 and calls == []
    assert target.read_text() == "original"
    assert "file://" not in output.stdout


def test_html_uses_same_ordered_results_and_partial_failure_exits_one(monkeypatch, tmp_path):
    calls = fake_checks(
        monkeypatch,
        [
            success("ALAB"),
            {"success": False, "ticker": "BAD", "error": "failed"},
            success("161890.KS"),
        ],
    )
    target = tmp_path / "nested" / "check.html"
    output = runner.invoke(cli.app, ["check", "ALAB", "BAD", "161890", "--html", str(target)])
    assert output.exit_code == 1
    text = target.read_text("utf-8")
    assert text.index("ALAB") < text.index("BAD") < text.index("161890.KS")
    assert "ALAB" in output.stdout and "BAD" in output.stdout
    assert str(target) in output.stdout and target.as_uri() in output.stdout
    assert calls == [(["ALAB", "BAD", "161890"], {"include_chart": True})]


@pytest.mark.parametrize("kind", ["existing", "directory", "parent_file", "dangling_symlink"])
def test_invalid_output_path_fails_before_queries(monkeypatch, tmp_path, kind):
    calls = fake_checks(monkeypatch)
    target = tmp_path / "check.html"
    if kind == "existing":
        target.write_text("original")
    elif kind == "directory":
        target.mkdir()
    elif kind == "parent_file":
        target.write_text("parent")
        target = target / "check.html"
    else:
        target.symlink_to(tmp_path / "missing")
    output = runner.invoke(cli.app, ["check", "ALAB", "--html", str(target)])
    assert output.exit_code != 0 and calls == []


def test_force_alone_is_usage_error_before_queries(monkeypatch):
    calls = fake_checks(monkeypatch)
    output = runner.invoke(cli.app, ["check", "ALAB", "--force"])
    assert output.exit_code == 2 and calls == []


def test_force_replaces_complete_utf8_file(monkeypatch, tmp_path):
    fake_checks(monkeypatch)
    target = tmp_path / "check.html"
    target.write_text("original")
    output = runner.invoke(cli.app, ["check", "ALAB", "--html", str(target), "--force"])
    assert output.exit_code == 0 and '<html lang="ko">' in target.read_text("utf-8")
    assert list(tmp_path.iterdir()) == [target]


def test_failed_atomic_replace_preserves_original_and_reports_failure(monkeypatch, tmp_path):
    fake_checks(monkeypatch)
    target = tmp_path / "check.html"
    target.write_text("original")

    def fail(*args, **kwargs):
        raise OSError("disk write failed")

    monkeypatch.setattr(Path, "replace", fail)
    output = runner.invoke(cli.app, ["check", "ALAB", "--html", str(target), "--force"])
    assert output.exit_code == 1 and "disk write failed" in output.stdout
    assert target.read_text() == "original" and list(tmp_path.iterdir()) == [target]
    assert "HTML 저장:" not in output.stdout
    assert "file://" not in output.stdout


def test_failed_html_render_does_not_print_a_success_link(monkeypatch, tmp_path):
    fake_checks(monkeypatch)
    target = tmp_path / "check.html"

    def fail(*args, **kwargs):
        raise ValueError("render failed")

    monkeypatch.setattr("src.pipelines.check_html.render_check_html", fail)
    output = runner.invoke(cli.app, ["check", "ALAB", "--html", str(target)])

    assert output.exit_code == 1 and "render failed" in output.stdout
    assert not target.exists()
    assert "HTML 저장:" not in output.stdout and "file://" not in output.stdout


def test_file_created_during_query_is_not_overwritten_without_force(monkeypatch, tmp_path):
    target = tmp_path / "check.html"

    async def run(queries, **kwargs):
        target.write_text("created during query")
        return [success("ALAB")]

    monkeypatch.setattr(cli, "run_quick_checks", run)
    output = runner.invoke(cli.app, ["check", "ALAB", "--html", str(target)])
    assert output.exit_code == 1 and "HTML 저장 실패" in output.stdout
    assert target.read_text() == "created during query"
    assert list(tmp_path.iterdir()) == [target]
