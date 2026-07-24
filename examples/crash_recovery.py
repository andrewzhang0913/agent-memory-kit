"""Crash recovery: pick up a task that was interrupted mid-flight.

The pain this solves: a process is killed (OOM, ctrl-C, deploy restart) while a
session is still open. Nothing called ``end_session``. On the next run the agent
must be able to notice the dangling session and continue it, instead of losing
the thread or starting blind.

Because the journal is append-only and every action is flushed to disk as it
happens, the work already logged survives the crash. ``find_open_session_ids``
surfaces the session that was never closed.

Run:

    python examples/crash_recovery.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from agent_memory import Journal, MemoryConfig, Recall


def _identity() -> dict:
    return {"agent_id": "coder", "memory_scope": "global"}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="agent-memory-crash-"))
    config = MemoryConfig(home=tmp)
    config.ensure_dirs()
    registry_src = Path(__file__).parent / "identity_registry.example.json"
    shutil.copy(registry_src, config.identity_registry_path)
    print(f"Demo store: {tmp}\n")

    ident = _identity()

    # --- Run 1: work starts, logs progress, then the process is KILLED ---------
    # We simulate the crash by simply never calling end_session().
    print("Run 1 (interrupted):")
    journal = Journal(config=config)
    sid = journal.start_session("migrate the users table to add a jti column", identity_overrides=ident)
    journal.log_action("wrote migration 045; applied on the local db", sid=sid, identity_overrides=ident)
    journal.log_action("started backfilling existing rows...", sid=sid, identity_overrides=ident)
    print("  <process killed here — end_session never ran>\n")

    # --- Run 2: fresh process. Did we lose the thread? --------------------------
    # A brand-new Journal instance, as if the program restarted from scratch.
    print("Run 2 (restart):")
    fresh = Journal(config=config)
    open_sessions = fresh.find_open_session_ids(agent_id="coder")
    if not open_sessions:
        print("  no dangling session found (unexpected)")
        return

    resume_sid = fresh.find_last_open_session_id(agent_id="coder")
    print(f"  found dangling session to resume: {resume_sid}")

    # The work logged before the crash is still there — recall proves it.
    recall = Recall(config=config)
    print("  recovered context from before the crash:")
    for h in recall.search("migration users table jti backfill", scope="global", limit=5):
        print(f"    [{h.score}] {h.text[:64]}")

    # Continue the SAME session and close it out cleanly this time.
    fresh.log_action("resumed: finished the backfill, verified row counts", sid=resume_sid, identity_overrides=ident)
    fresh.end_session(resume_sid, identity_overrides=ident)

    remaining = fresh.find_open_session_ids(agent_id="coder")
    print(f"\n  open sessions after clean close: {remaining or 'none'} — thread recovered, not lost")


if __name__ == "__main__":
    main()
