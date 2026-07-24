"""Deterministic entity / time index over the journal.

A no-LLM, explainable index that complements vector recall: it extracts entity
mentions (from a caller-supplied known-entity list plus code-like tokens and
backtick/wiki-link spans) and dates from journal records, and builds an inverted
entity->records map plus a date index. Useful for "what do I know about X" and
"what happened around date Y" lookups without any embedding service.

This is a generic, vault-agnostic distillation of the original system's entity
indexer: it reads the append-only journal only, and takes its entity vocabulary
as configuration rather than hardcoding a personal list.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import DEFAULT_CONFIG, MemoryConfig

DATE_RE = re.compile(r"(20\d{2})[-_/]?([01]\d)[-_/]?([0-3]\d)")
BACKTICK_RE = re.compile(r"`([^`\n]{2,120})`")
WIKI_LINK_RE = re.compile(r"\[\[([^\]\n|#]+)(?:[|#][^\]\n]+)?\]\]")
CODE_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_.:-]{2,}\b")
_STOPWORDS = {"the", "and", "for", "with", "from", "this", "that", "http", "https", "www", "json"}
MAX_ENTITY_PER_DOC = 80


def normalize_entity(value: str) -> str:
    value = value.strip().strip("`[](){}<>,.!?:;")
    value = re.sub(r"\s+", " ", value)
    return value[:120]


def is_noise_entity(value: str) -> bool:
    if len(value) < 2 or len(value) > 120:
        return True
    if value.lower() in _STOPWORDS | {"unknown", "none", "markdown"}:
        return True
    return bool(re.fullmatch(r"\d+", value))


def collect_entities(text: str, known_entities: list[str]) -> list[str]:
    counter: Counter[str] = Counter()
    lowered_text = text.lower()
    for known in known_entities:
        if known.lower() in lowered_text:
            counter[known] += 5
    for pattern in (BACKTICK_RE, WIKI_LINK_RE):
        for match in pattern.findall(text):
            entity = normalize_entity(match if isinstance(match, str) else match[0])
            if not is_noise_entity(entity):
                counter[entity] += 3
    for token in CODE_TOKEN_RE.findall(text):
        if token.lower() in _STOPWORDS:
            continue
        if any(ch in token for ch in "./_-:") or token[:1].isupper() or token.isupper():
            entity = normalize_entity(token)
            if not is_noise_entity(entity):
                counter[entity] += 1
    return [entity for entity, _ in counter.most_common(MAX_ENTITY_PER_DOC)]


def parse_dates(*sources: str) -> list[str]:
    found: list[str] = []
    for source in sources:
        for year, month, day in DATE_RE.findall(source or ""):
            try:
                normalized = datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
            except ValueError:
                continue
            if normalized not in found:
                found.append(normalized)
    return found


def _record_text(record: dict) -> str:
    parts = [
        str(record.get("goal", "")),
        str(record.get("action", "")),
        str(record.get("status", "")),
        " ".join(str(f) for f in record.get("files", []) if f),
    ]
    return "\n".join(p for p in parts if p.strip())


def build_index(
    known_entities: Optional[list[str]] = None,
    config: Optional[MemoryConfig] = None,
) -> dict[str, Any]:
    """Build an entity/time index from the journal.

    ``known_entities`` is your domain vocabulary (project names, tools, people);
    mentions of these get a strong weight. Everything else is discovered from
    code-like tokens and markup spans.
    """
    cfg = config or DEFAULT_CONFIG
    known = known_entities or []
    journal = cfg.journal_path

    documents: list[dict[str, Any]] = []
    if journal.exists():
        for line_no, line in enumerate(journal.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = _record_text(record)
            if not text.strip():
                continue
            ts = str(record.get("ts", ""))
            dates = parse_dates(ts)
            documents.append(
                {
                    "id": f"journal:{line_no}",
                    "type": record.get("type", "record"),
                    "session": record.get("sid", ""),
                    "scope": record.get("memoryScope", ""),
                    "date": dates[0] if dates else "",
                    "timestamp": ts,
                    "entities": collect_entities(text, known),
                    "preview": re.sub(r"\s+", " ", text).strip()[:360],
                }
            )

    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_date: dict[str, list[str]] = defaultdict(list)
    for doc in documents:
        for entity in doc["entities"]:
            by_entity[entity.lower()].append({"entity": entity, "documentId": doc["id"], "date": doc["date"]})
        if doc["date"]:
            by_date[doc["date"]].append(doc["id"])

    top_entities = [
        {"entity": e, "count": len(items)}
        for e, items in sorted(by_entity.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:200]
    ]
    return {
        "kind": "entity-time-index",
        "version": 1,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "documentCount": len(documents),
        "entityCount": len(by_entity),
        "topEntities": top_entities,
        "byDate": dict(by_date),
        "documents": documents,
    }


def write_index(index: dict[str, Any], config: Optional[MemoryConfig] = None) -> Path:
    cfg = config or DEFAULT_CONFIG
    out_path = cfg.home / "index" / "entity_time_index.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path
