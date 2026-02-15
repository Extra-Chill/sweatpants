"""Tests for configuration defaults."""

from pathlib import Path

from sweatpants.config import Settings


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

    settings = Settings()
    settings.ensure_directories()

    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "data" / "exports").is_dir()
