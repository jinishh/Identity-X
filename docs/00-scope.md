# 00 · Scope

## Problem (official, condensed)

**SIH26190 — Secure Digital Document Management System for Legal and Investigation Documents**
Ministry of Home Affairs · **NCRB, Women Safety Division** · Software · Blockchain & Cybersecurity

Law-enforcement and legal institutions handle FIRs, police reports, investigation records,
witness statements, charge sheets, court filings, evidence records, forensic reports, legal
notices and judgments. Paper-based or fragmented digital handling causes: slow retrieval,
unauthorized access, tampering risk, no version control, poor inter-department collaboration,
process delays, and weak auditability.

The platform must:

1. Digitize and centralize document storage
2. Ensure secure access and confidentiality
3. Prevent unauthorized modifications
4. Maintain a complete audit trail of document activities
5. Enable efficient search and retrieval
6. Support collaboration among authorized stakeholders
7. Ensure compliance with legal and regulatory requirements

…while *"preserving legal validity and evidentiary integrity"*.

## Our framing

Not a document CRUD app with crypto attached. A **case-centric evidentiary vault**:

```
CASE
 ├── Members (who is assigned, in what capacity, until when)
 ├── Documents
 │     ├── Versions (immutable, WORM-locked, hash-linked)
 │     ├── Sensitivity · Type · Retention state      ← three separate axes
 │     ├── SHA-256 + signed manifest
 │     ├── OCR text, entities, PII spans
 │     └── Derivatives (redacted copy, §63 certificate)
 ├── Shares (scoped, time-bound, approved)
 ├── Custody transfers (two-party acknowledged)
 └── Audit chain (hash-linked, signed checkpoints)
```

### Requirement → feature traceability

| # | Requirement | Where it's met |
|---|---|---|
| 1 | Digitize & centralize | Case workspace, upload pipeline, OCR (eng+hin) for scanned paper |
| 2 | Secure access & confidentiality | 2FA, case-scoped access, sensitivity levels, AES-256-GCM per-file keys, victim-identity redaction, watermarked viewer |
| 3 | Prevent unauthorized modification | WORM object lock, immutable versions, SHA-256 + signed manifests, GCM authentication, no-delete policy |
| 4 | Complete audit trail | Hash-chained audit log written in the same transaction as the action, signed checkpoints stored WORM, chain verifier |
| 5 | Search & retrieval | Postgres full-text + trigram fuzzy (+ semantic, stretch), page-level snippets, access-aware results |
| 6 | Collaboration | Case membership, approval inbox, scoped shares with expiry, custody transfers, review workflow |
| 7 | Legal / regulatory compliance | BSA §63 certificate (pre-filled), BNS §72 victim-identity protection, retention & legal hold, DPDP-minded PII handling |
| ★ | Evidentiary integrity | Public verification portal (hash computed in the court's browser), integrity report, certificate QR |

## Differentiators (what judges should remember)

1. **Women-safety first.** `VICTIM_PROTECTED` sensitivity: originals only to lead IO, supervisor,
   prosecutor; everyone else gets an auto-redacted copy; every access requires a stated purpose
   and raises an audit alert. Directly serves the sponsoring division and BNS §72.
2. **Integrity you can demo live.** Five tamper scenarios, each caught by a different layer
   (see [03-integrity-model.md](03-integrity-model.md#tamper-scenarios)).
3. **Court verification without disclosure.** The verifier's browser hashes the file; only the
   hash is sent.
4. **Honest legal claims.** Ed25519 demonstrates signing; production swaps in a CCA DSC / eSign
   adapter. The §63 certificate is generated pre-filled *for signature* — the system does not
   claim to make evidence admissible by itself.

## Feature tiers

**Must (core demo — nothing ships without these)**
- Login + TOTP 2FA, role dashboards
- Cases: create, members, status lifecycle
- Upload: client hash → server hash match → validation → encrypt → WORM store → signed manifest → audit
- Document viewer (watermarked), immutable version history
- Case-scoped + sensitivity-based access; ACCESS DENIED is audited
- Audit explorer, chain verification, signed checkpoints
- Integrity verification (internal) + public verification portal
- Shares with expiry, approval inbox, custody transfer

**Should (differentiators)**
- Async processing pipeline with live status (Redis + worker)
- ClamAV malware scan + quarantine
- OCR (OCRmyPDF, eng+hin), entity + PII extraction
- Auto-redacted copies for `VICTIM_PROTECTED`
- §63 BSA certificate PDF with QR
- Keyword + fuzzy search with page snippets
- Alerts (integrity, malware, break-glass, victim-record access, denied bursts)
- Break-glass emergency access
- Legal hold

**Stretch**
- Semantic search (pgvector, multilingual embeddings)
- Document-type classifier, duplicate / near-duplicate detection
- Merkle-root anchoring to an external ledger
- Uploader-held signing keys in the browser (WebCrypto Ed25519)
- Local-LLM summaries (advisory, always cited)

## Non-goals (say so if asked)

- Mobile app (responsive web only)
- Hyperledger Fabric network (roadmap item; prototype anchors Merkle roots)
- Microservices, Kafka, Kubernetes, OpenSearch
- Video evidence at scale (prototype caps upload size)
- Real CCTNS / ICJS / e-Sakshya integration (API-first design, adapters on the roadmap)
- Generative "ask the case" chatbot

## Submission build (5 Oct 2026)

The idea-round submission is a GitHub repository plus a demo video, built in ~2½ days. It
implements all **Must** items and most **Should** items on a deliberately smaller stack:

| Blueprint | Submission build |
|---|---|
| PostgreSQL, pg_trgm | SQLite (WAL) + FTS5 |
| SeaweedFS Object Lock | Encrypted files on disk, read-only after write, overwrite refused in code |
| Redis + Celery | Background thread per upload |
| ClamAV | Built-in signature scan (EICAR) |
| OCRmyPDF | Text-layer extraction (PyMuPDF) |
| Refresh-cookie rotation | Access token in session storage |
| Break-glass | Not built (endpoint returns 501) |

The contract (`contracts/openapi.yaml`) and the access model are unchanged, so moving to the
production stack does not change the frontend.

## Assumptions (revisit when the team confirms)

- Built solo with AI assistance before 5 Oct; teammates join after mid-terms.
- Single-tenant deployment per state; one KEK per deployment for the prototype.
- All seed data is fictional (people, places, police stations, vehicle numbers).
- Upload limit 50 MB; allowed types: PDF, JPEG, PNG, TIFF.

## Glossary

| Term | Meaning |
|---|---|
| IO | Investigating Officer |
| SHO | Station House Officer |
| APP / PP | (Assistant) Public Prosecutor |
| FSL | Forensic Science Laboratory |
| BNS / BNSS / BSA | Bharatiya Nyaya Sanhita / Nagarik Suraksha Sanhita / Sakshya Adhiniyam (2023) |
| CCTNS / ICJS | Crime & Criminal Tracking Network & Systems / Inter-operable Criminal Justice System |
| WORM | Write Once Read Many (object lock) |
| DEK / KEK | Data Encryption Key (per file) / Key Encryption Key (wraps DEKs) |
| Manifest | Canonical JSON describing a version (hash, size, uploader, time…), signed |
