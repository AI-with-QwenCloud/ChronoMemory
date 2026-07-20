import sqlite3

from core.embedder import embed
from core.memory_entry import MemoryEntry

AUDIT_DB_PATH = "chronomemory_audit.db"


def build_entry(text: str, provenance: str, importance: float, user_id: str) -> MemoryEntry:
    return MemoryEntry(
        text=text,
        embedding=embed(text),
        provenance=provenance,
        importance=importance,
        user_id=user_id,
    )


def hold(entry: MemoryEntry) -> None:
    conn = sqlite3.connect(AUDIT_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO flagged_memories (id, text, provenance, trust_score, user_id) VALUES (?, ?, ?, ?, ?)",
        (entry.id, entry.text, entry.provenance, entry.trust_score, entry.user_id),
    )
    cur.execute(
        "INSERT INTO audit_log (event_type, detail, user_id) VALUES (?, ?, ?)",
        (
            "vigil_flagged",
            f"held {entry.id} provenance={entry.provenance} trust_score={entry.trust_score}",
            entry.user_id,
        ),
    )
    conn.commit()
    conn.close()
