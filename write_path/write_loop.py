import os
import sqlite3

import psycopg2
from dotenv import load_dotenv

from write_path import contradiction_gate, vigil
from write_path.extractor import ExtractionError, extract_facts

load_dotenv()

AUDIT_DB_PATH = "chronomemory_audit.db"

# schema.sql sizes the ivfflat index for a much larger table (lists=100);
# Postgres defaults ivfflat.probes to 1, which searches roughly 1/lists of
# the data per query — on a small/medium table that makes nearest-neighbor
# lookups (recall, contradiction_gate) miss real matches unpredictably.
# sqrt(lists) is the standard starting point for probes.
IVFFLAT_PROBES = 10


def _log_failure(event_type: str, detail: str, user_id: str) -> None:
    conn = sqlite3.connect(AUDIT_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_log (event_type, detail, user_id) VALUES (?, ?, ?)",
        (event_type, detail, user_id),
    )
    conn.commit()
    conn.close()


def write_loop(turn_text: str, provenance: str, user_id: str) -> None:
    conn = psycopg2.connect(
        host=os.environ["CHRONOMEM_DB_HOST"],
        dbname=os.environ["CHRONOMEM_DB_NAME"],
        user=os.environ["CHRONOMEM_DB_USER"],
        password=os.environ["CHRONOMEM_DB_PASSWORD"],
    )
    try:
        cur = conn.cursor()
        cur.execute("SET ivfflat.probes = %s", (IVFFLAT_PROBES,))

        try:
            facts = extract_facts(turn_text)
        except ExtractionError as e:
            _log_failure(f"extraction_{e.category}", str(e), user_id)
            return
        except Exception as e:
            _log_failure("write_failure", f"extraction failed (unexpected): {e}", user_id)
            return

        for fact in facts:
            try:
                entry = vigil.build_entry(fact["text"], provenance, fact["importance"], user_id)

                if entry.is_flagged():
                    vigil.hold(entry)
                    continue

                # Concurrent writes for the same user (e.g. the user_turn and
                # agent_turn dispatch_write threads for one chat turn) each run
                # their own find_similar_active() neighbor search in
                # resolve_and_link — without serializing them, two near-simultaneous
                # writes can race past each other, each searching before the other's
                # INSERT is visible, so neither ever discovers the other. A
                # transaction-scoped advisory lock keyed on user_id forces
                # concurrent writers for the same user to take turns, so every
                # insert+resolve is guaranteed to see everything already committed
                # for that user. Auto-released at commit/rollback below, so a crash
                # or dropped connection can't leave it stuck.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)", (user_id,))

                cur.execute(
                    """
                    INSERT INTO memories (id, text, embedding, importance, relevance_score,
                                          access_count, status, provenance, trust_score, user_id)
                    VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entry.id, entry.text, entry.embedding, entry.importance,
                        entry.relevance_score, entry.access_count, entry.status,
                        entry.provenance, entry.trust_score, entry.user_id,
                    ),
                )
                contradiction_gate.resolve_and_link(cur, entry)
                conn.commit()
            except Exception as e:
                conn.rollback()
                _log_failure("write_failure", f"failed to commit fact {fact!r}: {e}", user_id)
    finally:
        conn.close()
