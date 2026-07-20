import sqlite3

DB_PATH = "chronomemory_audit.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS flagged_memories (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    provenance  TEXT NOT NULL,
    trust_score REAL NOT NULL,
    flagged_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
""")

conn.commit()
conn.close()
print(f"SQLite audit db initialized at {DB_PATH}")
