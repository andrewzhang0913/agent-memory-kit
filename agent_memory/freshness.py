"""Memory freshness sentinel.

Every memory product a system *consumes* (a generated report, a digest, a
distilled-facts file) has an expected refresh cadence. When one silently stops
refreshing, downstream code keeps quoting stale conclusions without anyone
noticing. This sentinel generalizes that failure into automatic detection: it
compares each product's file mtime against its expected cadence and reports
FRESH / STALE / MISSING.

The sentinel is itself a memory product (it writes its own report), so it can
be watched by the same mechanism.

Unlike the rest of the kit, the product registry is *caller-supplied* — you
declare the products you care about and their cadences.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DEFAULT_CONFIG, MemoryConfig

FRESH = "FRESH"
STALE = "STALE"
MISSING = "MISSING"


@dataclass
class Product:
    """One consumed memory product and its expected refresh cadence."""

    key: str
    path: Path
    cadence_hours: float
    # Grace multiplier: flag STALE only past cadence * (1 + grace). Absorbs
    # jitter (a daily job that slips a few hours) without false alarms.
    grace: float = 0.5
    note: str = ""

    def deadline_hours(self) -> float:
        return self.cadence_hours * (1.0 + self.grace)


def _mtime(path: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def evaluate(product: Product, now: datetime) -> dict:
    ts = _mtime(product.path)
    if ts is None:
        return {
            "key": product.key,
            "status": MISSING,
            "path": str(product.path),
            "ageHours": None,
            "cadenceHours": product.cadence_hours,
            "deadlineHours": round(product.deadline_hours(), 1),
            "lastRefresh": None,
            "note": product.note,
        }
    age_hours = (now - ts).total_seconds() / 3600.0
    status = STALE if age_hours > product.deadline_hours() else FRESH
    return {
        "key": product.key,
        "status": status,
        "path": str(product.path),
        "ageHours": round(age_hours, 1),
        "cadenceHours": product.cadence_hours,
        "deadlineHours": round(product.deadline_hours(), 1),
        "lastRefresh": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "note": product.note,
    }


def run(products: list[Product], now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    items = [evaluate(p, now) for p in products]
    stale = [i["key"] for i in items if i["status"] == STALE]
    missing = [i["key"] for i in items if i["status"] == MISSING]
    if missing:
        overall = MISSING
    elif stale:
        overall = STALE
    else:
        overall = FRESH
    return {
        "kind": "memory-freshness",
        "generatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "overall": overall,
        "staleKeys": stale,
        "missingKeys": missing,
        "products": items,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Memory Freshness Sentinel",
        "",
        f"- generatedAt: {report['generatedAt']}",
        f"- overall: {report['overall']}",
        f"- staleKeys: {', '.join(report['staleKeys']) or 'none'}",
        f"- missingKeys: {', '.join(report['missingKeys']) or 'none'}",
        "",
        "## Products",
        "",
        "| key | status | ageHours | deadlineHours | lastRefresh | note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for i in report["products"]:
        lines.append(
            f"| {i['key']} | {i['status']} | {i['ageHours']} | "
            f"{i['deadlineHours']} | {i['lastRefresh'] or 'n/a'} | {i['note']} |"
        )
    return "\n".join(lines) + "\n"


def summary_line(report: dict) -> str:
    """One-line status, suitable for a shared snapshot."""
    overall = report["overall"]
    if overall == FRESH:
        return f"{FRESH} | all {len(report['products'])} products within cadence"
    flagged = report["staleKeys"] + report["missingKeys"]
    return f"{overall} | stale/missing: {', '.join(flagged)}"


def write_outputs(report: dict, config: Optional[MemoryConfig] = None) -> Path:
    cfg = config or DEFAULT_CONFIG
    cfg.freshness_dir.mkdir(parents=True, exist_ok=True)
    json_path = cfg.freshness_dir / "memory-freshness-latest.json"
    md_path = cfg.freshness_dir / "memory-freshness-latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path


def main(products: Optional[list[Product]] = None) -> int:
    """CLI entrypoint.

    Without an explicit product list (the default when run as a script) there is
    nothing to check — real callers import ``run``/``Product`` and supply their
    own registry. We print guidance and exit 0 rather than guessing.
    """
    parser = argparse.ArgumentParser(description="Memory freshness sentinel")
    parser.add_argument("--quiet", action="store_true", help="Only print the summary line")
    args = parser.parse_args()

    if not products:
        print(
            "No product registry supplied. Import agent_memory.freshness and call "
            "run([Product(...), ...]); see docs and examples/quickstart.py."
        )
        return 0

    report = run(products)
    print(summary_line(report) if args.quiet else render_markdown(report))
    write_outputs(report)
    return 2 if report["overall"] == MISSING else 0


if __name__ == "__main__":
    raise SystemExit(main())
