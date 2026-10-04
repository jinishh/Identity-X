-- 0001 · Foundation: extensions and one schema per concern.
--
-- The database is split the way the problem is split:
--   org     who belongs where (police stations, districts, FSL, prosecution)
--   iam     people, roles, how they sign in (password, authenticator, face)
--   cases   case files and who is assigned to them
--   docs    documents, their immutable versions, extracted text, certificates
--   collab  approvals, shares, custody transfers
--   audit   the hash-chained ledger — append-only, enforced here, not in the app
--   alerts  security alerts
--   demo    demo-only data (persona roster); empty in production

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy search over document text
CREATE EXTENSION IF NOT EXISTS citext;     -- case-insensitive e-mail addresses

CREATE SCHEMA org;
CREATE SCHEMA iam;
CREATE SCHEMA cases;
CREATE SCHEMA docs;
CREATE SCHEMA collab;
CREATE SCHEMA audit;
CREATE SCHEMA alerts;
CREATE SCHEMA demo;

COMMENT ON SCHEMA org    IS 'Organisational units: state HQ, districts, police stations, FSL, prosecution, NCRB cell.';
COMMENT ON SCHEMA iam    IS 'Identity and access: users, roles, permissions, credentials (password, TOTP, face), sessions.';
COMMENT ON SCHEMA cases  IS 'Case files and case membership (who may act on which case, in what capacity).';
COMMENT ON SCHEMA docs   IS 'Documents, immutable versions, processing steps, extracted text and entities, derivatives, certificates.';
COMMENT ON SCHEMA collab IS 'Requests needing a second officer: shares, custody transfers, reviews, legal-hold release.';
COMMENT ON SCHEMA audit  IS 'Append-only, hash-chained audit ledger and its signed checkpoints.';
COMMENT ON SCHEMA alerts IS 'Security alerts raised by integrity checks, malware scanning and access patterns.';
COMMENT ON SCHEMA demo   IS 'Demo-mode helpers only (persona roster). Not used when CFV_DEMO_MODE=false.';

-- One rule shared by several tables: some rows are written once and never changed.
CREATE FUNCTION public.forbid_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% on %.% is not allowed: this table is append-only',
    TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END $$;
COMMENT ON FUNCTION public.forbid_change() IS 'Trigger body that rejects UPDATE / DELETE / TRUNCATE on append-only tables.';
