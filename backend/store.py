import sqlite3
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "jobs.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, video_id TEXT, url TEXT, kind TEXT,
                captions INTEGER, status TEXT, progress INTEGER DEFAULT 0,
                title TEXT DEFAULT '', error TEXT DEFAULT '',
                created REAL, updated REAL, media TEXT DEFAULT '')""")
            db.execute("UPDATE jobs SET status='failed', error='Server restarted. Please try again.' WHERE status='downloading'")

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC")]

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def add(self, video_id, url, kind, captions):
        now = time.time()
        job_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO jobs (id, video_id, url, kind, captions, status, created, updated) VALUES (?,?,?,?,?,'queued',?,?)",
                       (job_id, video_id, url, kind, int(captions), now, now))
        return self.get(job_id)

    def update(self, job_id, **fields):
        allowed = {"status", "progress", "title", "error", "media"}
        if not fields.keys() <= allowed:
            raise ValueError("Unknown job field")
        fields["updated"] = time.time()
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {', '.join(f'{key}=?' for key in fields)} WHERE id=?",
                       (*fields.values(), job_id))

    def delete(self, job_id):
        with self.connect() as db:
            db.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def public_job(job):
    return {key: value for key, value in job.items() if key != "media"}
