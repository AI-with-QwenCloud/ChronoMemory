"""Regression test for per-user memory isolation: a memory written by one
user must never be visible to another user's recall(), even when the query
text is a near-exact semantic match. LLM boundary is mocked (like
phase3_pipeline_test.py), so this is deterministic and safe to trust on a
single run.
"""
import os

import psycopg2
from dotenv import load_dotenv

from read_path.recall import recall
from write_path import write_loop as wl

load_dotenv()

IVFFLAT_PROBES = 10

USER_A_ID = "00000000-0000-0000-0000-0000000000a1"
USER_A_USERNAME = "isolation_test_user_a"
USER_B_ID = "00000000-0000-0000-0000-0000000000b1"
USER_B_USERNAME = "isolation_test_user_b"


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


def _cleanup_since(cur, conn, serial_no_floor: int) -> None:
    cur.execute("SELECT id FROM memories WHERE serial_no > %s", (serial_no_floor,))
    ids = [r[0] for r in cur.fetchall()]
    if not ids:
        return
    cur.execute("UPDATE memories SET superseded_by = NULL WHERE superseded_by = ANY(%s::uuid[])", (ids,))
    cur.execute("DELETE FROM memories WHERE id = ANY(%s::uuid[])", (ids,))
    conn.commit()


conn = pg_connect()
cur = conn.cursor()

cur.execute(
    "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, 'unused') "
    "ON CONFLICT (id) DO NOTHING",
    (USER_A_ID, USER_A_USERNAME),
)
cur.execute(
    "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, 'unused') "
    "ON CONFLICT (id) DO NOTHING",
    (USER_B_ID, USER_B_USERNAME),
)
conn.commit()

cur.execute("SELECT COALESCE(max(serial_no), 0) FROM memories")
starting_serial_no = cur.fetchone()[0]

original_extract_facts = wl.extract_facts

try:
    wl.extract_facts = lambda turn_text: [
        {"text": "User A's secret project codename is Nightingale.", "importance": 0.9}
    ]
    wl.write_loop("irrelevant text — extract_facts is mocked", "user_turn", USER_A_ID)
    conn.commit()

    results_as_b = recall(cur, "What is the secret project codename?", USER_B_ID, top_k=10)
    conn.commit()
    texts_visible_to_b = {entry.text for entry, _ in results_as_b}
    assert "User A's secret project codename is Nightingale." not in texts_visible_to_b, (
        "user A's memory leaked into user B's recall() results"
    )
    print("PASS: user B's recall() never returns user A's memory.")

    results_as_a = recall(cur, "What is the secret project codename?", USER_A_ID, top_k=10)
    conn.commit()
    texts_visible_to_a = {entry.text for entry, _ in results_as_a}
    assert "User A's secret project codename is Nightingale." in texts_visible_to_a, (
        "user A's own recall() should still return their own memory"
    )
    print("PASS: user A's own recall() still returns their own memory.")

    print("\nUser isolation test PASSED (fully mocked, zero network calls).")
finally:
    wl.extract_facts = original_extract_facts
    _cleanup_since(cur, conn, starting_serial_no)
    cur.close()
    conn.close()
