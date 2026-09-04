-- 003_import_status.sql
--
-- PROBLEM
-- `imports` had no status column. The row was committed before any data was
-- fetched (server.py:601), so a crash, timeout or redeploy mid-import left an
-- orphan row that looked identical to a successful one -- visible in GET
-- /imports forever, with total_records NULL or 0 and no way to tell it failed.
--
-- There was also no record of how complete an import was: every HTTP or parse
-- failure was a silent `continue`, so an import could store 40 of 71 notices
-- and report success.
--
-- FIX
-- Add an explicit lifecycle status plus the per-run fetch counters, so an
-- import is self-describing:
--
--   pending    row created, work not started
--   running    fetch in progress
--   completed  finished, nothing dropped
--   partial    finished, but http_failed + parse_failed > 0
--   failed     aborted with an error (see error_message)
--
-- SAFETY
-- Idempotent. Additive only -- no existing column is altered or dropped.
-- Existing rows are backfilled to 'completed' since they predate tracking.

BEGIN;

ALTER TABLE imports ADD COLUMN IF NOT EXISTS status        text;
ALTER TABLE imports ADD COLUMN IF NOT EXISTS error_message text;
ALTER TABLE imports ADD COLUMN IF NOT EXISTS started_at    timestamptz;
ALTER TABLE imports ADD COLUMN IF NOT EXISTS finished_at   timestamptz;
ALTER TABLE imports ADD COLUMN IF NOT EXISTS listed        integer NOT NULL DEFAULT 0;
ALTER TABLE imports ADD COLUMN IF NOT EXISTS fetched       integer NOT NULL DEFAULT 0;
ALTER TABLE imports ADD COLUMN IF NOT EXISTS http_failed   integer NOT NULL DEFAULT 0;
ALTER TABLE imports ADD COLUMN IF NOT EXISTS parse_failed  integer NOT NULL DEFAULT 0;

-- Pre-existing rows finished before this column existed; treat them as done
-- rather than leaving them indistinguishable from crashed runs.
UPDATE imports SET status = 'completed' WHERE status IS NULL;

ALTER TABLE imports ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE imports ALTER COLUMN status SET NOT NULL;

ALTER TABLE imports DROP CONSTRAINT IF EXISTS imports_status_check;
ALTER TABLE imports ADD CONSTRAINT imports_status_check
    CHECK (status IN ('pending', 'running', 'completed', 'partial', 'failed'));

CREATE INDEX IF NOT EXISTS idx_imports_status ON imports (status);

COMMIT;
