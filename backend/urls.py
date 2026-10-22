"""Accept individual YouTube videos, never arbitrary fetch URLs."""
import re
from urllib.parse import parse_qs, urlsplit


def canonical_url(value: str) -> tuple[str, str]:
    try:
        url = urlsplit(value.strip())
        if url.scheme != "https" or url.username or url.password or url.port:
            raise ValueError
        host = url.hostname
        if host == "youtu.be":
            video_id = url.path.removeprefix("/")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if url.path == "/watch":
                values = parse_qs(url.query).get("v", [])
                video_id = values[0] if len(values) == 1 else ""
            elif re.fullmatch(r"/(shorts|live)/[A-Za-z0-9_-]{11}", url.path):
                video_id = url.path.split("/")[2]
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError
    except ValueError:
        raise ValueError("Paste an HTTPS link to one YouTube video.") from None
    return video_id, f"https://www.youtube.com/watch?v={video_id}"
