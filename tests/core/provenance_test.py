"""Pure-Python test for the provenance/trust table in memory_entry.py — no
DB, no network, no embedding model load. Should be instant and can never
flake; run this first when touching provenance or trust levels.
"""
from core.memory_entry import (
    EMBEDDING_DIM,
    TRUST_SCORES,
    VALID_PROVENANCE,
    VIGIL_FLAG_THRESHOLD,
    MemoryEntry,
)

DUMMY_EMBEDDING = [0.0] * EMBEDDING_DIM
DUMMY_USER_ID = "00000000-0000-0000-0000-000000000001"

EXPECTED_FLAGGED = {"external_doc", "web_content"}
EXPECTED_PASSING = VALID_PROVENANCE - EXPECTED_FLAGGED

EXPECTED_DESCENDING_ORDER = [
    "user_turn", "agent_turn", "tool_output", "stdout", "third_party_message",
    "external_doc", "web_content",
]

# 1. VALID_PROVENANCE and TRUST_SCORES must define exactly the same set —
# an entry in one without the other is a config bug waiting to raise
# KeyError or silently admit an unscored provenance.
assert set(TRUST_SCORES.keys()) == VALID_PROVENANCE, (
    f"TRUST_SCORES and VALID_PROVENANCE disagree: "
    f"{set(TRUST_SCORES.keys()) ^ VALID_PROVENANCE}"
)
print("PASS: VALID_PROVENANCE and TRUST_SCORES define exactly the same set.")

# 2. Every provenance constructs a MemoryEntry with the correct trust_score.
for provenance, expected_trust in TRUST_SCORES.items():
    entry = MemoryEntry(
        text=f"fact via {provenance}", embedding=DUMMY_EMBEDDING,
        provenance=provenance, user_id=DUMMY_USER_ID,
    )
    assert entry.trust_score == expected_trust, (
        f"{provenance}: expected trust_score {expected_trust}, got {entry.trust_score}"
    )
print(f"PASS: all {len(TRUST_SCORES)} provenance categories assign the expected trust_score.")

# 3. VIGIL flags exactly the sources below 0.5, and no others.
for provenance in EXPECTED_FLAGGED:
    entry = MemoryEntry(text="x", embedding=DUMMY_EMBEDDING, provenance=provenance, user_id=DUMMY_USER_ID)
    assert entry.is_flagged(), f"{provenance} (trust={entry.trust_score}) should be flagged"

for provenance in EXPECTED_PASSING:
    entry = MemoryEntry(text="x", embedding=DUMMY_EMBEDDING, provenance=provenance, user_id=DUMMY_USER_ID)
    assert not entry.is_flagged(), f"{provenance} (trust={entry.trust_score}) should NOT be flagged"

print(f"PASS: VIGIL flags exactly {sorted(EXPECTED_FLAGGED)} (below {VIGIL_FLAG_THRESHOLD}), no others.")

# 4. The trust hierarchy is strictly descending in the order the system
# prompt claims — if this drifts, the agent is telling itself something untrue.
scores_in_order = [TRUST_SCORES[p] for p in EXPECTED_DESCENDING_ORDER]
for higher, lower in zip(scores_in_order, scores_in_order[1:]):
    assert higher >= lower, (
        f"trust hierarchy is not descending: {EXPECTED_DESCENDING_ORDER} -> {scores_in_order}"
    )
print("PASS: trust hierarchy is monotonically descending in the documented order.")

# 5. An invalid provenance is still rejected (unchanged regression guard).
try:
    MemoryEntry(text="x", embedding=DUMMY_EMBEDDING, provenance="not_a_real_source", user_id=DUMMY_USER_ID)
    raise AssertionError("expected ValueError for an invalid provenance")
except ValueError:
    print("PASS: an invalid provenance is still rejected.")

# 6. user_id is required and stored exactly as given.
entry_with_user = MemoryEntry(
    text="x", embedding=DUMMY_EMBEDDING, provenance="user_turn", user_id=DUMMY_USER_ID
)
assert entry_with_user.user_id == DUMMY_USER_ID, "user_id must be stored exactly as given"
print("PASS: user_id is stored exactly as given.")

# 7. An empty user_id is rejected.
try:
    MemoryEntry(text="x", embedding=DUMMY_EMBEDDING, provenance="user_turn", user_id="")
    raise AssertionError("expected ValueError for an empty user_id")
except ValueError:
    print("PASS: an empty user_id is still rejected.")

print("\nProvenance test PASSED (fully deterministic, zero network/DB calls).")
