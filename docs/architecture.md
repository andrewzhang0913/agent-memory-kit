# Architecture

agent-memory-kit is a **local-first, file-backed layered memory** for AI agents.
Data flows upward from raw events to distilled knowledge; each layer has a
distinct store and a distinct refresh cadence.

## The layered model

### L1 — Working memory / black box (`journal.py`)

An append-only JSONL **operation journal**. Every record is one JSON line,
stamped with a resolved `actor` identity, `agentId`, `memoryScope`, `taskOwner`,
and `ts`. Three verbs: `start`, `log`, `end`.

This is the rawest, most trustworthy layer — nothing mutates it, higher layers
are *derived* from it. A **single-active-session** policy auto-closes dangling
sessions when a new one starts, so consumers never see two concurrent open
sessions from one actor.

### L2 — Episodic memory (application-layer)

Periodic human-readable summaries built by reading L1 (e.g. daily notes). This
is deployment-specific (it depends on how you want to organize summaries), so
the kit documents the concept but does not ship an opinionated implementation.

### L3 — Semantic memory + recall

Durable, queryable knowledge:

- **Recall** (`recall.py` + `backends/`) — answers "what past memory is relevant
  to this query?" via a pluggable `RecallBackend`. The zero-dependency
  `LexicalBackend` scores journal records by term overlap; richer backends
  (vector stores) implement the same protocol. See
  [recall-backends.md](recall-backends.md).
- **Entity/time index** (`entity_index.py`) — a no-LLM, explainable index that
  extracts entity mentions and dates from the journal, building an inverted
  entity→records map plus a date index. Complements vector recall for "what do
  I know about X" / "what happened around date Y".
- **Distillation** (`distiller.py`) — an example LLM consumer that turns recent
  episodic text into durable "lessons", using the resilient LLM client.

### L4 — Lifecycle (merge / forget / downrank)

The safety-critical layer. The original system keeps this as a **manual
confirmation queue**: it flags duplicates, conflicts, and staleness, but
**never auto-deletes, merges, or downranks**. The kit documents this stance as
a design principle (see [design-principles.md](design-principles.md)); automatic
lifecycle mutation is deliberately out of scope.

## Cross-cutting components

### Resilient LLM client (`llm.py`)

A stdlib-only `chat()` with an ordered tier ladder. Each consumer task (distill,
classify, review, summarize) is "LLM call + structured output + persist", so
they all share one resilient client rather than each reimplementing timeout /
retry / validation. See [design-principles.md](design-principles.md).

### Identity & scope model (`identity.py`)

Resolves *which agent am I*, *who wrote this record*, *who owns this task*, and
enforces a write-time memory-scope guardrail. See
[identity-model.md](identity-model.md).

### Freshness sentinel (`freshness.py`)

Generalizes "a memory product silently stopped refreshing" into automatic
detection: each product declares a cadence; the sentinel reports
`FRESH`/`STALE`/`MISSING`. The sentinel is itself a memory product, so it can be
watched by the same mechanism.

## Data flow

```
agent action ──▶ L1 journal (append-only, identity-stamped)
                   │
                   ├──▶ recall backend  ──▶ "what's relevant to X?"
                   ├──▶ entity index    ──▶ "what do I know about X / around date Y?"
                   └──▶ distiller (LLM) ──▶ durable lessons (L3 semantic)

freshness sentinel ──▶ watches every consumed product's refresh cadence
```

## Configuration

Everything routes through `config.py` (`MemoryConfig`). The default store is
`./.agent-memory` under the working directory, overridable by `AGENT_MEMORY_HOME`
or by passing a `MemoryConfig` explicitly. There are **no machine-specific or
personal paths** baked in.
