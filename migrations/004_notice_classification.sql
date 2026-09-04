-- 004_notice_classification.sql
--
-- PROBLEM
-- The importer filtered on TenderNed's coarse `typePublicatie == 'AGO'` and
-- treated everything it returned as an award. Measured against 300 live AGO
-- records on 2026-09-04:
--
--   awards      253  84.3%   genuine award notices
--   cancelled    27   9.0%   vroegtijdige beeindiging -- procedure was killed
--   veat         20   6.7%   intent to award without competition; NO winner yet
--
-- So ~16% of stored "awards" are not awards. VEAT rows in particular have no
-- winner, so any winner-based analysis (lead gen, market share, SROI targeting)
-- was being fed rows whose winner fields are empty or misleading.
--
-- Cancellations are the inverse problem: they were being counted as awards
-- when they are the opposite signal, and they cannot be filtered out server-side
-- because `publicatieType=VBE` is broken (returns the entire 145,300-row corpus).
--
-- FIX
-- Persist the real form code and a derived classification so downstream queries
-- can say what they actually mean.
--
-- SAFETY
-- Idempotent, additive. Existing rows get record_type NULL (unclassified) rather
-- than a guess -- they were imported before the code was captured, and inventing
-- a classification for them would be worse than admitting we do not know.

BEGIN;

-- The real eForms / standard-form code: EF29, EF25, EFE4, SF03, ...
ALTER TABLE notices ADD COLUMN IF NOT EXISTS publicatie_code text;

-- Derived: awards | veat | open_tenders | prior_information | modifications
--        | cancelled | unknown
ALTER TABLE notices ADD COLUMN IF NOT EXISTS record_type text;

-- TenderNed's coarse bucket, kept for traceability back to the source feed.
ALTER TABLE notices ADD COLUMN IF NOT EXISTS type_publicatie text;

-- Early termination, from the isVroegtijdigeBeeindiging booleans.
ALTER TABLE notices ADD COLUMN IF NOT EXISTS is_cancelled boolean NOT NULL DEFAULT false;

-- Almost every analytical query will filter on this.
CREATE INDEX IF NOT EXISTS idx_notices_record_type ON notices (record_type);
CREATE INDEX IF NOT EXISTS idx_notices_publicatie_code ON notices (publicatie_code);

COMMIT;
