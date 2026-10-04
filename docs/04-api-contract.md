# 04 · API Contract

The full contract is **[`contracts/openapi.yaml`](../contracts/openapi.yaml)** (OpenAPI 3.1,
78 operations). It is the single source of truth:

- **Frontend** generates types with `openapi-typescript` and calls the API through
  `openapi-fetch`; MSW mock handlers are typed from the same file.
- **Backend** implements it in FastAPI; a contract test (Schemathesis) checks the running
  server against this file.
- Change the YAML first, then both sides. Lint: `npx @redocly/cli lint contracts/openapi.yaml`.

## Conventions

| Topic | Rule |
|---|---|
| Base URL | `/api/v1` (backend on `:8010`) |
| Auth | `Authorization: Bearer <access JWT>` — 15 min, kept **in memory only**. Refresh token in `cfv_refresh` cookie (HttpOnly, Secure, SameSite=Strict, path `/api/v1/auth`), rotated on every use. |
| Login | `POST /auth/login` → `mfa_token` → `POST /auth/mfa/verify` (or enrol on first login). No access token is ever issued without MFA. |
| IDs / time | UUIDv7; RFC 3339 UTC. UI renders IST. |
| Lists | `?page=1&page_size=20` → `{ items, total, page, page_size }` |
| Errors | `application/problem+json` with `code` |
| 403 | Policy denial; `deny_reason` ∈ `NOT_A_CASE_MEMBER`, `SENSITIVITY`, `CASE_CLOSED`, `LEGAL_HOLD`, `SELF_APPROVAL`, … Always audited. |
| 428 | Obligation missing: `PURPOSE_REQUIRED` → re-send with `purpose`; `STEP_UP_REQUIRED` → `POST /auth/step-up`, then retry. The frontend handles both with one interceptor + dialog. |
| 202 | Uploads and redactions are async. Poll `GET /versions/{id}/processing` every 1 s until `READY` / `QUARANTINED` / `FAILED`. |
| Content | Never streamed from a JSON endpoint. `POST /versions/{id}/access` evaluates policy, audits, and returns a 60-second single-use `/content/{token}` URL (so the PDF viewer can load it without a JWT in the URL). |
| Permissions in UI | The UI never re-implements policy. `Case.my_permissions` and `Document.access` tell it which buttons to show; the server is still the authority. |
| Rate limits | Login 5/min/IP, public verify 30/min/IP, everything else 300/min/user. `429` + `Retry-After`. |

## Key flows (sequence)

**Login**
```
login(service_id, password) ─► { mfa_token, mfa_enrolment_required }
  ├─ enrolment required ─► startMfaEnrolment ─► QR ─► confirmMfaEnrolment(code)
  └─ else ─────────────────► verifyMfa(code)
◄─ { access_token, user: Me }   + refresh cookie
```

**Upload**
```
browser SHA-256 ─► uploadDocument(file, metadata{client_sha256}) ─► 202 {version_id}
poll getProcessing(version_id) … steps flip PENDING → RUNNING → DONE
READY ─► getDocument
```

**View a victim-protected original**
```
requestContentAccess(variant=ORIGINAL)  ─► 428 PURPOSE_REQUIRED
  dialog → purpose ─► requestContentAccess(…, purpose) ─► 200 { url, watermark }
viewer GET url
```

**Download it**
```
requestContentAccess(disposition=attachment, purpose) ─► 428 STEP_UP_REQUIRED
  dialog → TOTP ─► stepUp(code) ─► retry ─► 200
```

**Share**
```
requestShare ─► Request(PENDING) ─► supervisor: decideRequest(APPROVE) ─► Share created
```

**Court verification**
```
QR ─► /verify/{code} ─► getPublicCertificate(code)
drop file ─► browser SHA-256 ─► publicVerify(code, sha256) ─► MATCH | MISMATCH
```

## Endpoint index

### System

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/health` | `getHealth` | public | Liveness and dependency status |

### Auth

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `POST` | `/auth/login` | `login` | public | Step 1 — password. Always followed by MFA. |
| `POST` | `/auth/mfa/verify` | `verifyMfa` | public | Step 2 — TOTP. Returns access token; sets refresh cookie. |
| `POST` | `/auth/mfa/enrol` | `startMfaEnrolment` | public | First login only — get a TOTP secret to scan. |
| `POST` | `/auth/mfa/enrol/confirm` | `confirmMfaEnrolment` | public | Confirm mfa enrolment |
| `POST` | `/auth/refresh` | `refreshToken` | public | Rotate refresh cookie, get a new access token. |
| `POST` | `/auth/step-up` | `stepUp` | 🔒 | Re-enter TOTP; satisfies STEP_UP_REQUIRED for 5 minutes. |
| `POST` | `/auth/logout` | `logout` | 🔒 | Logout |
| `GET` | `/auth/me` | `getMe` | 🔒 | Get me |

### Dashboard

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/dashboard/summary` | `getDashboardSummary` | 🔒 | Role-aware KPIs, my cases, recent activity. |

