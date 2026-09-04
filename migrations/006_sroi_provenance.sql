-- Make every SROI result explicit about whether it is a grounded AI assessment
-- or an insufficient-evidence keyword fallback.
BEGIN;
ALTER TABLE sroi_results ADD COLUMN IF NOT EXISTS analysis_method TEXT;
ALTER TABLE sroi_results ADD COLUMN IF NOT EXISTS verdict TEXT;
ALTER TABLE notice_sroi_results ADD COLUMN IF NOT EXISTS analysis_method TEXT;
ALTER TABLE notice_sroi_results ADD COLUMN IF NOT EXISTS verdict TEXT;
COMMIT;
