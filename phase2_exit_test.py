import os
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv

import decay_scorer
from context_assembler import assemble_context
from embedder import embed
from memory_entry import MemoryEntry
from recall import recall

load_dotenv()

NOW = datetime.now(timezone.utc)

# (text, importance, days_ago, last_accessed_recent, access_count)
SPECS = [
    ("User prefers strict camelCase naming for variables", 0.8, 1, True, 0),      # 0  query anchor
    ("User is allergic to peanuts and shellfish", 0.6, 3, False, 0),              # 1
    ("Team standup happens every day at 9:30am", 0.5, 5, True, 2),                # 2
    ("User's favorite programming language is Python", 0.7, 2, False, 0),         # 3
    ("User is planning a trip to Japan in the spring", 0.4, 8, True, 0),          # 4
    ("The database migration script needs a rollback plan", 0.65, 4, False, 0),   # 5
    ("User's cat is named Waffles", 0.3, 10, True, 0),                           # 6
    ("User dislikes tabs and always configures editors for spaces", 0.55, 6, False, 0),  # 7
    ("The quarterly report is due at the end of the month", 0.45, 7, True, 0),    # 8
    ("User's favorite recipe is a simple garlic pasta", 0.25, 11, False, 0),      # 9
    ("User works remotely from Raleigh, North Carolina", 0.5, 9, True, 0),        # 10
    ("The staging environment uses a separate Postgres instance", 0.6, 2, False, 0),  # 11
    ("User prefers dark mode in every application", 0.35, 12, True, 0),           # 12
    ("User's manager asked for a status update on Friday", 0.5, 1, False, 0),     # 13
    ("User is learning to play the guitar in their free time", 0.3, 5, True, 0),  # 14
    ("The CI pipeline runs unit tests before every deploy", 0.7, 3, False, 3),    # 15  access_count=3 basis for decision #6
    ("User's preferred IDE is VS Code with the Vim keybindings", 0.5, 4, True, 0),   # 16  reinforcement test A
    ("User's backup laptop is an older MacBook Pro", 0.5, 4, True, 0),               # 17  reinforcement test B
    ("This memory is old, low importance, and should get pruned during recall", 0.2, 13, False, 0),  # 18  prunable
    ("User's team uses Slack for day-to-day communication", 0.45, 6, True, 0),    # 19
]
assert len(SPECS) == 20

entries: list[MemoryEntry] = []
for text, importance, days_ago, recent_access, access_count in SPECS:
    last_accessed = (NOW - timedelta(hours=1)) if recent_access else None
    entries.append(
        MemoryEntry(
            text=text,
            embedding=embed(text),
            provenance="user_turn",
            timestamp=NOW - timedelta(days=days_ago),
            importance=importance,
            access_count=access_count,
            last_accessed=last_accessed,
        )
    )

conn = psycopg2.connect(
    host=os.environ["CHRONOMEM_DB_HOST"],
    dbname=os.environ["CHRONOMEM_DB_NAME"],
    user=os.environ["CHRONOMEM_DB_USER"],
    password=os.environ["CHRONOMEM_DB_PASSWORD"],
)
cur = conn.cursor()

