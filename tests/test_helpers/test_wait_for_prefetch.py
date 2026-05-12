"""Tests for wait_for_prefetch helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from trader.helpers.wait_for_prefetch import main


def _fake_run_factory(grep_returns: list[str]):
    """Build a subprocess.run replacement that scripts git log responses.

    grep_returns supplies stdout strings for successive `git log --grep=...`
    calls. fetch and pull always succeed silently.
    """
    grep_iter = iter(grep_returns)

    def fake_run(args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        res.stderr = ""
        if "log" in args:
            try:
                res.stdout = next(grep_iter)
            except StopIteration:
                res.stdout = ""
        else:
            res.stdout = ""
        return res

    return fake_run


def test_returns_0_when_commit_found_immediately(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        _fake_run_factory(["abc123 prefetch: daily 2026-05-12\n"]),
    )
    monkeypatch.setattr("time.sleep", MagicMock())

    rc = main([
        "--kind", "daily", "--run-date", "2026-05-12",
        "--timeout", "60", "--interval", "1",
    ])
    assert rc == 0


def test_returns_0_after_waiting(monkeypatch):
    """First two polls return empty; third returns the commit."""
    monkeypatch.setattr(
        "subprocess.run",
        _fake_run_factory(["", "", "abc123 prefetch: daily 2026-05-12\n"]),
    )
    sleep_mock = MagicMock()
    monkeypatch.setattr("time.sleep", sleep_mock)

    rc = main([
        "--kind", "daily", "--run-date", "2026-05-12",
        "--timeout", "300", "--interval", "1",
    ])
    assert rc == 0
    assert sleep_mock.call_count == 2


def test_returns_1_on_timeout(monkeypatch):
    """grep always returns empty and timeout=0 → exit 1 after the first miss."""
    monkeypatch.setattr("subprocess.run", _fake_run_factory(["", "", "", "", ""]))
    monkeypatch.setattr("time.sleep", MagicMock())

    rc = main([
        "--kind", "daily", "--run-date", "2026-05-12",
        "--timeout", "0", "--interval", "1",
    ])
    assert rc == 1


def test_grep_pattern_includes_kind_and_date(monkeypatch):
    """The grep pattern must match the prefetch workflows' commit messages."""
    captured: list[list[str]] = []

    def fake_run(args, **kwargs):
        if "log" in args:
            captured.append(list(args))
        return MagicMock(returncode=0, stdout="found\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("time.sleep", MagicMock())

    main([
        "--kind", "rebalance", "--run-date", "2026-05-15",
        "--timeout", "60",
    ])
    assert captured, "git log was never called"
    assert any("--grep=prefetch: rebalance 2026-05-15" == a for a in captured[0])
