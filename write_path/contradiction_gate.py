import json

from core.memory_entry import MemoryEntry
from core.qwen_client import chat
from read_path import recall
from write_path.extractor import _strip_code_fence

NLI_TOP_K = 5

NLI_SYSTEM_PROMPT_TEMPLATE = """You are comparing two statements for factual consistency.

Statement A (existing memory): "{existing_text}"
Statement B (new information): "{new_text}"

Classify the relationship from B's perspective as exactly one of:
- "contradiction": B states something that cannot both be true if A is also true (a fact changed, a preference flipped, etc.)
- "entailment": B restates or reinforces the same fact as A.
- "neutral": B is unrelated or complementary to A, no conflict.

Return ONLY JSON (no markdown fences): {{"label": "contradiction" | "entailment" | "neutral", "score": <confidence 0.0-1.0>}}"""


def find_similar_active(
    cur, embedding: list[float], exclude_id: str, top_k: int = NLI_TOP_K
) -> list[tuple[MemoryEntry, float]]:
    cur.execute(
        f"""
        SELECT {recall.ENTRY_COLUMNS}, embedding <=> %s::vector AS distance
        FROM memories
        WHERE status = 'active' AND id != %s::uuid
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding, exclude_id, embedding, top_k),
    )
    neighbors = []
    for *entry_row, distance in cur.fetchall():
        entry = recall._row_to_entry(entry_row)
        neighbors.append((entry, 1 - distance))
    return neighbors


def classify(existing_text: str, new_text: str) -> tuple[str, float]:
    prompt = NLI_SYSTEM_PROMPT_TEMPLATE.format(existing_text=existing_text, new_text=new_text)
    response = chat("scorer", [{"role": "system", "content": prompt}])
    content = response["choices"][0]["message"]["content"]
    result = json.loads(_strip_code_fence(content))

    label = result["label"]
    if label not in ("contradiction", "entailment", "neutral"):
        raise ValueError(f"unexpected NLI label: {label!r}")
    score = max(0.0, min(float(result["score"]), 1.0))
    return label, score


def resolve_and_link(cur, new_entry: MemoryEntry) -> None:
    # new_entry must already be committed into `memories` before this runs —
    # `superseded_by` is FK-constrained against `memories.id`, so pointing an
    # old row's `superseded_by` at new_entry.id fails unless that row exists.
    neighbors = find_similar_active(cur, new_entry.embedding, exclude_id=new_entry.id)

    for neighbor_entry, _similarity in neighbors:
        label, score = classify(neighbor_entry.text, new_entry.text)

        if label == "contradiction":
            cur.execute(
                "UPDATE memories SET status = 'superseded', superseded_by = %s WHERE id = %s",
                (new_entry.id, neighbor_entry.id),
            )
            cur.execute(
                """
                INSERT INTO contradiction_logs (winning_id, losing_id, nli_label, nli_score)
                VALUES (%s, %s, %s, %s)
                """,
                (new_entry.id, neighbor_entry.id, label, score),
            )
        else:
            cur.execute(
                """
                INSERT INTO relational_links (source_id, target_id, link_type, strength)
                VALUES (%s, %s, %s, %s)
                """,
                (new_entry.id, neighbor_entry.id, label, score),
            )
