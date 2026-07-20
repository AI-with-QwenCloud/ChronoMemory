-- Governed ChronoMemory-OS — Phase 1 schema
-- Four tables: users -> memories -> relational_links -> contradiction_logs
-- (memories.contradiction_log_id is wired up via ALTER TABLE at the bottom,
-- since contradiction_logs itself references memories.id and would
-- otherwise create a circular forward reference.)

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- for gen_random_uuid()

-- 0. users — one row per person; every memory belongs to exactly one user
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 1. memories — the core table
CREATE TABLE memories (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    serial_no            BIGSERIAL UNIQUE NOT NULL, -- deterministic max(serial_no) contradiction resolution
    text                 TEXT NOT NULL,
    embedding            VECTOR(384) NOT NULL,
    timestamp            TIMESTAMPTZ NOT NULL DEFAULT now(),
    importance           DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    relevance_score      DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    access_count         INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'archived', 'superseded')),
    superseded_by        UUID REFERENCES memories(id),
    provenance           TEXT NOT NULL
                         CHECK (provenance IN ('user_turn', 'agent_turn', 'tool_output', 'stdout',
                                                'third_party_message', 'external_doc', 'web_content')),
    trust_score          DOUBLE PRECISION NOT NULL,
    contradiction_log_id UUID, -- FK added below, after contradiction_logs exists
    last_accessed        TIMESTAMPTZ,
    kv_slot_id           TEXT
);

-- Cosine-similarity index — the read path's dual-recall search relies on this.
CREATE INDEX idx_memories_embedding_cosine
    ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Read path filters on status = 'active' constantly.
CREATE INDEX idx_memories_status ON memories (status);

-- Every read/write path query filters by user_id first.
CREATE INDEX idx_memories_user ON memories (user_id);

-- 2. relational_links — spreading-activation edges (starts empty by design)
CREATE TABLE relational_links (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    link_type   TEXT NOT NULL,
    strength    DOUBLE PRECISION NOT NULL DEFAULT 0.5
);

CREATE INDEX idx_relational_links_source ON relational_links (source_id);
CREATE INDEX idx_relational_links_target ON relational_links (target_id);

-- 3. contradiction_logs — audit trail for the write path's NLI gate
CREATE TABLE contradiction_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    winning_id  UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    losing_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    nli_label   TEXT NOT NULL,
    nli_score   DOUBLE PRECISION NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Wire up memories.contradiction_log_id now that contradiction_logs exists.
ALTER TABLE memories
    ADD CONSTRAINT fk_memories_contradiction_log
    FOREIGN KEY (contradiction_log_id) REFERENCES contradiction_logs(id);
