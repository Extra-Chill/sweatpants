"""Tests for configuration defaults."""

from pathlib import Path

from sweatpants.config import Settings, get_settings


def test_exports_dir_defaults_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SWEATPANTS_DATA_DIR", str(tmp_path / "data"))

    settings = Settings()

    assert settings.data_dir == Path(tmp_path / "data")
    assert settings.exports_dir == Path(tmp_path / "data" / "exports")


def test_exports_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SWEATPANTS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SWEATPANTS_EXPORTS_DIR", str(tmp_path / "my_exports"))

    settings = Settings()

    assert settings.exports_dir == Path(tmp_path / "my_exports")


def test_ensure_directories_creates_exports_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SWEATPANTS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SWEATPANTS_MODULES_DIR", str(tmp_path / "data" / "modules"))

    settings = Settings()
    settings.ensure_directories()

    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "data" / "exports").is_dir()
    assert (tmp_path / "data" / "modules").is_dir()


def test_get_settings_respects_sweatpants_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / "sweatpants.env"
    env_file.write_text(
        "\n".join(
            [
                f"SWEATPANTS_DATA_DIR={tmp_path / 'from_env_file'}",
                "SWEATPANTS_BROWSER_POOL_SIZE=7",
                "",
            ]
        )
    )

    monkeypatch.delenv("SWEATPANTS_DATA_DIR", raising=False)
    monkeypatch.delenv("SWEATPANTS_BROWSER_POOL_SIZE", raising=False)
    monkeypatch.setenv("SWEATPANTS_ENV_FILE", str(env_file))

    settings = get_settings()

    assert settings.data_dir == Path(tmp_path / "from_env_file")
    assert settings.browser_pool_size == 7
