"""Deterministic test for trust.composite_trust — no LLM calls involved at
all (corroboration counting and staleness checks are pure DB/math), so this
should never flake.
"""
import os
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv

from embedder import embed
from memory_entry import MemoryEntry
from trust import (
    CORROBORATION_BONUS_CAP,
    CORROBORATION_BONUS_PER_LINK,
    STALE_ACCESS_THRESHOLD,
    STALENESS_PENALTY,
    composite_trust,
)

load_dotenv()

NOW = datetime.now(timezone.utc)


def pg_connect():
    conn = psycopg2.connect(
        host=os.environ["CHRONOMEM_DB_HOST"],
        dbname=os.environ["CHRONOMEM_DB_NAME"],
        user=os.environ["CHRONOMEM_DB_USER"],
        password=os.environ["CHRONOMEM_DB_PASSWORD"],
    )
    with conn.cursor() as cur:
        cur.execute("SET ivfflat.probes = 10")
    conn.commit()
    return conn


def _cleanup_since(cur, conn, serial_no_floor: int) -> None:
    cur.execute("SELECT id FROM memories WHERE serial_no > %s", (serial_no_floor,))
    ids = [r[0] for r in cur.fetchall()]
    if not ids:
        return
    cur.execute("UPDATE memories SET superseded_by = NULL WHERE superseded_by = ANY(%s::uuid[])", (ids,))
    cur.execute("DELETE FROM memories WHERE id = ANY(%s::uuid[])", (ids,))
    conn.commit()


def _insert(cur, entry: MemoryEntry) -> None:
    cur.execute(
        """
        INSERT INTO memories (id, text, embedding, importance, relevance_score,
                              access_count, status, provenance, trust_score, last_accessed)
        VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            entry.id, entry.text, entry.embedding, entry.importance, entry.relevance_score,
            entry.access_count, entry.status, entry.provenance, entry.trust_score, entry.last_accessed,
        ),
    )


conn = pg_connect()
cur = conn.cursor()
cur.execute("SELECT COALESCE(max(serial_no), 0) FROM memories")
starting_serial_no = cur.fetchone()[0]

try:
    # 1. No links, fresh, low access — composite equals the plain base trust score.
    plain = MemoryEntry(
        text="Plain fact with no corroboration.", embedding=embed("plain fact"),
        provenance="tool_output", last_accessed=NOW,
    )
    _insert(cur, plain)
    conn.commit()

    result = composite_trust(cur, plain, NOW)
    assert result == plain.trust_score, f"expected {plain.trust_score}, got {result}"
    print("PASS: an uncorroborated, fresh, rarely-accessed entry gets no adjustment.")

    # 2. Corroborating entailment/neutral links raise the score, capped.
    corroborated = MemoryEntry(
        text="Corroborated fact.", embedding=embed("corroborated fact"),
        provenance="tool_output", last_accessed=NOW,
    )
    _insert(cur, corroborated)
    conn.commit()

    for link_type in ("entailment", "neutral", "entailment", "neutral", "entailment"):
        cur.execute(
            "INSERT INTO relational_links (source_id, target_id, link_type, strength) VALUES (%s, %s, %s, 0.8)",
            (plain.id, corroborated.id, link_type),
        )
    conn.commit()

    result = composite_trust(cur, corroborated, NOW)
    expected_bonus = min(5 * CORROBORATION_BONUS_PER_LINK, CORROBORATION_BONUS_CAP)
    expected = min(1.0, corroborated.trust_score + expected_bonus)
    assert abs(result - expected) < 1e-9, f"expected {expected} (capped bonus), got {result}"
    assert result > corroborated.trust_score, "corroboration should raise trust above the base score"
    print(f"PASS: corroborating links raise trust, capped at +{CORROBORATION_BONUS_CAP} ({result:.3f}).")

    # 3. A 'contradiction' link must NOT count as corroboration.
    contradicted = MemoryEntry(
        text="Fact with an incoming contradiction link only.", embedding=embed("contradicted fact"),
        provenance="tool_output", last_accessed=NOW,
    )
    _insert(cur, contradicted)
    conn.commit()
    cur.execute(
        "INSERT INTO relational_links (source_id, target_id, link_type, strength) VALUES (%s, %s, 'contradiction', 0.9)",
        (plain.id, contradicted.id),
    )
    conn.commit()

    result = composite_trust(cur, contradicted, NOW)
    assert result == contradicted.trust_score, f"contradiction link must not bump trust, got {result}"
    print("PASS: a 'contradiction' link does not count as corroboration.")

    # 4. Frequently accessed + stale => staleness penalty applies.
    stale_popular = MemoryEntry(
        text="Popular but stale fact.", embedding=embed("stale popular fact"),
        provenance="user_turn", access_count=STALE_ACCESS_THRESHOLD,
        timestamp=NOW - timedelta(days=365), last_accessed=NOW - timedelta(days=365),
    )
    _insert(cur, stale_popular)
    conn.commit()

    result = composite_trust(cur, stale_popular, NOW)
    expected = max(0.0, stale_popular.trust_score - STALENESS_PENALTY)
    assert abs(result - expected) < 1e-9, f"expected staleness penalty applied, got {result}"
    assert result < stale_popular.trust_score, "frequently-used + stale should lower trust"
    print(f"PASS: frequently-accessed + stale facts get the staleness penalty ({result:.3f}).")

    # 5. Frequently accessed but still FRESH => no penalty.
    fresh_popular = MemoryEntry(
        text="Popular and still fresh fact.", embedding=embed("fresh popular fact"),
        provenance="user_turn", access_count=STALE_ACCESS_THRESHOLD, last_accessed=NOW,
    )
    _insert(cur, fresh_popular)
    conn.commit()

    result = composite_trust(cur, fresh_popular, NOW)
    assert result == fresh_popular.trust_score, "a fresh, popular fact should not be penalized"
    print("PASS: frequently-accessed but still-fresh facts are not penalized.")

    print("\nTrust test PASSED (fully deterministic, zero network calls).")
finally:
    _cleanup_since(cur, conn, starting_serial_no)
    cur.close()
    conn.close()
