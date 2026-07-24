"""Tests for the append-only journal: roundtrip, single-active-session, guardrail."""
import json

import pytest

from agent_memory.journal import Journal


def _read_records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_write_read_roundtrip(config):
    j = Journal(config=config)
    ov = {"agent_id": "researcher", "memory_scope": "global"}
    sid = j.start_session("goal one", identity_overrides=ov)
    j.log_action("did a thing", sid=sid, identity_overrides=ov)
    j.end_session(sid, identity_overrides=ov)

    records = _read_records(config.journal_path)
    types = [r["type"] for r in records]
    assert types == ["start", "log", "end"]
    assert all(r["agentId"] == "researcher" for r in records)
    assert all(r["memoryScope"] == "global" for r in records)
    assert all("ts" in r and "actor" in r and "taskOwner" in r for r in records)


def test_single_active_session_auto_closes_stale(config):
    j = Journal(config=config)
    ov = {"agent_id": "researcher", "memory_scope": "global"}
    sid1 = j.start_session("first", identity_overrides=ov)
    sid2 = j.start_session("second", identity_overrides=ov)

    assert sid1 != sid2
    # Starting the second session must have auto-closed the first.
    open_now = j.find_open_session_ids()
    assert open_now == [sid2]
    records = _read_records(config.journal_path)
    superseded = [r for r in records if r.get("status") == "superseded_by_new_session"]
    assert len(superseded) == 1
    assert superseded[0]["sid"] == sid1


def test_active_sessions_are_isolated_per_agent(config):
    j = Journal(config=config)
    researcher = {"agent_id": "researcher", "memory_scope": "global"}
    writer = {"agent_id": "writer", "memory_scope": "agent:writer"}

    researcher_sid = j.start_session("research", identity_overrides=researcher)
    writer_sid = j.start_session("write", identity_overrides=writer)

    assert j.find_open_session_ids(agent_id="researcher") == [researcher_sid]
    assert j.find_open_session_ids(agent_id="writer") == [writer_sid]
    assert j.find_open_session_ids() == [researcher_sid, writer_sid]
    assert not [
        record
        for record in _read_records(config.journal_path)
        if record.get("status") == "superseded_by_new_session"
    ]


def test_scope_guardrail_rejects_disallowed_scope(config):
    j = Journal(config=config)
    # 'writer' is only allowed agent:writer, not global.
    with pytest.raises(ValueError):
        j.start_session(
            "blocked",
            identity_overrides={"agent_id": "writer", "memory_scope": "global"},
        )


def test_alias_normalizes_to_canonical(config):
    j = Journal(config=config)
    sid = j.start_session(
        "via alias",
        identity_overrides={"agent_id": "res", "memory_scope": "global"},
    )
    records = _read_records(config.journal_path)
    assert records[0]["agentId"] == "researcher"  # 'res' -> 'researcher'
    assert records[0]["actor"]["identityStatus"] == "alias-normalized"
    j.end_session(sid, identity_overrides={"agent_id": "res", "memory_scope": "global"})