### Directory

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/units` | `listUnits` | 🔒 | List units |
| `GET` | `/directory` | `searchDirectory` | 🔒 | Find users to add as members / share with / transfer custody to. |
| `GET` | `/users` | `listUsers` | 🔒 | ADMIN only. |
| `POST` | `/users` | `createUser` | 🔒 | ADMIN only. User must enrol MFA on first login. |
| `GET` | `/users/{userId}` | `getUser` | 🔒 | Get user |
| `PATCH` | `/users/{userId}` | `updateUser` | 🔒 | ADMIN only. Cannot change own role. |
| `POST` | `/users/{userId}/reset-mfa` | `resetUserMfa` | 🔒 | ADMIN only. Forces re-enrolment at next login. |

### Cases

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/cases` | `listCases` | 🔒 | Cases the caller can see (membership, jurisdiction, auditor metadata view). |
| `POST` | `/cases` | `createCase` | 🔒 | Create case |
| `GET` | `/cases/{caseId}` | `getCase` | 🔒 | Get case |
| `PATCH` | `/cases/{caseId}` | `updateCase` | 🔒 | Update case |
| `POST` | `/cases/{caseId}/status` | `changeCaseStatus` | 🔒 | Change case status |
| `GET` | `/cases/{caseId}/members` | `listCaseMembers` | 🔒 | List case members |
| `POST` | `/cases/{caseId}/members` | `addCaseMember` | 🔒 | Add case member |
| `POST` | `/cases/{caseId}/members/{memberId}/remove` | `removeCaseMember` | 🔒 | Remove case member |
| `GET` | `/cases/{caseId}/timeline` | `getCaseTimeline` | 🔒 | Chain-of-custody timeline — audit events for this case, newest first. |
| `POST` | `/cases/{caseId}/break-glass` | `startBreakGlass` | 🔒 | Emergency read access for 60 min. Requires step-up; raises HIGH alert. |

### Documents

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/cases/{caseId}/documents` | `listCaseDocuments` | 🔒 | List case documents |
| `POST` | `/cases/{caseId}/documents` | `uploadDocument` | 🔒 | Upload v1 of a new document. Returns 202; poll processing. |
| `GET` | `/documents/{documentId}` | `getDocument` | 🔒 | Get document |
| `PATCH` | `/documents/{documentId}` | `updateDocument` | 🔒 | Title / type / tags only. Sensitivity has its own endpoint. |
| `POST` | `/documents/{documentId}/sensitivity` | `changeSensitivity` | 🔒 | Raise (uploaders) or lower (SUPERVISOR, step-up, not own upload). |
| `POST` | `/documents/{documentId}/legal-hold` | `setLegalHold` | 🔒 | Set legal hold |
| `POST` | `/documents/{documentId}/legal-hold/release` | `requestLegalHoldRelease` | 🔒 | Creates a LEGAL_HOLD_RELEASE request; a different approver must decide. |
| `POST` | `/documents/{documentId}/withdraw` | `withdrawDocument` | 🔒 | Soft withdrawal (nothing is deleted). Blocked on LEGAL_HOLD. |
| `GET` | `/documents/{documentId}/timeline` | `getDocumentTimeline` | 🔒 | Chain of custody for one document, oldest first. |

### Versions

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/documents/{documentId}/versions` | `listVersions` | 🔒 | List versions |
| `POST` | `/documents/{documentId}/versions` | `uploadVersion` | 🔒 | Upload a new version. Previous versions remain immutable. |
| `GET` | `/versions/{versionId}` | `getVersion` | 🔒 | Get version |
| `GET` | `/versions/{versionId}/processing` | `getProcessing` | 🔒 | Pipeline state. Poll every 1 s until status is terminal. |
| `POST` | `/versions/{versionId}/access` | `requestContentAccess` | 🔒 | Check access + obligations, audit it, return a 60 s single-use content URL (may downgrade to REDACTED) |
| `GET` | `/content/{token}` | `getContent` | public | Streams decrypted (and watermarked, for inline views) bytes. Token is the credential; expires in 60 s, single use. |
| `GET` | `/versions/{versionId}/manifest` | `getManifest` | 🔒 | Get manifest |
| `POST` | `/versions/{versionId}/verify` | `verifyVersion` | 🔒 | Full integrity check (object, lock, ciphertext, decrypt, hash, manifest, signature, audit anchor, version link). |
| `GET` | `/versions/{versionId}/entities` | `listEntities` | 🔒 | Extracted entities. Values of PII/victim identifiers are masked unless the caller may see the original. |
| `GET` | `/versions/{versionId}/redactions` | `listRedactions` | 🔒 | List redactions |
| `POST` | `/versions/{versionId}/redactions` | `createRedaction` | 🔒 | Generate a redacted copy (async). AUTO uses extracted PII; entity_ids lets the user choose. |

