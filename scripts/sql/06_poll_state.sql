-- ============================================================
-- ops.poll_state
-- Operational bookkeeping for the polling-based promotion workflow:
-- "what's the most recent merged_at timestamp we've already
-- processed, so we don't re-process or miss PRs."
--
-- Deliberately NOT in the audit schema and NOT append-only -- this
-- is housekeeping, not a record of who-approved-what. The actual
-- audit trail is audit.agent_versions; this table just makes
-- polling idempotent.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.poll_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Seed the starting point. Using a far-past date means the first
-- poll run will pick up every historical merged PR touching
-- agent.yaml -- intentional, so nothing from before this workflow
-- existed is silently skipped. Adjust if you want to start from
-- "now" instead.
INSERT INTO ops.poll_state (key, value)
VALUES ('agent_registry_last_merged_at', '1970-01-01T00:00:00Z')
ON CONFLICT (key) DO NOTHING;

-- audit_promoter gets read/write here, unlike on the audit tables --
-- this table is allowed to be updated, that's its whole purpose.
GRANT USAGE ON SCHEMA ops TO audit_promoter;
GRANT SELECT, INSERT, UPDATE ON ops.poll_state TO audit_promoter;
