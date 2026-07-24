"""Central configuration for agent-memory-kit.

Every path and endpoint the kit uses flows through here, resolved from
environment variables with neutral defaults. There is no machine-specific or
personal path baked in — the default data root is ``./.agent-memory`` under the
current working directory, overridable by ``AGENT_MEMORY_HOME``.

This module is the single choke point for "where does my memory live", so a
host application can relocate the whole store by setting one env var or passing
a ``MemoryConfig`` explicitly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_HOME = "AGENT_MEMORY_HOME"
ENV_JOURNAL = "AGENT_MEMORY_JOURNAL"
ENV_REGISTRY = "AGENT_MEMORY_IDENTITY_REGISTRY"

# LLM endpoint/model env overrides (see llm.py).
ENV_UPSTREAM_BASE_URL = "AGENT_MEMORY_LLM_BASE_URL"
ENV_UPSTREAM_MODEL = "AGENT_MEMORY_LLM_MODEL"
ENV_UPSTREAM_API_KEY = "AGENT_MEMORY_LLM_API_KEY"
ENV_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
ENV_LOCAL_BASE_URL = "AGENT_MEMORY_LOCAL_LLM_BASE_URL"
ENV_LOCAL_MODEL = "AGENT_MEMORY_LOCAL_LLM_MODEL"


def _expand(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser()


def default_home() -> Path:
    """Resolve the memory home directory from env, else ./.agent-memory."""
    env_value = os.environ.get(ENV_HOME, "").strip()
    if env_value:
        return _expand(env_value)
    return Path.cwd() / ".agent-memory"


@dataclass
class MemoryConfig:
    """Resolved locations for a memory store.

    Pass an instance explicitly for full control, or call ``MemoryConfig.load()``
    to build one from environment variables.
    """

    home: Path = field(default_factory=default_home)
    journal_path: Path | None = None
    identity_registry_path: Path | None = None
    freshness_dir: Path | None = None

    def __post_init__(self) -> None:
        self.home = _expand(self.home)
        if self.journal_path is None:
            self.journal_path = self.home / "journal" / "operation_journal.jsonl"
        if self.identity_registry_path is None:
            self.identity_registry_path = self.home / "identity_registry.json"
        if self.freshness_dir is None:
            self.freshness_dir = self.home / "freshness"
        self.journal_path = _expand(self.journal_path)
        self.identity_registry_path = _expand(self.identity_registry_path)
        self.freshness_dir = _expand(self.freshness_dir)

    @classmethod
    def load(cls) -> "MemoryConfig":
        """Build a config from environment variables."""
        home = default_home()
        journal = os.environ.get(ENV_JOURNAL, "").strip()
        registry = os.environ.get(ENV_REGISTRY, "").strip()
        return cls(
            home=home,
            journal_path=_expand(journal) if journal else None,
            identity_registry_path=_expand(registry) if registry else None,
        )

    def ensure_dirs(self) -> None:
        """Create the directories backing this config (idempotent)."""
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self.identity_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.freshness_dir.mkdir(parents=True, exist_ok=True)


# A module-level default for callers that don't want to thread config through.
DEFAULT_CONFIG = MemoryConfig.load()
