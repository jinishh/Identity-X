# The database

PostgreSQL 16. Everything the application knows lives here, except the encrypted file bytes
(on write-once storage) and private signing keys (outside the database by design).

The schema is defined by plain, commented SQL in [`migrations/`](migrations/). The application
maps onto it; it does not create it. [ERD.md](ERD.md) is generated from the live catalogue.

## Schemas

| Schema | What it holds |
|---|---|
| `org` | Units — state HQ, district, police stations, FSL, prosecution, NCRB cell — as a tree |
| `iam` | Users, roles, permissions, authenticator secrets, activation codes, face templates, sessions, signing public keys |
| `cases` | Case files and who is assigned to each, in what capacity |
| `docs` | Documents, immutable versions, pipeline steps, extracted entities, full-text index, redacted copies, §63 certificates |
| `collab` | Requests that need a second officer (shares, custody transfers, reviews), and shares |
| `audit` | The hash-chained ledger and its signed checkpoints |
| `alerts` | Security alerts |
| `demo` | The persona roster used by the sign-in page in demo mode |

## Three database roles

| Role | Used by | Can |
|---|---|---|
| `cfv_owner` | migrations, demo reset | owns every schema; still blocked by the append-only triggers |
| `cfv_app` | the running API | SELECT / INSERT / UPDATE — **no DELETE anywhere**; on `audit.*` only INSERT and SELECT |
| `cfv_readonly` | pgAdmin, auditors | SELECT on structure and metadata — **not** password hashes, authenticator secrets, activation codes, face templates, or document text / extracted values |

## Protections that live in the database, not the app

| Rule | Enforced by |
|---|---|
| Ledger rows can't be changed or removed — not even by the owner | `events_append_only`, `events_no_truncate` triggers → `public.forbid_change()` |
| A sealed document version can't have its hash, signature or bytes reference changed | `versions_frozen_once_sealed` trigger |
| Versions are never deleted | `versions_never_deleted` trigger |
| Nobody approves their own request | `CHECK nobody_approves_their_own_request` |
| One lead IO per case | partial unique index `one_active_lead_io` |
| One active face template per person | partial unique index `face_templates_one_active` |
| Active users must have a password; invited ones may not sign in | `CHECK active_users_have_a_password` + app |
| Shares always expire | `CHECK shares_expire_after_creation` |
| Phone numbers, emails, service IDs, SHA-256 values are well-formed | `CHECK` constraints with regular expressions |
| The app can't delete evidence | `cfv_app` has no DELETE grant |

## Run it

```bash
scripts/db.sh init        # once: creates a private PostgreSQL 16 cluster on 127.0.0.1:5433
scripts/db.sh start       # after a reboot
```

The API applies pending migrations on start-up and seeds an empty database. To rebuild
everything from scratch: `backend/.venv/bin/python -m app.seed`.

To look at it: `scripts/pgadmin.sh` → http://127.0.0.1:5050 (two connections are pre-registered:
read-only and owner). Or `scripts/db.sh psql read`.

Local development credentials (not secrets — for this laptop only):
`cfv_owner / cfv_owner_dev`, `cfv_app / cfv_app_dev`, `cfv_readonly / cfv_read_dev`, superuser `postgres / cfv_super_dev`.

## Queries for the demo (pgAdmin → Query Tool)

On the **read only** connection:

```sql
-- who has an account, and which sign-in methods they've set up (no secrets)
SELECT * FROM iam.v_people ORDER BY role;

-- roles and what they may do
SELECT r.title, string_agg(rp.permission_code, ', ') AS permissions
FROM iam.roles r LEFT JOIN iam.role_permissions rp ON rp.role_code = r.code
GROUP BY r.title, r.tier ORDER BY r.tier;

-- the document register: every file and its current fingerprint
SELECT * FROM docs.v_document_register WHERE case_number = 'NV/SHN/0142/2026';

-- the ledger, newest first
SELECT * FROM audit.v_ledger LIMIT 20;

-- structural chain check: should return no rows
SELECT * FROM audit.chain_problems;

-- the index exists (138 pages, some with redacted twins) …
SELECT count(*) AS pages, count(*) FILTER (WHERE redacted) AS redacted_twins FROM docs.text_index;

-- … but these are refused: secrets and document content are not readable here
SELECT password_hash FROM iam.users;
SELECT body FROM docs.text_index LIMIT 1;
```

On the **owner** connection — demo sign-in details (owner only; the app can't read this):

```sql
SELECT * FROM demo.credentials;   -- live authenticator codes, computed in SQL
```

Full-text search exactly as the app runs it:

```sql
SELECT d.title, t.page_no, ts_headline('simple', t.body, q) AS snippet
FROM docs.text_index t JOIN docs.documents d ON d.id = t.document_id,
     websearch_to_tsquery('simple', 'white SUV bus stand') q
WHERE t.tsv @@ q AND NOT t.redacted;
```

…and even the schema owner is stopped here:

```sql
DELETE FROM audit.events WHERE seq = 1;
-- ERROR: DELETE on audit.events is not allowed: this table is append-only

UPDATE docs.versions SET sha256 = repeat('0', 64) WHERE processing_status = 'READY';
-- ERROR: version … is sealed; its content, hashes and signature cannot change
```

(A determined DBA can still switch a trigger off — that is exactly what the tamper lab's
T3/T4 scenarios do — and the hash chain plus the checkpoints sealed outside the database
catch it.)
