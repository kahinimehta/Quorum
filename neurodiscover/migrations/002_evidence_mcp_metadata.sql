-- MCP two-stage pull metadata (run once on existing DBs)
-- Safe to re-run: ignore "duplicate column" errors.

ALTER TABLE evidence ADD COLUMN is_preprint INTEGER DEFAULT 0;
ALTER TABLE evidence ADD COLUMN publication_year INTEGER;

-- SQLite: recreate CHECK by copying table if needed; for existing rows map legacy access_type:
--   open -> published_oa, restricted -> published_paywalled
UPDATE evidence SET access_type = 'published_oa' WHERE access_type = 'open';
UPDATE evidence SET access_type = 'published_paywalled' WHERE access_type = 'restricted';
UPDATE evidence SET publication_year = year WHERE publication_year IS NULL AND year IS NOT NULL;
