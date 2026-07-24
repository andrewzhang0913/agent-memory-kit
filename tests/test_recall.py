"""Tests for recall: lexical backend scoring, scope filter, fallback chain."""
from agent_memory.journal import Journal
from agent_memory.recall import Recall
from agent_memory.backends.base import Record
from agent_memory.backends.lexical import LexicalBackend


def _seed(config):
    j = Journal(config=config)
    ov = {"agent_id": "researcher", "memory_scope": "global"}
    sid = j.start_session("investigate deploy timeout", identity_overrides=ov)
    j.log_action("gateway bridge killed the morning job at 8s timeout", sid=sid, identity_overrides=ov)
    j.log_action("unrelated note about coffee", sid=sid, identity_overrides=ov)
    j.end_session(sid, identity_overrides=ov)


def test_lexical_recall_ranks_relevant_first(config):
    _seed(config)
    backend = LexicalBackend(config=config)
    hits = backend.search("morning job timeout", limit=3)
    assert hits
    assert "timeout" in hits[0].text.lower()


def test_lexical_recall_scope_filter(config):
    _seed(config)
    backend = LexicalBackend(config=config)
    # Records were written to global; an agent-scope filter yields nothing.
    assert backend.search("timeout", scope="agent:writer") == []
    assert backend.search("timeout", scope="global")


def test_recall_reports_degraded_for_lexical(config):
    _seed(config)
    recall = Recall(config=config)
    hits = recall.search("timeout", limit=2)
    assert hits
    assert recall.last_backend == "LexicalBackend"
    assert recall.degraded is True  # lexical is honestly flagged as non-semantic


def test_recall_falls_back_when_primary_empty(config):
    _seed(config)

    class EmptyBackend:
        degraded = False

        def search(self, query, scope=None, limit=5):
            return []

    recall = Recall(primary=EmptyBackend(), fallbacks=[LexicalBackend(config=config)])
    hits = recall.search("timeout", limit=2)
    assert hits
    assert recall.last_backend == "LexicalBackend"


def test_recall_handles_raising_primary(config):
    _seed(config)

    class BrokenBackend:
        degraded = False

        def search(self, query, scope=None, limit=5):
            raise RuntimeError("boom")

    recall = Recall(primary=BrokenBackend(), fallbacks=[LexicalBackend(config=config)])
    hits = recall.search("timeout", limit=2)
    assert hits  # fell through the exception to the lexical fallback
