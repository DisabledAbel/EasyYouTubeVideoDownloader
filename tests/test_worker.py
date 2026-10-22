import json
from zipfile import ZipFile

import pytest

from backend.worker import download


def test_metadata_and_bundle(tmp_path, monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, url, download):
            return {"id": "fKy7ljRr0AA", "title": "Test speech", "duration": 100,
                    "description": "A description", "url": "https://signed-private-media-url"}
        def process_info(self, info):
            (tmp_path / "media.mp4").write_bytes(b"video")
            (tmp_path / "media.en.vtt").write_text("WEBVTT")

    monkeypatch.setattr("backend.worker.YoutubeDL", FakeYoutubeDL)
    job = {"url": "https://youtu.be/fKy7ljRr0AA", "video_id": "fKy7ljRr0AA", "kind": "video", "captions": True}
    download(job, tmp_path, 100000, 7200)
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["source_url"] == "https://www.youtube.com/watch?v=fKy7ljRr0AA"
    assert "archived_at" in metadata
    assert "signed-private" not in (tmp_path / "metadata.json").read_text()
    with ZipFile(tmp_path / "archive.zip") as archive:
        assert set(archive.namelist()) == {"media.mp4", "media.en.vtt", "metadata.json", "description.txt"}


@pytest.mark.parametrize("info", [{"is_live": True}, {"duration": 7201}, {"_type": "playlist"}])
def test_rejects_live_long_and_playlist(tmp_path, monkeypatch, info):
    class FakeYoutubeDL:
        def __init__(self, _): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, *_args, **_kwargs): return info
        def process_info(self, _): pytest.fail("Should reject before downloading")
    monkeypatch.setattr("backend.worker.YoutubeDL", FakeYoutubeDL)
    with pytest.raises(ValueError):
        download({"url": "https://youtu.be/fKy7ljRr0AA", "kind": "video", "captions": True}, tmp_path, 1000, 7200)
