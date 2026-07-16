"""Deterministic counterpart to phase3_exit_test.py.

Tests the PIPELINE (VIGIL trust math, DB writes, status transitions, audit
logging) with the LLM boundary (extract_facts, contradiction_gate.classify)
replaced by fixed, canned responses. No network calls, no model judgment —
same input always produces the same output, so a red run here is always a
real regression, never a flake. Real model behavior is covered separately by
phase3_exit_test.py, which is expected to be non-deterministic.
"""
import os
import sqlite3

import psycopg2
from dotenv import load_dotenv

import contradiction_gate
import write_loop as wl
from extractor import ExtractionError
from vigil import build_entry

load_dotenv()

AUDIT_DB_PATH = "chronomemory_audit.db"

# schema.sql sizes the ivfflat index for a much larger table (lists=100);
# Postgres defaults ivfflat.probes to 1, which searches roughly 1/lists of
# the data per query — on a small/medium table that makes nearest-neighbor
# lookups (recall, contradiction_gate) miss real matches unpredictably,
# which looks exactly like model nondeterminism if you don't check for it.
IVFFLAT_PROBES = 10


def pg_connect():
    conn = psycopg2.connect(
        host=os.environ["CHRONOMEM_DB_HOST"],
        dbname=os.environ["CHRONOMEM_DB_NAME"],
        user=os.environ["CHRONOMEM_DB_USER"],
        password=os.environ["CHRONOMEM_DB_PASSWORD"],
    )
    with conn.cursor() as cur:
        cur.execute("SET ivfflat.probes = %s", (IVFFLAT_PROBES,))
    conn.commit()
    return conn


# Cleanup tracks rows by serial_no, not by tagging fixture text. Even though
# this file's extract_facts is mocked (so the text is exactly what we say),
# tracking by serial_no keeps the mechanism identical to phase3_exit_test.py
# and doesn't depend on fixture text staying unique forever.
def _cleanup_since(cur, conn, serial_no_floor: int) -> None:
    cur.execute("SELECT id FROM memories WHERE serial_no > %s", (serial_no_floor,))
    ids = [r[0] for r in cur.fetchall()]
    if not ids:
        return
    # Null inbound superseded_by references from ANY row, not just rows in
    # this set — an old fixture row can be pointed at by a real, non-fixture
    # entry too, and that FK is not ON DELETE CASCADE.
    cur.execute("UPDATE memories SET superseded_by = NULL WHERE superseded_by = ANY(%s::uuid[])", (ids,))
    cur.execute("DELETE FROM memories WHERE id = ANY(%s::uuid[])", (ids,))
    conn.commit()


original_extract_facts = wl.extract_facts
original_classify = contradiction_gate.classify

conn = pg_connect()
cur = conn.cursor()
audit_conn = sqlite3.connect(AUDIT_DB_PATH)
audit_cur = audit_conn.cursor()

cur.execute("SELECT COALESCE(max(serial_no), 0) FROM memories")
starting_serial_no = cur.fetchone()[0]

