-- NeuroDiscover backend queries for Person 2 (Kahii / Alia)
-- Run: python3 cli.py query "$(cat queries.sql | head -1)"  # one query at a time
-- Or use queries individually in Flask/sqlite3.

-- ---------------------------------------------------------------------------
-- GET /api/discover/parkinsons  — disease overview + subgroups + connections
-- ---------------------------------------------------------------------------

-- Subgroups with evidence counts
SELECT s.subgroup_id, s.name, s.defining_features, s.notes,
       COUNT(DISTINCT se.evidence_id) AS evidence_count
FROM subgroups s
LEFT JOIN subgroup_evidence se ON se.subgroup_id = s.subgroup_id
GROUP BY s.subgroup_id
ORDER BY s.name;

-- Treatment connections with scores and subgroup name
SELECT tc.connection_id, s.name AS subgroup, tc.mechanism, tc.treatment,
       tc.evidence_strength, tc.commercial_potential,
       (tc.evidence_strength * 0.55 + tc.commercial_potential * 0.45) AS confidence
FROM treatment_connections tc
JOIN subgroups s ON s.subgroup_id = tc.subgroup_id
ORDER BY confidence DESC NULLS LAST;

-- Evidence backing a connection (for detail panels)
SELECT e.evidence_id, e.source_type, e.source_id, e.title, e.year,
       e.key_result, e.study_type, e.sample_size, e.evidence_snippet,
       e.url, e.access_status
FROM evidence e
JOIN connection_evidence ce ON ce.evidence_id = e.evidence_id
WHERE ce.connection_id = :connection_id;

-- ---------------------------------------------------------------------------
-- GET /api/agents  — latest agent trace
-- ---------------------------------------------------------------------------

SELECT run_id, agent_name, step_order, summary, payload, created_at
FROM agent_outputs
WHERE run_id = (SELECT run_id FROM agent_outputs ORDER BY output_id DESC LIMIT 1)
ORDER BY output_id;

-- All traces grouped by run (for history)
SELECT run_id, COUNT(*) AS steps, MIN(created_at) AS started_at
FROM agent_outputs
GROUP BY run_id
ORDER BY started_at DESC;

-- ---------------------------------------------------------------------------
-- GET /api/recommendations  — ranked output
-- ---------------------------------------------------------------------------

SELECT r.rec_id, r.run_id, r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
       tc.mechanism, tc.evidence_strength, tc.commercial_potential
FROM recommendations r
LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
ORDER BY r.confidence DESC;

-- Top recommendation only
SELECT r.*, tc.mechanism
FROM recommendations r
LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
ORDER BY r.confidence DESC
LIMIT 1;

-- ---------------------------------------------------------------------------
-- Literature agent / scan monitoring
-- ---------------------------------------------------------------------------

SELECT disease, last_scan_at, last_run_id FROM scan_state WHERE id = 1;

SELECT source_type, source_id, title, access_status, pulled_at, last_scanned_at
FROM evidence
ORDER BY pulled_at DESC
LIMIT 20;

-- Evidence ready for downstream agents (Agent 2 entry point)
SELECT evidence_id, subgroup, mechanism, treatment, key_result, study_type, sample_size
FROM evidence
WHERE subgroup IS NOT NULL;
