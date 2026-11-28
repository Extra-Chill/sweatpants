"""HTTP request setup without transcription dependencies."""
from urllib.request import Request, urlopen


USER_AGENT = "Sweatpants/1.0 (+https://github.com/Extra-Chill/sweatpants)"


def open_audio_url(url: str, auth_header: str | None = None):
    """Open an audio URL with an honest client identity and optional credentials."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    if auth_header:
        request.add_header("Authorization", auth_header)
    return urlopen(request, timeout=300)
