# 07 · Architecture & Conventions

## Shape

A **modular monolith**: one FastAPI app with clear internal modules, one worker process, and
off-the-shelf infrastructure. No microservices.

```
┌──────────────────────────── Browser ────────────────────────────┐
│ React + Vite + TS · shadcn/ui · TanStack Query/Table · Zod       │
│ WebCrypto SHA-256 · openapi-fetch (typed from contracts/)        │
│ MSW mocks (Phase 1) ─ swapped for real API (Phase 2)             │
└───────────────────────────────┬─────────────────────────────────┘
                                │ /api/v1
┌───────────────────────────────▼─────────────────────────────────┐
│ FastAPI (modular monolith)                                       │
│  auth · policy · cases · documents · versions · collaboration    │
│  certificates · search · audit · alerts · public · demo          │
│  crypto/ (envelope AES-GCM, Ed25519, JCS, Merkle)                │
└──────┬───────────────────┬─────────────────────┬────────────────┘
       │                   │                     │ enqueue
┌──────▼──────┐   ┌────────▼────────┐   ┌────────▼───────┐
│ PostgreSQL  │   │ SeaweedFS (S3)  │   │ Redis          │
│ metadata    │   │ cfv-evidence    │   └────────┬───────┘
│ audit chain │   │  versioned+lock │            │
│ FTS·trgm    │   │ cfv-derivatives │   ┌────────▼───────────────┐
│ pgvector*   │   │ cfv-checkpoints │   │ Worker (Celery)        │
└─────────────┘   │  COMPLIANCE lock│   │ scan · encrypt · store │
                  │ cfv-quarantine  │   │ sign · OCR · extract   │
                  └─────────────────┘   │ index · redact · cert  │
                                        │ checkpoints (beat)     │
                                        └───────┬────────────────┘
                                                │
                                        ┌───────▼───────┐
                                        │ ClamAV (opt.) │
                                        └───────────────┘
```
`*` stretch

## Stack (pinned choices)

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, TypeScript (strict), Tailwind CSS v4, shadcn/ui, React Router, TanStack Query + Table, React Hook Form + Zod, Recharts, `react-pdf`, `qrcode.react`, `lucide-react`, `sonner` |
| API types | `openapi-typescript` + `openapi-fetch`; MSW v2 for mocks |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, `argon2-cffi`, `pyotp`, `PyJWT`, `cryptography`, `rfc8785` (JCS), `boto3`, `python-magic` |
| Worker | Celery + Redis (beat for checkpoints / share expiry) |
| Documents | OCRmyPDF + Tesseract (`eng`, `hin`), PyMuPDF (render, redact, watermark), ReportLab (certificate PDF), `clamd` |
| Data | PostgreSQL 16 (`pg_trgm`, `pgcrypto`, `vector`*) |
| Storage | SeaweedFS S3 gateway (versioning + object lock). MinIO is **not** used — its community edition is archived and its images were withdrawn. |
| Testing | Vitest + Testing Library + Playwright (frontend); pytest + Schemathesis (backend/contract) |
| Run | Docker Compose |

## Repo layout

```
case-file-vault/
├── contracts/openapi.yaml
├── docs/
├── frontend/
│   ├── src/
│   │   ├── api/            generated types, client, 428 interceptor
│   │   ├── mocks/          MSW handlers + fixture world (mirrors 06-demo-story)
│   │   ├── components/     shared components (05-screens)
│   │   ├── features/       auth, dashboard, cases, documents, inbox, audit, alerts,
│   │   │                   search, verify, admin, demo
│   │   ├── lib/            hashing, formatting (IST), i18n
│   │   └── routes.tsx
│   └── …
├── backend/
│   ├── app/
│   │   ├── api/            routers per tag
│   │   ├── policy/         decide() from 01-roles-permissions §9
│   │   ├── crypto/         envelope, signing, jcs, merkle
│   │   ├── audit/          chain writer, verifier, checkpoints
│   │   ├── storage/        S3 client wrapper
│   │   ├── workers/        pipeline steps
│   │   └── models/         SQLAlchemy
│   ├── migrations/
│   └── tests/
└── infra/
    ├── docker-compose.yml
    └── seed/
```

## Local ports

Chosen to avoid clashes with other local projects (8000/8001 are already in use on this machine).

| Service | Port |
|---|---|
| Frontend (Vite) | 5173 |
| Backend API | 8010 |
| PostgreSQL | 5433 |
| SeaweedFS S3 | 8333 |
| Redis | 6380 |
| ClamAV | 3310 |

## Conventions

- **Contract first:** change `contracts/openapi.yaml` → regenerate types → implement.
- **Policy in one place:** every router calls `policy.decide()`; no ad-hoc role checks.
- **Audit in the same transaction** as the action; a helper makes it impossible to forget.
- **No secrets in git.** `.env.example` documents variables; keys under `infra/secrets/`
  (git-ignored) for local runs.
- **Never log document content, OCR text, or victim identifiers** to application logs.
- Commits: conventional (`feat(upload): …`), small PRs, `main` always runnable.

## Phase plan from here

| Phase | Deliverable | Exit criteria |
|---|---|---|
| **1 · Frontend on mocks** | Screens 1–17 against MSW with the seed world | Whole 5-minute demo clickable end-to-end on mocks (tamper scenarios simulated) |
| **2 · Core backend** | Auth/MFA, policy, cases, upload pipeline (critical steps), content access, versions, audit chain + checkpoints, verify, requests/shares/custody, public verify | Frontend switched off MSW; demo steps 1–3, 5–9, 11–13 real |
| **3 · Differentiators** | OCR, entities/PII, redaction, §63 PDF, search, alerts, break-glass, ClamAV | Demo steps 4, 10, 14 real |
| **4 · Stretch** | Semantic search, classifier, Merkle anchoring, browser-held keys | Optional |
| **5 · Polish** | Seed generator, Compose one-command start, demo reset, recorded backup video | Fresh laptop → `docker compose up` → demo in < 10 min |
