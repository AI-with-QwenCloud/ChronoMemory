from datetime import datetime

from core.memory_entry import MemoryEntry
from read_path import decay_scorer

# MemGuard-style composite trust: a memory's static, provenance-based
# trust_score (set once at write time — see memory_entry.TRUST_SCORES) is
# adjusted at read time by two signals ChronoMemory already computes for
# other purposes but never fed back into trust: corroboration from the
# relational-links graph, and a penalty for memories that are both
# frequently retrieved and stale — MemGuard's "confidently wrong" case,
# riskier than a wrong fact nobody asks about.
#
# This never affects VIGIL's write-time admission gate (memory_entry.
# MemoryEntry.is_flagged), which must stay a static, provenance-only check:
# a brand-new candidate has no retrieval history or corroborating links yet,
# so the only trustworthy signal at that moment is where it came from.

CORROBORATION_BONUS_PER_LINK = 0.05
CORROBORATION_BONUS_CAP = 0.15

STALE_ACCESS_THRESHOLD = 3
STALE_FRESHNESS_THRESHOLD = 0.3
STALENESS_PENALTY = 0.1


def _corroboration_bonus_map(cur, entry_ids: list[str]) -> dict[str, float]:
    """One round-trip for any number of ids — callers looping over entries
    (e.g. rendering a list of memories) must batch through this rather than
    calling composite_trust per-row, or they reintroduce the N+1 this replaced.
    """
    if not entry_ids:
        return {}
    cur.execute(
        """
        SELECT target_id, count(*) FROM relational_links
        WHERE target_id = ANY(%s::uuid[]) AND link_type IN ('entailment', 'neutral')
        GROUP BY target_id
        """,
        (entry_ids,),
    )
    counts = {str(target_id): count for target_id, count in cur.fetchall()}
    return {
        entry_id: min(counts.get(entry_id, 0) * CORROBORATION_BONUS_PER_LINK, CORROBORATION_BONUS_CAP)
        for entry_id in entry_ids
    }


def _staleness_penalty(entry: MemoryEntry, freshness: float) -> float:
    if entry.access_count >= STALE_ACCESS_THRESHOLD and freshness < STALE_FRESHNESS_THRESHOLD:
        return STALENESS_PENALTY
    return 0.0


def composite_trust(cur, entry: MemoryEntry, now: datetime) -> float:
    freshness = decay_scorer.freshness(entry, now)
    bonus = _corroboration_bonus_map(cur, [entry.id])[entry.id]
    penalty = _staleness_penalty(entry, freshness)
    return max(0.0, min(1.0, entry.trust_score + bonus - penalty))


def composite_trust_batch(cur, entries: list[MemoryEntry], now: datetime) -> dict[str, float]:
    """Same result as calling composite_trust per entry, but one query total
    instead of one per entry — use this for any list/dashboard render.
    """
    bonuses = _corroboration_bonus_map(cur, [entry.id for entry in entries])
    result = {}
    for entry in entries:
        freshness = decay_scorer.freshness(entry, now)
        penalty = _staleness_penalty(entry, freshness)
        result[entry.id] = max(0.0, min(1.0, entry.trust_score + bonuses[entry.id] - penalty))
    return result
