-- 0002 · Organisation and identity.

-- ───────────── org ─────────────
CREATE TABLE org.units (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code       text NOT NULL UNIQUE,
  name       text NOT NULL,
  type       text NOT NULL CHECK (type IN ('STATE_HQ','DISTRICT_HQ','POLICE_STATION','FSL','PROSECUTION_OFFICE','NCRB_CELL')),
  parent_id  uuid REFERENCES org.units(id),
  district   text,
  state      text
);
COMMENT ON TABLE org.units IS 'Hierarchy of units. A supervisor oversees their unit and everything below it.';

-- ───────────── roles & permissions ─────────────
CREATE TABLE iam.roles (
  code              text PRIMARY KEY,
  title             text NOT NULL,
  description       text NOT NULL,
  tier              smallint NOT NULL,          -- display order, highest authority first
  is_administrative boolean NOT NULL,           -- manages accounts, never case content
  sees_case_content boolean NOT NULL
);
COMMENT ON TABLE iam.roles IS 'System roles. Administrative roles manage accounts but can never open case documents.';

CREATE TABLE iam.permissions (
  code        text PRIMARY KEY,
  description text NOT NULL
);

CREATE TABLE iam.role_permissions (
  role_code       text NOT NULL REFERENCES iam.roles(code),
  permission_code text NOT NULL REFERENCES iam.permissions(code),
  PRIMARY KEY (role_code, permission_code)
);
COMMENT ON TABLE iam.role_permissions IS 'System-wide permissions per role. Case-level access also depends on case membership and document sensitivity (see app/policy.py).';

-- ───────────── users ─────────────
CREATE TABLE iam.users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id     text NOT NULL UNIQUE CHECK (service_id ~ '^[A-Z]{2}-[A-Z]{2,4}-[0-9]{3,6}$'),
  full_name      text NOT NULL,
  rank           text,
  role_code      text NOT NULL REFERENCES iam.roles(code),
  unit_id        uuid NOT NULL REFERENCES org.units(id),
  email          citext NOT NULL UNIQUE CHECK (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  phone          text NOT NULL UNIQUE CHECK (phone ~ '^\+91[6-9][0-9]{9}$'),
  status         text NOT NULL DEFAULT 'INVITED' CHECK (status IN ('INVITED','ACTIVE','LOCKED','DISABLED')),
  password_hash  text,                        -- argon2id; NULL until the officer activates
  failed_logins  integer NOT NULL DEFAULT 0,
  locked_until   timestamptz,
  step_up_until  timestamptz,                 -- 2FA re-entered recently (for downloads etc.)
  activated_at   timestamptz,
  last_login_at  timestamptz,
  created_by     uuid REFERENCES iam.users(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT active_users_have_a_password CHECK (status = 'INVITED' OR password_hash IS NOT NULL)
);
COMMENT ON TABLE iam.users IS 'Officers and staff. Created by an admin as INVITED; the officer activates with a one-time code, sets a password and enrols an authenticator.';
COMMENT ON COLUMN iam.users.password_hash IS 'argon2id hash. Passwords are never stored or recoverable.';
CREATE INDEX users_unit_idx ON iam.users(unit_id);

-- Authenticator app (TOTP) — the second factor, always required.
CREATE TABLE iam.totp_credentials (
  user_id            uuid PRIMARY KEY REFERENCES iam.users(id),
  secret_enc         bytea NOT NULL,          -- AES-256-GCM under the KEK
  confirmed_at       timestamptz,             -- NULL while enrolment is in progress
  last_used_counter  bigint                   -- refuses replay of a code already used
);
COMMENT ON TABLE iam.totp_credentials IS 'Authenticator-app secret per user, encrypted. Every sign-in ends with a code from it.';

-- One-time activation codes handed to a new officer by their admin.
CREATE TABLE iam.activation_codes (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES iam.users(id),
  code_hash  text NOT NULL,                   -- sha-256 of the code; the code itself is shown once
  issued_by  uuid REFERENCES iam.users(id),
  issued_at  timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  used_at    timestamptz
);
CREATE INDEX activation_codes_user_idx ON iam.activation_codes(user_id);

-- Face sign-in: a face template (not a photo), encrypted. Optional, enrolled from Settings.
CREATE TABLE iam.face_templates (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES iam.users(id),
  template_enc bytea NOT NULL,                -- AES-256-GCM of a float32 embedding
  model        text NOT NULL,                 -- which network produced it
  dims         smallint NOT NULL,
  samples      smallint NOT NULL,             -- frames averaged at enrolment
  quality      real,                          -- mean detection confidence
  enrolled_at  timestamptz NOT NULL DEFAULT now(),
  revoked_at   timestamptz
);
COMMENT ON TABLE iam.face_templates IS 'Face embeddings for passwordless first factor. No images are stored. The authenticator code is still required after a face match.';
CREATE UNIQUE INDEX face_templates_one_active ON iam.face_templates(user_id) WHERE revoked_at IS NULL;

-- Server-side sessions, so a sign-out or an admin action takes effect immediately.
CREATE TABLE iam.sessions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES iam.users(id),
  first_factor text NOT NULL CHECK (first_factor IN ('PASSWORD','FACE','ACTIVATION')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  last_seen_at timestamptz,
  revoked_at   timestamptz,
  ip           text,
  user_agent   text
);
CREATE INDEX sessions_user_idx ON iam.sessions(user_id) WHERE revoked_at IS NULL;

-- Ed25519 public keys used to sign manifests, checkpoints and certificates.
CREATE TABLE iam.signing_keys (
  kid        text PRIMARY KEY,
  purpose    text NOT NULL CHECK (purpose IN ('MANIFEST','CHECKPOINT','CERTIFICATE','USER_ATTESTATION')),
  algorithm  text NOT NULL DEFAULT 'Ed25519',
  public_key bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  retired_at timestamptz
);
COMMENT ON TABLE iam.signing_keys IS 'Public halves only. Private keys live outside the database (key files in the prototype; HSM / Vault in production).';

-- ───────────── demo ─────────────
CREATE TABLE demo.personas (
  user_id  uuid PRIMARY KEY REFERENCES iam.users(id),
  sort     smallint NOT NULL,
  headline text NOT NULL,
  shows    text NOT NULL,
  activation_code text  -- demo only: lets the video show first-time activation of an INVITED account
);
COMMENT ON TABLE demo.personas IS 'Which seeded accounts the sign-in page offers in demo mode, and what each one is for.';
