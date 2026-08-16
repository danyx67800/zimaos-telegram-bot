"""Accesso al database SQLite locale per le note."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class Database:
    """Wrapper thread-safe minimale attorno a sqlite3.

    Le operazioni sono volutamente sincrone: per un bot privato a basso
    traffico l'overhead è irrilevante e si evitano dipendenze extra
    (aiosqlite, SQLAlchemy, ecc.).
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def add_note(self, user_id: int, content: str) -> int:
        """Salva una nota e restituisce il suo ID."""
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute(
                "INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)",
                (user_id, content, created_at),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_notes(self, user_id: int) -> list[dict]:
        """Elenco delle note dell'utente, dalla più recente."""
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, content, created_at FROM notes "
                "WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_note(self, user_id: int, note_id: int) -> dict | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, content, created_at FROM notes "
                "WHERE id = ? AND user_id = ?",
                (note_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def delete_note(self, user_id: int, note_id: int) -> bool:
        """Elimina una nota; True se esisteva, False altrimenti."""
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute(
                "DELETE FROM notes WHERE id = ? AND user_id = ?",
                (note_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def count_notes(self, user_id: int) -> int:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM notes WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["c"])
