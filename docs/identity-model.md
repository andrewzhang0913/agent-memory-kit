# Identity & scope model

When several agents (or several runs of one agent) share a memory store, three
questions must be answered for **every** record:

1. **Which agent am I?** (actor identity)
2. **Who wrote this record?** (authored trace)
3. **Who owns this task?** (task-owner trace, may differ from the actor)

`identity.py` answers them via a small JSON registry plus alias normalization.

## The registry

A plain JSON file (path from `MemoryConfig.identity_registry_path`). Example:

```json
{
  "version": 1,
  "defaultAgentId": "researcher",
  "aliasToCanonical": { "res": "researcher" },
  "agents": {
    "researcher": {
      "displayName": "Research Agent",
      "aliases": ["res"],
      "defaultMemoryScope": "agent:researcher",
      "sharedMemoryScopes": ["global"],
      "allowedMemoryScopes": ["agent:researcher", "global"]
    }
  }
}
```

See [`examples/identity_registry.example.json`](../examples/identity_registry.example.json).
If no registry file exists, a neutral single-agent fallback is used so the kit
works out of the box.

## Canonical IDs & aliases

`canonicalize_agent_id("res")` → `"researcher"`. Aliases are descriptive only —
they normalize to a canonical ID and must never be written as an author
identity. An unknown ID passes through (lowercased) rather than being silently
remapped, so typos are visible instead of misattributed.

## Two scope types

- **`global`** — stable facts every agent may read (architecture, shared
  context, contracts).
- **`agent:<canonicalId>`** — one agent's own work traces / preferences.

## The write-time scope guardrail

Each agent declares `allowedMemoryScopes`. `validate_memory_scope_for_actor`
**raises** (in strict mode, the default) if a record targets a scope the actor
is not allowed to write. `Journal` calls this on every append, so a mis-scoped
write fails loudly instead of polluting another agent's memory.

`allowedMemoryScopes` is **authoritative when set** — the kit does not widen it.
If you omit it, the allow-list is derived from `defaultMemoryScope` +
`sharedMemoryScopes`.

```python
# 'writer' allows only agent:writer; writing global is rejected:
journal.start_session("x", identity_overrides={"agent_id": "writer", "memory_scope": "global"})
# -> ValueError: memory scope 'global' is not allowed for actor 'writer'
```

## Honest fallbacks

Identity that cannot be resolved cleanly is **marked**, not fabricated:

- `explicit` — an agent id was supplied.
- `alias-normalized` — supplied id was an alias, normalized to canonical.
- `defaulted` — no id supplied, fell back to the registry default.
- `legacy-partial` / `legacy-inferred` / `unknown` — for records that predate
  identity stamping.

A record never gets a fabricated precise author; the status field tells you how
much to trust the attribution.

## Overrides

Identity can be supplied three ways (highest precedence first): explicit
`identity_overrides` dict / CLI args → environment variables
(`AGENT_MEMORY_AGENT_ID`, `AGENT_MEMORY_MEMORY_SCOPE`, …) → registry defaults.
