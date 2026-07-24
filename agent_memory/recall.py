"""High-level memory recall facade.

Wraps a ``RecallBackend`` (default: the zero-dep lexical backend) and offers an
optional fallback chain — mirroring the resilient-LLM-client philosophy: try the
rich backend, fall back to a simpler one rather than returning nothing, and be
explicit when running degraded.
"""
from __future__ import annotations

from typing import Optional

from .backends.base import RecallBackend, Record
from .backends.lexical import LexicalBackend
from .config import MemoryConfig


class Recall:
    """Recall over one primary backend with optional fallbacks.

    Example::

        recall = Recall()                      # lexical default
        hits = recall.search("deploy timeout", scope="global", limit=5)

        # rich primary with lexical fallback:
        recall = Recall(primary=my_vector_backend, fallbacks=[LexicalBackend()])
    """

    def __init__(
        self,
        primary: Optional[RecallBackend] = None,
        fallbacks: Optional[list[RecallBackend]] = None,
        config: Optional[MemoryConfig] = None,
    ):
        self.primary = primary or LexicalBackend(config=config)
        self.fallbacks = fallbacks or []
        self.last_backend: str = ""
        self.degraded: bool = False

    def search(self, query: str, scope: str | None = None, limit: int = 5) -> list[Record]:
        chain = [self.primary, *self.fallbacks]
        last_exc: Optional[Exception] = None
        for backend in chain:
            try:
                results = backend.search(query, scope=scope, limit=limit)
            except Exception as exc:  # noqa: BLE001 - try next backend
                last_exc = exc
                continue
            if results:
                self.last_backend = type(backend).__name__
                self.degraded = bool(getattr(backend, "degraded", False))
                return results
        # Nothing matched anywhere. Surface degraded state from the last backend.
        self.last_backend = type(chain[-1]).__name__ if chain else ""
        self.degraded = bool(getattr(chain[-1], "degraded", False)) if chain else True
        if last_exc and all(
            isinstance(getattr(b, "degraded", False), bool) for b in chain
        ):
            # every backend errored — return empty rather than raise; recall is
            # best-effort, an empty result is a valid (if unhelpful) answer.
            pass
        return []
