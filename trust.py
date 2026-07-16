from datetime import datetime

import decay_scorer
from memory_entry import MemoryEntry

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


def _corroboration_bonus(cur, entry_id: str) -> float:
    cur.execute(
        """
        SELECT count(*) FROM relational_links
        WHERE target_id = %s::uuid AND link_type IN ('entailment', 'neutral')
        """,
        (entry_id,),
    )
    count = cur.fetchone()[0]
    return min(count * CORROBORATION_BONUS_PER_LINK, CORROBORATION_BONUS_CAP)


def _staleness_penalty(entry: MemoryEntry, freshness: float) -> float:
    if entry.access_count >= STALE_ACCESS_THRESHOLD and freshness < STALE_FRESHNESS_THRESHOLD:
        return STALENESS_PENALTY
    return 0.0


def composite_trust(cur, entry: MemoryEntry, now: datetime) -> float:
    freshness = decay_scorer.freshness(entry, now)
    bonus = _corroboration_bonus(cur, entry.id)
    penalty = _staleness_penalty(entry, freshness)
    return max(0.0, min(1.0, entry.trust_score + bonus - penalty))
