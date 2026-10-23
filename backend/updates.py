"""Check the published Docker tag without forwarding any app credentials."""

import json
import re
import threading
import time
from urllib.request import Request, urlopen

REPOSITORY = "DisabledAbel/EasyYouTubeVideoDownloader"
IMAGE = REPOSITORY.lower()
CACHE_SECONDS = 15 * 60
MAX_RESPONSE_BYTES = 1024 * 1024


def read_json(url, headers=None):
    request = Request(url, headers={"User-Agent": "EasyYouTubeVideoDownloader",
                                    "Accept": "application/json", **(headers or {})})
    with urlopen(request, timeout=5) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Update response is too large")
    return json.loads(body)


class UpdateChecker:
    def __init__(self, revision, *, fetch=read_json, clock=time.monotonic):
        self.revision = revision if re.fullmatch(r"[0-9a-f]{40}", revision) else None
        self.fetch = fetch
        self.clock = clock
        self.lock = threading.Lock()
        self.expires = 0
        self.cached = None

    def check(self):
        result = {"status": "unmanaged", "current_revision": self.revision,
                  "latest_revision": None}
        # Source builds have no official image identity; do not suggest replacing them.
        if self.revision is None:
            return result
        with self.lock:
            if self.cached is not None and self.clock() < self.expires:
                return self.cached.copy()
            result["status"] = "unavailable"
            try:
                token = self.fetch(
                    f"https://ghcr.io/token?service=ghcr.io&scope=repository:{IMAGE}:pull")["token"]
                if not isinstance(token, str) or not token:
                    raise ValueError("Invalid registry response")
                manifest = self.fetch(f"https://ghcr.io/v2/{IMAGE}/manifests/latest", {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.oci.image.index.v1+json",
                })
                latest = manifest.get("annotations", {}).get("org.opencontainers.image.revision")
                if not isinstance(latest, str) or not re.fullmatch(r"[0-9a-f]{40}", latest):
                    raise ValueError("Published revision is unavailable")
                result["latest_revision"] = latest
                if latest == self.revision:
                    result["status"] = "current"
                else:
                    # Different is not necessarily newer (for example, a tag rollback).
                    comparison = self.fetch(
                        f"https://api.github.com/repos/{REPOSITORY}/compare/"
                        f"{self.revision}...{latest}?per_page=1", {
                            "Accept": "application/vnd.github+json",
                        })
                    status = comparison.get("status")
                    if status == "ahead":
                        result["status"] = "available"
                    elif status in {"identical", "behind"}:
                        result["status"] = "current"
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                # Offline/rate-limited checks must not interrupt normal app use.
                result["status"] = "unavailable"
            self.cached = result.copy()
            self.expires = self.clock() + CACHE_SECONDS
            return result
