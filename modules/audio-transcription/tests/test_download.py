"""Request tests that do not import torch, Whisper, or the SDK."""
import importlib.util
from io import BytesIO
from pathlib import Path

import pytest


@pytest.mark.parametrize("auth_header", [None, "Bearer test-token"])
def test_download_headers(monkeypatch, auth_header):
    path = Path(__file__).resolve().parents[1] / "audio_download.py"
    spec = importlib.util.spec_from_file_location("audio_download_test", path)
    download = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(download)
    calls = []
    response = BytesIO(b"audio data")

    def urlopen(request, timeout):
        calls.append((request, timeout))
        return response

    monkeypatch.setattr(download, "urlopen", urlopen)
    with download.open_audio_url("https://cdn.example/audio.mp3", auth_header) as result:
        assert result is response
        assert result.read() == b"audio data"

    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == "https://cdn.example/audio.mp3"
    assert request.get_header("User-agent") == (
        "Sweatpants/1.0 (+https://github.com/Extra-Chill/sweatpants)"
    )
    assert request.get_header("Authorization") == auth_header
    assert timeout == 300
