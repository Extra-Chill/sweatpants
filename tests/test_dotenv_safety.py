"""Tests for dotenv loading safety.

The Settings class uses DotEnvSettingsSource under the hood. In hardened
deployments, the CLI may be executed from a directory the current user cannot
stat/traverse (e.g. /root). Dotenv probing should not crash in that case.
"""

import os

import pytest

from sweatpants.config import Settings


def test_dotenv_probe_does_not_crash_when_cwd_unreadable(monkeypatch, tmp_path):
    # Create a directory that is not traversable by the current user.
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o000)

    old_cwd = os.getcwd()
    try:
        os.chdir(locked)
        # Should not raise even though `.env` stat() will fail.
        Settings()
    finally:
        os.chdir(old_cwd)
        locked.chmod(0o755)
