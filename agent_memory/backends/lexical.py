"""Zero-dependency lexical recall backend (the default).

Reads the append-only journal and scores records by simple term overlap +
recency. No embeddings, no external service — the library works out of the box.
For semantic/vector recall, use or write a richer backend (see
``hermes_lancedb.py`` and ``docs/recall-backends.md``).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from ..config import DEFAULT_CONFIG, MemoryConfig
from .base import Record

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text or "")]


def _record_text(record: dict) -> str:
    parts = [
        str(record.get("action", "")),
        str(record.get("goal", "")),
    ]
    meta = record.get("meta")
    if isinstance(meta, dict):
        parts.extend(str(v) for v in meta.values())
    files = record.get("files")
    if isinstance(files, list):
        parts.extend(str(f) for f in files)
    return " ".join(p for p in parts if p)


class LexicalBackend:
    """Term-overlap + recency scoring over the journal. Always ``degraded``-free
    in the sense that it is the intended default, but it is lexical-only, so it
    reports ``degraded = True`` to be honest about not being semantic."""

    degraded = True

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.path = self.config.journal_path

    def _iter_records(self):
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def search(self, query: str, scope: str | None = None, limit: int = 5) -> list[Record]:
        query_terms = set(_tokenize(query))
        scored: list[tuple[float, dict, str]] = []
        for record in self._iter_records():
            if scope is not None and record.get("memoryScope", "global") != scope:
                continue
            text = _record_text(record)
            if not text:
                continue
            tokens = _tokenize(text)
            if not tokens:
                continue
            overlap = sum(1 for t in tokens if t in query_terms)
            if overlap == 0 and query_terms:
                continue
            # term overlap normalized by record length + a small recency nudge
            base = overlap / (len(set(tokens)) ** 0.5)
            score = base
            scored.append((score, record, text))

        # recency: later journal lines (appended later) get a tiny tiebreaker
        ranked = sorted(
            enumerate(scored), key=lambda pair: (pair[1][0], pair[0]), reverse=True
        )
        results: list[Record] = []
        for _idx, (score, record, text) in ranked[:limit]:
            results.append(
                Record(
                    text=text,
                    score=round(score, 4),
                    scope=record.get("memoryScope", "global"),
                    source=str(record.get("agentId", "")),
                    timestamp=str(record.get("ts", "")),
                    meta={"type": record.get("type", ""), "sid": record.get("sid", "")},
                )
            )
        return results
