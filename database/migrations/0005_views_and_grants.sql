-- 0005 · Readable views and who may do what at the database level.

-- ───────────── views (handy in pgAdmin; contain no secrets) ─────────────
CREATE VIEW iam.v_people AS
SELECT u.service_id, u.full_name, u.rank, r.title AS role, un.name AS unit,
       u.email, u.phone, u.status,
       (t.confirmed_at IS NOT NULL) AS has_authenticator,
       (f.id IS NOT NULL)           AS has_face_login,
       u.last_login_at, u.created_at
FROM iam.users u
JOIN iam.roles r ON r.code = u.role_code
JOIN org.units un ON un.id = u.unit_id
LEFT JOIN iam.totp_credentials t ON t.user_id = u.id
LEFT JOIN iam.face_templates f ON f.user_id = u.id AND f.revoked_at IS NULL;
COMMENT ON VIEW iam.v_people IS 'Who has an account, in what role, and which sign-in methods they have set up. No secrets.';

CREATE VIEW cases.v_case_overview AS
SELECT c.case_number, c.title, c.category, c.status, c.is_victim_protected,
       un.name AS police_station, lead.full_name AS lead_io,
       (SELECT count(*) FROM docs.documents d WHERE d.case_id = c.id AND d.status = 'ACTIVE') AS documents,
       (SELECT count(*) FROM cases.case_members m WHERE m.case_id = c.id AND m.removed_at IS NULL) AS members,
       c.next_hearing_date, c.updated_at
FROM cases.cases c
JOIN org.units un ON un.id = c.unit_id
JOIN iam.users lead ON lead.id = c.lead_io_id;

CREATE VIEW docs.v_document_register AS
SELECT d.doc_number, c.case_number, d.title, d.doc_type, d.sensitivity, d.retention_state,
       v.version_no, v.sha256, v.manifest_sha256, v.signing_key_id, v.processing_status,
       v.last_verification, cust.full_name AS custodian, v.uploaded_at
FROM docs.documents d
JOIN cases.cases c ON c.id = d.case_id
LEFT JOIN docs.versions v ON v.id = d.current_version_id
JOIN iam.users cust ON cust.id = d.custodian_id;
COMMENT ON VIEW docs.v_document_register IS 'The document register: every file, its current fingerprint and signature key.';

CREATE VIEW audit.v_ledger AS
SELECT e.seq, e.occurred_at, e.actor_service_id, e.action, e.outcome, e.summary, e.purpose,
       left(e.prev_hash, 12) || '…' AS prev, left(e.event_hash, 12) || '…' AS hash
FROM audit.events e ORDER BY e.seq DESC;

-- ───────────── privileges ─────────────
-- The app (cfv_app) can read and write what it needs, but:
--   · it can never DELETE anything — evidence is withdrawn, revoked, disabled; never removed
--   · on the audit ledger it may only INSERT and SELECT
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['org','iam','cases','docs','collab','audit','alerts','demo'] LOOP
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO cfv_app, cfv_readonly', s);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO cfv_app', s);
  END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA org, iam, cases, docs, collab, alerts, demo TO cfv_app;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA audit TO cfv_app;
REVOKE UPDATE ON ALL TABLES IN SCHEMA audit FROM cfv_app;

-- Read-only inspection role: everything except secrets.
GRANT SELECT ON ALL TABLES IN SCHEMA org, cases, docs, collab, audit, alerts, demo TO cfv_readonly;
GRANT SELECT ON iam.roles, iam.permissions, iam.role_permissions, iam.sessions, iam.signing_keys, iam.v_people TO cfv_readonly;
GRANT SELECT (id, service_id, full_name, rank, role_code, unit_id, email, phone, status, activated_at,
              last_login_at, created_by, created_at) ON iam.users TO cfv_readonly;
GRANT SELECT (id, user_id, model, dims, samples, quality, enrolled_at, revoked_at) ON iam.face_templates TO cfv_readonly;
-- iam.totp_credentials and iam.activation_codes: no access at all for cfv_readonly.
-- Sensitive columns on cases/docs are encrypted at rest regardless of who reads them.
