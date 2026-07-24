"""Quickstart: record -> recall -> distill, on plain local files.

Runs with zero external services. The distill step uses the LLM ladder; if no
LLM is reachable it degrades gracefully and says so. Run:

    python examples/quickstart.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from agent_memory import (
    Journal,
    MemoryConfig,
    Recall,
    Product,
    freshness_run,
    summary_line,
)
from agent_memory.distiller import distill


def main() -> None:
    # Isolated, throwaway store under a temp dir.
    tmp = Path(tempfile.mkdtemp(prefix="agent-memory-demo-"))
    config = MemoryConfig(home=tmp)
    config.ensure_dirs()
    # Install the example identity registry so "researcher" is a defined agent
    # allowed to write the global scope (otherwise the scope guardrail rejects
    # the write — which is the intended safety behavior).
    registry_src = Path(__file__).parent / "identity_registry.example.json"
    shutil.copy(registry_src, config.identity_registry_path)
    print(f"Demo store: {tmp}\n")

    # 1) Record some work into the black-box journal.
    journal = Journal(config=config)
    overrides = {"agent_id": "researcher", "memory_scope": "global"}
    sid = journal.start_session("investigate deploy timeout", identity_overrides=overrides)
    journal.log_action(
        "found gateway bridge killed morning job at 8s timeout; raised to 150s",
        files=["runtime_watch.py"],
        sid=sid,
        identity_overrides=overrides,
    )
    journal.log_action(
        "verified job now completes in ~95s end-to-end",
        sid=sid,
        identity_overrides=overrides,
    )
    journal.end_session(sid, identity_overrides=overrides)
    print()

    # 2) Recall relevant memory (zero-dep lexical backend).
    recall = Recall(config=config)
    hits = recall.search("why did the morning job stop", limit=3)
    print(f"Recall via {recall.last_backend} (degraded={recall.degraded}):")
    for h in hits:
        print(f"  [{h.score}] {h.text[:80]}")
    print()

    # 3) Freshness sentinel over the journal as a 'product'.
    products = [Product("journal", config.journal_path, cadence_hours=24)]
    report = freshness_run(products)
    print("Freshness:", summary_line(report))
    print()

    # 4) Distill lessons via the LLM ladder (degrades if no LLM reachable).
    episodic = "\n".join(h.text for h in hits) or "no recent notes"
    lessons = distill(episodic, on_event=lambda m: print(" ", m))
    if lessons:
        print("\nDistilled lessons:\n" + lessons)
    else:
        print("\nNo LLM reachable (or no new lessons) — recall + journal still work offline.")


if __name__ == "__main__":
    main()
