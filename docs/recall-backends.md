# Recall backends

Recall answers "what past memory is relevant to this query?". The kit makes the
backend pluggable so you can start with zero dependencies and upgrade to a
vector store without changing call sites.

## The protocol

```python
class RecallBackend(Protocol):
    degraded: bool
    def search(self, query: str, scope: str | None = None, limit: int = 5) -> list[Record]: ...
```

- `search` returns up to `limit` `Record`s (see `backends/base.py`) ranked by
  relevance. `scope` optionally restricts to one memory scope (`"global"`,
  `"agent:foo"`); `None` means no filter.
- `degraded` signals the backend is on a reduced-quality path (e.g. lexical-only
  because an embedding service was down), so callers can be honest about it.

A `Record` carries `text`, `score`, `scope`, `source`, `timestamp`, `meta`.

## Built-in: `LexicalBackend` (default, zero-dependency)

Scores journal records by term overlap. No embeddings, no external services —
the library works out of the box. It reports `degraded=True` to be honest that
it is lexical, not semantic.

```python
from agent_memory import Recall
hits = Recall().search("deploy timeout", scope="global", limit=5)
```

## Reference adapter: `HermesLanceDBBackend`

A reference implementation (in `backends/hermes_lancedb.py`) that shells out
to a Node script performing 6-signal hybrid fusion over a LanceDB vector store:

```
score = vector*0.42 + bm25*0.24 + lexical*0.16 + entity*0.10 + temporal*0.05 + importance*0.03
```

with graceful degradation to BM25/lexical/entity/temporal when embeddings are
unavailable. It requires Node.js + a search script + a LanceDB store + an
embedding endpoint — **none installed by the kit**. It exists to (a) show
adapter authors the JSON contract and (b) let an existing deployment keep its
rich recall.

JSON contract: the script reads `{"query", "scope", "limit"}` and prints a JSON
array of `{"text", "score", "scope", "source", "timestamp"}`.

## Built-in: `SqliteVecBackend`

Implements a `RecallBackend` backed by [sqlite-vec](https://github.com/asg017/sqlite-vec), adding real semantic search while keeping the kit's zero-external-service property.

To use it, you must install the optional `sqlite-vec` extra:
```bash
pip install -e ".[sqlite-vec]"
```

It requires you to supply an `embed_fn` callable that turns a string into a list of floats. If the embedding step fails or is unavailable, `SqliteVecBackend` degrades gracefully by returning empty results and setting `degraded=True`, allowing a fallback chain (like `LexicalBackend`) to take over.

`sqlite-vec` also requires a Python `sqlite3` build with loadable-extension
support. Some platform-provided Python builds disable this capability. In that
case the backend marks itself as degraded and returns no results, allowing the
same fallback chain to continue without crashing the caller.

## Fallback chains

`Recall` accepts a primary backend plus fallbacks, mirroring the LLM ladder: try
the rich backend, fall back to a simpler one rather than returning nothing.

```python
from agent_memory import Recall, LexicalBackend
from agent_memory.backends.sqlite_vec import SqliteVecBackend

# Assuming you have an embed_fn(text: str) -> list[float]
sqlite_backend = SqliteVecBackend(embed_fn=my_embed_fn)
recall = Recall(primary=sqlite_backend, fallbacks=[LexicalBackend()])
hits = recall.search("...")
print(recall.last_backend, recall.degraded)
```

A primary that raises or returns empty falls through to the next backend; recall
is best-effort, so an empty result is a valid (if unhelpful) answer rather than
an exception.

## Writing your own backend

Implement the protocol over any store (sqlite-vec, chromadb, pgvector, an API).
Set `degraded` honestly. That's it — no registration step. A proper embedded
vector backend (e.g. **sqlite-vec**, which would keep the zero-external-service
property while adding real semantic search) is a **welcome community
contribution** and is the recommended next backend to add.
