"""Tests for the freshness sentinel: FRESH/STALE boundary, MISSING, overall."""
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from agent_memory.freshness import FRESH, MISSING, STALE, Product, evaluate, run


def _touch(path: Path, age_hours: float) -> None:
    path.write_text("x", encoding="utf-8")
    when = time.time() - age_hours * 3600
    os.utime(path, (when, when))


def test_fresh_within_cadence(tmp_path):
    p = tmp_path / "fresh.json"
    _touch(p, age_hours=1)
    prod = Product("fresh", p, cadence_hours=24, grace=0.5)  # deadline 36h
    result = evaluate(prod, datetime.now())
    assert result["status"] == FRESH


def test_stale_past_deadline(tmp_path):
    p = tmp_path / "stale.json"
    _touch(p, age_hours=40)  # > 36h deadline
    prod = Product("stale", p, cadence_hours=24, grace=0.5)
    result = evaluate(prod, datetime.now())
    assert result["status"] == STALE
    assert result["ageHours"] >= 39


def test_boundary_exact(tmp_path):
    p = tmp_path / "edge.json"
    prod = Product("edge", p, cadence_hours=10, grace=0.0)  # deadline exactly 10h
    ts = datetime.now()
    _touch(p, age_hours=0)
    # 9h old -> fresh; 11h old -> stale
    assert evaluate(prod, ts + timedelta(hours=9))["status"] == FRESH
    assert evaluate(prod, ts + timedelta(hours=11))["status"] == STALE


def test_missing_product(tmp_path):
    prod = Product("ghost", tmp_path / "nope.json", cadence_hours=24)
    result = evaluate(prod, datetime.now())
    assert result["status"] == MISSING
    assert result["ageHours"] is None


def test_run_overall_precedence(tmp_path):
    fresh = tmp_path / "f.json"
    stale = tmp_path / "s.json"
    _touch(fresh, 1)
    _touch(stale, 100)
    missing = Product("m", tmp_path / "gone.json", cadence_hours=24)
    report = run([
        Product("f", fresh, cadence_hours=24),
        Product("s", stale, cadence_hours=24),
        missing,
    ])
    # MISSING dominates overall.
    assert report["overall"] == MISSING
    assert "s" in report["staleKeys"]
    assert "m" in report["missingKeys"]
