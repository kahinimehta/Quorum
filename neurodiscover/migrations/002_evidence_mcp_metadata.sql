-- MCP two-stage pull metadata — run once on existing DBs.
-- Target is the shared Postgres/Supabase DB; local SQLite users should rebuild
-- (`cli.py build`) instead, since SQLite lacks ADD COLUMN IF NOT EXISTS / BOOLEAN.

-- is_preprint must be BOOLEAN to match schema.pg.sql + upsert_evidence (sends a bool).
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS is_preprint BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS publication_year INTEGER;

-- Backfill access_type for legacy rows from access_status (the column that holds
-- open/restricted/abstract_only — NOT access_type, which is brand-new/NULL here).
UPDATE evidence SET access_type = 'published_oa'
  WHERE access_type IS NULL AND access_status = 'open';
UPDATE evidence SET access_type = 'published_paywalled'
  WHERE access_type IS NULL AND access_status = 'restricted';
UPDATE evidence SET access_type = 'preprint'
  WHERE access_type IS NULL AND access_status = 'abstract_only';
UPDATE evidence SET publication_year = year
  WHERE publication_year IS NULL AND year IS NOT NULL;