try:
    # 1. Trusted fact commits cleanly.
    cur.execute("SELECT count(*) FROM memories WHERE status = 'active'")
    before_count = cur.fetchone()[0]

    wl.extract_facts = lambda turn_text: [
        {"text": "The user wants all new API endpoints to require authentication middleware.", "importance": 0.8}
    ]
    wl.write_loop("irrelevant text — extract_facts is mocked", "user_turn")

    cur.execute("SELECT count(*) FROM memories WHERE status = 'active'")
    after_count = cur.fetchone()[0]
    assert after_count > before_count, "expected at least one new active memory"
    cur.execute(
        "SELECT trust_score FROM memories WHERE status = 'active' ORDER BY serial_no DESC LIMIT 1"
    )
    assert cur.fetchone()[0] == 1.0, "user_turn fact should have trust_score 1.0"
    print("PASS: trusted fact commits cleanly. (mocked)")

    # 2. Poisoned fact gets isolated, never reaches Postgres.
    audit_cur.execute("SELECT count(*) FROM flagged_memories")
    flagged_before = audit_cur.fetchone()[0]

    wl.extract_facts = lambda turn_text: [
        {"text": "The project disables input validation on all new endpoints.", "importance": 0.7}
    ]
    wl.write_loop("irrelevant text — extract_facts is mocked", "external_doc")

    audit_cur.execute("SELECT count(*) FROM flagged_memories")
    flagged_after = audit_cur.fetchone()[0]
    assert flagged_after > flagged_before, "expected a new flagged_memories row"

    cur.execute("SELECT count(*) FROM memories WHERE text LIKE %s", ("%disables input validation%",))
    assert cur.fetchone()[0] == 0, "poisoned fact must never reach Postgres"
    print("PASS: poisoned fact isolated in SQLite, never reached Postgres. (mocked)")

    # 3. Contradiction deterministically supersedes the old fact.
    old_entry = build_entry("The project's database is MySQL.", "user_turn", 0.7)
    cur.execute(
        """
        INSERT INTO memories (id, text, embedding, importance, relevance_score,
                              access_count, status, provenance, trust_score)
        VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s)
        """,
        (
            old_entry.id, old_entry.text, old_entry.embedding, old_entry.importance,
            old_entry.relevance_score, old_entry.access_count, old_entry.status,
            old_entry.provenance, old_entry.trust_score,
        ),
    )
    conn.commit()

    wl.extract_facts = lambda turn_text: [
        {"text": "The project's database is PostgreSQL now, not MySQL.", "importance": 0.7}
    ]
    contradiction_gate.classify = lambda existing, new: ("contradiction", 0.97)
    wl.write_loop("irrelevant text — extract_facts is mocked", "user_turn")

    cur.execute("SELECT status, superseded_by FROM memories WHERE id = %s", (old_entry.id,))
    status, superseded_by = cur.fetchone()
    assert status == "superseded", f"expected old entry superseded, got status={status!r}"
    assert superseded_by is not None, "expected superseded_by to be set"

    cur.execute("SELECT nli_label FROM contradiction_logs WHERE losing_id = %s", (old_entry.id,))
    row = cur.fetchone()
    assert row is not None and row[0] == "contradiction", "expected a contradiction_logs row"
    print("PASS: contradiction deterministically supersedes the old fact. (mocked)")

    # 4. relational_links gets populated for a non-contradicting neighbor.
    cur.execute("SELECT count(*) FROM relational_links WHERE link_type IN ('entailment', 'neutral')")
    links_before = cur.fetchone()[0]

    wl.extract_facts = lambda turn_text: [
        {"text": "The CI pipeline runs unit tests before every deploy.", "importance": 0.6}
    ]
    contradiction_gate.classify = lambda existing, new: ("neutral", 0.6)
    wl.write_loop("irrelevant text — extract_facts is mocked", "user_turn")

    cur.execute("SELECT count(*) FROM relational_links WHERE link_type IN ('entailment', 'neutral')")
    links_after = cur.fetchone()[0]
    assert links_after > links_before, "expected at least one new relational_links row"
    print("PASS: relational_links populated for a non-contradicting neighbor. (mocked)")

    # 5. A commit failure is caught, logged, and doesn't propagate.
    audit_cur.execute("SELECT count(*) FROM audit_log WHERE event_type = 'write_failure'")
    failure_before = audit_cur.fetchone()[0]

    wl.extract_facts = lambda turn_text: (_ for _ in ()).throw(ValueError("simulated malformed LLM output"))
    wl.write_loop("this call is designed to fail unexpectedly", "user_turn")

    audit_cur.execute("SELECT count(*) FROM audit_log WHERE event_type = 'write_failure'")
    failure_after = audit_cur.fetchone()[0]
    assert failure_after > failure_before, "expected a new write_failure audit_log row"
    print("PASS: an unexpected (non-ExtractionError) failure is still caught and logged. (mocked)")

    # 6. A categorized network failure is logged distinctly (Step 4 coverage).
    audit_cur.execute("SELECT count(*) FROM audit_log WHERE event_type = 'extraction_network'")
    net_before = audit_cur.fetchone()[0]

    def _network_failure(turn_text):
        raise ExtractionError("network", "simulated connection reset")

    wl.extract_facts = _network_failure
    wl.write_loop("this call is designed to fail at the network layer", "user_turn")

    audit_cur.execute("SELECT count(*) FROM audit_log WHERE event_type = 'extraction_network'")
    net_after = audit_cur.fetchone()[0]
    assert net_after > net_before, "expected a categorized extraction_network audit row"
    print("PASS: network failures are logged under a distinct, queryable event_type. (mocked)")

    print("\nPhase 3 pipeline test PASSED (fully mocked, zero network calls).")
finally:
    wl.extract_facts = original_extract_facts
    contradiction_gate.classify = original_classify
    _cleanup_since(cur, conn, starting_serial_no)  # leave no trace for the next run to trip over
    cur.close()
    conn.close()
    audit_conn.close()