### Collaboration

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/documents/{documentId}/shares` | `listDocumentShares` | 🔒 | List document shares |
| `POST` | `/documents/{documentId}/shares` | `requestShare` | 🔒 | Creates a SHARE request for supervisor approval. |
| `POST` | `/documents/{documentId}/custody-transfers` | `initiateCustodyTransfer` | 🔒 | Current custodian only. Recipient must accept via the request inbox. |
| `POST` | `/shares/{shareId}/revoke` | `revokeShare` | 🔒 | Revoke share |
| `GET` | `/shared-with-me` | `listSharedWithMe` | 🔒 | List shared with me |
| `POST` | `/versions/{versionId}/review` | `submitForReview` | 🔒 | CHARGESHEET / INVESTIGATION_REPORT only. Creates a REVIEW request. |
| `GET` | `/requests` | `listRequests` | 🔒 | List requests |
| `GET` | `/requests/{requestId}` | `getRequest` | 🔒 | Get request |
| `POST` | `/requests/{requestId}/decision` | `decideRequest` | 🔒 | Approve / reject. Never by the requester. Approving a SHARE creates the share; a CUSTODY_TRANSFER moves custody. |
| `POST` | `/requests/{requestId}/cancel` | `cancelRequest` | 🔒 | Requester only, while PENDING. |

### Certificates

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/versions/{versionId}/certificates` | `listVersionCertificates` | 🔒 | List version certificates |
| `POST` | `/versions/{versionId}/certificates` | `issueCertificate` | 🔒 | Generate a BSA §63 certificate, pre-filled for signature. |
| `GET` | `/certificates/{certificateId}` | `getCertificate` | 🔒 | Get certificate |
| `POST` | `/certificates/{certificateId}/revoke` | `revokeCertificate` | 🔒 | Revoke certificate |

### Search

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/search` | `search` | 🔒 | Access-aware search over metadata and OCR text. Snippets are redacted where the caller may only see redacted content. |

### Audit

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/audit/events` | `listAuditEvents` | 🔒 | List audit events |
| `GET` | `/audit/events/{seq}` | `getAuditEvent` | 🔒 | Get audit event |
| `POST` | `/audit/verify-chain` | `verifyAuditChain` | 🔒 | AUDITOR. Walks the chain and checkpoints; reports the first break. |
| `GET` | `/audit/checkpoints` | `listCheckpoints` | 🔒 | List checkpoints |
| `GET` | `/audit/export` | `exportAudit` | 🔒 | AUDITOR. CSV export of the filtered range (the export itself is audited). |

### Alerts

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/alerts` | `listAlerts` | 🔒 | List alerts |
| `POST` | `/alerts/{alertId}/acknowledge` | `acknowledgeAlert` | 🔒 | Acknowledge alert |
| `POST` | `/alerts/{alertId}/resolve` | `resolveAlert` | 🔒 | Resolve alert |
| `GET` | `/break-glass` | `listBreakGlassSessions` | 🔒 | List break glass sessions |
| `POST` | `/break-glass/{sessionId}/end` | `endBreakGlass` | 🔒 | End break glass |
| `POST` | `/break-glass/{sessionId}/review` | `reviewBreakGlass` | 🔒 | Review break glass |

### Public

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `GET` | `/public/certificates/{code}` | `getPublicCertificate` | public | What the QR code opens. Only facts printed on the certificate. |
| `POST` | `/public/verify/{code}` | `publicVerify` | public | Compare a SHA-256 computed in the verifier's browser. The file is never uploaded. |
| `GET` | `/public/keys` | `listPublicKeys` | public | Public keys for offline verification of manifests, checkpoints and certificates. |

### Demo

| Method | Path | operationId | Auth | Purpose |
|---|---|---|---|---|
| `POST` | `/demo/tamper` | `demoTamper` | 🔒 | ADMIN, DEMO_MODE only. Executes a tamper scenario (see 03-integrity-model §7). |
| `POST` | `/demo/reset` | `demoReset` | 🔒 | ADMIN, DEMO_MODE only. Restore seed snapshot. |
