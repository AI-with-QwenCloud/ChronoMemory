import os
import psycopg2
from dotenv import load_dotenv

from memory_entry import MemoryEntry
from embedder import embed

load_dotenv()

conn = psycopg2.connect(
    host=os.environ["CHRONOMEM_DB_HOST"],
    dbname=os.environ["CHRONOMEM_DB_NAME"],
    user=os.environ["CHRONOMEM_DB_USER"],
    password=os.environ["CHRONOMEM_DB_PASSWORD"],
)
cur = conn.cursor()

# 1. Build and insert a test memory
test_text = "User prefers strict camelCase conventions"
entry = MemoryEntry(
    text=test_text,
    embedding=embed(test_text),
    provenance="user_turn",
)

cur.execute(
    """
    INSERT INTO memories (id, text, embedding, importance, relevance_score,
                           access_count, status, provenance, trust_score)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
    (
        entry.id,
        entry.text,
        entry.embedding,
        entry.importance,
        entry.relevance_score,
        entry.access_count,
        entry.status,
        entry.provenance,
        entry.trust_score,
    ),
)
conn.commit()
print(f"Inserted memory {entry.id}")

# 2. Query back with a related-but-different sentence
query_text = "they like camelCase for variable names"
query_embedding = embed(query_text)

cur.execute(
    """
    SELECT id, text, embedding <=> %s::vector AS distance
    FROM memories
    WHERE status = 'active'
    ORDER BY embedding <=> %s::vector
    LIMIT 5
    """,
    (query_embedding, query_embedding),
)

rows = cur.fetchall()
print("\nTop results:")
for row_id, text, distance in rows:
    marker = " <-- our inserted row" if str(row_id) == entry.id else ""
    print(f"  distance={distance:.4f}  text={text!r}{marker}")

cur.close()
conn.close()
