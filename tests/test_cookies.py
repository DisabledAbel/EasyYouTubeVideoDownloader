import json
import os
from http.cookiejar import CookieJar
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.cookies import MAX_COOKIE_BYTES, cookie_path, load_cookies, save_cookies
from backend.worker import download

KEY = "test-server-key-at-least-24-characters"
AUTH = {"Authorization": f"Bearer {KEY}"}
ENDPOINT = "/api/settings/youtube-cookies"
SECRET = "test-session-value-not-a-real-credential"
COOKIES = f"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\t{SECRET}\n"


def test_cookie_api_lifecycle_and_privacy(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, api_key=KEY))
    for method in ("get", "post", "delete"):
        assert getattr(client, method)(ENDPOINT).status_code == 401
    assert client.get(ENDPOINT, headers=AUTH).json() == {"configured": False}
    uploaded = client.post(ENDPOINT, headers=AUTH, json={"cookies": COOKIES})
    assert uploaded.status_code == 200
    assert uploaded.json() == {"configured": True}
    assert uploaded.headers["cache-control"] == "no-store"
    assert SECRET not in uploaded.text
    path = cookie_path(tmp_path)
    assert SECRET in path.read_text()
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    # Credentials survive server recreation, but cannot be downloaded through a public route.
    other = TestClient(create_app(data_dir=tmp_path, api_key=KEY))
    assert other.get(ENDPOINT, headers=AUTH).json() == {"configured": True}
    assert other.get("/.credentials/youtube-cookies.txt").status_code == 404
    assert other.get(ENDPOINT, headers=AUTH).json() == {"configured": True}
    assert other.delete(ENDPOINT, headers=AUTH).json() == {"configured": False}
    assert not path.exists()
    assert other.delete(ENDPOINT, headers=AUTH).status_code == 200


@pytest.mark.parametrize("content", [
    "not a cookie file", COOKIES.replace(".youtube.com", ".google.com"),
    COOKIES.replace(".youtube.com", ".youtube.com.evil.example"),
    COOKIES.replace("\tTRUE\t/", "\tFALSE\t/"),
    COOKIES.replace("\t0\tSID", "\tnot-an-expiry\tSID"),
    COOKIES.replace("\tSID\t", "\t\t"), COOKIES.replace(SECRET, "x" * MAX_COOKIE_BYTES),
    COOKIES.replace(SECRET, "\x00"), COOKIES.replace(SECRET, "\ud800"),
])
def test_invalid_upload_keeps_existing_session_without_echo(tmp_path, content):
    save_cookies(tmp_path, COOKIES)
    client = TestClient(create_app(data_dir=tmp_path, api_key=KEY))
    response = client.post(ENDPOINT, headers=AUTH, content=json.dumps({"cookies": content}).encode())
    assert response.status_code == 422
    assert SECRET not in response.text
    assert cookie_path(tmp_path).read_text() == COOKIES
    assert not list(cookie_path(tmp_path).parent.glob(".upload-*"))


@pytest.mark.parametrize("body", [b"invalid-json", json.dumps({"cookies": 123}).encode(),
                                  json.dumps({"cookies": COOKIES, "extra": SECRET}).encode()])
def test_bad_envelope_does_not_echo_input(tmp_path, body):
    client = TestClient(create_app(data_dir=tmp_path, api_key=KEY))
    response = client.post(ENDPOINT, headers=AUTH, content=body)
    assert response.status_code == 422
    assert SECRET not in response.text
    assert not cookie_path(tmp_path).exists()


def test_cookie_upload_stream_limit(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, api_key=KEY))
    response = client.post(ENDPOINT, headers=AUTH, content=b"x" * (MAX_COOKIE_BYTES * 6 + 1025))
    assert response.status_code == 413
    assert not cookie_path(tmp_path).exists()


def test_session_http_only_and_expired_cookies(tmp_path):
    content = COOKIES.replace(".youtube.com", "#HttpOnly_.youtube.com")
    content += ".youtube.com\tTRUE\t/\tTRUE\t1\texpired\told\n"
    save_cookies(tmp_path, content)
    cookies = load_cookies(tmp_path)
    assert len(cookies) == 1
    assert cookies[0].name == "SID" and cookies[0].value == SECRET
    assert cookies[0].expires is None
    assert load_cookies(tmp_path / "missing") == []


def test_worker_uses_memory_only_session_excluded_from_bundle(tmp_path, monkeypatch):
    save_cookies(tmp_path, COOKIES)
    directory = tmp_path / "job"
    jars = []

    class FakeYoutubeDL:
        def __init__(self, options):
            assert "cookiefile" not in options
            self.cookiejar = CookieJar()
            jars.append(self.cookiejar)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, *_args, **_kwargs):
            assert [cookie.value for cookie in self.cookiejar] == [SECRET]
            # Removing saved cookies during an active download stays removed.
            cookie_path(tmp_path).unlink()
            return {"id": "fKy7ljRr0AA", "title": "Test", "duration": 1}
        def process_info(self, _):
            (directory / "media.mp4").write_bytes(b"test")

    monkeypatch.setattr("backend.worker.YoutubeDL", FakeYoutubeDL)
    download({"url": "https://youtu.be/fKy7ljRr0AA", "video_id": "fKy7ljRr0AA",
              "kind": "video", "captions": False}, directory, 100000, 7200, cookie_root=tmp_path)
    assert not cookie_path(tmp_path).exists()
    with ZipFile(directory / "archive.zip") as bundle:
        assert set(bundle.namelist()) == {"media.mp4", "metadata.json", "description.txt"}
        assert all(SECRET.encode() not in bundle.read(name) for name in bundle.namelist())


def test_atomic_save_failure_keeps_session_and_cleans_temporary(tmp_path, monkeypatch):
    save_cookies(tmp_path, COOKIES)
    def fail(*_):
        raise OSError("write failed")
    monkeypatch.setattr("backend.cookies.os.replace", fail)
    with pytest.raises(OSError):
        save_cookies(tmp_path, COOKIES.replace(SECRET, "replacement"))
    assert cookie_path(tmp_path).read_text() == COOKIES
    assert not list(cookie_path(tmp_path).parent.glob(".upload-*"))


def test_session_works_in_real_ytdlp_jar_only_for_youtube(tmp_path):
    from urllib.request import Request
    from yt_dlp import YoutubeDL

    save_cookies(tmp_path, COOKIES)
    with YoutubeDL({"quiet": True, "cachedir": False}) as ydl:
        for cookie in load_cookies(tmp_path):
            ydl.cookiejar.set_cookie(cookie)
        youtube = Request("https://www.youtube.com/watch?v=fKy7ljRr0AA")
        other = Request("https://youtube.com.evil.example/")
        ydl.cookiejar.add_cookie_header(youtube)
        ydl.cookiejar.add_cookie_header(other)
        assert youtube.get_header("Cookie") == f"SID={SECRET}"
        assert other.get_header("Cookie") is None
        assert ydl.params.get("cookiefile") is None