# 3. Insert all 20 mock memories.
for e in entries:
    cur.execute(
        """
        INSERT INTO memories (id, text, embedding, timestamp, importance, relevance_score,
                               access_count, status, provenance, trust_score, last_accessed)
        VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (e.id, e.text, e.embedding, e.timestamp, e.importance, e.relevance_score,
         e.access_count, e.status, e.provenance, e.trust_score, e.last_accessed),
    )
conn.commit()
print(f"Inserted {len(entries)} mock memories.")

# 4. Seed 3-5 relational_links (varied strength). The first link guarantees the
# prunable memory (18) is reachable via spreading activation from the query anchor (0).
LINKS = [
    (entries[0].id, entries[18].id, "related_to", 0.6),
    (entries[0].id, entries[9].id, "related_to", 0.3),
    (entries[3].id, entries[11].id, "related_to", 0.8),
    (entries[7].id, entries[12].id, "related_to", 0.45),
    (entries[15].id, entries[19].id, "related_to", 0.55),
]
for source_id, target_id, link_type, strength in LINKS:
    cur.execute(
        """
        INSERT INTO relational_links (source_id, target_id, link_type, strength)
        VALUES (%s, %s, %s, %s)
        """,
        (source_id, target_id, link_type, strength),
    )
conn.commit()
print(f"Seeded {len(LINKS)} relational_links.")

# 5. Run dual-recall search.
query = "What naming convention does the user prefer for variables?"
candidates = recall(cur, query, top_k=10)
conn.commit()
print(f"recall() returned {len(candidates)} candidates.")
assert len(candidates) > 0, "recall() returned no candidates"

# 6. Assemble context with a deliberately small char_budget so trimming triggers.
system_prompt = "You are the ChronoMemory agent. Use retrieved memories faithfully."
pinned_profile = "User profile: software engineer, working in a Postgres/Python stack."
recent_turns = [{"role": "user", "content": "Can you remind me what naming convention I like?"}]


def _msg_len(m: dict) -> int:
    return len(str(m.get("content", "")))


prefix_preview = [
    {"content": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]},
    {"content": [{"type": "text", "text": pinned_profile, "cache_control": {"type": "ephemeral"}}]},
]
middle_preview = [{"content": f"[{e.provenance}] {e.text}"} for e, _ in candidates]
prefix_footer_len = sum(_msg_len(m) for m in prefix_preview + recent_turns)
middle_len = sum(_msg_len(m) for m in middle_preview)
full_len = prefix_footer_len + middle_len
# Budget = prefix/footer (untouchable) + half the middle content, so trimming
# triggers but doesn't necessarily wipe out every candidate.
char_budget = prefix_footer_len + middle_len // 2
print(f"Full un-trimmed length={full_len}, char_budget={char_budget}")

messages = assemble_context(cur, system_prompt, pinned_profile, candidates, recent_turns, NOW, char_budget=char_budget)
conn.commit()

# 7a. Pinned prefix present and first.
assert messages[0]["content"][0]["text"] == system_prompt, "system prompt is not the first message"
assert messages[0]["content"][0]["cache_control"] == {"type": "ephemeral"}, "system prompt missing cache_control"
assert messages[1]["content"][0]["text"] == pinned_profile, "pinned profile is not the second message"
print("PASS: pinned prefix present and first.")

# 7b. Total length respects char_budget.
total_len = sum(_msg_len(m) for m in messages)
assert total_len <= char_budget, f"assembled output ({total_len} chars) exceeds char_budget ({char_budget})"
print(f"PASS: assembled output ({total_len} chars) within char_budget ({char_budget}).")

# 7c. At least one candidate was dropped from the middle.
survived = sum(1 for e, _ in candidates if any(e.text in str(m.get("content", "")) for m in messages))
assert 0 < survived < len(candidates), f"expected partial trimming, got {survived}/{len(candidates)} survivors"
print(f"PASS: trimming dropped candidates ({survived}/{len(candidates)} survived).")

# 7d. Old/low-importance memory (18) was archived by recall()'s live pruning.
cur.execute("SELECT status FROM memories WHERE id = %s", (entries[18].id,))
status = cur.fetchone()[0]
assert status == "archived", f"expected prunable memory to be archived, got status={status!r}"
print("PASS: old/low-importance memory archived by live pruning.")

# 7e. access_count extends effective half-life (decision #6).
high_access_entry = entries[15]  # access_count=3
clone_no_access = MemoryEntry(
    text="clone for half-life comparison",
    embedding=high_access_entry.embedding,
    provenance="user_turn",
    timestamp=high_access_entry.timestamp,
    importance=high_access_entry.importance,
    access_count=0,
)
hl_with_access = decay_scorer.effective_half_life(high_access_entry)
hl_without_access = decay_scorer.effective_half_life(clone_no_access)
assert hl_with_access > hl_without_access, (
    f"expected access_count=3 half-life ({hl_with_access}) > access_count=0 half-life ({hl_without_access})"
)
print(f"PASS: effective_half_life scales with access_count ({hl_with_access} > {hl_without_access}).")

# 7f. match_strength scales the reinforcement bump (decision #7).
entry_a, entry_b = entries[16], entries[17]
start_a, start_b = entry_a.relevance_score, entry_b.relevance_score
assert start_a == start_b, "reinforcement test entries must start with equal relevance_score"
decay_scorer.reinforce(cur, entry_a, match_strength=0.9, now=NOW)
decay_scorer.reinforce(cur, entry_b, match_strength=0.1, now=NOW)
conn.commit()
assert entry_a.relevance_score > entry_b.relevance_score, (
    f"expected stronger match_strength to yield a bigger bump: "
    f"a={entry_a.relevance_score} b={entry_b.relevance_score}"
)
print(
    f"PASS: match-strength-scaled reinforcement "
    f"(a: {start_a}->{entry_a.relevance_score}, b: {start_b}->{entry_b.relevance_score})."
)

cur.close()
conn.close()
print("\nPhase 2 exit test PASSED.")
