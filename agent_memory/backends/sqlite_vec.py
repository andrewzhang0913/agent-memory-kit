"""Sqlite-vec recall backend.

Uses sqlite-vec to provide an embedded vector store for real semantic search.
"""
from __future__ import annotations

import json
import struct
import sqlite3
from typing import Any, Callable, Optional

from .base import Record


def _serialize_f32(vector: list[float]) -> bytes:
    """Serialize a list of floats into a format sqlite-vec accepts."""
    return struct.pack(f"{len(vector)}f", *vector)


class SqliteVecBackend:
    """RecallBackend backed by sqlite-vec."""
    
    degraded = False

    def __init__(
        self,
        db_path: str = ":memory:",
        embed_fn: Optional[Callable[[str], list[float]]] = None,
    ):
        try:
            import sqlite_vec
            self._sqlite_vec = sqlite_vec
        except ImportError:
            raise ImportError(
                "sqlite-vec is not installed. "
                "Please install it with: pip install -e \".[sqlite-vec]\""
            )

        self.db_path = db_path
        self.embed_fn = embed_fn
        self.degraded = False
        self._db: Optional[sqlite3.Connection] = None
        self._initialized = False

    def _get_db(self) -> sqlite3.Connection:
        if self._db is not None:
            return self._db

        db = sqlite3.connect(self.db_path)
        load_extension = getattr(db, "load_extension", None)
        if not callable(load_extension):
            db.close()
            self.degraded = True
            raise RuntimeError(
                "sqlite-vec is unavailable because this Python sqlite3 build "
                "does not support loadable extensions"
            )

        enable_load_extension = getattr(db, "enable_load_extension", None)
        try:
            if callable(enable_load_extension):
                enable_load_extension(True)
            self._sqlite_vec.load(db)
        except (AttributeError, OSError, sqlite3.Error) as exc:
            db.close()
            self.degraded = True
            raise RuntimeError(f"failed to load the sqlite-vec extension: {exc}") from exc
        finally:
            if callable(enable_load_extension):
                try:
                    enable_load_extension(False)
                except sqlite3.Error:
                    # The connection may already be closed after a load failure.
                    pass
        self._db = db
        return db

    def _init_schema(self, embed_dim: int):
        if self._initialized:
            return
        
        db = self._get_db()
        db.execute(
            '''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                scope TEXT,
                source TEXT,
                timestamp TEXT,
                meta_json TEXT
            )
            '''
        )
        db.execute(
            f'''
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_records USING vec0(
                id INTEGER PRIMARY KEY,
                embedding FLOAT[{embed_dim}]
            )
            '''
        )
        self._initialized = True

    def add(self, record: Record):
        """Insert a record into the sqlite-vec store.
        
        If `embed_fn` fails or is missing, this is skipped and `degraded` is set.
        """
        if not self.embed_fn:
            self.degraded = True
            return

        try:
            embedding = self.embed_fn(record.text)
        except Exception:
            self.degraded = True
            return

        try:
            self._init_schema(len(embedding))
        except RuntimeError:
            # A Python build without SQLite extension loading cannot use
            # sqlite-vec. Stay available as an empty, degraded backend so a
            # Recall fallback (for example LexicalBackend) can take over.
            self.degraded = True
            return
        db = self._get_db()
        
        cursor = db.cursor()
        cursor.execute(
            '''
            INSERT INTO records (text, scope, source, timestamp, meta_json)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (
                record.text,
                record.scope,
                record.source,
                record.timestamp,
                json.dumps(record.meta)
            )
        )
        record_id = cursor.lastrowid
        
        cursor.execute(
            '''
            INSERT INTO vec_records (id, embedding)
            VALUES (?, ?)
            ''',
            (record_id, _serialize_f32(embedding))
        )
        db.commit()

    def search(self, query: str, scope: str | None = None, limit: int = 5) -> list[Record]:
        """Return up to ``limit`` records relevant to ``query``.

        ``scope`` optionally restricts results to one memory scope (e.g.
        ``"global"`` or ``"agent:foo"``); None means no scope filter.
        """
        if not self.embed_fn:
            self.degraded = True
            return []

        try:
            embedding = self.embed_fn(query)
            # If not initialized, there are no records
            if not self._initialized:
                return []
            
            db = self._get_db()
            cursor = db.cursor()
            
            if scope is not None:
                cursor.execute(
                    '''
                    SELECT r.text, r.scope, r.source, r.timestamp, r.meta_json, v.distance
                    FROM vec_records v
                    JOIN records r ON v.id = r.id
                    WHERE r.scope = ? AND v.embedding MATCH ? AND k = ?
                    ORDER BY v.distance
                    ''',
                    (scope, _serialize_f32(embedding), limit)
                )
            else:
                cursor.execute(
                    '''
                    SELECT r.text, r.scope, r.source, r.timestamp, r.meta_json, v.distance
                    FROM vec_records v
                    JOIN records r ON v.id = r.id
                    WHERE v.embedding MATCH ? AND k = ?
                    ORDER BY v.distance
                    ''',
                    (_serialize_f32(embedding), limit)
                )
                
            rows = cursor.fetchall()
            results = []
            for text, res_scope, source, timestamp, meta_json, distance in rows:
                results.append(
                    Record(
                        text=text,
                        score=float(1.0 / (1.0 + distance)),
                        scope=res_scope,
                        source=source,
                        timestamp=timestamp,
                        meta=json.loads(meta_json) if meta_json else {}
                    )
                )
            return results
            
        except Exception:
            self.degraded = True
            return []
