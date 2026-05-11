"""Tests for publish_report helper.

Tests telegram send and git commit+push via in-process mocking.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trader.helpers.publish_report import main


def test_happy_path(tmp_path, monkeypatch):
    """Telegram + git succeed, exit 0, files written."""
    # Setup
    report_path = tmp_path / "report.md"
    report_text = "# Portfolio Report\n\nDATA\n"
    report_path.write_text(report_text)

    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("trader.config.settings.reports_dir", reports_dir)

    # Mock telegram.send
    mock_telegram_send = MagicMock(return_value=True)
    monkeypatch.setattr("trader.publish.telegram.send", mock_telegram_send)

    # Mock subprocess.run to track git calls
    git_calls = []

    def fake_run(args, **kwargs):
        git_calls.append(args)
        res = MagicMock()
        res.returncode = 0
        res.stdout = ""
        res.stderr = ""
        return res

    monkeypatch.setattr("subprocess.run", fake_run)

    # Act
    rc = main(["--report", str(report_path), "--run-date", "2026-04-28"])

    # Assert
    assert rc == 0
    assert mock_telegram_send.called
    assert mock_telegram_send.call_args[0][0] == report_text
    assert (reports_dir / "2026-04-28.md").exists()
    assert (reports_dir / "2026-04-28.md").read_text() == report_text
    # Check git calls: add, commit, fetch, rebase, push to main
    assert ["git", "add", "data/", "reports/"] in git_calls
    assert any("commit" in call for call in git_calls)
    assert ["git", "fetch", "origin", "main"] in git_calls
    assert ["git", "rebase", "origin/main"] in git_calls
    assert ["git", "push", "origin", "HEAD:main"] in git_calls


def test_telegram_failure_non_fatal(tmp_path, monkeypatch):
    """Telegram.send raises; helper logs but continues to commit+push; exit 0."""
    # Setup
    report_path = tmp_path / "report.md"
    report_text = "# Report\n"
    report_path.write_text(report_text)

    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("trader.config.settings.reports_dir", reports_dir)

    # Mock telegram.send to raise
    def raise_error(text):
        raise Exception("Telegram API error")

    monkeypatch.setattr("trader.publish.telegram.send", raise_error)

    # Mock subprocess.run
    def fake_run(args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        res.stdout = ""
        res.stderr = ""
        return res

    monkeypatch.setattr("subprocess.run", fake_run)

    # Act
    rc = main(["--report", str(report_path), "--run-date", "2026-04-28"])

    # Assert: exit 0 even though telegram failed
    assert rc == 0
    # Report still written
    assert (reports_dir / "2026-04-28.md").exists()


def test_name_flag_overrides_filename(tmp_path, monkeypatch):
    """--name lets the rebalance pipeline write a distinct file so the daily
    report (same RUN_DATE) does not collide and lose its push notification."""
    report_path = tmp_path / "report-rebalance.md"
    report_text = "# Weekly Rebalance Report\n"
    report_path.write_text(report_text)

    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("trader.config.settings.reports_dir", reports_dir)
    monkeypatch.setattr("trader.publish.telegram.send", MagicMock(return_value=True))
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    rc = main([
        "--report", str(report_path),
        "--run-date", "2026-05-01",
        "--name", "2026-05-01-rebalance",
        "--no-telegram",
    ])
    assert rc == 0
    assert (reports_dir / "2026-05-01-rebalance.md").exists()
    assert not (reports_dir / "2026-05-01.md").exists()


def test_git_push_failure_returns_nonzero(tmp_path, monkeypatch):
    """Git push fails (rc=1); helper exits 1."""
    # Setup
    report_path = tmp_path / "report.md"
    report_text = "# Report\n"
    report_path.write_text(report_text)

    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("trader.config.settings.reports_dir", reports_dir)

    # Mock telegram.send
    monkeypatch.setattr("trader.publish.telegram.send", MagicMock(return_value=True))

    # Mock subprocess.run: push returns non-zero
    def fake_run(args, **kwargs):
        res = MagicMock()
        # push fails
        if args[:2] == ["git", "push"]:
            res.returncode = 1
        else:
            res.returncode = 0
        res.stdout = ""
        res.stderr = ""
        return res

    monkeypatch.setattr("subprocess.run", fake_run)

    # Act
    rc = main(["--report", str(report_path), "--run-date", "2026-04-28"])

    # Assert
    assert rc == 1
