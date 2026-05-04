from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    fred_api_key: str = ""
    git_remote_url: str = ""
    enable_heartbeat: bool = False

    starting_nav: float = 50_000.0
    execute: bool = False
    kill_switch: bool = False

    shortlist_size: int = 50
    portfolio_size: int = 15
    max_weight_per_name: float = 0.10
    max_weight_per_sector: float = 0.25
    min_sectors: int = 8
    max_turnover_per_run: float = 0.40

    data_dir: Path = ROOT / "data"
    reports_dir: Path = ROOT / "reports"
    logs_dir: Path = ROOT / "logs"

    @property
    def ledger_path(self) -> Path:
        return self.data_dir / "ledger.json"

    @property
    def fundamentals_cache_path(self) -> Path:
        return self.data_dir / "fundamentals_cache.json"

    @property
    def universe_dir(self) -> Path:
        return self.data_dir / "universe"


settings = Settings()
