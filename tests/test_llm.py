"""Tests for the resilient LLM client — ladder, validators, explicit failure."""
import pytest

from agent_memory import llm
from agent_memory.llm import LLMError, Tier, chat, json_object, non_empty_text


def _tier(name="t", model="m", base="http://example.test/v1"):
    return Tier(name=name, base_url=base, model=model, timeout=1)


def test_non_empty_text_rejects_blank():
    assert non_empty_text("hello") == "hello"
    with pytest.raises(ValueError):
        non_empty_text("")
    with pytest.raises(ValueError):
        non_empty_text("   ")


def test_json_object_tolerates_fences_and_prose():
    assert json_object('```json\n{"a":1}\n```') == {"a": 1}
    assert json_object('here you go: {"b": 2} done') == {"b": 2}
    with pytest.raises(ValueError):
        json_object("")
    with pytest.raises(ValueError):
        json_object("no json here")


def test_chat_returns_first_valid_tier(monkeypatch):
    calls = []

    def fake_post(tier, messages):
        calls.append(tier.name)
        return "ANSWER"

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    out = chat([{"role": "user", "content": "hi"}], [_tier("a"), _tier("b")])
    assert out == "ANSWER"
    assert calls == ["a"]  # stopped at first success


def test_chat_falls_through_to_next_tier(monkeypatch):
    calls = []

    def fake_post(tier, messages):
        calls.append(tier.name)
        if tier.name == "dead":
            raise ConnectionError("refused")
        return "OK"

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    out = chat(
        [{"role": "user", "content": "hi"}],
        [_tier("dead"), _tier("live")],
        retries=0,
    )
    assert out == "OK"
    assert calls == ["dead", "live"]


def test_chat_rejects_empty_content_and_falls_through(monkeypatch):
    # Simulates a "thinking" model that returns empty content.
    def fake_post(tier, messages):
        return "" if tier.name == "thinker" else "REAL"

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    out = chat(
        [{"role": "user", "content": "hi"}],
        [_tier("thinker"), _tier("gemma")],
        retries=0,
    )
    assert out == "REAL"


def test_chat_raises_when_all_tiers_exhausted(monkeypatch):
    def fake_post(tier, messages):
        raise ConnectionError("refused")

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    with pytest.raises(LLMError):
        chat([{"role": "user", "content": "hi"}], [_tier("a"), _tier("b")], retries=0)


def test_chat_raises_on_empty_ladder():
    with pytest.raises(LLMError):
        chat([{"role": "user", "content": "hi"}], [Tier(name="bad", base_url="", model="")])
