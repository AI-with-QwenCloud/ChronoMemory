from datetime import datetime, timezone

from core.embedder import embed
from core.memory_entry import MemoryEntry
from read_path import decay_scorer

ENTRY_COLUMNS = """id, user_id, text, embedding, importance, relevance_score, access_count,
                   status, provenance, trust_score, last_accessed, timestamp"""


def _parse_embedding(raw) -> list[float]:
    if isinstance(raw, str):
        return [float(x) for x in raw.strip("[]").split(",")]
    return list(raw)


def _row_to_entry(row) -> MemoryEntry:
    (entry_id, user_id, text, embedding, importance, relevance_score, access_count,
     status, provenance, trust_score, last_accessed, timestamp) = row
    return MemoryEntry(
        text=text,
        embedding=_parse_embedding(embedding),
        provenance=provenance,
        user_id=str(user_id),
        id=str(entry_id),
        timestamp=timestamp,
        importance=importance,
        relevance_score=relevance_score,
        access_count=access_count,
        status=status,
        trust_score=trust_score,
        last_accessed=last_accessed,
    )


def _semantic_recall(
    cur, query_embedding: list[float], user_id: str, top_k: int
) -> dict[str, tuple[MemoryEntry, float]]:
    cur.execute(
        f"""
        SELECT {ENTRY_COLUMNS}, embedding <=> %s::vector AS distance
        FROM memories
        WHERE status = 'active' AND user_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_embedding, user_id, query_embedding, top_k),
    )
    candidates: dict[str, tuple[MemoryEntry, float]] = {}
    for *entry_row, distance in cur.fetchall():
        entry = _row_to_entry(entry_row)
        candidates[entry.id] = (entry, 1 - distance)
    return candidates


def _spreading_activation(
    cur, source_ids: list[str], user_id: str
) -> dict[str, tuple[MemoryEntry, float]]:
    if not source_ids:
        return {}

    cur.execute(
        """
        SELECT target_id, link_type, strength
        FROM relational_links
        WHERE source_id = ANY(%s::uuid[])
        """,
        (source_ids,),
    )
    link_rows = cur.fetchall()
    if not link_rows:
        return {}

    strength_by_target = {str(target_id): strength for target_id, _link_type, strength in link_rows}
    target_ids = list(strength_by_target.keys())

    cur.execute(
        f"""
        SELECT {ENTRY_COLUMNS}
        FROM memories
        WHERE status = 'active' AND user_id = %s AND id = ANY(%s::uuid[])
        """,
        (user_id, target_ids),
    )
    candidates: dict[str, tuple[MemoryEntry, float]] = {}
    for entry_row in cur.fetchall():
        entry = _row_to_entry(entry_row)
        candidates[entry.id] = (entry, strength_by_target[entry.id])
    return candidates


def recall(cur, query_text: str, user_id: str, top_k: int = 10) -> list[tuple[MemoryEntry, float]]:
    query_embedding = embed(query_text)

    semantic_candidates = _semantic_recall(cur, query_embedding, user_id, top_k)
    linked_candidates = _spreading_activation(cur, list(semantic_candidates.keys()), user_id)

    merged = dict(linked_candidates)
    merged.update(semantic_candidates)  # semantic hits win on conflict

    now = datetime.now(timezone.utc)
    scored: list[tuple[float, MemoryEntry, float]] = []
    for entry, match_strength in merged.values():
        entry_score = decay_scorer.score(entry, now)
        if decay_scorer.is_prunable(entry_score):
            decay_scorer.prune(cur, entry.id)
            continue
        scored.append((entry_score, entry, match_strength))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [(entry, match_strength) for _, entry, match_strength in scored[:top_k]]
