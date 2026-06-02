-- NeuroDiscover (Quorum) — SQLite schema
-- Person 3 (Data Engineer) deliverable.
-- This is the contract between the agent pipeline (Person 4),
-- the DB (Person 3), and the backend API (Person 2). Lock the field names.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. EVIDENCE  -----------------------------------------------------------
-- One row per pulled source. source_type lets manuscripts, clinical
-- trials, and grants live in the same table and feed the same agents.
CREATE TABLE evidence (
    evidence_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type      TEXT NOT NULL CHECK (source_type IN ('literature','trial','grant')),
    source_id        TEXT NOT NULL,            -- PMID / DOI / NCT id / grant core_project_num
    title            TEXT,
    year             INTEGER,
    venue            TEXT,                      -- journal / "ClinicalTrials.gov" / funder
    subgroup         TEXT,                      -- free-text tag, e.g. 'GBA-mutation PD'
    mechanism        TEXT,
    treatment        TEXT,
    key_result       TEXT,                      -- the finding, 1-2 sentences
    study_type       TEXT,                      -- in vitro / mouse / cohort / RCT / Phase 2 ...
    sample_size      INTEGER,                   -- powers the skeptic agent
    evidence_snippet TEXT,                      -- short verbatim line for the dashboard citation
    url              TEXT,
    doi              TEXT,                      -- secondary stable id when PMID missing
    access_status    TEXT CHECK (access_status IN ('open','abstract_only','restricted')),
    pulled_at        TEXT DEFAULT (datetime('now')),
    last_scanned_at  TEXT,                      -- updated on each incremental scan hit
    UNIQUE (source_type, source_id)             -- dedup: same source pulled twice = one row
);

-- 2. SUBGROUPS  ----------------------------------------------------------
CREATE TABLE subgroups (
    subgroup_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL UNIQUE,
    defining_features  TEXT,
    notes              TEXT
);

-- 3. TREATMENT_CONNECTIONS  ---------------------------------------------
-- subgroup -> mechanism -> treatment, with the two scores the
-- skeptic and commercial agents fill in later.
CREATE TABLE treatment_connections (
    connection_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    subgroup_id          INTEGER NOT NULL REFERENCES subgroups(subgroup_id),
    mechanism            TEXT,
    treatment            TEXT NOT NULL,
    evidence_strength    REAL,   -- 0-100, set by Evidence Scoring (skeptic) agent
    commercial_potential REAL,   -- 0-100, set by Commercial Discovery agent
    UNIQUE (subgroup_id, treatment)
);

-- many-to-many: which evidence backs which connection
CREATE TABLE connection_evidence (
    connection_id  INTEGER NOT NULL REFERENCES treatment_connections(connection_id),
    evidence_id    INTEGER NOT NULL REFERENCES evidence(evidence_id),
    PRIMARY KEY (connection_id, evidence_id)
);

-- many-to-many: which evidence backs which subgroup
CREATE TABLE subgroup_evidence (
    subgroup_id    INTEGER NOT NULL REFERENCES subgroups(subgroup_id),
    evidence_id    INTEGER NOT NULL REFERENCES evidence(evidence_id),
    PRIMARY KEY (subgroup_id, evidence_id)
);

-- 4. AGENT_OUTPUTS  ------------------------------------------------------
-- Append-only trace. Every agent writes one line as it runs; the
-- dashboard reads this to show "how each agent contributed".
CREATE TABLE agent_outputs (
    output_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT,                          -- groups one discovery run
    agent_name   TEXT NOT NULL,
    step_order   INTEGER,
    summary      TEXT,                          -- human-readable "what I did"
    payload      TEXT,                          -- optional JSON blob
    created_at   TEXT DEFAULT (datetime('now'))
);

-- 5. RECOMMENDATIONS  ----------------------------------------------------
CREATE TABLE recommendations (
    rec_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT,
    connection_id INTEGER REFERENCES treatment_connections(connection_id),
    subgroup      TEXT,
    treatment     TEXT,
    confidence    REAL,                          -- evidence_strength*0.55 + commercial_potential*0.45
    tier          TEXT CHECK (tier IN ('Prioritize','Monitor','Reject')),
    rationale     TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

-- 6. SCAN_STATE  ---------------------------------------------------------
-- Singleton row tracking the literature agent's last incremental scan.
CREATE TABLE scan_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    disease       TEXT NOT NULL DEFAULT 'Parkinson disease',
    last_scan_at  TEXT,
    last_run_id   TEXT
);
INSERT INTO scan_state (id, disease) VALUES (1, 'Parkinson disease');

-- Helpful indexes for the agent joins
CREATE INDEX idx_evidence_subgroup ON evidence(subgroup);
CREATE INDEX idx_conn_subgroup     ON treatment_connections(subgroup_id);
CREATE INDEX idx_evidence_source   ON evidence(source_type, source_id);
