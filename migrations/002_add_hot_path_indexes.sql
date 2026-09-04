-- 002_add_hot_path_indexes.sql
--
-- PROBLEM
-- `notices` had only notices_pkey(id) and the (now dropped) global notice_id key.
-- Every hot read filters on import_id + owner_code and was a full seq scan:
--
--   GET /imports/{id}/notices            server.py:1012-1015
--   GET /imports/{id}/download           server.py:1088-1091
--   SROI result lookups                  server.py:1484-1487, :1917-1921, :1981-1985
--
-- Invisible at 71 rows; the measured ingest rate is ~12,640 notices/year, so this
-- table reaches six figures within a year of real use.
--
-- `func.lower(province) == region` (server.py:1021, :1097) cannot use a plain
-- index on province -- it needs the expression index.
--
-- SAFETY
-- Idempotent (IF NOT EXISTS). Plain CREATE INDEX takes a write lock; at current
-- table sizes that is instant. For a large table, use CONCURRENTLY instead
-- (which cannot run inside a transaction block).

CREATE INDEX IF NOT EXISTS idx_notices_import_owner
    ON notices (import_id, owner_code);

CREATE INDEX IF NOT EXISTS idx_notices_province_lower
    ON notices (lower(province));

CREATE INDEX IF NOT EXISTS idx_imports_owner_created
    ON imports (owner_code, created_at DESC);
