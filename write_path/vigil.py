import sqlite3

from core.embedder import embed
from core.memory_entry import MemoryEntry

AUDIT_DB_PATH = "chronomemory_audit.db"


def build_entry(text: str, provenance: str, importance: float) -> MemoryEntry:
    return MemoryEntry(
        text=text,
        embedding=embed(text),
        provenance=provenance,
        importance=importance,
    )


def hold(entry: MemoryEntry) -> None:
    conn = sqlite3.connect(AUDIT_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO flagged_memories (id, text, provenance, trust_score) VALUES (?, ?, ?, ?)",
        (entry.id, entry.text, entry.provenance, entry.trust_score),
    )
    cur.execute(
        "INSERT INTO audit_log (event_type, detail) VALUES (?, ?)",
        (
            "vigil_flagged",
            f"held {entry.id} provenance={entry.provenance} trust_score={entry.trust_score}",
        ),
    )
    conn.commit()
    conn.close()
