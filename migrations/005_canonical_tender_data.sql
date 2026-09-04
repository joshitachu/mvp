-- Canonical, reprocessable TenderNed data layer.
--
-- This migration is additive: the existing owner-scoped `notices` table and
-- legacy tenderned_raw*_cached tables stay online while new imports populate
-- these tables. Once historical data has been backfilled, the legacy cache
-- tables can be retired in a separately approved migration.

BEGIN;

CREATE TABLE IF NOT EXISTS tender_notices (
  id BIGSERIAL PRIMARY KEY,
  notice_id TEXT NOT NULL UNIQUE,
  publicatie_id BIGINT UNIQUE,
  publicatie_datum DATE,
  publicatie_code TEXT,
  type_publicatie TEXT,
  record_type TEXT,
  is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
  title TEXT,
  description TEXT,
  source_url TEXT,
  winner_company_id BIGINT,
  buyer_company_id BIGINT,
  listing_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_xml TEXT NOT NULL,
  parsed_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tender_notices_date ON tender_notices (publicatie_datum);
CREATE INDEX IF NOT EXISTS idx_tender_notices_type_date ON tender_notices (record_type, publicatie_datum);

CREATE TABLE IF NOT EXISTS tender_companies (
  id BIGSERIAL PRIMARY KEY,
  kvk TEXT UNIQUE,
  canonical_key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  street TEXT,
  postcode TEXT,
  city TEXT,
  province TEXT,
  country TEXT,
  website TEXT,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tender_companies_name ON tender_companies (name);
CREATE INDEX IF NOT EXISTS idx_tender_companies_province ON tender_companies (province);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tender_notices_winner_company_id_fkey') THEN
    ALTER TABLE tender_notices ADD CONSTRAINT tender_notices_winner_company_id_fkey
      FOREIGN KEY (winner_company_id) REFERENCES tender_companies(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tender_notices_buyer_company_id_fkey') THEN
    ALTER TABLE tender_notices ADD CONSTRAINT tender_notices_buyer_company_id_fkey
      FOREIGN KEY (buyer_company_id) REFERENCES tender_companies(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS tender_notice_cpvs (
  id BIGSERIAL PRIMARY KEY,
  notice_id BIGINT NOT NULL REFERENCES tender_notices(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  label TEXT,
  is_main BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT tender_notice_cpvs_notice_code_key UNIQUE (notice_id, code)
);
CREATE INDEX IF NOT EXISTS idx_tender_notice_cpvs_code ON tender_notice_cpvs (code);

CREATE TABLE IF NOT EXISTS tender_notice_lots (
  id BIGSERIAL PRIMARY KEY,
  notice_id BIGINT NOT NULL REFERENCES tender_notices(id) ON DELETE CASCADE,
  external_lot_id TEXT NOT NULL,
  title TEXT,
  description TEXT,
  awarded_company_id BIGINT REFERENCES tender_companies(id) ON DELETE SET NULL,
  award_value NUMERIC,
  currency TEXT,
  award_date DATE,
  contract_start DATE,
  contract_end DATE,
  CONSTRAINT tender_notice_lots_notice_external_key UNIQUE (notice_id, external_lot_id)
);
CREATE INDEX IF NOT EXISTS idx_tender_notice_lots_company ON tender_notice_lots (awarded_company_id);

COMMIT;
