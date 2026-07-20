# Per-User Memory Isolation — Design

## Context

ChronoMemory's `memories` table (and the SQLite audit trail) currently has no
`user_id` or `session_id` column anywhere. Every query in the read and write
paths operates over one global, unscoped pool. `app.py` has no login concept
either — Streamlit's `st.session_state` only holds ephemeral chat history for
the current browser tab, not memory ownership. In practice, anyone using the
app shares one memory pool with everyone else who has ever used it.

This is the first of four known gaps (the others — connection pooling, an
eval harness for retrieval/contradiction/poisoning-detection accuracy, and
closing out the VIGIL held-fact review loop — are deliberately out of scope
here and will each get their own design/plan later). This spec covers only
per-user memory isolation.

## Decisions made

- **Isolation unit: per-user only.** Not per-project, not per-session. A
  user's memories persist and are shared across every project/session they
  use the assistant in. Per-project scoping within a user is an explicit
  non-goal for this pass.
- **Identity: real login**, password-based, self-contained (no OAuth,
  no external identity provider).
- **Account creation: self-serve signup form** inside the app.
- **Auth library: `streamlit-authenticator`.** Hand-rolling this was
  rejected because Streamlit reruns the entire script on every interaction —
  a `session_state`-only login would log users out on every page refresh.
  `streamlit-authenticator` handles bcrypt hashing and cookie-based sessions
  that survive a refresh.
- **Existing data: wiped.** Current Postgres/SQLite contents are dev/demo
  data from building phases 1–3, not worth a backfill migration. Schema is
  dropped and recreated with the new columns from the start.

## Schema changes

### Postgres (`db/schema.sql`)

New table:

```sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`memories` gains:

```sql
user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
```

plus an index (`idx_memories_user`).

`relational_links` and `contradiction_logs` are **not** changed. They only
ever connect two memory rows, and every code path that creates a link or a
contradiction (`contradiction_gate.find_similar_active`) is scoped to one
user's memories once the change below lands — so a link spanning two users
becomes structurally impossible, not just conventionally avoided. Adding a
redundant `user_id` column there would be unused surface area.

### SQLite (`db/init_sqlite.py`)

`flagged_memories` and `audit_log` both gain a `user_id TEXT` column
(SQLite has no native UUID type; store the Postgres UUID as text), so the
"Flagged" sidebar tab and audit trail can be filtered per user.

## Auth flow (`app.py`)

- On each run, load `users(username, password_hash)` from Postgres into the
  credentials structure `streamlit-authenticator` expects.
- Render the library's login widget before anything else in the app; block
  the rest of the UI until `authentication_status` is true.
- Signup form: collect username + password, hash with the library's hasher,
  `INSERT INTO users`, then reload credentials so the new account can log in
  immediately without a restart.
- After login, resolve `username → users.id` once per run and carry that
  `user_id` through every call below. Add a logout button
  (`authenticator.logout()`).
- **Known risk to verify during implementation, not assume:**
  `streamlit-authenticator`'s public API changed between the 0.3.x and
  0.4.x lines (return values from `.login()`, presence/shape of
  `.register_user()`). The implementation step must pin a specific version
  in `requirements.txt` and check that version's actual method signatures
  before wiring calls to it.

## Read/write path changes

Every query touching `memories` gets a `user_id` filter; every place a
`MemoryEntry` is constructed gets a `user_id` to put on it.

- `core/memory_entry.py` — `MemoryEntry` gets a required `user_id: str`
  field, no default. Any construction site that forgets to pass it fails at
  construction time instead of silently defaulting into the wrong tenant's
  data.
- `read_path/recall.py`
  - `ENTRY_COLUMNS` includes `user_id`; `_row_to_entry` unpacks it.
  - `_semantic_recall` adds `AND user_id = %s`.
  - `_spreading_activation`'s memories lookup adds `AND user_id = %s` too
    (defense in depth — target ids should already be same-user via the
    invariant above, but the filter is cheap and removes any doubt).
  - `recall()` takes `user_id` as a required parameter.
- `write_path/contradiction_gate.py` — `find_similar_active` adds
  `AND user_id = %s`, so a new fact can only be compared against, superseded
  by, or linked to that same user's existing memories. `resolve_and_link`
  passes `new_entry.user_id` through.
- `write_path/vigil.py` — `build_entry(..., user_id)` sets it on the
  `MemoryEntry`; `hold()` writes `user_id` into `flagged_memories`.
- `write_path/write_loop.py` — `write_loop(turn_text, provenance, user_id)`;
  the `INSERT INTO memories` includes `user_id`; `_log_failure` takes and
  stores `user_id` on audit-log rows.
- `app.py` — every query site (sidebar Memories tab, Flagged tab, the
  "Promote to Postgres" button, `dispatch_write`/`run_blocking_write`, the
  chat flow's `recall.recall` call) passes the logged-in `user_id`.

## Testing

- Update existing tests (`tests/core/provenance_test.py`,
  `tests/read_path/phase2_exit_test.py`,
  `tests/write_path/phase3_pipeline_test.py`, `tests/read_path/trust_test.py`,
  the live suite) to construct entries and call recall/write_loop with a
  `user_id`.
- **New test, not incidental churn — this is the one that proves the fix
  works:** write a memory as user A, then confirm user B's `recall()` never
  returns it even when the query text is a near-exact semantic match to
  user A's memory. Add this alongside the existing read-path exit tests.

## Rollout

- Drop and recreate the Postgres schema and the SQLite audit db.
- Add `streamlit-authenticator` (pinned version) to `requirements.txt`.

## Explicit non-goals for this pass

Per-project scoping within a user, connection pooling, the eval harness,
closing the VIGIL held-fact review loop further, and password reset/email
flows. Each is a separate, independent gap to design and implement on its
own.
