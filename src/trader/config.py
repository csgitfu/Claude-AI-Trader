from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    fred_api_key: str = ""

    starting_nav: float = 1_000_000.0
    execute: bool = False
    kill_switch: bool = False
    daily_budget_usd: float = 25.0
    enable_heartbeat: bool = False

    model_scorer: str = "claude-haiku-4-5-20251001"
    model_debate: str = "claude-opus-4-7"
    model_probability: str = "claude-opus-4-7"
    model_selector: str = "claude-opus-4-7"
    model_newswriter: str = "claude-opus-4-7"

    shortlist_size: int = 50
    portfolio_size: int = 15
    max_weight_per_name: float = 0.10
    max_weight_per_sector: float = 0.25
    min_sectors: int = 8
    agent_concurrency: int = 5

    data_dir: Path = ROOT / "data"
    reports_dir: Path = ROOT / "reports"
    logs_dir: Path = ROOT / "logs"
    prompts_dir: Path = Path(__file__).parent / "prompts"

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
