"""Configuration management for Sweatpants."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SWEATPANTS_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    data_dir: Path = Path("/var/lib/sweatpants")
    modules_dir: Path = Path("/var/lib/sweatpants/modules")
    db_path: Path = Path("/var/lib/sweatpants/sweatpants.db")

    api_host: str = "127.0.0.1"
    api_port: int = 8420
    api_auth_token: str = ""

    proxy_service_url: str = "http://127.0.0.1:8421"

    browser_pool_size: int = 3
    browser_restart_hours: int = 4

    log_level: str = "INFO"

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.modules_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
