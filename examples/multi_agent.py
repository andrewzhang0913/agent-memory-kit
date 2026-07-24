"""Multi-agent collaboration: shared context written once, read by everyone.

The pain this solves: when a second agent picks up a task, it should NOT need
the background re-explained. One agent writes shared facts to the ``global``
scope; another agent recalls them without any hand-off. Private notes stay
private to each agent, and a write to a scope an agent isn't allowed to touch is
rejected — not silently accepted.

Run:

    python examples/multi_agent.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from agent_memory import Journal, MemoryConfig, Recall
from agent_memory.identity import validate_memory_scope_for_actor, resolve_actor_identity


def _identity(agent_id: str, scope: str) -> dict:
    return {"agent_id": agent_id, "memory_scope": scope}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="agent-memory-multi-"))
    config = MemoryConfig(home=tmp)
    config.ensure_dirs()
    # Registry defines three agents (researcher / writer / coder), each allowed
    # its own agent:<id> scope plus the shared global scope.
    registry_src = Path(__file__).parent / "identity_registry.example.json"
    shutil.copy(registry_src, config.identity_registry_path)
    print(f"Demo store: {tmp}\n")

    journal = Journal(config=config)

    # 1) The researcher establishes shared context in the GLOBAL scope.
    #    This is the background that would otherwise be re-explained to whoever
    #    picks up the task next.
    res = _identity("researcher", "global")
    sid = journal.start_session("investigate the deploy timeout", identity_overrides=res)
    journal.log_action(
        "root cause: gateway bridge kills the morning job at an 8s timeout",
        sid=sid,
        identity_overrides=res,
    )
    journal.log_action(
        "fix agreed: raise bridge timeout to 150s; job then completes in ~95s",
        sid=sid,
        identity_overrides=res,
    )
    journal.end_session(sid, identity_overrides=res)
    print()

    # 2) The researcher also keeps a PRIVATE note in its own agent scope.
    journal.log_action(
        "personal reminder: double-check the OpenRouter fallback tier next time",
        identity_overrides=_identity("researcher", "agent:researcher"),
    )
    print()

    # 3) A DIFFERENT agent (the coder) picks up the task cold and recalls the
    #    shared context — no hand-off, no re-explaining.
    recall = Recall(config=config)
    print("Coder recalls shared context (scope=global):")
    for h in recall.search("why does the morning job fail", scope="global", limit=5):
        print(f"  [{h.score}] {h.text[:72]}")
    print()

    # 4) The scope guardrail: the coder may NOT write to the researcher's
    #    private scope. This is rejected, not silently accepted.
    intruder = resolve_actor_identity(
        _identity("coder", "agent:researcher"), config=config
    )
    try:
        validate_memory_scope_for_actor(intruder, strict=True)
        print("guardrail FAILED — cross-agent write should have been rejected")
    except ValueError as exc:
        print(f"Guardrail held — coder blocked from researcher's private scope:\n  {exc}")


if __name__ == "__main__":
    main()
