"""Recall backend protocol.

A ``RecallBackend`` answers "what past memory is relevant to this query?". The
kit ships a zero-dependency lexical backend (``lexical.py``) as the default and
a reference adapter for an external Hermes + LanceDB vector store
(``hermes_lancedb.py``). Write your own by implementing this protocol — e.g.
backing onto sqlite-vec, chromadb, or any vector store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Record:
    """A single recalled memory item."""

    text: str
    score: float = 0.0
    scope: str = "global"
    source: str = ""
    timestamp: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class RecallBackend(Protocol):
    """Pluggable recall interface.

    ``degraded`` signals that the backend is running on a reduced-quality path
    (e.g. lexical-only because an embedding service was unavailable), so callers
    can surface that to the user rather than silently trusting weaker results.
    """

    degraded: bool

    def search(self, query: str, scope: str | None = None, limit: int = 5) -> list[Record]:
        """Return up to ``limit`` records relevant to ``query``.

        ``scope`` optionally restricts results to one memory scope (e.g.
        ``"global"`` or ``"agent:foo"``); None means no scope filter.
        """
        ...
