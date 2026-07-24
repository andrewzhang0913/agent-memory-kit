"""Append-only "black box" operation journal (L1 working memory).

Every record is one JSON line, stamped with a resolved ``actor`` identity,
``agentId``, ``memoryScope`` and ``taskOwner`` (see ``identity.py``). Three verbs:
``start --goal``, ``log --action``, ``end --status``.

Single-active-session policy: starting a new session auto-closes any dangling
open sessions, so downstream consumers never see two concurrent open sessions
from the same actor.

The journal is the rawest layer; higher layers (episodic summaries, semantic
distillation) are built by reading it, never by mutating it.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any, Optional

from .config import DEFAULT_CONFIG, MemoryConfig
from .identity import (
    add_identity_arguments,
    attach_actor_identity,
    identity_overrides_from_args,
    resolve_actor_identity,
)


class Journal:
    """Append-only JSONL operation journal."""

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.path = self.config.journal_path

    def _append(self, data: dict[str, Any], identity_overrides: Optional[dict] = None) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = attach_actor_identity(data, identity_overrides, config=self.config)
        payload["ts"] = datetime.now().isoformat()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def _iter_records(self):
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def has_records_for_date(self, date_str: str) -> bool:
        return any(
            str(r.get("ts", "")).startswith(date_str) for r in self._iter_records()
        )

    def find_open_session_ids(self, agent_id: Optional[str] = None) -> list[str]:
        session_state: dict[str, str] = {}
        for record in self._iter_records():
            record_agent_id = record.get("agentId") or (record.get("actor") or {}).get("id")
            if agent_id and record_agent_id != agent_id:
                continue
            sid = record.get("sid")
            if not sid:
                continue
            if record.get("type") == "start":
                session_state[sid] = "open"
            elif record.get("type") == "end":
                session_state[sid] = "closed"
        return [sid for sid, state in session_state.items() if state == "open"]

    def find_last_open_session_id(self, agent_id: Optional[str] = None) -> Optional[str]:
        open_sessions = self.find_open_session_ids(agent_id=agent_id)
        return open_sessions[-1] if open_sessions else None

    def start_session(
        self, goal: str, sid: Optional[str] = None, identity_overrides: Optional[dict] = None
    ) -> str:
        sid = sid or datetime.now().strftime("s_%Y%m%d_%H%M%S_%f")
        actor = resolve_actor_identity(identity_overrides, config=self.config)
        # Single-active-session: close dangling sessions before opening a new one,
        # so one actor never carries two concurrent open sessions. Other agents
        # remain independent and may work concurrently in the shared journal.
        stale = [s for s in self.find_open_session_ids(agent_id=actor["id"]) if s != sid]
        for stale_sid in stale:
            self._append(
                {
                    "sid": stale_sid,
                    "type": "end",
                    "action": "Session Ended",
                    "status": "superseded_by_new_session",
                },
                identity_overrides,
            )
        self._append(
            {"sid": sid, "type": "start", "action": "Session Started", "goal": goal},
            identity_overrides,
        )
        if stale:
            print(f"Auto-closed stale sessions: {', '.join(stale)}")
        print(f"Session started: {sid}")
        return sid

    def log_action(
        self,
        action: str,
        files: Optional[list[str]] = None,
        status: str = "ok",
        meta: Optional[dict] = None,
        sid: Optional[str] = None,
        identity_overrides: Optional[dict] = None,
    ) -> None:
        data: dict[str, Any] = {
            "type": "log",
            "action": action,
            "files": files or [],
            "status": status,
            "meta": meta or {},
        }
        if sid:
            data["sid"] = sid
        self._append(data, identity_overrides)
        print(f"Action logged: {action}")

    def end_session(
        self, sid: Optional[str] = None, status: str = "ok", identity_overrides: Optional[dict] = None
    ) -> int:
        if not sid:
            actor = resolve_actor_identity(identity_overrides, config=self.config)
            sid = self.find_last_open_session_id(agent_id=actor["id"])
        if not sid:
            print("No active session found.")
            return 1
        self._append(
            {"sid": sid, "type": "end", "action": "Session Ended", "status": status},
            identity_overrides,
        )
        print(f"Session ended: {sid}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent memory black-box journal")
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--goal", required=True, help="Goal of the session")
    start_parser.add_argument("--sid", help="Optional session ID override")
    add_identity_arguments(start_parser)

    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("--action", required=True, help="Action description")
    log_parser.add_argument("--sid", help="Session ID to attach the log to")
    log_parser.add_argument("--files", nargs="*", help="Files involved")
    log_parser.add_argument("--status", default="ok", choices=["ok", "error"])
    add_identity_arguments(log_parser)

    end_parser = subparsers.add_parser("end")
    end_parser.add_argument("--sid", help="Session ID to end (default: latest open)")
    end_parser.add_argument("--status", default="ok", help="Final status")
    add_identity_arguments(end_parser)

    args = parser.parse_args()
    identity_overrides = identity_overrides_from_args(args)
    journal = Journal()

    try:
        if args.command == "start":
            journal.start_session(args.goal, args.sid, identity_overrides)
        elif args.command == "log":
            journal.log_action(
                args.action, args.files, args.status, sid=args.sid, identity_overrides=identity_overrides
            )
        elif args.command == "end":
            return journal.end_session(args.sid, args.status, identity_overrides)
        else:
            parser.print_help()
    except ValueError as exc:
        print(f"Identity guardrail rejected write: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
