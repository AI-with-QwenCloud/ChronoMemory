"""Applies any not-yet-applied files in db/migrations_sqlite/, in filename
order, to the host-side audit db. Idempotent -- safe to run on every deploy
and every bootstrap, unlike CREATE TABLE IF NOT EXISTS on its own, which
silently no-ops on a table that already exists with stale columns (the
"no such column: user_id" bug this replaces). Stdlib-only: this runs
directly on the host, not inside the app container.
"""
import sqlite3
from pathlib import Path

DB_PATH = "chronomemory_audit.db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations_sqlite"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.name
        cur.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,))
        if cur.fetchone():
            print(f"==> {version}: already applied, skipping")
            continue
        print(f"==> {version}: applying")
        cur.executescript(path.read_text())
        cur.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
        conn.commit()

    print("==> sqlite schema up to date")
    conn.close()


if __name__ == "__main__":
    main()
