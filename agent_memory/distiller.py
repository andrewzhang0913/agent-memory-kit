"""Example LLM consumer: a semantic distiller.

Reads recent episodic text and extracts new, durable "lessons" via the resilient
LLM client. This is a worked example of the consumer pattern: build messages →
pick a tier ladder → call ``chat`` with a validator → handle ``LLMError``
explicitly. Adapt the prompt and I/O to your own store.
"""
from __future__ import annotations

from typing import Callable, Optional

from .llm import LLMError, canonical_tiers, chat

SYSTEM_PROMPT = """You distill durable lessons from an agent's recent activity.

Read the recent episodic notes and extract NEW, reusable lessons and technical
know-how. You are given the current lessons; do NOT repeat anything already
covered or semantically similar. Focus on new failures encountered, new
practices that worked, or discoveries not yet recorded.

If there are no new high-value lessons, output exactly: NO_NEW_LESSONS

Output plain bullet lines (no code fences):
- [Lesson] <what happened and how to avoid/repeat it>
- [Know-how] <reusable technical detail>
"""


def distill(
    episodic_text: str,
    current_lessons: str = "",
    *,
    max_tokens: int = 1024,
    on_event: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Return distilled lessons text, or None if no LLM tier produced output.

    Returns the literal ``"NO_NEW_LESSONS"`` when the model finds nothing new —
    callers should treat that as "success, nothing to append".
    """
    if not episodic_text.strip():
        return None

    user = f"Recent episodic notes:\n\n{episodic_text}"
    if current_lessons.strip():
        user = (
            "Current lessons (do NOT duplicate):\n"
            f"```\n{current_lessons}\n```\n\n"
            f"Now extract ONLY NEW lessons from:\n\n{episodic_text}"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    tiers = canonical_tiers(max_tokens=max_tokens, temperature=0.2)
    try:
        return chat(messages, tiers, on_event=on_event)  # type: ignore[return-value]
    except LLMError as exc:
        if on_event:
            on_event(f"[distiller] all tiers failed: {exc}")
        return None
