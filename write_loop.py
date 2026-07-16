import os
import sqlite3

import psycopg2
from dotenv import load_dotenv

import contradiction_gate
import vigil
from extractor import ExtractionError, extract_facts

load_dotenv()

AUDIT_DB_PATH = "chronomemory_audit.db"

# schema.sql sizes the ivfflat index for a much larger table (lists=100);
# Postgres defaults ivfflat.probes to 1, which searches roughly 1/lists of
# the data per query — on a small/medium table that makes nearest-neighbor
# lookups (recall, contradiction_gate) miss real matches unpredictably.
# sqrt(lists) is the standard starting point for probes.
IVFFLAT_PROBES = 10


def _log_failure(event_type: str, detail: str) -> None:
    conn = sqlite3.connect(AUDIT_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_log (event_type, detail) VALUES (?, ?)",
        (event_type, detail),
    )
    conn.commit()
    conn.close()


def write_loop(turn_text: str, provenance: str) -> None:
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
            _log_failure(f"extraction_{e.category}", str(e))
            return
        except Exception as e:
            _log_failure("write_failure", f"extraction failed (unexpected): {e}")
            return

        for fact in facts:
            try:
                entry = vigil.build_entry(fact["text"], provenance, fact["importance"])

                if entry.is_flagged():
                    vigil.hold(entry)
                    continue

                cur.execute(
                    """
                    INSERT INTO memories (id, text, embedding, importance, relevance_score,
                                          access_count, status, provenance, trust_score)
                    VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entry.id, entry.text, entry.embedding, entry.importance,
                        entry.relevance_score, entry.access_count, entry.status,
                        entry.provenance, entry.trust_score,
                    ),
                )
                contradiction_gate.resolve_and_link(cur, entry)
                conn.commit()
            except Exception as e:
                conn.rollback()
                _log_failure("write_failure", f"failed to commit fact {fact!r}: {e}")
    finally:
        conn.close()
