"""Multi-agent identity and memory-scope model.

When several AI agents (or several runs of one agent) share a memory store, three
questions must be answered for every record: *which agent am I*, *who wrote
this record*, and *who owns this task*. This module answers them via a small
JSON registry plus alias normalization.

Two scope types:

* **global** — stable facts every agent may read/write (architecture, shared
  context, contracts).
* **agent:<canonicalId>** — one agent's own work traces / preferences.

Each agent declares ``allowedMemoryScopes``; ``validate_memory_scope_for_actor``
rejects a write that targets a scope the actor is not allowed to use. Identity
that cannot be resolved cleanly is marked honestly (``legacy-inferred`` /
``unknown``) rather than fabricated.

The registry is plain JSON; see ``examples/identity_registry.example.json``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, MemoryConfig

ENV_AGENT_ID = "AGENT_MEMORY_AGENT_ID"
ENV_AGENT_NAME = "AGENT_MEMORY_AGENT_NAME"
ENV_AGENT_ROLE = "AGENT_MEMORY_AGENT_ROLE"
ENV_AGENT_OWNER = "AGENT_MEMORY_AGENT_OWNER"
ENV_AGENT_KIND = "AGENT_MEMORY_AGENT_KIND"
ENV_AGENT_SOURCE = "AGENT_MEMORY_AGENT_SOURCE"
ENV_MEMORY_SCOPE = "AGENT_MEMORY_SCOPE"
ENV_SHARED_SCOPES = "AGENT_MEMORY_SHARED_SCOPES"

# Neutral fallback registry, used only when no registry file exists. It defines
# a single generic agent so the kit works out of the box; real deployments ship
# their own registry JSON.
FALLBACK_REGISTRY: dict[str, Any] = {
    "version": 1,
    "defaultAgentId": "agent",
    "aliasToCanonical": {"agent": "agent", "default": "agent"},
    "agents": {
        "agent": {
            "displayName": "Agent",
            "aliases": ["default"],
            "role": "generic agent",
            "kind": "agent",
            "defaultSource": "cli",
            "defaultMemoryScope": "agent:agent",
            "sharedMemoryScopes": ["global"],
            "notes": "Fallback registry (no registry file found)",
        }
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_agent_identity_registry(config: MemoryConfig | None = None) -> dict[str, Any]:
    cfg = config or DEFAULT_CONFIG
    registry = _read_json(cfg.identity_registry_path)
    if registry:
        return registry
    return FALLBACK_REGISTRY


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _split_csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _clean_text(value)
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def canonicalize_agent_id(agent_id: str | None, registry: dict[str, Any] | None = None) -> str:
    data = registry or load_agent_identity_registry()
    alias_map = data.get("aliasToCanonical", {}) if isinstance(data.get("aliasToCanonical"), dict) else {}
    default_agent_id = _clean_text(data.get("defaultAgentId")) or "agent"
    candidate = _clean_text(agent_id).lower()
    if not candidate:
        return default_agent_id
    if candidate in alias_map:
        return _clean_text(alias_map[candidate]) or default_agent_id
    agents = data.get("agents", {}) if isinstance(data.get("agents"), dict) else {}
    if candidate in agents:
        return candidate
    for canonical_id, raw_definition in agents.items():
        definition = raw_definition if isinstance(raw_definition, dict) else {}
        aliases = [alias.lower() for alias in _split_csv(definition.get("aliases", []))]
        if candidate in aliases:
            return canonical_id
    return candidate


def get_agent_definition(agent_id: str | None, registry: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    data = registry or load_agent_identity_registry()
    canonical_id = canonicalize_agent_id(agent_id, data)
    agents = data.get("agents", {}) if isinstance(data.get("agents"), dict) else {}
    raw_definition = agents.get(canonical_id, {})
    definition = raw_definition if isinstance(raw_definition, dict) else {}
    return canonical_id, definition


def allowed_memory_scopes_for_agent(agent_id: str | None, registry: dict[str, Any] | None = None) -> list[str]:
    data = registry or load_agent_identity_registry()
    canonical_id, definition = get_agent_definition(agent_id, data)
    # An explicit allowedMemoryScopes list is authoritative — we do not widen it.
    explicit = _split_csv(definition.get("allowedMemoryScopes", []))
    if explicit:
        return explicit
    # Otherwise derive the allow-list from default + shared scopes.
    allowed: list[str] = []
    default_scope = _clean_text(definition.get("defaultMemoryScope"))
    if default_scope:
        allowed.append(default_scope)
    for scope in _split_csv(definition.get("sharedMemoryScopes", [])):
        if scope not in allowed:
            allowed.append(scope)
    if not allowed and canonical_id:
        allowed.append(f"agent:{canonical_id}")
    return allowed or ["global"]


def validate_memory_scope_for_actor(
    actor: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    strict: bool = True,
) -> tuple[str, list[str]]:
    data = registry or load_agent_identity_registry()
    canonical_id = _clean_text(actor.get("id")) or "unknown"
    memory_scope = _clean_text(actor.get("memoryScope")) or "global"
    allowed_scopes = allowed_memory_scopes_for_agent(canonical_id, data)
    if memory_scope in allowed_scopes:
        return memory_scope, allowed_scopes
    if strict:
        raise ValueError(
            f"memory scope '{memory_scope}' is not allowed for actor '{canonical_id}'; "
            f"allowed scopes: {', '.join(allowed_scopes)}"
        )
    return memory_scope, allowed_scopes


def resolve_actor_identity(
    overrides: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    fallback_to_default: bool = True,
    config: MemoryConfig | None = None,
) -> dict[str, Any]:
    environment = env or os.environ
    provided = overrides or {}
    registry = load_agent_identity_registry(config)

    requested_agent_id = (
        _clean_text(provided.get("agent_id"))
        or _clean_text(environment.get(ENV_AGENT_ID))
    )
    canonical_id = canonicalize_agent_id(requested_agent_id, registry)
    if not canonical_id and fallback_to_default:
        canonical_id = canonicalize_agent_id(None, registry)

    _, definition = get_agent_definition(canonical_id, registry)
    aliases = _split_csv(provided.get("aliases")) or _split_csv(definition.get("aliases", []))
    shared_scopes = (
        _split_csv(provided.get("shared_memory_scopes"))
        or _split_csv(environment.get(ENV_SHARED_SCOPES))
        or _split_csv(definition.get("sharedMemoryScopes", []))
        or ["global"]
    )
    display_name = _first_text(
        provided.get("display_name"),
        environment.get(ENV_AGENT_NAME),
        definition.get("displayName"),
        canonical_id,
        "unknown",
    )
    role = _first_text(
        provided.get("role"),
        environment.get(ENV_AGENT_ROLE),
        definition.get("role"),
    )
    owner = _first_text(
        provided.get("owner"),
        environment.get(ENV_AGENT_OWNER),
        definition.get("owner"),
        "unknown",
    )
    kind = _first_text(
        provided.get("kind"),
        environment.get(ENV_AGENT_KIND),
        definition.get("kind"),
        "agent",
    )
    source = _first_text(
        provided.get("source"),
        environment.get(ENV_AGENT_SOURCE),
        definition.get("defaultSource"),
        "manual",
    )
    memory_scope = _first_text(
        provided.get("memory_scope"),
        environment.get(ENV_MEMORY_SCOPE),
        definition.get("defaultMemoryScope"),
        "global",
    )
    actor = {
        "id": canonical_id or "unknown",
        "requestedId": requested_agent_id or canonical_id or "unknown",
        "displayName": display_name,
        "aliases": aliases,
        "role": role,
        "owner": owner,
        "kind": kind,
        "source": source,
        "memoryScope": memory_scope,
        "sharedMemoryScopes": shared_scopes,
        "workspace": (
            _clean_text(provided.get("workspace"))
            or cwd
            or _clean_text(definition.get("workspaceHint"))
        ),
        "identityStatus": "explicit" if requested_agent_id else "defaulted",
    }
    if requested_agent_id and requested_agent_id != canonical_id:
        actor["identityStatus"] = "alias-normalized"
    notes = _clean_text(definition.get("notes"))
    if notes:
        actor["notes"] = notes
    return actor


def resolve_task_owner_identity(
    task_owner_id: Any | None,
    *,
    actor: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    fallback_to_actor: bool = True,
) -> dict[str, Any]:
    data = registry or load_agent_identity_registry()
    actor_data = actor or {}
    requested_owner_id = _clean_text(task_owner_id)

    owner_id = ""
    if requested_owner_id:
        owner_id = canonicalize_agent_id(requested_owner_id, data)
    elif fallback_to_actor:
        owner_id = canonicalize_agent_id(actor_data.get("id"), data)
    if not owner_id and fallback_to_actor:
        owner_id = canonicalize_agent_id(None, data)

    _, definition = get_agent_definition(owner_id, data)
    display_name = _first_text(
        definition.get("displayName"),
        actor_data.get("displayName") if actor_data.get("id") == owner_id else "",
        owner_id,
        "unknown",
    )
    role = _first_text(
        definition.get("role"),
        actor_data.get("role") if actor_data.get("id") == owner_id else "",
    )
    kind = _first_text(
        definition.get("kind"),
        actor_data.get("kind") if actor_data.get("id") == owner_id else "",
        "agent",
    )
    ownership_status = "unknown"
    if requested_owner_id:
        ownership_status = "explicit"
        if requested_owner_id != owner_id:
            ownership_status = "alias-normalized"
    elif owner_id:
        ownership_status = "default-actor"

    return {
        "id": owner_id or "unknown",
        "requestedId": requested_owner_id or owner_id or "unknown",
        "displayName": display_name,
        "role": role,
        "kind": kind,
        "ownershipStatus": ownership_status,
    }


def attach_actor_identity(
    record: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    config: MemoryConfig | None = None,
) -> dict[str, Any]:
    identity_overrides = overrides or {}
    registry = load_agent_identity_registry(config)
    actor = resolve_actor_identity(identity_overrides, cwd=os.getcwd(), config=config)
    validate_memory_scope_for_actor(actor, registry=registry)
    task_owner = resolve_task_owner_identity(
        identity_overrides.get("task_owner"),
        actor=actor,
        registry=registry,
    )
    enriched = dict(record)
    enriched["actor"] = actor
    enriched["agentId"] = actor.get("id", "unknown")
    enriched["memoryScope"] = actor.get("memoryScope", "global")
    enriched["taskOwner"] = task_owner
    return enriched


def resolve_record_actor(record: dict[str, Any], fallback_unknown: bool = True) -> dict[str, Any]:
    if isinstance(record.get("actor"), dict):
        actor = dict(record["actor"])
        actor.setdefault("id", _clean_text(record.get("agentId")) or "unknown")
        actor.setdefault("memoryScope", _clean_text(record.get("memoryScope")) or "global")
        actor.setdefault("displayName", actor.get("id", "unknown"))
        actor.setdefault("sharedMemoryScopes", ["global"])
        actor.setdefault("identityStatus", "recorded")
        return actor
    if record.get("agentId") or record.get("memoryScope"):
        actor = resolve_actor_identity(
            {"agent_id": record.get("agentId"), "memory_scope": record.get("memoryScope")},
            fallback_to_default=fallback_unknown,
        )
        actor["identityStatus"] = "legacy-partial"
        return actor
    actor = resolve_actor_identity({"agent_id": None}, fallback_to_default=fallback_unknown)
    actor["identityStatus"] = "legacy-inferred" if fallback_unknown else "unknown"
    return actor


def actor_display(actor: dict[str, Any]) -> str:
    display_name = _clean_text(actor.get("displayName")) or _clean_text(actor.get("id")) or "unknown"
    canonical_id = _clean_text(actor.get("id")) or "unknown"
    label = f"{display_name} [{canonical_id}]"
    status = _clean_text(actor.get("identityStatus"))
    if status and status not in {"recorded", "explicit"}:
        label += f" ({status})"
    return label


def add_identity_arguments(parser: Any) -> None:
    parser.add_argument("--agent-id", help="Canonical or alias agent identity")
    parser.add_argument("--agent-name", help="Actor display name override")
    parser.add_argument("--agent-role", help="Actor role override")
    parser.add_argument("--agent-source", help="Source/runtime marker override")
    parser.add_argument("--memory-scope", help="Primary memory scope override")
    parser.add_argument("--shared-memory-scopes", help="Comma-separated shared memory scopes")
    parser.add_argument("--task-owner", help="Canonical or alias task owner identity")


def identity_overrides_from_args(args: Any) -> dict[str, Any]:
    return {
        "agent_id": getattr(args, "agent_id", None),
        "display_name": getattr(args, "agent_name", None),
        "role": getattr(args, "agent_role", None),
        "source": getattr(args, "agent_source", None),
        "memory_scope": getattr(args, "memory_scope", None),
        "shared_memory_scopes": getattr(args, "shared_memory_scopes", None),
        "task_owner": getattr(args, "task_owner", None),
    }
