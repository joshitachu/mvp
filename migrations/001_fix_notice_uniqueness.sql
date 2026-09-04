-- 001_fix_notice_uniqueness.sql
--
-- PROBLEM
-- `notices.notice_id` carried a GLOBAL unique constraint (notices_notice_id_key).
-- The upsert in server.py used `ON CONFLICT (notice_id) DO UPDATE SET
-- import_id = excluded.import_id, ..., owner_code = excluded.owner_code`.
--
-- Consequence: when a second user imported an overlapping date range, every
-- shared notice was re-parented to the newer import AND had its owner_code
-- overwritten. The earlier import silently lost those rows while its
-- `total_records` counter still advertised the original count.
--
-- Reproduced 2026-09-04: import A went from 71 rows to 0 while still
-- reporting total_records = 71.
--
-- FIX
-- Uniqueness belongs to (import_id, notice_id): the same TenderNed notice may
-- legitimately appear in many imports, once per import.
--
-- SAFETY
-- Idempotent. Run inside a transaction. Aborts if duplicate (import_id,
-- notice_id) pairs exist rather than silently discarding rows.

BEGIN;

-- Guard: refuse to proceed if the new constraint would be violated.
DO $$
DECLARE
    dup_count bigint;
BEGIN
    SELECT count(*) INTO dup_count
    FROM (
        SELECT import_id, notice_id
        FROM notices
        WHERE notice_id IS NOT NULL
        GROUP BY import_id, notice_id
        HAVING count(*) > 1
    ) d;

    IF dup_count > 0 THEN
        RAISE EXCEPTION
            'Cannot add UNIQUE(import_id, notice_id): % duplicate pair(s) exist. Resolve before migrating.',
            dup_count;
    END IF;
END $$;

ALTER TABLE notices DROP CONSTRAINT IF EXISTS notices_notice_id_key;

ALTER TABLE notices
    ADD CONSTRAINT notices_import_id_notice_id_key UNIQUE (import_id, notice_id);

COMMIT;
