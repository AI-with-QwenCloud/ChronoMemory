# ChronoMemory

Governed ChronoMemory-OS is a memory layer for LLM agents built around one idea: a fact is only as trustworthy as where it came from. Every memory carries a provenance tag (user turn, agent turn, tool output, third-party message, external doc, or web content), which sets a base trust score before the content is ever evaluated. Facts below a trust threshold are held for human review instead of silently entering active memory — a defense against prompt-injection-style poisoning, not just a recall feature. On top of that, memory decays over time on a Weibull-shaped curve, and contradicting facts are resolved deterministically via LLM-based natural-language-inference classification, with a full audit trail of every decision.

The backend runs on Alibaba Cloud (Qwen Cloud for all LLM calls, ECS for hosting) — see [Proof of Alibaba Cloud deployment](#proof-of-alibaba-cloud-deployment) below.

## Layout

Code is grouped by bounded context, not by technical type — the same seams the phase history was already built along (phase2 = read path, phase3 = write path):

- `core/` — shared primitives with no opinion about read or write: `memory_entry`, `embedder`, `qwen_client`, `prompts`, `trim`.
- `read_path/` — recall and everything that scores/ranks/trims what the agent sees: `recall`, `decay_scorer`, `context_assembler`, `trust`.
- `write_path/` — turning a turn into a governed memory: `extractor`, `vigil`, `contradiction_gate`, `write_loop`.
- `db/` — one-time setup: `schema.sql` (Postgres), `init_sqlite.py` (audit trail).
- `tests/` — mirrors the same three buckets; run with `python -m tests.run_exit_tests` (add `--live` for the non-deterministic Qwen-judgment suite) from the repo root.
- `app.py` — the Streamlit UI; the only file allowed to import from both `read_path` and `write_path`.

## Running it

The app needs its own Postgres (with `pgvector`) and its own Qwen API key — nothing is bundled, shared, or committed. `.env` is gitignored; you must create your own.

### Local

1. Python 3.11 (newer breaks `sentence-transformers`/`torch` wheels — see `phase4-cloud-deployment-guide.md`).
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. Start Postgres with pgvector, e.g.:
   ```
   docker run -d --name chronomem-db -e POSTGRES_PASSWORD=<pw> -e POSTGRES_DB=chronomemory -p 5432:5432 pgvector/pgvector:pg16
   docker exec -i chronomem-db psql -U postgres -d chronomemory < db/schema.sql
   ```
4. Init the SQLite audit db: `python3 db/init_sqlite.py`
5. Create a `.env` in the repo root:
   ```
   QWEN_KEY_AGENT=<your Alibaba Model Studio / DashScope API key>
   QWEN_KEY_BACKGROUND=<same key, or a separate one for extraction/scoring>
   CHRONOMEM_DB_HOST=localhost
   CHRONOMEM_DB_NAME=chronomemory
   CHRONOMEM_DB_USER=postgres
   CHRONOMEM_DB_PASSWORD=<the password you set in step 3>
   CHRONOMEM_AUTH_COOKIE_KEY=<any random secret string, e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`>
   ```
   (`CHRONOMEM_DEMO_MODE=true` optionally enables the sandbox panel in the sidebar.)
6. `streamlit run app.py` → http://localhost:8501, then use the sign-up form to create your first account.

### Alibaba Cloud (ECS)

Full architecture, troubleshooting, and teardown steps: `phase4-cloud-deployment-guide.md`. Condensed:

1. Create a RAM user scoped to `AliyunECSFullAccess` + `AliyunVPCFullAccess`, then `aliyun configure --mode AK`.
2. Provision a VPC/vSwitch/security group (`22/tcp` to your IP only, `8501/tcp` scoped or open) and a key pair; launch an instance (e.g. `ecs.t6-c1m2.large`) tagged `app=chronomemory`.
3. `rsync` the repo to `/opt/chronomemory` on the instance (exclude `.git`, `__pycache__`, `.env`, `chronomemory_audit.db`); separately `scp` a `.env` built for the remote host (`CHRONOMEM_DB_HOST=localhost`, since Postgres runs on the same box).
4. On the instance: `CHRONOMEM_DB_PASSWORD=<pw> bash deploy/bootstrap_ecs.sh`
5. Verify from your own machine (needs its own `ALIBABA_CLOUD_ACCESS_KEY_ID`/`ALIBABA_CLOUD_ACCESS_KEY_SECRET`):
   ```
   python3 deploy/verify_alibaba_deployment.py
   ```
6. Stop the instance (`StopInstance`) when you're not actively using it — port 8501 has no auth in front of it, so a running instance is reachable by anyone with the IP.

## Proof of Alibaba Cloud deployment

[`deploy/verify_alibaba_deployment.py`](deploy/verify_alibaba_deployment.py) calls the Alibaba Cloud ECS OpenAPI (`DescribeInstances`) directly via the `alibabacloud_ecs20140526` SDK, and asserts the tagged instance is `Running` with a public IP — proof the backend is actually live on Alibaba Cloud infrastructure. This is also the app's second independent point of Alibaba Cloud API usage: [`core/qwen_client.py`](core/qwen_client.py) separately calls Alibaba's Qwen Cloud (Model Studio/MaaS) endpoint for every chat completion the app makes. Full deployment architecture and reasoning: `phase4-cloud-deployment-guide.md`.

## License

MIT — see [LICENSE](LICENSE).