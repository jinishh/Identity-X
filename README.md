<div align="center">

# 🔐 Case-File Vault

**A tamper-evident digital evidence vault for legal & investigation documents**

Smart India Hackathon 2026 · Problem Statement **SIH26190** · Team **Identity X** (ID 186448)
Ministry of Home Affairs / NCRB — Women Safety Division · Theme: Blockchain & Cybersecurity

![Docker](https://img.shields.io/badge/run%20with-Docker-2496ED?logo=docker&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.12-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/end--to--end%20checks-46%20passing-2E7D32)

> **Protect → Prove → Trace → Verify → Certify**

![Sign-in page](docs/screenshots/01-login.png)

</div>

---

## Contents

1. [What is this?](#what-is-this)
2. [Screenshots](#screenshots)
3. [Features](#features)
4. [Quick start (Docker)](#quick-start-docker)
5. [Demo logins](#demo-logins)
6. [Getting into the database](#getting-into-the-database)
7. [Adding a new user](#adding-a-new-user)
8. [Tech stack & dependencies](#tech-stack--dependencies)
9. [Architecture](#architecture)
10. [Project structure](#project-structure)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)
13. [Run without Docker](#run-without-docker)
14. [Honest limits](#honest-limits)
15. [Documentation](#documentation)

---

## What is this?

Police and courts handle FIRs, witness statements, forensic reports and charge-sheets that
are often tied up in paper or scattered across folders. Files get lost, edited, or seen by
people who shouldn't see them — and nobody can prove what happened.

**Case-File Vault** is a *case-centric evidence vault*. Every document is fingerprinted in the
officer's browser, re-checked on the server, encrypted with its own key, stored write-once,
sealed with a signed manifest and anchored into a hash-chained audit ledger. Access depends on
the officer's role **on that case** and the document's sensitivity. Victim identity is
protected by design (BNS §72), and a court can verify a copy **without the file ever leaving
their machine**.

| The problem (PS 26190) | How the vault answers it |
|---|---|
| Slow retrieval | Case workspace + full-text and fuzzy search with page-level snippets |
| Unauthorized access | Role + case-membership access, 2FA on every sign-in, face sign-in, watermarked viewer |
| Tampering risk | AES-256-GCM per-file keys, write-once storage, SHA-256 + Ed25519-signed manifests |
| No version control | Immutable, hash-linked versions |
| Poor collaboration | Share requests with supervisor approval, expiring shares, two-party custody transfer |
| Weak auditability | Hash-chained ledger with signed Merkle checkpoints sealed outside the database |
| Legal validity | Pre-filled BSA §63 certificate with QR code and a public MATCH / MISMATCH check |

All people, places, phone numbers and vehicle numbers in the demo data are **fictional**.

---

## Screenshots

Every screenshot below is taken from the running application, using the demo data.

### 1 · Sign in and work on a case

| | |
|---|---|
| ![Dashboard](docs/screenshots/02-dashboard.png) **Role-aware docket** — open cases, custody, and a live integrity summary. | ![Case workspace](docs/screenshots/03-case-workspace.png) **Case workspace** — every document with its sensitivity, version, custodian and seal. Victim-protected cases are flagged (BNS §72). |
| ![Chain of custody](docs/screenshots/04-chain-of-custody.png) **Chain of custody** — every action on the case, newest first, including denied attempts. | ![Search](docs/screenshots/11-search.png) **Search** — keyword and fuzzy search across the text inside documents, with highlighted snippets. |

### 2 · Protect: the upload pipeline

![Upload pipeline](docs/screenshots/05-upload-pipeline.png)

The file is fingerprinted in the browser, then sealed step by step, live: server re-hash →
file validation → malware scan → **per-file AES-256-GCM encryption** → write-once storage →
**signed manifest** → anchored in the audit chain → text extraction, PII detection and
auto-redaction → search index.

### 3 · Protect: victim-record handling

| | | |
|---|---|---|
| ![Purpose prompt](docs/screenshots/07-purpose-prompt.png) **Purpose prompt** — opening a victim original requires a stated reason, written to the ledger. | ![Watermarked viewer](docs/screenshots/08-watermarked-viewer.png) **Watermarked viewer** — stamped with the viewer's name, service ID, time and case. | ![Redacted copy](docs/screenshots/09-redacted-copy.png) **Auto-redacted copy** — the co-investigator sees the facts, not the victim's identity. |

![Access denied](docs/screenshots/10-access-denied.png)

**Access denied** — an officer from another station is refused, and the attempt itself is
written to the tamper-evident ledger and shown to the supervisor.

### 4 · Prove & verify: integrity and the §63 certificate

| | |
|---|---|
| ![Integrity](docs/screenshots/06-integrity-verified.png) **One-click integrity check** — nine checks, including stored bytes, write-once lock and signature. | ![Certificate](docs/screenshots/12-certificate.png) **§63 certificate** — pre-filled for signature, with a QR code and verification code. |
| ![Match](docs/screenshots/13-verify-match.png) **Public verification: MATCH** — the court's browser hashes the file; only the hash is sent. | ![Mismatch](docs/screenshots/14-verify-mismatch.png) **Public verification: MISMATCH** — one changed byte gives a different fingerprint, and raises an alert. |

### 5 · Collaborate, monitor and administer

| | |
|---|---|
| ![Approvals](docs/screenshots/15-approvals.png) **Approvals** — shares and reviews need a second officer; no self-approval. | ![Alerts](docs/screenshots/16-alerts.png) **Security alerts** — mismatched copies, denial bursts, off-hours access, victim-record access. |
| ![Accounts](docs/screenshots/17-accounts.png) **Account administration** — administrators manage people but never see case content. | |

### 6 · Trace: the tamper-evident ledger

| | |
|---|---|
| ![Ledger intact](docs/screenshots/18-ledger-intact.png) **Chain intact** — every event's hash covers the one before it; checkpoints are signed. | ![Ledger broken](docs/screenshots/20-ledger-broken.png) **Chain broken** — after a "rogue database admin" edits one event, verification pinpoints the exact entry. |

![Tamper lab](docs/screenshots/19-tamper-lab.png)

**Tamper lab** — a demo-only panel that plays the attacker (overwrite evidence, flip
ciphertext bytes, edit an audit row, rewrite the whole chain). Each attack is caught by a
different layer.

---

## Features

| Area | What works (real code, not mock-ups) |
|---|---|
| Sign-in | Email **or** mobile number + password, **or** face — then an authenticator (TOTP) code, always. Codes are single-use; lockout after 5 failures; server-side sessions. |
| First sign-in | Admin creates the account (INVITED) and hands over a one-time activation code → officer proves identity, sets their own password, links an authenticator app by QR. |
| Roles | Super Admin (state) · Admin (district) · Supervisor · Investigator · Prosecutor · Forensic Expert · Auditor. Administrators never see case content. |
| Face sign-in | Runs in the browser (face-api): detection, landmarks, blink check, 128-d template. Only the template is sent, stored encrypted. |
| Database | PostgreSQL 16 with 8 schemas, versioned SQL migrations, three roles (owner / app / read-only), append-only triggers, CHECK constraints, full-text search. |
| Cases | Role-aware dashboards, case list, case workspace, people, chain-of-custody timeline, status lifecycle. |
| Upload pipeline | Browser SHA-256 → server re-hash (mismatch = rejected + alert) → file-signature check → malware signature scan (EICAR → quarantine) → AES-256-GCM, one key per file → write-once storage → Ed25519-signed manifest → audit anchor → text extraction → PII detection → auto-redaction → full-text index. |
| Access control | Case membership + supervisor jurisdiction + custody + time-limited shares. Four sensitivity levels. "State your purpose" and "re-enter 2FA" prompts. Every denial is audited. |
| Victim protection | Victim-protected cases default to the highest sensitivity; non-key members get a redacted copy; every view of an original needs a purpose and alerts the supervisor. |
| Viewer | Canvas-rendered and watermarked. Downloads are a separate audited action and stay byte-identical. |
| Versions | Immutable, hash-linked versions (each manifest carries the previous version's hash). |
| Collaboration | Share requests → supervisor approval → scoped, expiring shares; two-party custody transfer; charge-sheet review. |
| Integrity | One-click 9-check verification; whole-chain audit verification with signed Merkle checkpoints. |
| §63 certificate | Pre-filled BSA §63 PDF with QR → public verification page → MATCH / MISMATCH. |
| Search | Full-text and fuzzy (typo-tolerant) search over extracted text, page-level snippets, redacted snippets for restricted viewers. |
| Alerts | Malware, in-transit tampering, integrity failure, chain break, denial bursts, off-hours access, victim-record access. |
| Tamper lab | Super-admin-only demo panel with four attack scenarios. |

---

## Quick start (Docker)

The only thing you need is **Docker**. No Python, Node or PostgreSQL install.

### Prerequisites

| Requirement | Notes |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Windows, macOS or Linux. Open it and wait until it says *running*. |
| ~4 GB free disk space | For the images (database, Python API, Node web app). |
| Free ports **5173**, **8010**, **5433** | Web app, API, database. |
| **Google Chrome** | Needed for the face sign-in camera. |

### Step by step

**1. Get the code**

```bash
git clone https://github.com/jinishh/Identity-X.git
cd Identity-X
```

**2. Start everything** (run from the folder that contains `docker-compose.yml`)

```bash
docker compose up --build
```

The first start takes a few minutes: it downloads the images, creates the database and users,
applies the migrations and **seeds the fictional demo world** (about 30 seconds). Wait for:

```
api-1  | INFO:     Application startup complete.
web-1  |   ➜  Local:   http://localhost:5173/
```

Leave this terminal running. Add `-d` (`docker compose up -d --build`) to run in the
background instead.

**3. Open the app** → <http://localhost:5173> in Chrome.

**4. Get a login.** Nothing on the sign-in page reveals an account or password, on purpose.
In a **second terminal**, in the same folder:

```bash
docker compose exec db psql -U cfv_owner -d case_file_vault -x -c "SELECT * FROM demo.credentials;"
```

This prints every demo user's email, mobile number, password and the **current 6-digit
authenticator code**.

**5. Sign in:** enter the email and password, press *Continue*, then type the authenticator
code. Codes refresh every 30 seconds and each works **once** — if one is refused, wait for the
next and run the query again.

### Everyday commands

| Task | Command |
|---|---|
| Stop | `docker compose down` |
| Start again (fast) | `docker compose up` |
| Reset to fresh demo data | Sign in as the super admin → **Tamper lab** → *Reset demo data* |
| Wipe everything and start over | `docker compose down -v`, then `docker compose up --build` |
| See logs | `docker compose logs -f api` |
| Run the end-to-end test | `docker compose exec api python tests/smoke_test.py` |

Ports: **5173** web · **8010** API (docs at <http://localhost:8010/docs>) · **5433** PostgreSQL.

---

## Demo logins

All demo accounts are fictional. Get the password and the current authenticator code with the
query in [step 4](#step-by-step).

| Persona | Sign in with | Use it to show |
|---|---|---|
| Anjali Verma — lead investigating officer | `anjali.verma@nvpolice.example` | Upload pipeline, purpose prompt, sharing, certificate, face sign-in |
| Rohit Kumar — co-investigator | `rohit.kumar@nvpolice.example` (or mobile `98100 45002`) | Automatic redacted copy of victim records |
| Meera Nair — station house officer | `meera.nair@nvpolice.example` | Approvals inbox, alerts |
| Farhan Siddiqui — prosecutor | `farhan.siddiqui@nvpolice.example` | Hearings, shared documents |
| Dr. Kavya Iyer — forensic expert | `kavya.iyer@nvpolice.example` | Custody transfer, forensic report |
| Suresh Patil — NCRB auditor | `suresh.patil@nvpolice.example` | Audit ledger, chain verification (no document content) |
| Neha Joshi — district admin | `neha.joshi@nvpolice.example` | Creating officer accounts (no case access) |
| Rajeev Menon — super admin | `rajeev.menon@nvpolice.example` | Admins, units, roles, **tamper lab** |
| Arjun Mehta — officer at another station | `arjun.mehta@nvpolice.example` | **Access denied** |
| Pooja Thakur — new officer | activation code from `demo.credentials` | First-time activation |

The hero case is **NV/SHN/0142/2026**. A 5-minute click-by-click demo script is in
[docs/06-demo-story.md](docs/06-demo-story.md).

---

## Getting into the database

PostgreSQL runs in its own container and is exposed on your computer only, at port **5433**.

| | |
|---|---|
| Host / port | `localhost` / `5433` |
| Database | `case_file_vault` |
| Full access (schema owner) | `cfv_owner` / `cfv_owner_dev` |
| Read-only inspection | `cfv_readonly` / `cfv_read_dev` |

Use any client (DBeaver, pgAdmin, TablePlus…), or open a shell inside the container:

```bash
docker compose exec db psql -U cfv_owner -d case_file_vault
```

Handy queries:

```sql
\dn                                      -- the 8 schemas
SELECT * FROM iam.v_people;              -- who has an account (no secrets)
SELECT * FROM audit.events ORDER BY seq DESC LIMIT 10;   -- the hash-chained ledger
SELECT * FROM demo.credentials;          -- demo passwords + live authenticator codes (owner only)
```

The app itself connects as a restricted role (`cfv_app`) that cannot delete evidence and can
only append to the audit ledger. These credentials are local development values for a laptop
demo — never reuse them anywhere real.

---

## Adding a new user

1. Sign in as the district admin **Neha Joshi** (`neha.joshi@nvpolice.example`).
2. Open **Accounts** → **New account**. Enter name, service ID, role, unit, and email or mobile.
   The account starts as *invited*.
3. Copy the **one-time activation code** shown and hand it to the new person.
4. They open <http://localhost:5173/activate>, enter the code, choose their own password and
   scan a QR code with an authenticator app (Google Authenticator, etc.).
5. They can now sign in with email, password and an authenticator code.

Only the **super admin** can create administrators. Administrators never see case content, so
add the new officer to a case from a case member's account. Accounts live in your own database
volume — a friend running the project gets a separate database with only the demo users.

---

## Tech stack & dependencies

Docker installs everything below for you.

| Layer | Technology |
|---|---|
| **Frontend** | React 19 · TypeScript · Vite 8 · Tailwind CSS 4 · React Router · TanStack Query · Radix UI · Recharts · react-pdf · Phosphor & Lucide icons |
| **In-browser security** | WebCrypto SHA-256 · face-api (`@vladmandic/face-api`) for face sign-in · `qrcode.react` |
| **API client** | `openapi-fetch` with types generated from `contracts/openapi.yaml` |
| **Backend** | Python 3.12 · FastAPI · Uvicorn · SQLAlchemy 2 · Pydantic 2 · psycopg 3 |
| **Cryptography** | `cryptography` (AES-256-GCM, Ed25519) · `argon2-cffi` (password hashing) · `pyotp` (TOTP, RFC 6238) · `PyJWT` · `rfc8785` (canonical JSON) · Merkle trees |
| **Documents** | PyMuPDF (render, redact, text) · ReportLab (§63 certificate PDF) · Pillow · `qrcode` |
| **Database** | PostgreSQL 16 — extensions `pgcrypto`, `pg_trgm`, `citext`; full-text search |
| **Packaging** | Docker · Docker Compose |

<details>
<summary><b>Exact pinned versions</b></summary>

**Backend** (`backend/requirements.txt`)

```
fastapi==0.118.*      uvicorn[standard]==0.37.*   sqlalchemy==2.0.*     pydantic==2.*
python-multipart      pyjwt==2.*                  argon2-cffi==25.*     pyotp==2.*
cryptography==46.*    rfc8785==0.1.*              reportlab==4.*        qrcode==8.*
pillow==11.*          pymupdf==1.26.*             psycopg[binary]==3.2.*  httpx==0.28.*
```

**Frontend** — see [frontend/package.json](frontend/package.json).

</details>

---

## Architecture

```
  Browser (React + Vite + TypeScript)
   │  WebCrypto SHA-256 · face-api · typed API client
   │
   │  /api/v1  (proxied by Vite)
   ▼
  FastAPI — modular monolith ───────────────────────────────┐
   │  policy · cases · documents · audit · alerts           │
   │  crypto: AES-256-GCM · Ed25519 · Merkle                │
   │                                                        │
   ├── as cfv_app ──► PostgreSQL 16                         ├─► write-once object store
   │                  org · iam · cases · docs              │   (encrypted files, read-only)
   │                  collab · audit · alerts · demo        │
   │                  triggers · FTS · grants               └─► sealed checkpoints
   │                                                            (signed, read-only)
```

`contracts/openapi.yaml` is the single source of truth; the frontend types are generated from it.

| This prototype | Production design ([docs/07](docs/07-architecture.md)) |
|---|---|
| PostgreSQL 16 in a container | Managed / HA PostgreSQL; row-level security |
| Encrypted files on disk, read-only after write | S3-compatible storage with Object Lock (COMPLIANCE) |
| Pipeline in a background thread | Redis + Celery workers |
| Built-in signature scan (EICAR) | ClamAV |
| Text-layer extraction | OCRmyPDF + Tesseract (English + Hindi) |
| Key files on disk | Vault Transit / HSM with key rotation |
| Platform Ed25519 signature | CCA-licensed DSC / Aadhaar eSign |
| Signed checkpoints on disk | Checkpoints anchored to a permissioned ledger |

---

## Project structure

```
case-file-vault/
├── docker-compose.yml        one-command run: db + api + web
├── docker/db-init/           creates the database roles on first start
├── backend/
│   ├── Dockerfile
│   ├── app/                  FastAPI app: routers, policy, crypto, audit, pipeline, seed
│   ├── tests/smoke_test.py   46-check end-to-end test
│   └── requirements*.txt
├── frontend/
│   ├── Dockerfile
│   └── src/                  React app: features/, components/, lib/, api/
├── database/
│   ├── migrations/           versioned SQL (schemas, roles, triggers, grants)
│   └── ERD.md                entity-relationship diagram
├── contracts/openapi.yaml    API contract
├── docs/                     design docs and screenshots
└── scripts/                  helper scripts (local Postgres, pgAdmin, ERD)
```

---

## Testing

The end-to-end test runs against the real database and walks the whole demo — sign-in by
email, mobile and face, first-time activation, account administration by role, the upload
pipeline, purpose and 2FA prompts, redacted fallback, access denial, share approval, §63
certificate, public MATCH / MISMATCH and the tamper scenarios.

```bash
docker compose exec api python tests/smoke_test.py
```

Expected ending: `all 46 checks passed`. It **resets the demo data when it finishes**, so run
it before preparing a presentation, not after.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `no configuration file provided` | Run commands from the folder that contains `docker-compose.yml`. |
| `Cannot connect to the Docker daemon` / pipe errors | Docker Desktop is not running. Open it and wait until it says *running*. |
| `port is already allocated` | Something else uses 5173, 8010 or 5433. Stop it, or change the left-hand port numbers in `docker-compose.yml`. |
| Page doesn't load right after start | The first start seeds the demo data (~30 s). Wait for `Application startup complete` in the logs. |
| Authenticator code refused | Codes are single-use and last 30 seconds. Wait for the next one and re-run the credentials query. |
| Face sign-in doesn't ask for the camera | Use Chrome and allow camera access. Register your face first under **Settings**. |
| Want a completely clean slate | `docker compose down -v`, then `docker compose up --build`. |

---

## Run without Docker

Only needed if you want to develop against local services. Requires Python 3.12, Node 20+ and
the PostgreSQL 16 binaries (Linux/macOS shell).

```bash
scripts/db.sh init                                  # private PostgreSQL 16 cluster on :5433 (once)

cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8010          # applies migrations, seeds on first start

cd ../frontend
npm install && npm run dev                          # http://localhost:5173
```

Optional: `scripts/pgadmin.sh` starts pgAdmin 4 on <http://127.0.0.1:5050>.

---

## Honest limits

- A matching hash proves the bytes are unchanged. It does **not** prove authorship, truth or
  admissibility. The §63 certificate is **pre-filled for signature**, not self-certifying.
- Ed25519 here is the platform's attestation, not a legally recognised digital signature.
  Production would use a CCA-licensed DSC / Aadhaar eSign adapter.
- Keys live in files for the prototype. The demo storage lock can be bypassed by a root user
  (that is tamper scenario T5, and it is detected).
- Face sign-in uses an open model in the browser with a blink check. That stops a printed
  photo, not a determined replay attack; production would add certified presentation-attack
  detection. Face only replaces the password — the authenticator code is always required.
- **Not in this build:** break-glass emergency access, OCR of scanned images, semantic search,
  AI document classification, SMS/email OTP, a real blockchain network (the prototype uses a
  hash chain with signed Merkle checkpoints; anchoring to a permissioned ledger is the
  production step).

---

## Documentation

| Doc | What it decides |
|---|---|
| [docs/00-scope.md](docs/00-scope.md) | Requirement traceability, feature tiers |
| [docs/01-roles-permissions.md](docs/01-roles-permissions.md) | Roles, permission matrix, case-scoped access, sensitivity rules |
| [docs/02-data-model.md](docs/02-data-model.md) | Entities, enums, invariants |
| [docs/03-integrity-model.md](docs/03-integrity-model.md) | Pipeline, encryption, manifests, audit chain, tamper scenarios |
| [docs/04-api-contract.md](docs/04-api-contract.md) | API conventions and endpoint index |
| [docs/05-screens.md](docs/05-screens.md) | Screens, routes, roles |
| [docs/06-demo-story.md](docs/06-demo-story.md) | Seed world and the 5-minute demo script |
| [docs/07-architecture.md](docs/07-architecture.md) | Production stack and conventions |
| [database/README.md](database/README.md) | Database design, roles and grants |

---

<div align="center">

**Team Identity X** · SIH 2026 · PS 26190
All people, places and records in the demo data are fictional.

</div>
