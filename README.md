# agent-memory-kit

[![CI](https://github.com/andrewzhang0913/agent-memory-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/andrewzhang0913/agent-memory-kit/actions/workflows/ci.yml)

**English** | [简体中文](README.zh-CN.md)

A local-first, layered memory kit for AI agents. Plain files, zero required
dependencies, runs offline.

> **No memory, no intelligence — and stale or wrong memory is more dangerous
> than no memory.** This kit is built around *closing the half-open loops*
> where a memory system silently uses empty, stale, or mis-scoped data without
> anyone noticing.

## Why this exists

This kit didn't start as a memory "feature set." It grew out of four concrete
pains from running agents for real, day after day:

| The pain | What the kit does about it |
|----------|----------------------------|
| **The process dies mid-task** (OOM, ctrl-C, deploy restart) and the work-in-progress is lost | Append-only journal — every action is flushed to disk *as it happens*, so nothing already done is lost when the process is killed |
| **A task is interrupted** and the next run starts blind | `find_open_session_ids` surfaces the session that was never closed, so the agent resumes the thread instead of losing it |
| **A second agent picks up the task** and the memory doesn't carry over | Canonical identity + `agent:<id>` scopes give every trace a stable owner, so who-did-what stays legible across agents and runs |
| **Agents collaborate** and you keep re-explaining the same background | A shared `global` scope: write the context once, every agent recalls it — with a write-time guardrail so they can't corrupt each other's private memory |

Each of these is a bug we hit, not a feature we imagined. See it run:
[`examples/crash_recovery.py`](examples/crash_recovery.py) and
[`examples/multi_agent.py`](examples/multi_agent.py).

## What's inside

It distills these patterns into a small, reusable library:

- **Resilient tiered LLM client** — an ordered fallback ladder (upstream →
  OpenRouter → local) with per-tier timeout, retry, and *validation as the pass
  condition* (empty "thinking-model" output is rejected and falls through).
  Failure is explicit (`LLMError`), never a silent empty string.
- **Multi-agent identity & scope model** — canonical IDs + alias normalization,
  `global` vs `agent:<id>` memory scopes, a write-time scope guardrail, and an
  honest authored-trace (identity that can't be resolved is marked, not faked).
- **Append-only black-box journal** — every action recorded as one JSON line
  stamped with actor/scope/task-owner; single-active-session policy.
- **Freshness sentinel** — declare each memory product's expected refresh
  cadence; the sentinel flags `FRESH` / `STALE` / `MISSING` so a job that
  silently stops refreshing is caught automatically.
- **Pluggable recall** — a `RecallBackend` protocol with a zero-dependency
  lexical default and a reference Hermes adapter for an external vector store.

## Install

```bash
pip install -e .          # core (stdlib-only)
pip install -e ".[dev]"   # + pytest
```

Requires Python ≥ 3.10. The core has **no runtime dependencies**.

## Quickstart

```bash
python examples/quickstart.py
```

Records a session → recalls it (lexical backend) → checks freshness → distills
lessons via the LLM ladder (degrades gracefully if no LLM is reachable). Runs
entirely on plain files in a temp dir.

Two more runnable examples map directly to the pains above:

```bash
python examples/crash_recovery.py   # interrupt a session, resume it on restart
python examples/multi_agent.py      # shared context across agents + scope guardrail
```

```python
from agent_memory import Journal, Recall, MemoryConfig

config = MemoryConfig(home="~/.agent-memory")
config.ensure_dirs()

journal = Journal(config=config)
ov = {"agent_id": "researcher", "memory_scope": "global"}
sid = journal.start_session("investigate deploy timeout", identity_overrides=ov)
journal.log_action("raised the bridge timeout from 8s to 150s", sid=sid, identity_overrides=ov)
journal.end_session(sid, identity_overrides=ov)

hits = Recall(config=config).search("why did the job stop", limit=5)
for h in hits:
    print(h.score, h.text)
```

## Architecture at a glance

A layered model where data flows upward from raw events to distilled knowledge:

| Layer | What | Module |
|-------|------|--------|
| L1 | Append-only operation journal (black box) | `journal.py` |
| L2 | Episodic summaries (application-layer) | *example only* |
| L3 | Semantic facts + recall (vector/lexical) + entity index | `recall.py`, `entity_index.py`, `distiller.py` |
| L4 | Lifecycle (merge/forget) — **manual queue, never auto-mutate** | *documented* |

Cross-cutting: the resilient LLM client (`llm.py`), the identity/scope model
(`identity.py`), and the freshness sentinel (`freshness.py`).

See [`docs/architecture.md`](docs/architecture.md),
[`docs/identity-model.md`](docs/identity-model.md),
[`docs/design-principles.md`](docs/design-principles.md), and
[`docs/recall-backends.md`](docs/recall-backends.md).

## Scope of this library

This kit is the **reusable core** extracted from a larger personal system. The
application layer of that system (Obsidian-vault curation, news/weather morning
digests, a Hermes gateway integration) is intentionally **not** shipped —
those are deployment-specific. What's here is the general machinery, and the
Hermes/LanceDB recall path ships only as a *reference adapter* showing the
backend contract. A proper embedded vector backend (e.g. sqlite-vec) is a
welcome community contribution — see [`docs/recall-backends.md`](docs/recall-backends.md).

## License

MIT — see [LICENSE](LICENSE).
