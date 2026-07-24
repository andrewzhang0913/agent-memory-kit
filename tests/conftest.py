"""Shared fixtures: isolated memory store + example identity registry."""
import json
from pathlib import Path

import pytest

from agent_memory.config import MemoryConfig

EXAMPLE_REGISTRY = {
    "version": 1,
    "defaultAgentId": "researcher",
    "aliasToCanonical": {"researcher": "researcher", "res": "researcher", "writer": "writer"},
    "agents": {
        "researcher": {
            "displayName": "Research Agent",
            "aliases": ["res"],
            "defaultMemoryScope": "agent:researcher",
            "sharedMemoryScopes": ["global"],
            "allowedMemoryScopes": ["agent:researcher", "global"],
        },
        "writer": {
            "displayName": "Writer Agent",
            "defaultMemoryScope": "agent:writer",
            "sharedMemoryScopes": ["global"],
            "allowedMemoryScopes": ["agent:writer"],
        },
    },
}


@pytest.fixture
def config(tmp_path: Path) -> MemoryConfig:
    cfg = MemoryConfig(home=tmp_path)
    cfg.ensure_dirs()
    cfg.identity_registry_path.write_text(
        json.dumps(EXAMPLE_REGISTRY), encoding="utf-8"
    )
    return cfg
