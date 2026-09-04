BEGIN;
CREATE TABLE IF NOT EXISTS saved_searches (
  id BIGSERIAL PRIMARY KEY, owner_code TEXT NOT NULL, name TEXT NOT NULL,
  filters JSONB NOT NULL DEFAULT '{}'::jsonb, is_alert_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  last_checked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT saved_searches_owner_name_key UNIQUE (owner_code, name)
);
CREATE TABLE IF NOT EXISTS saved_search_alerts (
  id BIGSERIAL PRIMARY KEY, saved_search_id BIGINT NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
  tender_notice_id BIGINT NOT NULL REFERENCES tender_notices(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), read_at TIMESTAMPTZ,
  CONSTRAINT saved_search_alerts_search_notice_key UNIQUE (saved_search_id, tender_notice_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_search_alerts_unread ON saved_search_alerts (saved_search_id, read_at);
COMMIT;
