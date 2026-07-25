"""Tests for sqlite-vec backend."""
import pytest

from agent_memory.backends.base import Record

# Skip entirely if sqlite-vec is not available
pytest.importorskip("sqlite_vec")

from agent_memory.backends.sqlite_vec import SqliteVecBackend


def dummy_embed(text: str) -> list[float]:
    """A dummy embedding that returns a 3-dimensional vector based on simple heuristics."""
    if "timeout" in text.lower():
        return [1.0, 0.0, 0.0]
    if "coffee" in text.lower():
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


def test_sqlite_vec_search_ranks_relevant():
    backend = SqliteVecBackend(embed_fn=dummy_embed)
    backend.add(Record(text="morning job timeout", scope="global"))
    backend.add(Record(text="unrelated note about coffee", scope="global"))
    
    hits = backend.search("timeout", limit=3)
    assert len(hits) > 0
    assert "timeout" in hits[0].text.lower()
    
    hits2 = backend.search("coffee", limit=3)
    assert len(hits2) > 0
    assert "coffee" in hits2[0].text.lower()


def test_sqlite_vec_scope_filter():
    backend = SqliteVecBackend(embed_fn=dummy_embed)
    backend.add(Record(text="morning job timeout", scope="global"))
    backend.add(Record(text="another timeout", scope="agent:foo"))
    
    hits_global = backend.search("timeout", scope="global")
    assert len(hits_global) == 1
    assert hits_global[0].scope == "global"
    
    hits_foo = backend.search("timeout", scope="agent:foo")
    assert len(hits_foo) == 1
    assert hits_foo[0].scope == "agent:foo"


def test_sqlite_vec_limit_respected():
    backend = SqliteVecBackend(embed_fn=dummy_embed)
    backend.add(Record(text="timeout 1", scope="global"))
    backend.add(Record(text="timeout 2", scope="global"))
    backend.add(Record(text="timeout 3", scope="global"))
    
    hits = backend.search("timeout", limit=2)
    assert len(hits) == 2


def test_sqlite_vec_empty_results():
    backend = SqliteVecBackend(embed_fn=dummy_embed)
    # Search on empty db
    hits = backend.search("timeout")
    assert hits == []
    assert backend.degraded is False


def test_sqlite_vec_degraded_when_embed_fails():
    def failing_embed(text: str) -> list[float]:
        raise ValueError("Embedding API down")
        
    backend = SqliteVecBackend(embed_fn=failing_embed)
    hits = backend.search("timeout")
    assert hits == []
    assert backend.degraded is True


def test_sqlite_vec_degraded_when_no_embed_fn():
    backend = SqliteVecBackend()
    hits = backend.search("timeout")
    assert hits == []
    assert backend.degraded is True
