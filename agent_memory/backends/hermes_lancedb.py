"""Reference recall adapter: external Hermes + LanceDB vector store.

This is a REFERENCE adapter, not a hard dependency of the kit. It shells out to
a Node script (``search_lancedb.mjs`` in the original system) that performs a
6-signal hybrid fusion over a LanceDB vector store:

    score = vector*0.42 + bm25*0.24 + lexical*0.16
          + entity*0.10 + temporal*0.05 + importance*0.03

with graceful degradation to BM25/lexical/entity/temporal signals when the
embedding service is unavailable.

Requirements (NOT installed by the kit):
  * Node.js on PATH
  * a search script implementing the JSON contract below
  * a LanceDB store + embedding endpoint

It exists to (a) show adapter authors the contract and (b) let an existing
deployment keep its rich recall. If you don't have this stack, use
``LexicalBackend`` (the default) or write your own backend.

JSON contract: the script reads a JSON request on argv/stdin
``{"query": str, "scope": str|null, "limit": int}`` and prints a JSON array of
``{"text": str, "score": float, "scope": str, "source": str, "timestamp": str}``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .base import Record


class HermesLanceDBBackend:
    """Adapter wrapping a Node-based LanceDB hybrid search script."""

    def __init__(
        self,
        search_script: str | Path,
        node_bin: str = "node",
        timeout: float = 30.0,
        db_path: Optional[str | Path] = None,
    ):
        self.search_script = Path(search_script).expanduser()
        self.node_bin = node_bin
        self.timeout = timeout
        self.db_path = str(Path(db_path).expanduser()) if db_path else None
        self.degraded = False

    def available(self) -> bool:
        return bool(shutil.which(self.node_bin)) and self.search_script.exists()

    def search(self, query: str, scope: str | None = None, limit: int = 5) -> list[Record]:
        if not self.available():
            # Honest signal: caller should fall back to a lexical backend.
            self.degraded = True
            return []
        request = json.dumps({"query": query, "scope": scope, "limit": limit})
        env_args = [self.node_bin, str(self.search_script)]
        try:
            proc = subprocess.run(
                env_args,
                input=request,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
            rows = json.loads(proc.stdout or "[]")
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            self.degraded = True
            return []
        results: list[Record] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            results.append(
                Record(
                    text=str(row.get("text", "")),
                    score=float(row.get("score", 0.0) or 0.0),
                    scope=str(row.get("scope", "global")),
                    source=str(row.get("source", "")),
                    timestamp=str(row.get("timestamp", "")),
                    meta={
                        k: v
                        for k, v in row.items()
                        if k not in {"text", "score", "scope", "source", "timestamp"}
                    },
                )
            )
        return results
