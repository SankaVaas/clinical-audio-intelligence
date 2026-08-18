-- Row-Level Security: defense in depth alongside application-level tenant
-- scoping. Even a query that forgets a WHERE tenant_id = ... clause cannot
-- cross tenant boundaries once RLS is enabled and the app role has no
-- BYPASSRLS privilege.

ALTER TABLE audio_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinical_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log      ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_sessions ON audio_sessions
    USING (tenant_id = current_setting('app.current_tenant')::text);

CREATE POLICY tenant_isolation_notes ON clinical_notes
    USING (tenant_id = current_setting('app.current_tenant')::text);

CREATE POLICY tenant_isolation_audit ON audit_log
    USING (tenant_id = current_setting('app.current_tenant')::text);

-- App connection sets this per-request/per-connection:
--   SELECT set_config('app.current_tenant', $1, false);
-- driven by backend/tenancy/middleware.py's current_tenant contextvar.

ALTER ROLE app_runtime_role NOBYPASSRLS;
