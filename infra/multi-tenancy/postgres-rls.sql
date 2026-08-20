-- Row-Level Security: defense in depth alongside application-level tenant
-- scoping. Even a query that forgets a WHERE tenant_id = ... clause cannot
-- cross tenant boundaries once RLS is enabled and the app role has no
-- BYPASSRLS privilege.
--
-- NOTE: audio_sessions and clinical_notes are aspirational -- session
-- state is currently in-process memory only (backend/audio/manager.py),
-- not persisted to Postgres; see the "Known constraint" note in
-- docs/ARCHITECTURE.md on why (Kafka/PubSub externalization deferred).
-- Their policies below apply the moment those tables are introduced, e.g.
-- if session state moves out of process memory. audit_log is the one
-- table that's real today; only its policy is active in
-- infra/local-dev/postgres-init.

ALTER TABLE IF EXISTS audio_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS clinical_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
-- FORCE, not just ENABLE: without it, the table OWNER (typically the
-- migration-running role) bypasses RLS entirely, which would make this
-- policy meaningless for any connection using that role by accident.
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'audio_sessions') THEN
        CREATE POLICY tenant_isolation_sessions ON audio_sessions
            USING (tenant_id = current_setting('app.current_tenant')::text);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'clinical_notes') THEN
        CREATE POLICY tenant_isolation_notes ON clinical_notes
            USING (tenant_id = current_setting('app.current_tenant')::text);
    END IF;
END $$;

CREATE POLICY tenant_isolation_audit ON audit_log
    USING (tenant_id = current_setting('app.current_tenant')::text);

-- App connection sets this per-request/per-connection:
--   SELECT set_config('app.current_tenant', $1, false);
-- driven by backend/tenancy/db.py's acquire_tenant_conn(), called from
-- every tenant-scoped query path (backend/audit/service.py, and the
-- /audit route in backend/main.py).

ALTER ROLE app_runtime_role NOBYPASSRLS;
