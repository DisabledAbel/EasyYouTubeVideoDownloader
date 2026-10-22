"""Private, server-wide YouTube session cookies; never part of job artifacts."""
import os
import tempfile
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path

MAX_COOKIE_BYTES = 64 * 1024
COOKIE_HEADER = "# Netscape HTTP Cookie File"


def cookie_path(root: Path) -> Path:
    return root / ".credentials" / "youtube-cookies.txt"


def validate_cookies(content: str) -> str:
    try:
        size = len(content.encode("utf-8"))
    except UnicodeError:
        raise ValueError("Cookie file contains invalid text.") from None
    if size > MAX_COOKIE_BYTES:
        raise ValueError("Cookie file must be 64 KiB or smaller.")
    lines = content.splitlines()
    if not lines or lines[0].lstrip("\ufeff").strip() not in {
        COOKIE_HEADER, "# HTTP Cookie File"
    }:
        raise ValueError("Choose a Netscape-format YouTube cookies.txt file.")
    rows = []
    for line in lines[1:]:
        if not line.strip() or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        row = line.removeprefix("#HttpOnly_").split("\t")
        if len(row) != 7:
            raise ValueError("Cookie file contains an invalid cookie row.")
        domain, subdomains, path, secure, expires, name, value = row
        host = domain.removeprefix(".").lower()
        if host != "youtube.com" and not host.endswith(".youtube.com"):
            raise ValueError("Export only youtube.com cookies, not cookies for other websites.")
        labels = host.split(".")
        if any(not label or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in label)
               or label.startswith("-") or label.endswith("-") for label in labels):
            raise ValueError("Cookie file contains an invalid cookie domain.")
        if (subdomains not in {"TRUE", "FALSE"} or secure not in {"TRUE", "FALSE"}
                or (subdomains == "TRUE") != domain.startswith(".")
                or not path.startswith("/") or not expires.isascii() or not expires.isdigit()
                or len(expires) > 12 or not name
                or any(ord(c) < 32 or ord(c) > 126 for c in "".join(row))):
            raise ValueError("Cookie file contains an invalid cookie row.")
        # Discard comments; only cookie records are persisted.
        rows.append(line)
    if not rows:
        raise ValueError("Cookie file does not contain any YouTube cookies.")
    return COOKIE_HEADER + "\n" + "\n".join(rows) + "\n"


def save_cookies(root: Path, content: str):
    normalized = validate_cookies(content)
    path = cookie_path(root)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(normalized)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_cookies(root: Path):
    jar = MozillaCookieJar()
    try:
        jar.load(str(cookie_path(root)), ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        return []
    except (LoadError, OSError, ValueError):
        # CookieJar parse errors can contain session values. Never forward those errors.
        raise ValueError("Saved YouTube cookies could not be read. Upload the file again.") from None
    cookies = []
    for cookie in jar:
        if cookie.expires == 0:
            cookie.expires = None
            cookie.discard = True
        if not cookie.is_expired():
            cookies.append(cookie)
    return cookies
