"""One isolated, time-limited download. Invoked only by the API server."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from yt_dlp import YoutubeDL

from backend.files import directory_bytes
from backend.urls import canonical_url


def emit(**data):
    print(json.dumps(data), flush=True)


class QuietLogger:
    def debug(self, _): pass
    def warning(self, _): pass
    def error(self, _): pass


def download(job, directory: Path, max_bytes: int, max_duration: int):
    _, url = canonical_url(job["url"])
    directory.mkdir(parents=True, exist_ok=True)
    last_progress = -1

    def progress(data):
        nonlocal last_progress
        if directory_bytes(directory) > max_bytes:
            raise ValueError("Video exceeds the configured size limit.")
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        percent = min(99, int(data.get("downloaded_bytes", 0) * 100 / total)) if total else 0
        if percent != last_progress:
            emit(progress=percent)
            last_progress = percent

    options = {
        "quiet": True, "no_warnings": True, "logger": QuietLogger(),
        "noplaylist": True, "socket_timeout": 20, "retries": 2,
        "fragment_retries": 2, "concurrent_fragment_downloads": 1,
        "outtmpl": str(directory / "media.%(ext)s"),
        "max_filesize": max_bytes, "progress_hooks": [progress],
        "writesubtitles": bool(job["captions"]), "writeautomaticsub": False,
        "subtitleslangs": ["en.*"], "subtitlesformat": "vtt",
        "cachedir": False, "restrictfilenames": True,
        "js_runtimes": {"node": {}, "deno": {}},
        "format": "bestaudio/best" if job["kind"] == "audio" else
                  "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]",
        "merge_output_format": "mp4",
    }
    if job["kind"] == "audio":
        options["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info or info.get("_type", "video") != "video":
            raise ValueError("This link did not return an individual video.")
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise ValueError("Live and upcoming streams cannot be archived yet.")
        if (info.get("duration") or 0) > max_duration:
            raise ValueError("Video exceeds the configured duration limit.")
        emit(title=str(info.get("title") or job["video_id"]))
        ydl.process_info(info)

    media = [p for p in directory.glob("media.*") if p.suffix in {".mp4", ".m4a", ".webm", ".mkv"}]
    if len(media) != 1 or media[0].stat().st_size == 0:
        raise ValueError("No completed media file was produced. The video may exceed the size limit.")
    if directory_bytes(directory) > max_bytes:
        raise ValueError("Video exceeds the configured size limit.")
    metadata = {key: info.get(key) for key in
                ("id", "title", "description", "uploader", "upload_date", "duration", "license")}
    metadata.update(source_url=url, archived_at=datetime.now(timezone.utc).isoformat(),
                    format=job["kind"], captions="English creator captions when available",
                    rights_note="Copyright status has not been automatically verified.")
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (directory / "description.txt").write_text(str(info.get("description") or ""), encoding="utf-8")
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix in {".mp4", ".m4a", ".webm", ".mkv", ".vtt", ".json", ".txt"}]
    if sum(p.stat().st_size for p in files) > max_bytes:
        raise ValueError("Archive exceeds the configured size limit.")
    with ZipFile(directory / "archive.zip", "w", compression=ZIP_STORED) as archive:
        for path in files:
            archive.write(path, path.name)
    emit(media=media[0].name, progress=100)


if __name__ == "__main__":
    try:
        download(json.loads(sys.stdin.read()), Path(sys.argv[1]),
                 int(os.environ["MAX_ARCHIVE_BYTES"]), int(os.environ["MAX_DURATION_SECONDS"]))
    except Exception as exc:
        emit(error=str(exc)[-600:])
        sys.exit(1)
