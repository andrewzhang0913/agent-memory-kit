"""Tests for the identity model: canonicalization and scope validation."""
import pytest

from agent_memory.identity import (
    allowed_memory_scopes_for_agent,
    attach_actor_identity,
    canonicalize_agent_id,
    load_agent_identity_registry,
    resolve_actor_identity,
    validate_memory_scope_for_actor,
)


def test_alias_to_canonical(config):
    reg = load_agent_identity_registry(config)
    assert canonicalize_agent_id("res", reg) == "researcher"
    assert canonicalize_agent_id("researcher", reg) == "researcher"
    # Unknown id passes through as-is (lowercased).
    assert canonicalize_agent_id("ZZZ", reg) == "zzz"
    # Empty -> default.
    assert canonicalize_agent_id("", reg) == "researcher"


def test_allowed_scopes(config):
    reg = load_agent_identity_registry(config)
    assert set(allowed_memory_scopes_for_agent("researcher", reg)) == {"agent:researcher", "global"}
    assert allowed_memory_scopes_for_agent("writer", reg) == ["agent:writer"]


def test_validate_scope_rejects_disallowed(config):
    reg = load_agent_identity_registry(config)
    actor = {"id": "writer", "memoryScope": "global"}
    with pytest.raises(ValueError):
        validate_memory_scope_for_actor(actor, registry=reg, strict=True)
    # Non-strict returns instead of raising.
    scope, allowed = validate_memory_scope_for_actor(actor, registry=reg, strict=False)
    assert scope == "global"
    assert "global" not in allowed


def test_resolve_actor_marks_alias_normalized(config):
    actor = resolve_actor_identity({"agent_id": "res", "memory_scope": "global"}, config=config)
    assert actor["id"] == "researcher"
    assert actor["identityStatus"] == "alias-normalized"


def test_attach_actor_identity_enriches_record(config):
    record = attach_actor_identity(
        {"type": "log", "action": "x"},
        {"agent_id": "researcher", "memory_scope": "global"},
        config=config,
    )
    assert record["agentId"] == "researcher"
    assert record["memoryScope"] == "global"
    assert record["taskOwner"]["id"] == "researcher"  # defaults to actor
    assert record["actor"]["displayName"] == "Research Agent"
