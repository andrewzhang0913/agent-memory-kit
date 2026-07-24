"""agent-memory-kit: a local-first, layered memory kit for AI agents.

Public API:
    - config:   MemoryConfig
    - llm:      chat, Tier, canonical_tiers, gateway_tier, LLMError,
                non_empty_text, json_object
    - identity: resolve_actor_identity, attach_actor_identity,
                validate_memory_scope_for_actor, canonicalize_agent_id
    - journal:  Journal
    - recall:   Recall, Record, LexicalBackend
                HermesLanceDBBackend
    - freshness: Product, run as freshness_run, summary_line
"""
from .config import MemoryConfig, DEFAULT_CONFIG
from .llm import (
    LLMError,
    Tier,
    chat,
    canonical_tiers,
    gateway_tier,
    json_object,
    non_empty_text,
)
from .identity import (
    attach_actor_identity,
    canonicalize_agent_id,
    resolve_actor_identity,
    validate_memory_scope_for_actor,
)
from .journal import Journal
from .recall import Recall
from .backends.base import Record
from .backends.hermes_lancedb import HermesLanceDBBackend
from .backends.lexical import LexicalBackend
from .freshness import Product, run as freshness_run, summary_line

__version__ = "0.1.0"

__all__ = [
    "MemoryConfig",
    "DEFAULT_CONFIG",
    "LLMError",
    "Tier",
    "chat",
    "canonical_tiers",
    "gateway_tier",
    "json_object",
    "non_empty_text",
    "attach_actor_identity",
    "canonicalize_agent_id",
    "resolve_actor_identity",
    "validate_memory_scope_for_actor",
    "Journal",
    "Recall",
    "Record",
    "HermesLanceDBBackend",
    "LexicalBackend",
    "Product",
    "freshness_run",
    "summary_line",
]
