# Case-File Vault

**SIH 2026 · PS 26190 · Team Identity X (186448)**
Secure digital document management for legal & investigation documents —
Ministry of Home Affairs / NCRB, Women Safety Division.

> Protect → Prove → Trace → Verify → Certify

A case-centric evidence vault. Every document is fingerprinted in the officer's browser,
re-checked on the server, encrypted with its own key, stored write-once, sealed with a signed
manifest and anchored into a hash-chained audit ledger. Access depends on the officer's role
**on that case** and the document's sensitivity. Victim identity is protected by design
(BNS §72). Courts verify a copy without the file ever leaving their machine.

## What you can see in the prototype

| Area | What works (real code, not mock-ups) |
|---|---|
| Sign-in | Email **or** mobile number + password, **or** face (after registering it in Settings) — then an authenticator code, always. Codes are single-use; lockout after 5 failures; server-side sessions you can end remotely. |
| First sign-in | Admin creates the account (INVITED) and hands over a one-time activation code → officer proves identity, sets their own password, links an authenticator app by QR. |
| Roles | Super Admin (state) · Admin (district) · Supervisor · Investigator · Prosecutor · Forensic Expert · Auditor — defined in `iam.roles`, administrators never see case content. |
| Face sign-in | Runs in the browser (face-api): detection, landmarks, blink check, 128-d template. Only the template is sent; stored encrypted in `iam.face_templates`. 1:1 when an identifier is typed, 1:N otherwise. |
| Database | PostgreSQL 16 with 8 schemas, versioned SQL migrations, three roles (owner / app / read-only), append-only triggers, CHECK constraints, full-text search. See [database/README.md](database/README.md). |
| Cases | Role-aware dashboards, case list, case workspace, people, chain-of-custody timeline, status lifecycle, register case. |
| Upload pipeline | SHA-256 in the browser → server re-hash (mismatch = rejected + alert) → file-signature validation → malware signature scan (EICAR → quarantine) → **AES-256-GCM, one key per file** (envelope encryption) → write-once storage → **Ed25519-signed manifest** → audit anchor → text extraction → entity & PII detection → **auto-redaction** for victim-protected records → full-text index. Live, step by step. |
| Access control | Case membership + supervisor jurisdiction + custody + time-limited shares. Four sensitivity levels. 428 "state your purpose" and "re-enter 2FA" prompts. Every denial is audited; repeated denials raise an alert. |
| Victim protection | Victim-protected cases default to the highest sensitivity; non-key members automatically get a redacted copy; every view of an original needs a purpose and alerts the supervisor. |
| Viewer | Canvas-rendered, watermarked with the viewer's name, service ID, time and case. Downloads are a separate audited action and stay byte-identical. |
| Versions | Immutable, hash-linked versions (each manifest carries the previous version's hash). |
| Collaboration | Share requests → supervisor approval (no self-approval) → scoped, expiring shares; two-party custody transfer; charge-sheet review. |
| Integrity | One-click 9-check verification; whole-chain audit verification with signed **Merkle checkpoints** sealed outside the database. |
| §63 certificate | Pre-filled BSA §63 PDF (Part A + hash for Part B) with QR → public verification page → **MATCH / MISMATCH** computed from a hash made in the verifier's browser. |
| Search | Full-text search over extracted text and metadata, page-level snippets, redacted snippets for redacted-only viewers. |
| Alerts | Malware, in-transit tampering, integrity failure, chain break, denial bursts, off-hours access, victim-record access. |
| Tamper lab | Admin-only demo panel: overwrite evidence (blocked), flip ciphertext bytes (caught), edit an audit row (caught), rewrite the whole chain (caught by sealed checkpoints). |

## Run it with Docker (easiest — Windows, Mac or Linux)

Only [Docker Desktop](https://www.docker.com/products/docker-desktop/) is needed. In this folder:

```bash
docker compose up --build
```

First start takes a few minutes (downloads, then seeds the demo world). Open
http://localhost:5173 when the `web` container is up.

Demo logins and the current authenticator codes (refresh every 30 s):

```bash
docker compose exec db psql -U cfv_owner -d case_file_vault -c "SELECT * FROM demo.credentials;"
```

| Task | Command |
|---|---|
| Stop | `docker compose down` |
| Wipe all data and start fresh | `docker compose down -v` then `docker compose up --build` |
| End-to-end test (46 checks, resets data at the end) | `docker compose exec api python tests/smoke_test.py` |

Ports used: 5173 (web), 8010 (API), 5433 (PostgreSQL, for pgAdmin).

## Run it locally (without Docker)

Requirements: Python 3.12, Node 20+, PostgreSQL 16 binaries (`postgresql-16` package — no running server or sudo needed).

```bash
# 0 · Database — a private PostgreSQL 16 cluster on 127.0.0.1:5433 (once)
scripts/db.sh init
```

```bash
# 1 · API (port 8010) — applies migrations, seeds the fictional demo world on first start (~30 s)
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8010
```

```bash
# 2 · Web app (port 5173) — proxies /api to 8010
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in **Chrome** (the camera is needed for face sign-in) and pick a demo persona.

```bash
# 3 · Optional — look inside the database with pgAdmin 4 on http://127.0.0.1:5050
scripts/pgadmin.sh
```

**Demo logins.** Nothing on the sign-in page reveals an account, a password or a code. Demo
credentials exist only in the database, readable only by the schema owner. In pgAdmin, on the
**owner** connection, run:

```sql
SELECT * FROM demo.credentials;
```

It lists each persona's email, mobile, password, the invited officer's activation code, and the
**current authenticator code** — computed inside PostgreSQL (`demo.totp`, RFC 6238), refreshing every
30 s. The app role and the read-only role are both refused this view. With a real phone, scan the
QR during activation and use your own authenticator app instead.

| Persona | Sign in with | Use it to show |
|---|---|---|
| Anjali Verma — lead IO | `anjali.verma@nvpolice.example` | Upload pipeline, purpose prompt, sharing, certificate, face sign-in |
| Rohit Kumar — co-IO | `98100 45002` (mobile) | Automatic redacted copy of victim records |
| Meera Nair — SHO | `meera.nair@nvpolice.example` | Approvals inbox, alerts |
| Farhan Siddiqui — prosecutor | `farhan.siddiqui@nvpolice.example` | Hearings, shared documents |
| Dr. Kavya Iyer — FSL | `kavya.iyer@nvpolice.example` | Custody transfer, forensic report |
| Suresh Patil — NCRB auditor | `suresh.patil@nvpolice.example` | Audit ledger, chain verification (no document content) |
| Neha Joshi — district admin | `neha.joshi@nvpolice.example` | Creating officer accounts, activation codes (no case access) |
| Rajeev Menon — super admin | `rajeev.menon@nvpolice.example` | Admins, units, roles, tamper lab |
| Arjun Mehta — other station | `arjun.mehta@nvpolice.example` | ACCESS DENIED |
| Pooja Thakur — new officer | activation code `SHN4-7KQ2` | First-time activation |

Reset everything: **Demo controls → Reset demo data**, or `backend/.venv/bin/python -m app.seed`.

Backend end-to-end test (46 checks against PostgreSQL, resets data at the end):

```bash
backend/.venv/bin/pip install -r backend/requirements-dev.txt
backend/.venv/bin/python backend/tests/smoke_test.py
```

## Architecture

```
React + Vite + TS ── /api/v1 ──► FastAPI (modular monolith)  ── as cfv_app ──► PostgreSQL 16
  WebCrypto SHA-256                 policy · cases · documents · audit            org · iam · cases · docs
  face-api (in-browser)             crypto: AES-256-GCM · Ed25519 · Merkle         collab · audit · alerts
  openapi-fetch (typed)                  │                                         triggers · FTS · grants
                                 ┌───────┴──────────┐
                         write-once objects   sealed checkpoints
                         (encrypted, 0444)    (signed, 0444)
```

`contracts/openapi.yaml` is the single source of truth; the frontend's types are generated from it.

| Prototype (this repo) | Production design ([docs/07](docs/07-architecture.md)) |
|---|---|
| PostgreSQL 16, local cluster | Managed / HA PostgreSQL; pgvector for semantic search; row-level security |
| Encrypted files on disk, read-only after write | S3-compatible storage (SeaweedFS) with versioning + Object Lock (COMPLIANCE) |
| Pipeline in a background thread | Redis + Celery workers |
| Built-in signature scan (EICAR) | ClamAV |
| Text-layer extraction | OCRmyPDF + Tesseract (eng + hin) |
| Key files under `data/keys` | Vault Transit / HSM, key rotation |
| Platform Ed25519 signature | CCA-licensed DSC / Aadhaar eSign adapter for legal signatures |
| Signed checkpoints sealed on disk | Checkpoints anchored to a permissioned ledger |

## Honest limits

- A matching hash proves the bytes are unchanged. It does not prove authorship, truth or
  admissibility. The §63 certificate is **pre-filled for signature**, not self-certifying.
- Ed25519 here is the platform's attestation, not a legally recognised digital signature.
- Keys live in files for the prototype. The demo storage lock can be bypassed by a root user
  (that is tamper scenario T5, and it is detected).
- Face sign-in uses an open model in the browser with a blink check. That stops a printed
  photo, not a determined replay attack; production would add certified presentation-attack
  detection. Face only replaces the password — the authenticator code is always required.
- Extracted page text is stored in the database (for search) and readable only by the app role.
- Not in this build: break-glass access, OCR of scanned images, semantic search, SMS/email OTP.

## Blueprint

| Doc | What it decides |
|---|---|
| [docs/00-scope.md](docs/00-scope.md) | Requirement traceability, feature tiers, submission-build scope |
| [docs/01-roles-permissions.md](docs/01-roles-permissions.md) | Roles, permission matrix, case-scoped access, sensitivity rules |
| [docs/02-data-model.md](docs/02-data-model.md) | Entities, enums, invariants |
| [docs/03-integrity-model.md](docs/03-integrity-model.md) | Pipeline, encryption, manifests, audit chain, verification, tamper scenarios |
| [docs/04-api-contract.md](docs/04-api-contract.md) | API conventions + endpoint index |
| [docs/05-screens.md](docs/05-screens.md) | Screens, routes, roles, endpoints |
| [docs/06-demo-story.md](docs/06-demo-story.md) | Seed world and the 5-minute demo script |
| [docs/07-architecture.md](docs/07-architecture.md) | Production stack and conventions |

All people, places, phone numbers and vehicle numbers in the seed data are fictional.
