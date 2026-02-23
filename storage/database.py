"""SQLite storage for sessions, segments, and vocabulary."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from transcription.result import TranscriptionSegment


class Database:
    """Manages the SQLite database for transcripts and vocabulary."""

    def __init__(self, db_path: str):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _check_connected(self):
        if self._conn is None:
            raise RuntimeError("Database not connected")

    def connect(self):
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self):
        self._check_connected()
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                title TEXT
            );

            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                text TEXT NOT NULL,
                language TEXT DEFAULT 'fr',
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                translation TEXT NOT NULL,
                sentence TEXT,
                language TEXT DEFAULT 'fr',
                session_id INTEGER,
                added_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_segments_session
                ON segments(session_id);
            CREATE INDEX IF NOT EXISTS idx_vocabulary_word
                ON vocabulary(word);
            """
        )
        # Lightweight migration for older DBs created before vocabulary.language existed.
        cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(vocabulary)").fetchall()
        }
        if "language" not in cols:
            self._conn.execute(
                "ALTER TABLE vocabulary ADD COLUMN language TEXT DEFAULT 'fr'"
            )
        self._conn.commit()

    def start_session(self, title: str = "") -> int:
        self._check_connected()
        cursor = self._conn.execute(
            "INSERT INTO sessions (started_at, title) VALUES (?, ?)",
            (datetime.now().isoformat(), title),
        )
        self._conn.commit()
        return cursor.lastrowid

    def end_session(self, session_id: int):
        self._check_connected()
        self._conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (datetime.now().isoformat(), session_id),
        )
        self._conn.commit()

    def add_segment(self, session_id: int, segment: TranscriptionSegment):
        self.add_segments(session_id, [segment])

    def add_segments(self, session_id: int, segments: list[TranscriptionSegment]):
        self._check_connected()
        if not segments:
            return
        rows = [
            (
                session_id,
                seg.start_time,
                seg.end_time,
                seg.text,
                seg.language,
            )
            for seg in segments
        ]
        self._conn.executemany(
            "INSERT INTO segments (session_id, start_time, end_time, text, language) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def save_word(
        self,
        word: str,
        translation: str,
        sentence: str,
        language: str = "fr",
        session_id: int | None = None,
    ) -> int:
        self._check_connected()
        cursor = self._conn.execute(
            "INSERT INTO vocabulary (word, translation, sentence, language, session_id, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (word, translation, sentence, language, session_id, datetime.now().isoformat()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def delete_word(self, word_id: int) -> None:
        self._check_connected()
        self._conn.execute("DELETE FROM vocabulary WHERE id = ?", (word_id,))
        self._conn.commit()

    def get_vocabulary(
        self,
        session_id: int | None = None,
        language: str | None = None,
    ) -> list[dict]:
        self._check_connected()
        where: list[str] = []
        params: list = []
        if session_id is not None:
            where.append("session_id = ?")
            params.append(session_id)
        if language:
            where.append("language = ?")
            params.append(language)
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""

        rows = self._conn.execute(
            "SELECT id, word, translation, sentence, language, added_at FROM vocabulary "
            f"{where_sql} ORDER BY added_at",
            tuple(params),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_segments(self, session_id: int) -> list[dict]:
        self._check_connected()
        rows = self._conn.execute(
            "SELECT start_time, end_time, text FROM segments "
            "WHERE session_id = ? ORDER BY start_time",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sessions(self) -> list[dict]:
        self._check_connected()
        rows = self._conn.execute(
            "SELECT id, started_at, ended_at, title FROM sessions ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
