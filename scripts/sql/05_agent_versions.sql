-- ============================================================
-- audit.agent_versions
-- Bridges the git-based agent definition workflow to the existing
-- hash-chained event log. One row per approved-and-merged change
-- to an agent's configuration. The content_hash here is what
-- audit.agent_event_log.agent_version_hash should reference for
-- every execution event going forward, so any event can be traced
-- back to the exact, reviewed configuration that produced it.
--
-- This table is itself append-only, same rationale as
-- agent_event_log: a promotion record must not be editable or
-- deletable after the fact, since it IS the audit trail of "who
-- approved this version and when."
-- ============================================================

CREATE TABLE IF NOT EXISTS audit.agent_versions (
    version_id      BIGSERIAL PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    git_commit      TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    approver        TEXT NOT NULL,
    merged_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    raw_content     TEXT NOT NULL,   -- full agent.yaml content at this commit,
                                      -- so the audit trail is self-contained
                                      -- even if the git repo is later lost
                                      -- or rewritten
    UNIQUE (agent_id, content_hash)  -- the same exact config can't be
                                      -- "promoted" twice as if it were new
);

CREATE INDEX IF NOT EXISTS idx_agent_versions_agent_id
    ON audit.agent_versions (agent_id, merged_at);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_content_hash_format'
    ) THEN
        ALTER TABLE audit.agent_versions
            ADD CONSTRAINT chk_content_hash_format
            CHECK (content_hash ~ '^[a-f0-9]{64}$');
    END IF;
END
$$;

-- Append-only enforcement, same pattern as agent_event_log.
CREATE RULE agent_versions_no_update AS
    ON UPDATE TO audit.agent_versions DO INSTEAD NOTHING;
CREATE RULE agent_versions_no_delete AS
    ON DELETE TO audit.agent_versions DO INSTEAD NOTHING;

-- Grants: a dedicated role for the promotion script, separate from
-- audit_writer (which is for execution events). Separation matters --
-- the service account that logs routine execution events should never
-- also be able to write version-approval records; that would let a
-- compromised execution-logging credential fabricate an approval.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_promoter') THEN
        CREATE ROLE audit_promoter LOGIN PASSWORD 'CHANGE_ME';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA audit TO audit_promoter;
GRANT SELECT, INSERT ON audit.agent_versions TO audit_promoter;
GRANT USAGE ON SEQUENCE audit.agent_versions_version_id_seq TO audit_promoter;
REVOKE UPDATE, DELETE, TRUNCATE ON audit.agent_versions FROM audit_promoter, PUBLIC;

-- audit_reader (already created in 02_roles.sql) should also be able
-- to read this table for dashboards/inspection.
GRANT SELECT ON audit.agent_versions TO audit_reader;
