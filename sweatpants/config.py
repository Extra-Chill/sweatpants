"""Configuration management for Sweatpants."""

import os
from pathlib import Path
from typing import Annotated, Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("/var/lib/sweatpants")
    modules_dir: Path = Path("/var/lib/sweatpants/modules")
    exports_dir: Optional[Path] = None
    uploads_dir: Optional[Path] = None
    db_path: Path = Path("/var/lib/sweatpants/sweatpants.db")
    modules_config_path: Path = Path("/var/lib/sweatpants/modules.yaml")

    # Maximum size in bytes for a single uploaded artifact.
    # 500 MB default — accommodates ~5h of compressed audio at 192 kbps.
    uploads_max_bytes: int = 500 * 1024 * 1024
    # Age in hours after which an unclaimed upload may be garbage-collected.
    # An upload is "claimed" once a job is created that references it.
    uploads_ttl_hours: int = 24

    api_host: str = "127.0.0.1"
    api_port: int = 8420
    # Master admin token — full access to every endpoint. Used by orchestration
    # callers (CLI, ops scripts, trusted server-side code). Compare with
    # `api_signed_token_secret` below which is the HMAC key for short-lived
    # per-user scoped tokens.
    api_auth_token: str = ""
    # Shared secret used to validate signed bearer tokens minted by trusted
    # issuers (e.g. a WordPress plugin signing a short-lived "uploads:write"
    # token for an authenticated user). Empty disables signed-token auth;
    # only the master token is accepted in that case.
    api_signed_token_secret: str = ""

    # CORS allowlist for browser-direct callers (e.g. a React tab POSTing
    # audio uploads from an end-user's browser). Empty default = no CORS
    # middleware registered, identical to the pre-CORS behavior.
    #
    # `Annotated[..., NoDecode]` opts out of pydantic-settings' default JSON
    # decoding for list-typed env vars, so the `_split_csv` validator below
    # sees the raw string and can split on commas. Without NoDecode the
    # daemon crashes on startup because pydantic-settings tries
    # `json.loads("https://a.com,https://b.com")` before any validator runs.
    #
    # Accepted env var format:
    #   SWEATPANTS_API_CORS_ALLOW_ORIGINS=https://a.example.com,https://b.example.com
    api_cors_allow_origins: Annotated[list[str], NoDecode] = []
    # Whether to allow credentials (cookies, HTTP auth) on cross-origin
    # requests. Default false because signed tokens travel via
    # `Authorization: Bearer …`, not cookies, and `allow_credentials=true`
    # combined with a list-of-origins allowlist is what you want for
    # cookie-bearing flows specifically.
    api_cors_allow_credentials: bool = False
    # Browser cache duration for preflight responses, in seconds.
    api_cors_max_age: int = 86400

    @field_validator("api_cors_allow_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        """Split a comma-separated env-var string into a list of origins.

        Combined with `Annotated[..., NoDecode]` on the field declaration,
        this turns `SWEATPANTS_API_CORS_ALLOW_ORIGINS=https://a.com,https://b.com`
        into `["https://a.com", "https://b.com"]`. Plain `list[str]` defaults
        in pydantic-settings expect a JSON array, which is awkward to write
        in a `.env` file because of quoting.

        An already-decoded list (e.g. set from Python code, or a JSON array
        the operator chose to use anyway after stripping NoDecode) passes
        through unchanged.
        """
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    proxy_url: str = ""  # Full URL: http://user:pass@host:port
    proxy_rotation_url: str = ""  # URL pattern for sticky sessions: http://user-session-{session}:pass@host:port

    browser_pool_size: int = 3
    browser_restart_hours: int = 4

    log_level: str = "INFO"

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        """Derive defaults that depend on other settings.

        This keeps `exports_dir` configurable while still defaulting to
        `<data_dir>/exports`.
        """
        if self.exports_dir is None:
            self.exports_dir = self.data_dir / "exports"
        if self.uploads_dir is None:
            self.uploads_dir = self.data_dir / "uploads"

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.modules_dir.mkdir(parents=True, exist_ok=True)
        if self.exports_dir is not None:
            self.exports_dir.mkdir(parents=True, exist_ok=True)
        if self.uploads_dir is not None:
            self.uploads_dir.mkdir(parents=True, exist_ok=True)

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
    """Get application settings singleton.

    By default, Sweatpants does not probe for a `.env` file relative to the
    current working directory.

    To load settings from an env file, set `SWEATPANTS_ENV_FILE` to an absolute
    path.
    """

    env_file = os.environ.get("SWEATPANTS_ENV_FILE")
    if env_file:
        return Settings(_env_file=env_file)

    return Settings(_env_file=None)
