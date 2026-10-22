import asyncio
import sys
import time
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app, run_download
from backend.store import Store
from backend.urls import canonical_url

KEY = "test-secret-key-with-at-least-24-characters"
AUTH = {"Authorization": f"Bearer {KEY}"}
URL = "https://www.youtube.com/watch?v=fKy7ljRr0AA"


async def fake_download(store, job, *_):
    directory = store.root / job["id"]
    directory.mkdir()
    media = "media.mp4" if job["kind"] == "video" else "media.m4a"
    (directory / media).write_bytes(b"test media")
    with ZipFile(directory / "archive.zip", "w") as archive:
        archive.write(directory / media, media)
    store.update(job["id"], status="ready", progress=100, title="A recording", media=media)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path, api_key=KEY, runner=fake_download)) as client:
        yield client


def create(client, **extra):
    response = client.post("/api/jobs", headers=AUTH, json={"url": URL, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def wait_ready(client):
    for _ in range(30):
        jobs = client.get("/api/jobs", headers=AUTH).json()
        if jobs and jobs[0]["status"] == "ready":
            return jobs[0]
        time.sleep(0.05)
    pytest.fail("Download did not finish")


@pytest.mark.parametrize("url", [URL, "https://youtu.be/fKy7ljRr0AA?t=12", "https://m.youtube.com/watch?v=fKy7ljRr0AA&list=abc", "https://youtube.com/shorts/fKy7ljRr0AA"])
def test_canonical_links(url):
    assert canonical_url(url) == ("fKy7ljRr0AA", URL)


@pytest.mark.parametrize("url", [
    "http://youtube.com/watch?v=fKy7ljRr0AA", "https://youtube.com.evil.org/watch?v=fKy7ljRr0AA",
    "https://youtube.com@127.0.0.1/watch?v=fKy7ljRr0AA", "file:///etc/passwd",
    "https://youtube.com:443/watch?v=fKy7ljRr0AA", "https://youtube.com/playlist?list=abc",
    "https://youtu.be/../../secrets", "https://youtu.be/fKy7ljRr0AA/extra",
    "https://youtube.com/watch?v=fKy7ljRr0AA&v=abcdefghijk", "https://localhost/watch?v=fKy7ljRr0AA",
])
def test_rejects_non_video_urls(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_key_required(tmp_path):
    with pytest.raises(RuntimeError, match="ARCHIVE_API_KEY"):
        create_app(data_dir=tmp_path, api_key="")


def test_authentication(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/jobs").status_code == 401
    assert client.post("/api/jobs", json={"url": URL}).status_code == 401
    assert client.get("/api/jobs", headers={"Authorization": "Bearer incorrect"}).status_code == 401
    assert client.get("/api/jobs", headers=AUTH).headers["cache-control"] == "no-store"


def test_duplicate_and_formats(client):
    first = create(client)
    second = create(client, url="https://youtu.be/fKy7ljRr0AA")
    assert not first["duplicate"] and second["duplicate"]
    assert first["job"]["id"] == second["job"]["id"]
    assert "media" not in first["job"]
    assert create(client, kind="audio")["job"]["id"] != first["job"]["id"]
    assert create(client, captions=False)["job"]["id"] != first["job"]["id"]


def test_download_ticket_and_delete(client):
    create(client)
    job = wait_ready(client)
    for artifact in ("bundle", "media"):
        path = client.post(f"/api/jobs/{job['id']}/ticket?artifact={artifact}", headers=AUTH).json()["path"]
        response = client.get(path)
        assert response.status_code == 200
        assert response.content
        assert "attachment" in response.headers["content-disposition"]
        assert client.get(path + "bad").status_code == 401
        expired = path.replace(path.split("expires=")[1].split("&")[0], "1")
        assert client.get(expired).status_code == 401
    assert client.post(f"/api/jobs/{job['id']}/ticket").status_code == 401
    assert client.post(f"/api/jobs/{job['id']}/ticket?artifact=../secret", headers=AUTH).status_code == 422
    assert client.delete(f"/api/jobs/{job['id']}", headers=AUTH).status_code == 200
    assert not client.get("/api/jobs", headers=AUTH).json()
    assert client.get(path).status_code == 404


def test_storage_capacity(client, monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_JOBS", "1")
    app = create_app(data_dir=tmp_path, api_key=KEY, runner=fake_download)
    with TestClient(app) as limited:
        create(limited)
        assert limited.post("/api/jobs", headers=AUTH, json={"url": URL, "kind": "audio"}).status_code == 429


def test_invalid_input(client):
    assert client.post("/api/jobs", headers=AUTH, json={"url": "https://127.0.0.1"}).status_code == 422
    assert client.post("/api/jobs", headers=AUTH, json={"url": URL, "kind": "shell"}).status_code == 422
    assert client.delete("/api/jobs/not-a-job", headers=AUTH).status_code == 404


def test_cors_allows_only_configured_origin(client):
    allowed = client.options("/api/jobs", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8080"
    denied = client.options("/api/jobs", headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in denied.headers


def test_failed_runner_removes_partial_files(tmp_path):
    async def fail(store, job, *_):
        (store.root / job["id"]).mkdir()
        (store.root / job["id"] / "partial").write_bytes(b"partial")
        raise ValueError("Blocked by provider")

    with TestClient(create_app(data_dir=tmp_path, api_key=KEY, runner=fail)) as client:
        job = create(client)["job"]
        for _ in range(30):
            current = client.get("/api/jobs", headers=AUTH).json()[0]
            if current["status"] == "failed":
                break
            time.sleep(0.05)
        assert current["status"] == "failed"
        assert current["error"] == "Blocked by provider"
        assert not (tmp_path / job["id"]).exists()
        assert not create(client)["duplicate"]


def test_expiry_and_restart_recovery(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.add("fKy7ljRr0AA", URL, "video", True)
    store.update(job["id"], status="downloading")
    store = Store(tmp_path)
    assert store.get(job["id"])["status"] == "failed"
    with store.connect() as db:
        db.execute("UPDATE jobs SET updated=?", (time.time() - 90000,))
    with TestClient(create_app(data_dir=tmp_path, api_key=KEY, runner=fake_download)) as client:
        create(client)
        assert all(j["id"] != job["id"] for j in client.get("/api/jobs", headers=AUTH).json())


def test_timeout_kills_worker(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.add("fKy7ljRr0AA", URL, "video", True)
    real_spawn = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*_, **kwargs):
        process = await real_spawn(sys.executable,
                                  "-c", "import time; time.sleep(60)", **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(ValueError, match="timed out"):
        asyncio.run(run_download(store, job, 1000000, 0, 7200))
    assert processes[0].returncode is not None
