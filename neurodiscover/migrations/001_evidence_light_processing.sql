-- Run once on existing DBs (Supabase SQL editor or sqlite3 neurodiscover.db)
-- Safe to re-run: ignore "duplicate column" errors.

-- SQLite / Postgres (adjust IF NOT EXISTS per engine)
ALTER TABLE evidence ADD COLUMN abstract TEXT;
ALTER TABLE evidence ADD COLUMN methods_text TEXT;
ALTER TABLE evidence ADD COLUMN results_text TEXT;
ALTER TABLE evidence ADD COLUMN discussion_text TEXT;
ALTER TABLE evidence ADD COLUMN access_type TEXT;
ALTER TABLE evidence ADD COLUMN full_text_url TEXT;
