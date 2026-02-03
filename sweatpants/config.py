"""Configuration management for Sweatpants."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModuleSourceConfig(BaseModel):
    """Configuration for a module source repository."""

    repo: str
    modules: list[str] = Field(default_factory=list)


class ModulesConfig(BaseModel):
    """Configuration for module sources loaded from modules.yaml."""

    module_sources: list[ModuleSourceConfig] = Field(default_factory=list)


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
    modules_config_path: Path = Path("/var/lib/sweatpants/modules.yaml")

    api_host: str = "127.0.0.1"
    api_port: int = 8420
    api_auth_token: str = ""

    proxy_url: str = ""  # Full URL: http://user:pass@host:port
    proxy_rotation_url: str = ""  # URL pattern for sticky sessions: http://user-session-{session}:pass@host:port

    browser_pool_size: int = 3
    browser_restart_hours: int = 4

    log_level: str = "INFO"

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.modules_dir.mkdir(parents=True, exist_ok=True)

    def load_modules_config(self) -> Optional[ModulesConfig]:
        """Load module sources configuration from modules.yaml."""
        if not self.modules_config_path.exists():
            return None

        with open(self.modules_config_path) as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        return ModulesConfig(**data)


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
