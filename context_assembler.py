# cache_control: confirmed working (verify_cache_control.py, 2026-07-08). Bisected the
# minimum cacheable prefix: 1010 prompt tokens = miss, 1029 = hit, so the cutoff sits at
# (or very near) the common 1024-token minimum cache-block size. Any pinned prefix
# (system_prompt + pinned_profile combined) below ~1024 tokens gets zero caching benefit
# — pad the prefix past that if the token-savings goal matters for the demo.

from datetime import datetime

import decay_scorer
import trim
from memory_entry import MemoryEntry


def _pinned_message(text: str) -> dict:
    return {
        "role": "system",
        "content": [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
    }


def assemble_context(
    cur,
    system_prompt: str,
    pinned_profile: str,
    candidates: list[tuple[MemoryEntry, float]],
    recent_turns: list[dict],
    now: datetime,
    char_budget: int = 12000,
) -> list[dict]:
    prefix = [_pinned_message(system_prompt), _pinned_message(pinned_profile)]

    middle = []
    lookup: dict[str, tuple[MemoryEntry, float]] = {}
    for entry, match_strength in candidates:
        middle.append(
            {
                "role": "system",
                "content": f"[{entry.provenance}] {entry.text}",
                "_entry_id": entry.id,
            }
        )
        lookup[entry.id] = (entry, match_strength)

    footer = list(recent_turns)

    assembled = trim.trim_middle(prefix, middle, footer, char_budget)

    for message in assembled:
        entry_id = message.get("_entry_id")
        if entry_id is not None and entry_id in lookup:
            entry, match_strength = lookup[entry_id]
            decay_scorer.reinforce(cur, entry, match_strength, now)

    for message in assembled:
        message.pop("_entry_id", None)

    return assembled
