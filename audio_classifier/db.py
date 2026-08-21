from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS audio_files (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      path TEXT NOT NULL UNIQUE,
      size_bytes INTEGER NOT NULL,
      mtime REAL NOT NULL,
      sha256_head TEXT NOT NULL,
      duration REAL,
      fingerprint TEXT,
      fingerprinted_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS identifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      audio_file_id INTEGER NOT NULL,
      provider TEXT NOT NULL,
      score REAL,
      acoustid_id TEXT,
      musicbrainz_recording_id TEXT,
      title TEXT,
      artist TEXT,
      album TEXT,
      release_date TEXT,
      track_number TEXT,
      raw_json TEXT NOT NULL,
      chosen INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY(audio_file_id) REFERENCES audio_files(id)
    );
    CREATE TABLE IF NOT EXISTS operations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      audio_file_id INTEGER NOT NULL,
      old_path TEXT NOT NULL,
      new_path TEXT,
      wrote_tags INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL,
      error TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(audio_file_id) REFERENCES audio_files(id)
    );
    ''')
    conn.commit()


def upsert_audio_file(conn: sqlite3.Connection, path: Path, size_bytes: int, mtime: float, sha256_head: str) -> int:
    ts = now_iso()
    conn.execute(
        """INSERT INTO audio_files(path,size_bytes,mtime,sha256_head,created_at,updated_at)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET size_bytes=excluded.size_bytes, mtime=excluded.mtime, sha256_head=excluded.sha256_head, updated_at=excluded.updated_at""",
        (str(path), size_bytes, mtime, sha256_head, ts, ts),
    )
    conn.commit()
    return int(conn.execute("SELECT id FROM audio_files WHERE path=?", (str(path),)).fetchone()["id"])


def store_fingerprint(conn: sqlite3.Connection, file_id: int, duration: int, fingerprint: str) -> None:
    conn.execute("UPDATE audio_files SET duration=?, fingerprint=?, fingerprinted_at=?, updated_at=? WHERE id=?", (duration, fingerprint, now_iso(), now_iso(), file_id))
    conn.commit()


def store_identification(conn: sqlite3.Connection, file_id: int, metadata, provider: str = "acoustid") -> None:
    conn.execute("UPDATE identifications SET chosen=0 WHERE audio_file_id=?", (file_id,))
    conn.execute(
        """INSERT INTO identifications(audio_file_id,provider,score,acoustid_id,musicbrainz_recording_id,title,artist,album,release_date,track_number,raw_json,chosen,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (file_id, provider, metadata.score, metadata.acoustid_id, metadata.recording_id, metadata.title, metadata.artist, metadata.album, metadata.release_date, metadata.track_number, json.dumps(metadata.raw or {}, ensure_ascii=False), 1, now_iso()),
    )
    conn.commit()


def record_operation(conn: sqlite3.Connection, file_id: int, old_path: Path, new_path: Path | None, wrote_tags: bool, status: str, error: str = "") -> None:
    conn.execute("INSERT INTO operations(audio_file_id,old_path,new_path,wrote_tags,status,error,created_at) VALUES(?,?,?,?,?,?,?)", (file_id, str(old_path), str(new_path) if new_path else None, int(wrote_tags), status, error, now_iso()))
    conn.commit()
