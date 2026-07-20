# ChronoMemory

## Layout

Code is grouped by bounded context, not by technical type — the same seams the phase history was already built along (phase2 = read path, phase3 = write path):

- `core/` — shared primitives with no opinion about read or write: `memory_entry`, `embedder`, `qwen_client`, `prompts`, `trim`.
- `read_path/` — recall and everything that scores/ranks/trims what the agent sees: `recall`, `decay_scorer`, `context_assembler`, `trust`.
- `write_path/` — turning a turn into a governed memory: `extractor`, `vigil`, `contradiction_gate`, `write_loop`.
- `db/` — one-time setup: `schema.sql` (Postgres), `init_sqlite.py` (audit trail).
- `tests/` — mirrors the same three buckets; run with `python -m tests.run_exit_tests` (add `--live` for the non-deterministic Qwen-judgment suite) from the repo root.
- `app.py` — the Streamlit UI; the only file allowed to import from both `read_path` and `write_path`.