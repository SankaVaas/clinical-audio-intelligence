-- Append-only audit table. Ordinary app roles can INSERT and SELECT only;
-- UPDATE/DELETE are revoked so tampering requires superuser DB access,
-- which is itself logged and alertable separately (cloud audit trail).

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

CREATE ROLE app_audit_writer LOGIN;
GRANT INSERT, SELECT ON audit_log TO app_audit_writer;
REVOKE UPDATE, DELETE ON audit_log FROM app_audit_writer;
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

-- Belt-and-suspenders: trigger rejects UPDATE/DELETE even for roles that
-- somehow have the grant (e.g. future migration mistake).
CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
