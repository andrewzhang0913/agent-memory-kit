# Design principles

The kit exists to encode a few hard-won principles. They came from a
long-running multi-agent memory system where the recurring failure was never a
crash — it was **silence**: a memory product that quietly went empty, stale, or
mis-attributed, and was trusted anyway.

## 1. No memory, no intelligence — stale memory is worse than none

An agent without memory is merely forgetful. An agent acting on *wrong* or
*stale* memory is confidently wrong. So the development frontier is not "add
more memory features" but **close the half-open loops** where bad memory flows
downstream undetected. The freshness sentinel and the LLM client's explicit
failure both exist for this reason.

## 2. Failure must be explicit, never silent

`chat()` raises `LLMError` when every tier is exhausted. It never returns an
empty string that a caller might persist as if it were a real answer. The
caller decides what to do with failure (skip this round, fall back to a
deterministic path) — but it always *knows* failure happened.

This principle is why a real incident — a background job whose subprocess
timeout was too short — could silently stall for days: the failure was
swallowed. The kit's contract is the opposite: surface it.

## 3. Validation is the pass condition, not a post-check

In the LLM ladder, a tier "succeeds" only if its output passes the validator.
Empty content (e.g. a "thinking" model that spends its whole token budget on a
hidden reasoning field and returns nothing) is **rejected**, and the ladder
falls through to the next tier. Validators (`non_empty_text`, `json_object`,
or your own) are how a tier proves it actually answered.

## 4. Tiers are an ordered ladder; missing credentials drop silently

Resilience is expressed as an ordered list of tiers, each with its own timeout
and one retry on transient errors. A tier lacking credentials/config is dropped
silently, so a ladder is always best-effort and can end on a local safety net.
Adding or reordering fallbacks is a data change (the tier list), not a control-
flow rewrite.

## 5. Be honest about degraded modes

Recall backends carry a `degraded` flag. The zero-dep lexical backend reports
`degraded=True` because it is not semantic — callers can surface that to a user
rather than presenting weak lexical hits as if they were vector-quality recall.
Honesty about *how* an answer was produced is part of correctness.

## 6. Identity is authored, never faked

Every record carries who wrote it. When identity can't be resolved, it's marked
(`legacy-inferred`, `unknown`) rather than given a plausible-looking but false
author. See [identity-model.md](identity-model.md).

## 7. Destructive lifecycle actions are manual by default

Merging, forgetting, and downranking memory are powerful and irreversible-ish.
The safe default is a **flag-only queue**: detect duplicates/conflicts/staleness
and surface them, but require human confirmation before mutating. Automatic
forgetting is deliberately out of scope for this kit.

## 8. One choke point for location

All paths route through `MemoryConfig`. Relocating the entire store is one env
var (`AGENT_MEMORY_HOME`) or one constructor argument — never a code edit.
