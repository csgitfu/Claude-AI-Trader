"""Tests for publish_alert CLI."""

from __future__ import annotations

from trader.helpers import publish_alert
from trader.publish import telegram
from trader.config import settings


def test_failure_alert_sends(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send", lambda t: sent.append(t))
    rc = publish_alert.main(["--type", "failure", "--message", "stage 9 broke"])
    assert rc == 0
    assert sent == ["[FAILURE] stage 9 broke"]


def test_heartbeat_skipped_when_disabled(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send", lambda t: sent.append(t))
    monkeypatch.setattr(settings, "enable_heartbeat", False)
    rc = publish_alert.main(["--type", "heartbeat", "--message", "started"])
    assert rc == 0
    assert sent == []


def test_heartbeat_sent_when_enabled(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send", lambda t: sent.append(t))
    monkeypatch.setattr(settings, "enable_heartbeat", True)
    rc = publish_alert.main(["--type", "heartbeat", "--message", "started"])
    assert rc == 0
    assert sent == ["[HEARTBEAT] started"]


def test_telegram_failure_non_fatal(monkeypatch):
    def bad(t):
        raise RuntimeError("network down")

    monkeypatch.setattr(telegram, "send", bad)
    rc = publish_alert.main(["--type", "failure", "--message", "x"])
    assert rc == 0  # non-fatal
