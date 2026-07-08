import os
import sqlite3

import psycopg2
from dotenv import load_dotenv

import contradiction_gate
import vigil
from extractor import extract_facts

load_dotenv()

AUDIT_DB_PATH = "chronomemory_audit.db"


def _log_failure(detail: str) -> None:
    conn = sqlite3.connect(AUDIT_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_log (event_type, detail) VALUES (?, ?)",
        ("write_failure", detail),
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

        try:
            facts = extract_facts(turn_text)
        except Exception as e:
            _log_failure(f"extraction failed: {e}")
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
                _log_failure(f"failed to commit fact {fact!r}: {e}")
    finally:
        conn.close()
