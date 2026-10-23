import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import signal
import shutil
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.cookies import MAX_COOKIE_BYTES, cookie_path, save_cookies
from backend.files import directory_bytes
from backend.store import Store, public_job
from backend.urls import canonical_url
from backend.updates import UpdateChecker

logger = logging.getLogger(__name__)


class ArchiveRequest(BaseModel):
    url: str = Field(max_length=2048)
    kind: Literal["video", "audio"] = "video"
    captions: bool = True


async def run_download(store, job, max_bytes, timeout, duration):
    directory = store.root / job["id"]
    directory.mkdir(exist_ok=True)
    store.update(job["id"], status="downloading", error="")
    env = {**os.environ, "MAX_ARCHIVE_BYTES": str(max_bytes), "MAX_DURATION_SECONDS": str(duration),
           "YOUTUBE_COOKIE_ROOT": str(store.root)}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "backend.worker", str(directory),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=env, start_new_session=os.name == "posix")
    process.stdin.write(json.dumps(job).encode())
    await process.stdin.drain()
    process.stdin.close()
    result = {}

    async def read_progress():
        while line := await process.stdout.readline():
            data = json.loads(line)
            result.update(data)
            store.update(job["id"], **{k: v for k, v in data.items() if k in {"progress", "title"}})

    reader = asyncio.create_task(read_progress())
    started = time.monotonic()
    try:
        while process.returncode is None:
            if time.monotonic() - started > timeout:
                raise ValueError("Download timed out. Please try again.")
            # Allow room for the stored ZIP copy while enforcing a total disk budget.
            if directory_bytes(directory) > max_bytes * 2 + 1048576:
                raise ValueError("Archive exceeds the configured size limit.")
            await asyncio.sleep(0.25)
        await reader
        if process.returncode != 0 or "media" not in result:
            raise ValueError(result.get("error", "Download failed. YouTube may have blocked this server."))
        media = result["media"]
        if media not in {"media.mp4", "media.m4a", "media.webm", "media.mkv"} or not (directory / media).is_file():
            raise ValueError("Download did not produce a valid media file.")
        store.update(job["id"], status="ready", progress=100, media=media)
    finally:
        if process.returncode is None:
            if os.name == "posix":
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await reader


