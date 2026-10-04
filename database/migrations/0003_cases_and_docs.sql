-- 0003 · Case files, documents and everything derived from them.

-- ───────────── cases ─────────────
CREATE TABLE cases.cases (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_number            text NOT NULL UNIQUE,            -- NV/SHN/0142/2026
  fir_number             text NOT NULL,
  fir_date               date NOT NULL,
  unit_id                uuid NOT NULL REFERENCES org.units(id),
  title                  text NOT NULL,                   -- never the victim's name
  category               text NOT NULL CHECK (category IN ('CRIME_AGAINST_WOMEN','CRIME_AGAINST_CHILDREN','CYBER','PROPERTY','BODILY_HARM','ECONOMIC','NARCOTICS','OTHER')),
  offence_sections       text[] NOT NULL DEFAULT '{}',
  status                 text NOT NULL DEFAULT 'REGISTERED' CHECK (status IN ('REGISTERED','UNDER_INVESTIGATION','CHARGESHEET_FILED','FINAL_REPORT_FILED','UNDER_TRIAL','DISPOSED','CLOSED')),
  is_victim_protected    boolean NOT NULL DEFAULT false,
  victim_pseudonym       text,
  victim_identifiers_enc bytea,                           -- names/addresses to redact, encrypted
  default_sensitivity    text NOT NULL CHECK (default_sensitivity IN ('INTERNAL','CONFIDENTIAL','RESTRICTED','VICTIM_PROTECTED')),
  lead_io_id             uuid NOT NULL REFERENCES iam.users(id),
  court_name             text,
  next_hearing_date      date,
  description            text,
  created_by             uuid NOT NULL REFERENCES iam.users(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  closed_at              timestamptz,
  UNIQUE (unit_id, fir_number)
);
COMMENT ON TABLE cases.cases IS 'One row per FIR. Crimes against women and children are victim-protected automatically (BNS §72).';
COMMENT ON COLUMN cases.cases.victim_identifiers_enc IS 'Encrypted register of victim identifiers. Only ever decrypted inside the redaction step; never returned by the API.';
CREATE INDEX cases_unit_idx ON cases.cases(unit_id);
CREATE INDEX cases_status_idx ON cases.cases(status);

CREATE TABLE cases.case_members (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id        uuid NOT NULL REFERENCES cases.cases(id),
  user_id        uuid NOT NULL REFERENCES iam.users(id),
  capacity       text NOT NULL CHECK (capacity IN ('LEAD_IO','CO_IO','SUPERVISOR','PROSECUTOR','FORENSIC')),
  added_by       uuid NOT NULL REFERENCES iam.users(id),
  added_at       timestamptz NOT NULL DEFAULT now(),
  expires_at     timestamptz,
  removed_by     uuid REFERENCES iam.users(id),
  removed_at     timestamptz,
  removal_reason text
);
COMMENT ON TABLE cases.case_members IS 'Access to a case comes from here (plus supervisor jurisdiction, custody and shares). Members are removed, never deleted.';
CREATE UNIQUE INDEX one_active_lead_io ON cases.case_members(case_id) WHERE capacity = 'LEAD_IO' AND removed_at IS NULL;
CREATE UNIQUE INDEX one_active_membership ON cases.case_members(case_id, user_id) WHERE removed_at IS NULL;
CREATE INDEX case_members_user_idx ON cases.case_members(user_id) WHERE removed_at IS NULL;

-- ───────────── docs ─────────────
CREATE TABLE docs.documents (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_number         text NOT NULL UNIQUE,
  case_id            uuid NOT NULL REFERENCES cases.cases(id),
  title              text NOT NULL,
  doc_type           text NOT NULL CHECK (doc_type IN ('FIR','COMPLAINT','CASE_DIARY','WITNESS_STATEMENT','VICTIM_STATEMENT','ACCUSED_STATEMENT','SEIZURE_MEMO','ARREST_MEMO','MEDICAL_REPORT','FORENSIC_REPORT','PHOTO_EVIDENCE','CCTV_STILL','INVESTIGATION_REPORT','CHARGESHEET','COURT_FILING','COURT_ORDER','LEGAL_NOTICE','JUDGMENT','OTHER')),
  sensitivity        text NOT NULL CHECK (sensitivity IN ('INTERNAL','CONFIDENTIAL','RESTRICTED','VICTIM_PROTECTED')),
  retention_state    text NOT NULL DEFAULT 'ACTIVE' CHECK (retention_state IN ('ACTIVE','LEGAL_HOLD','ARCHIVED')),
  legal_hold_reason  text,
  legal_hold_by      uuid REFERENCES iam.users(id),
  legal_hold_at      timestamptz,
  status             text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','WITHDRAWN')),
  withdrawn_reason   text,
  withdrawn_by       uuid REFERENCES iam.users(id),
  withdrawn_at       timestamptz,
  custodian_id       uuid NOT NULL REFERENCES iam.users(id),
  current_version_id uuid,                                 -- FK added below (circular)
  tags               text[] NOT NULL DEFAULT '{}',
  created_by         uuid NOT NULL REFERENCES iam.users(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE docs.documents IS 'The logical document. Its bytes live in versions; documents are withdrawn, never deleted.';
CREATE INDEX documents_case_idx ON docs.documents(case_id);
CREATE INDEX documents_title_trgm ON docs.documents USING gin (title gin_trgm_ops);

CREATE TABLE docs.versions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id         uuid NOT NULL REFERENCES docs.documents(id),
  version_no          integer NOT NULL CHECK (version_no >= 1),
  parent_version_id   uuid REFERENCES docs.versions(id),
  change_note         text,
  original_filename   text NOT NULL,
  detected_mime       text NOT NULL,
  size_bytes          bigint NOT NULL CHECK (size_bytes > 0),
  sha256              char(64) NOT NULL,                   -- of the plaintext, computed by the server
  client_sha256       char(64) NOT NULL,                   -- computed in the officer's browser
  prev_version_sha256 char(64),                            -- links versions into a chain
  ciphertext_sha256   char(64),
  storage_key         text,
  enc_nonce           bytea,
  wrapped_dek         bytea,                               -- per-file key, wrapped by the KEK
  kek_id              text,
  manifest            jsonb,
  manifest_sha256     char(64),
  signature           bytea,                               -- Ed25519 over the canonical manifest
  signing_key_id      text REFERENCES iam.signing_keys(kid),
  processing_status   text NOT NULL DEFAULT 'RECEIVED' CHECK (processing_status IN ('RECEIVED','PROCESSING','READY','QUARANTINED','FAILED')),
  scan_result         text NOT NULL DEFAULT 'PENDING' CHECK (scan_result IN ('PENDING','CLEAN','INFECTED','SKIPPED','ERROR')),
  scan_detail         text,
  page_count          integer,
  ocr_status          text NOT NULL DEFAULT 'PENDING' CHECK (ocr_status IN ('PENDING','DONE','NOT_APPLICABLE','FAILED')),
  review_status       text NOT NULL DEFAULT 'NOT_REQUIRED' CHECK (review_status IN ('NOT_REQUIRED','PENDING','APPROVED','RETURNED')),
  retain_until        timestamptz,
  uploaded_by         uuid NOT NULL REFERENCES iam.users(id),
  uploaded_at         timestamptz NOT NULL DEFAULT now(),
  last_verified_at    timestamptz,
  last_verification   text CHECK (last_verification IN ('VERIFIED','FAILED')),
  UNIQUE (document_id, version_no),
  CONSTRAINT sha_is_hex CHECK (sha256 ~ '^[0-9a-f]{64}$')
);
COMMENT ON TABLE docs.versions IS 'One immutable upload. Once READY, only review status and verification results may change (enforced by trigger).';
CREATE INDEX versions_sha_idx ON docs.versions(sha256);

ALTER TABLE docs.documents
  ADD CONSTRAINT documents_current_version_fk FOREIGN KEY (current_version_id) REFERENCES docs.versions(id);

-- A sealed version is frozen: only bookkeeping columns may move.
CREATE FUNCTION docs.freeze_sealed_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.processing_status = 'READY' AND (
       NEW.sha256 IS DISTINCT FROM OLD.sha256 OR
       NEW.ciphertext_sha256 IS DISTINCT FROM OLD.ciphertext_sha256 OR
       NEW.storage_key IS DISTINCT FROM OLD.storage_key OR
       NEW.wrapped_dek IS DISTINCT FROM OLD.wrapped_dek OR
       NEW.manifest IS DISTINCT FROM OLD.manifest OR
       NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256 OR
       NEW.signature IS DISTINCT FROM OLD.signature OR
       NEW.uploaded_by IS DISTINCT FROM OLD.uploaded_by OR
       NEW.uploaded_at IS DISTINCT FROM OLD.uploaded_at OR
       NEW.processing_status IS DISTINCT FROM OLD.processing_status) THEN
    RAISE EXCEPTION 'version % is sealed; its content, hashes and signature cannot change', OLD.id
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER versions_frozen_once_sealed BEFORE UPDATE ON docs.versions
  FOR EACH ROW EXECUTE FUNCTION docs.freeze_sealed_version();
CREATE TRIGGER versions_never_deleted BEFORE DELETE ON docs.versions
  FOR EACH ROW EXECUTE FUNCTION public.forbid_change();

CREATE TABLE docs.processing_steps (
  id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  version_id  uuid NOT NULL REFERENCES docs.versions(id),
  step        text NOT NULL,
  seq         smallint NOT NULL,
  status      text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','DONE','SKIPPED','FAILED')),
  critical    boolean NOT NULL,
  started_at  timestamptz,
  finished_at timestamptz,
  detail      jsonb NOT NULL DEFAULT '{}',
  UNIQUE (version_id, step)
);
COMMENT ON TABLE docs.processing_steps IS 'The upload pipeline, step by step — what the officer watches live after uploading.';

CREATE TABLE docs.entities (
  id                   bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  version_id           uuid NOT NULL REFERENCES docs.versions(id),
  type                 text NOT NULL,
  value                text NOT NULL,
  page_no              integer NOT NULL,
  is_pii               boolean NOT NULL DEFAULT false,
  is_victim_identifier boolean NOT NULL DEFAULT false,
  confidence           real NOT NULL DEFAULT 1,
  source               text NOT NULL DEFAULT 'REGEX'
);
CREATE INDEX entities_version_idx ON docs.entities(version_id);

CREATE TABLE docs.derivatives (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_version_id uuid NOT NULL REFERENCES docs.versions(id),
  kind              text NOT NULL CHECK (kind IN ('REDACTED','CERTIFICATE_PDF','THUMBNAIL','OCR_PDF')),
  status            text NOT NULL DEFAULT 'READY',
  mime              text NOT NULL DEFAULT 'application/pdf',
  storage_key       text NOT NULL,
  sha256            char(64) NOT NULL,
  enc_nonce         bytea NOT NULL,
  wrapped_dek       bytea NOT NULL,
  kek_id            text NOT NULL,
  summary           jsonb NOT NULL DEFAULT '{}',
  created_by        uuid NOT NULL REFERENCES iam.users(id),
  created_at        timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE docs.derivatives IS 'Files made from a version: auto-redacted copies and §63 certificate PDFs. Encrypted like originals.';
CREATE INDEX derivatives_source_idx ON docs.derivatives(source_version_id);

-- Full-text index: one row per page, plus a redacted twin for victim-protected documents.
CREATE TABLE docs.text_index (
  id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  version_id  uuid NOT NULL REFERENCES docs.versions(id),
  document_id uuid NOT NULL REFERENCES docs.documents(id),
  page_no     integer NOT NULL,
  redacted    boolean NOT NULL,
  body        text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', body)) STORED
);
COMMENT ON TABLE docs.text_index IS 'Searchable page text. People who may only see redacted copies are only ever matched against redacted rows.';
CREATE INDEX text_index_tsv ON docs.text_index USING gin (tsv);
CREATE INDEX text_index_trgm ON docs.text_index USING gin (body gin_trgm_ops);
CREATE INDEX text_index_doc ON docs.text_index(document_id);

CREATE TABLE docs.certificates (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cert_number           text NOT NULL UNIQUE,
  version_id            uuid NOT NULL REFERENCES docs.versions(id),
  verification_code     text NOT NULL UNIQUE CHECK (verification_code ~ '^[A-Z2-7]{12}$'),
  sha256                char(64) NOT NULL,
  part_a                jsonb NOT NULL,
  part_b                jsonb NOT NULL,
  signatory_name        text NOT NULL,
  signatory_designation text NOT NULL,
  purpose               text,
  pdf_derivative_id     uuid REFERENCES docs.derivatives(id),
  signature             bytea NOT NULL,
  signing_key_id        text NOT NULL REFERENCES iam.signing_keys(kid),
  status                text NOT NULL DEFAULT 'ISSUED' CHECK (status IN ('ISSUED','REVOKED')),
  revoked_reason        text,
  revoked_at            timestamptz,
  issued_by             uuid NOT NULL REFERENCES iam.users(id),
  issued_at             timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE docs.certificates IS 'Bharatiya Sakshya Adhiniyam §63 certificates, pre-filled for signature. The verification code is printed as a QR.';
