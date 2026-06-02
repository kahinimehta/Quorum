-- NeuroDiscover — PostgreSQL schema (Supabase)
-- Same contract as schema.sql. Apply once in Supabase SQL Editor or: python3 cli.py init-supabase

-- 1. EVIDENCE
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id      SERIAL PRIMARY KEY,
    source_type      TEXT NOT NULL CHECK (source_type IN ('literature','trial','grant')),
    source_id        TEXT NOT NULL,
    title            TEXT,
    year             INTEGER,
    venue            TEXT,
    subgroup         TEXT,
    mechanism        TEXT,
    treatment        TEXT,
    key_result       TEXT,
    study_type       TEXT,
    sample_size      INTEGER,
    evidence_snippet TEXT,
    url              TEXT,
    doi              TEXT,
    access_status    TEXT CHECK (access_status IN ('open','abstract_only','restricted')),
    pulled_at        TIMESTAMPTZ DEFAULT NOW(),
    last_scanned_at  TIMESTAMPTZ,
    UNIQUE (source_type, source_id)
);

-- 2. SUBGROUPS
CREATE TABLE IF NOT EXISTS subgroups (
    subgroup_id        SERIAL PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE,
    defining_features  TEXT,
    notes              TEXT
);

-- 3. TREATMENT_CONNECTIONS
CREATE TABLE IF NOT EXISTS treatment_connections (
    connection_id        SERIAL PRIMARY KEY,
    subgroup_id          INTEGER NOT NULL REFERENCES subgroups(subgroup_id),
    mechanism            TEXT,
    treatment            TEXT NOT NULL,
    evidence_strength    REAL,
    commercial_potential REAL,
    UNIQUE (subgroup_id, treatment)
);

CREATE TABLE IF NOT EXISTS connection_evidence (
    connection_id  INTEGER NOT NULL REFERENCES treatment_connections(connection_id),
    evidence_id    INTEGER NOT NULL REFERENCES evidence(evidence_id),
    PRIMARY KEY (connection_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS subgroup_evidence (
    subgroup_id    INTEGER NOT NULL REFERENCES subgroups(subgroup_id),
    evidence_id    INTEGER NOT NULL REFERENCES evidence(evidence_id),
    PRIMARY KEY (subgroup_id, evidence_id)
);

-- 4. AGENT_OUTPUTS
CREATE TABLE IF NOT EXISTS agent_outputs (
    output_id    SERIAL PRIMARY KEY,
    run_id       TEXT,
    agent_name   TEXT NOT NULL,
    step_order   INTEGER,
    summary      TEXT,
    payload      TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 5. RECOMMENDATIONS
CREATE TABLE IF NOT EXISTS recommendations (
    rec_id        SERIAL PRIMARY KEY,
    run_id        TEXT,
    connection_id INTEGER REFERENCES treatment_connections(connection_id),
    subgroup      TEXT,
    treatment     TEXT,
    confidence    REAL,
    tier          TEXT CHECK (tier IN ('Prioritize','Monitor','Reject')),
    rationale     TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 6. SCAN_STATE
CREATE TABLE IF NOT EXISTS scan_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    disease       TEXT NOT NULL DEFAULT 'Parkinson disease',
    last_scan_at  TIMESTAMPTZ,
    last_run_id   TEXT
);

INSERT INTO scan_state (id, disease) VALUES (1, 'Parkinson disease')
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_evidence_subgroup ON evidence(subgroup);
CREATE INDEX IF NOT EXISTS idx_conn_subgroup ON treatment_connections(subgroup_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_type, source_id);
