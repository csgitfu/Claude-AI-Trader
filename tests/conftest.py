from pathlib import Path

import pytest

from trader.config import settings


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch):
    """Redirect all file-system outputs into a pytest tmp_path."""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "reports_dir", tmp_path / "reports")
    monkeypatch.setattr(settings, "logs_dir", tmp_path / "logs")
    (tmp_path / "data").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "data" / "universe").mkdir()
    yield tmp_path
