-- Same schema as infra/audit/postgres-audit-schema.sql, adapted only to
-- add a password to the app role (a real deployment gets this role's
-- credential from the secrets manager, not a hardcoded SQL file -- see
-- infra/security/external-secret.yaml). Kept as close to the production
-- schema as possible so local dev actually exercises the same DDL.

CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    actor_id      TEXT NOT NULL,
    action        TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id   TEXT NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{}',
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    prev_hash     TEXT NOT NULL,
    entry_hash    TEXT NOT NULL
);

CREATE INDEX idx_audit_tenant_time ON audit_log (tenant_id, timestamp DESC);
CREATE INDEX idx_audit_resource ON audit_log (resource_type, resource_id);

-- Dev-only password, not a secret worth protecting -- this database is
-- not reachable outside the docker-compose network.
CREATE ROLE app_runtime LOGIN PASSWORD 'dev_only_not_a_real_secret';

GRANT INSERT, SELECT ON audit_log TO app_runtime;
REVOKE UPDATE, DELETE ON audit_log FROM app_runtime;
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

-- Row-Level Security, exercised locally too, not just documented for
-- production -- see infra/multi-tenancy/postgres-rls.sql for the full
-- version with the audio_sessions/clinical_notes policies that only
-- apply once those tables exist.
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_audit ON audit_log
    USING (tenant_id = current_setting('app.current_tenant')::text);

ALTER ROLE app_runtime NOBYPASSRLS;
