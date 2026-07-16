import math
from datetime import datetime

from core.memory_entry import MemoryEntry

ETA_BASE_DAYS = 7.0
KAPPA = 0.8
ACCESS_HALF_LIFE_FACTOR = 0.5
ACCESS_HALF_LIFE_CAP = 5.0
BUMP_CAP = 0.1
PRUNE_THRESHOLD = 0.15


def effective_half_life(entry: MemoryEntry) -> float:
    multiplier = min(1 + entry.access_count * ACCESS_HALF_LIFE_FACTOR, ACCESS_HALF_LIFE_CAP)
    return ETA_BASE_DAYS * multiplier


def freshness(entry: MemoryEntry, now: datetime) -> float:
    tau = entry.last_accessed or entry.timestamp
    elapsed_days = max((now - tau).total_seconds() / 86400, 0)
    eta_i = effective_half_life(entry)
    return math.exp(-((elapsed_days / eta_i) ** KAPPA))


def score(entry: MemoryEntry, now: datetime) -> float:
    return entry.importance * entry.relevance_score * freshness(entry, now)


def is_prunable(memory_score: float) -> bool:
    return memory_score < PRUNE_THRESHOLD


def reinforce(cur, entry: MemoryEntry, match_strength: float, now: datetime) -> None:
    match_strength = max(0.0, min(match_strength, 1.0))
    bump = BUMP_CAP * match_strength

    entry.relevance_score = min(1.0, entry.relevance_score + bump)
    entry.access_count += 1
    entry.last_accessed = now

    cur.execute(
        """
        UPDATE memories
        SET relevance_score = %s, access_count = %s, last_accessed = %s
        WHERE id = %s
        """,
        (entry.relevance_score, entry.access_count, entry.last_accessed, entry.id),
    )


def prune(cur, entry_id: str) -> None:
    cur.execute("UPDATE memories SET status = 'archived' WHERE id = %s", (entry_id,))