def create_app(*, data_dir=None, api_key=None, frontend_dir=None, runner=run_download):
    key = api_key if api_key is not None else os.environ.get("ARCHIVE_API_KEY", "")
    if len(key) < 24:
        raise RuntimeError("Set ARCHIVE_API_KEY to a random secret of at least 24 characters.")
    root = Path(data_dir or os.environ.get("ARCHIVE_DATA_DIR", "data")).resolve()
    store = Store(root)
    updates = UpdateChecker(os.environ.get("ARCHIVE_BUILD_REVISION", ""))
    for job in store.list():
        if job["status"] == "failed":
            shutil.rmtree(root / job["id"], ignore_errors=True)
    max_bytes = int(os.environ.get("MAX_ARCHIVE_BYTES", 512 * 1024 * 1024))
    retention = int(os.environ.get("RETENTION_HOURS", "24")) * 3600
    max_jobs = int(os.environ.get("MAX_JOBS", "20"))
    timeout = int(os.environ.get("DOWNLOAD_TIMEOUT_SECONDS", "900"))
    duration = int(os.environ.get("MAX_DURATION_SECONDS", "7200"))

    def cleanup():
        for job in store.list():
            if job["status"] in {"ready", "failed"} and time.time() - job["updated"] > retention:
                shutil.rmtree(root / job["id"], ignore_errors=True)
                store.delete(job["id"])

    async def consume():
        while True:
            try:
                cleanup()
                pending = next((j for j in reversed(store.list()) if j["status"] == "queued"), None)
                if pending:
                    try:
                        await runner(store, pending, max_bytes, timeout, duration)
                    except asyncio.CancelledError:
                        try:
                            store.update(pending["id"], status="failed", error="Server stopped. Please try again.")
                        except Exception:
                            logger.exception("Could not mark interrupted archive as failed")
                        shutil.rmtree(root / pending["id"], ignore_errors=True)
                        raise
                    except Exception as exc:
                        store.update(pending["id"], status="failed", error=str(exc)[:600])
                        shutil.rmtree(root / pending["id"], ignore_errors=True)
                else:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Archive queue iteration failed; retrying")
                await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(_):
        task = asyncio.create_task(consume())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="EasyYouTubeVideoDownloader", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store = store
    origins = [s.strip() for s in os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",") if s.strip()]
    if "*" in origins:
        raise RuntimeError("ALLOWED_ORIGINS must contain explicit frontend origins.")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])
    bearer = HTTPBearer(auto_error=False)

    def authorized(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None or not secrets.compare_digest(credentials.credentials.encode(), key.encode()):
            raise HTTPException(401, "Enter the correct server access key.")

    def find_job(job_id):
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise HTTPException(404, "Archive not found.")
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "Archive not found.")
        return job

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/updates", dependencies=[Depends(authorized)])
    def update_status():
        # FastAPI runs synchronous routes in its thread pool, away from the queue.
        return updates.check()

    @app.get("/api/settings/youtube-cookies", dependencies=[Depends(authorized)])
    async def cookie_status():
        return {"configured": cookie_path(root).is_file()}

    @app.post("/api/settings/youtube-cookies", dependencies=[Depends(authorized)])
    async def upload_cookies(request: Request):
        # Bound the streamed JSON envelope before parsing; validation errors must not
        # echo the submitted credentials (including FastAPI/Pydantic input values).
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > MAX_COOKIE_BYTES * 6 + 1024:
                raise HTTPException(413, "Cookie file must be 64 KiB or smaller.")
            chunks.extend(chunk)
        try:
            body = json.loads(chunks)
        except (ValueError, UnicodeError):
            raise HTTPException(422, "Choose a valid YouTube cookies.txt file.") from None
        if not isinstance(body, dict) or set(body) != {"cookies"} or not isinstance(body["cookies"], str):
            raise HTTPException(422, "Choose a valid YouTube cookies.txt file.")
        try:
            save_cookies(root, body["cookies"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"configured": True}

    @app.delete("/api/settings/youtube-cookies", dependencies=[Depends(authorized)])
    async def remove_cookies():
        cookie_path(root).unlink(missing_ok=True)
        return {"configured": False}

    @app.get("/api/jobs", dependencies=[Depends(authorized)])
    async def list_jobs():
        return [public_job(j) for j in store.list()]

    @app.post("/api/jobs", dependencies=[Depends(authorized)])
    async def create_job(body: ArchiveRequest):
        try:
            video_id, url = canonical_url(body.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        cleanup()
        jobs = store.list()
        for job in jobs:
            if (job["video_id"], job["kind"], bool(job["captions"])) == (video_id, body.kind, body.captions) and job["status"] != "failed":
                return {"job": public_job(job), "duplicate": True}
        if len(jobs) >= max_jobs:
            raise HTTPException(429, "Archive storage is full. Delete an archive before adding another.")
        if sum(j["status"] in {"queued", "downloading"} for j in jobs) >= 5:
            raise HTTPException(429, "Five downloads are already queued. Please wait.")
        return {"job": public_job(store.add(video_id, url, body.kind, body.captions)), "duplicate": False}

    @app.delete("/api/jobs/{job_id}", dependencies=[Depends(authorized)])
    async def delete_job(job_id: str):
        job = find_job(job_id)
        if job["status"] in {"queued", "downloading"}:
            raise HTTPException(409, "Wait for this download to finish before deleting it.")
        shutil.rmtree(root / job_id, ignore_errors=True)
        store.delete(job_id)
        return {"deleted": True}

    def signature(job_id, artifact, expires):
        return hmac.new(key.encode(), f"{job_id}:{artifact}:{expires}".encode(), hashlib.sha256).hexdigest()

    @app.post("/api/jobs/{job_id}/ticket", dependencies=[Depends(authorized)])
    async def ticket(job_id: str, artifact: Literal["media", "bundle"] = "bundle"):
        job = find_job(job_id)
        if job["status"] != "ready":
            raise HTTPException(409, "This archive is not ready yet.")
        expires = int(time.time()) + 300
        token = signature(job_id, artifact, expires)
        return {"path": f"/api/files/{job_id}/{artifact}?expires={expires}&token={token}"}

    @app.get("/api/files/{job_id}/{artifact}")
    async def files(job_id: str, artifact: Literal["media", "bundle"], expires: int, token: str):
        if expires < time.time() or not hmac.compare_digest(token.encode(), signature(job_id, artifact, expires).encode()):
            raise HTTPException(401, "Download link expired. Click download again.")
        job = find_job(job_id)
        if job["status"] != "ready":
            raise HTTPException(409, "This archive is not ready yet.")
        filename = "archive.zip" if artifact == "bundle" else job["media"]
        path = root / job_id / filename
        if not path.is_file():
            raise HTTPException(404, "Archive file is no longer available.")
        suffix = path.suffix
        return FileResponse(path, filename=f"{job['video_id']}-{job['kind']}{suffix}")

    static = Path(frontend_dir or "frontend/dist")
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
    return app
