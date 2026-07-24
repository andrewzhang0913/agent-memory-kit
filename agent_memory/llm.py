"""Unified resilient LLM client.

One ``chat()`` entrypoint with an ordered list of fallback tiers, per-tier
timeout plus one retry on transient errors, and output validation that rejects
the empty content "thinking" models sometimes emit (they spend their whole
token budget on a hidden reasoning field and return empty content, which is
useless as a fallback).

The design contract:

* **Tiers are an ordered ladder.** Each tier gets its own timeout and one retry
  on transient failures. The first tier to return output that passes the
  validator wins; rejected output falls through to the next tier.
* **Failure is explicit.** If every usable tier is exhausted, ``chat`` raises
  ``LLMError`` — it never silently returns empty/None to the caller.
* **Validation is the pass condition, not a post-check.** A tier that returns
  empty or malformed content is treated as "did not answer", so the ladder
  keeps going.
* **Missing credentials drop silently.** A tier with no base_url/model is
  skipped, so a ladder is always best-effort and can end on a local safety net.

Stdlib-only (urllib) so it has zero install dependencies.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import (
    ENV_LOCAL_BASE_URL,
    ENV_LOCAL_MODEL,
    ENV_OPENROUTER_API_KEY,
    ENV_UPSTREAM_API_KEY,
    ENV_UPSTREAM_BASE_URL,
    ENV_UPSTREAM_MODEL,
)

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.S)

# Neutral defaults for the canonical ladder. Override via env (see config.py).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "google/gemma-2-9b-it:free"
# A local OpenAI-compatible server (e.g. Ollama) is the offline safety net.
# Prefer a model that emits content directly rather than a "thinking" model
# that returns empty content under a bounded max_tokens.
LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
LOCAL_MODEL = "llama3.2"


class LLMError(Exception):
    """Raised when every tier in the ladder fails or is unavailable."""


@dataclass
class Tier:
    """One rung of the fallback ladder."""

    name: str
    base_url: str
    model: str
    api_key: Optional[str] = None
    timeout: float = 60.0
    max_tokens: int = 1024
    temperature: float = 0.2
    extra_headers: dict = field(default_factory=dict)

    def usable(self) -> bool:
        return bool(self.base_url and self.model)


# A validator takes the raw assistant content string and returns a parsed
# result, or raises ValueError to reject this tier's output and fall through.
Validator = Callable[[str], object]


def non_empty_text(content: str) -> str:
    """Default validator: reject blank output (e.g. thinking-model empties)."""
    text = (content or "").strip()
    if not text:
        raise ValueError("empty content")
    return text


def json_object(content: str) -> dict:
    """Validator for endpoints expected to return a JSON object.

    Tolerates markdown code fences and prose around the object.
    """
    text = (content or "").strip()
    if not text:
        raise ValueError("empty content")
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
            break
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJ_RE.search(text)
        if not match:
            raise ValueError("no JSON object in content")
        return json.loads(match.group(0))


_INSECURE_CTX = ssl.create_default_context()
_INSECURE_CTX.check_hostname = False
_INSECURE_CTX.verify_mode = ssl.CERT_NONE

# Direct opener that ignores http(s)_proxy env, so local gateway/ollama rungs
# are never routed through a proxy.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _is_local(base_url: str) -> bool:
    return "127.0.0.1" in base_url or "localhost" in base_url


def _post_chat(tier: Tier, messages: list[dict]) -> str:
    """Single HTTP call to one tier; returns raw assistant content or raises."""
    url = f"{tier.base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json", **tier.extra_headers}
    if tier.api_key:
        headers["Authorization"] = f"Bearer {tier.api_key}"
    payload = {
        "model": tier.model,
        "messages": messages,
        "temperature": tier.temperature,
        "max_tokens": tier.max_tokens,
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    if _is_local(tier.base_url):
        with _NO_PROXY_OPENER.open(req, timeout=tier.timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    else:
        with urllib.request.urlopen(req, timeout=tier.timeout, context=_INSECURE_CTX) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"].get("content") or ""


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (408, 409, 425, 429, 500, 502, 503, 504)
    # Timeouts, connection resets, malformed payloads — worth one retry.
    return isinstance(exc, (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError))


def chat(
    messages: list[dict],
    tiers: list[Tier],
    validator: Validator = non_empty_text,
    retries: int = 1,
    on_event: Optional[Callable[[str], None]] = None,
) -> object:
    """Run messages through the tier ladder until one returns valid output.

    Each tier gets ``retries`` extra attempts on transient failures. Output is
    passed through ``validator``; rejected output falls through to the next
    tier. Raises LLMError only if every usable tier is exhausted.
    """
    log = on_event or (lambda _msg: None)
    usable = [t for t in tiers if t.usable()]
    if not usable:
        raise LLMError("no usable LLM tiers configured")

    last_error: Optional[Exception] = None
    for tier in usable:
        for attempt in range(retries + 1):
            try:
                raw = _post_chat(tier, messages)
                return validator(raw)
            except Exception as exc:  # noqa: BLE001 - classified below
                last_error = exc
                detail: object = exc
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        detail = f"{exc.code} {exc.read().decode('utf-8')[:200]}"
                    except Exception:
                        detail = str(exc.code)
                more = attempt < retries and _is_retryable(exc)
                log(
                    f"[llm] tier '{tier.name}' attempt {attempt + 1} failed: "
                    f"{detail}" + ("; retrying" if more else "; moving on")
                )
                if not more:
                    break
                time.sleep(min(2 ** attempt, 4))
    raise LLMError(f"all {len(usable)} LLM tier(s) failed; last error: {last_error}")


def upstream_tier(
    *, timeout: float = 60.0, max_tokens: int = 1024, temperature: float = 0.2
) -> Optional[Tier]:
    """Primary tier from env: a paid/high-quality OpenAI-compatible endpoint."""
    base_url = os.environ.get(ENV_UPSTREAM_BASE_URL, "").strip()
    model = os.environ.get(ENV_UPSTREAM_MODEL, "").strip()
    api_key = os.environ.get(ENV_UPSTREAM_API_KEY, "").strip() or None
    if not (base_url and model):
        return None
    return Tier(
        name="upstream",
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def openrouter_tier(
    *, timeout: float = 60.0, max_tokens: int = 1024, temperature: float = 0.2
) -> Optional[Tier]:
    api_key = os.environ.get(ENV_OPENROUTER_API_KEY, "").strip()
    if not api_key:
        return None
    return Tier(
        name="openrouter",
        base_url=OPENROUTER_BASE_URL,
        model=OPENROUTER_MODEL,
        api_key=api_key,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def local_tier(
    *, timeout: float = 90.0, max_tokens: int = 1024, temperature: float = 0.2
) -> Tier:
    """Local OpenAI-compatible server (e.g. Ollama) — the offline safety net.

    Generous timeout: a local model on CPU can be slow.
    """
    return Tier(
        name="local",
        base_url=os.environ.get(ENV_LOCAL_BASE_URL, LOCAL_BASE_URL),
        model=os.environ.get(ENV_LOCAL_MODEL, LOCAL_MODEL),
        api_key=None,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def canonical_tiers(
    *, max_tokens: int = 1024, temperature: float = 0.2
) -> list[Tier]:
    """The standard fallback ladder: upstream -> openrouter -> local.

    Tiers lacking credentials/config are silently dropped, so the ladder is
    always best-effort and ends with the local safety net.
    """
    tiers: list[Tier] = []
    up = upstream_tier(max_tokens=max_tokens, temperature=temperature)
    if up:
        tiers.append(up)
    orouter = openrouter_tier(max_tokens=max_tokens, temperature=temperature)
    if orouter:
        tiers.append(orouter)
    tiers.append(local_tier(max_tokens=max_tokens, temperature=temperature))
    return tiers


def gateway_tier(
    token: Optional[str],
    base_url: str,
    model: str,
    *,
    timeout: float = 60.0,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> Optional[Tier]:
    """A front tier for a local agent gateway (OpenAI-compatible).

    Returns None without a token so callers fall straight through to the rest
    of the ladder.
    """
    if not token:
        return None
    return Tier(
        name="gateway",
        base_url=base_url,
        model=model,
        api_key=token,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    )
