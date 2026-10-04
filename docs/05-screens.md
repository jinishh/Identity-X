# 05 · Screens

The Phase 1 build list. Every screen names its route, who sees it, the endpoints it uses and
the states it must handle. Build order is the **#** column.

## Design direction

- **Tone:** institutional and calm, not "hacker". Officers and judges should trust it at a glance.
- **Integrity is a first-class visual language**, used consistently everywhere:

  | State | Colour | Icon | Used for |
  |---|---|---|---|
  | Verified / clean / match | green | shield-check | integrity checks, chain valid, MATCH |
  | Pending / skipped / degraded | amber | clock / alert-triangle | processing, ClamAV skipped, step-up needed |
  | Failed / tampered / denied | red | shield-x | MISMATCH, chain broken, quarantined, ACCESS DENIED |
  | Locked / held | slate-blue | lock | WORM lock, legal hold |

- **Sensitivity badges** (always visible on a document): `INTERNAL` grey · `CONFIDENTIAL` blue ·
  `RESTRICTED` orange · `VICTIM_PROTECTED` purple with a shield-person icon.
- **Hashes** are shown as `8f9b…a821` with copy-to-clipboard and a full-value tooltip; monospace.
- Light + dark themes; IST times everywhere ("02 Oct 2026, 17:42 IST").
- English UI first; strings in an i18n file so Hindi can be added.

## App shell

Sidebar (role-filtered): Dashboard · Cases · Search · Inbox (badge) · Shared with me ·
Audit · Alerts (badge) · Admin. Top bar: global search, step-up status chip
("Elevated · 4:12"), user menu (role, unit, logout). Break-glass sessions show a red banner
with a countdown on every page.

## Screens

| # | Screen | Route | Roles | Endpoints |
|---|---|---|---|---|
| 1 | Login | `/login` | public | `login` |
| 2 | MFA verify / enrol | `/login/mfa` | public | `verifyMfa`, `startMfaEnrolment`, `confirmMfaEnrolment` |
| 3 | Dashboard | `/` | all except ADMIN (→ `/admin/users`) | `getDashboardSummary` |
| 4 | Case list | `/cases` | case roles, AUDITOR | `listCases` |
| 5 | New case | `/cases/new` | INVESTIGATOR, SUPERVISOR | `createCase`, `listUnits`, `searchDirectory` |
| 6 | Case workspace | `/cases/:caseId` (tabs below) | members, jurisdiction, AUDITOR (metadata) | `getCase`, `changeCaseStatus`, `updateCase` |
| 6a | — Documents tab | `/cases/:caseId/documents` | | `listCaseDocuments` |
| 6b | — Members tab | `/cases/:caseId/members` | | `listCaseMembers`, `addCaseMember`, `removeCaseMember`, `searchDirectory` |
| 6c | — Custody timeline tab | `/cases/:caseId/timeline` | | `getCaseTimeline` |
| 6d | — Access denied → break-glass | (403 `NOT_A_CASE_MEMBER` state) | INVESTIGATOR, SUPERVISOR | `startBreakGlass`, `endBreakGlass`, `stepUp` |
| 7 | Upload wizard | `/cases/:caseId/upload` | uploaders | `uploadDocument`, `getProcessing` |
| 8 | Document view | `/documents/:documentId` | per access | `getDocument`, `listVersions`, `requestContentAccess`, `getContent`, `getDocumentTimeline` |
| 8a | — Integrity panel | (side panel) | | `verifyVersion`, `getManifest` |
| 8b | — Versions panel | (side panel) | | `listVersions`, `uploadVersion` |
| 8c | — Sharing & custody panel | (side panel) | | `listDocumentShares`, `requestShare`, `revokeShare`, `initiateCustodyTransfer` |
| 8d | — Entities & redaction panel | (side panel) | | `listEntities`, `createRedaction`, `listRedactions` |
| 8e | — Certificates panel | (side panel) | | `listVersionCertificates`, `issueCertificate`, `getCertificate`, `revokeCertificate` |
| 8f | — Header actions | (toolbar) | per `access.actions` | `updateDocument`, `changeSensitivity`, `setLegalHold`, `requestLegalHoldRelease`, `withdrawDocument`, `submitForReview`, `getVersion` |
| 9 | Inbox | `/inbox` | all case roles | `listRequests`, `getRequest`, `decideRequest`, `cancelRequest` |
| 10 | Public verification | `/verify`, `/verify/:code` | public (no shell) | `getPublicCertificate`, `publicVerify` |
| 11 | Audit explorer | `/audit` | AUDITOR (all), SUPERVISOR/LEAD_IO (scoped) | `listAuditEvents`, `getAuditEvent`, `verifyAuditChain`, `listCheckpoints`, `exportAudit` |
| 12 | Alerts | `/alerts` | SUPERVISOR, AUDITOR | `listAlerts`, `acknowledgeAlert`, `resolveAlert` |
| 13 | Search | `/search` | all except ADMIN | `search` |
| 14 | Shared with me | `/shared` | all case roles | `listSharedWithMe` |
| 15 | Break-glass review | `/alerts/break-glass` | SUPERVISOR, AUDITOR | `listBreakGlassSessions`, `reviewBreakGlass` |
| 16 | Admin · users | `/admin/users` | ADMIN | `listUsers`, `getUser`, `createUser`, `updateUser`, `resetUserMfa`, `listUnits` |
| — | App shell (global) | every authed route | all | `getMe`, `refreshToken`, `stepUp`, `logout` |
| — | Public keys | `/verify/keys` | public | `listPublicKeys` |
| 17 | Demo control panel | `/demo` | ADMIN, `DEMO_MODE` | `demoTamper`, `demoReset`, `getHealth` |
| — | Not found / Forbidden | `*`, `/403` | | |

## Screen details

### 1–2 · Login + MFA
- Service ID + password → 6-digit OTP input (auto-advance, paste-friendly).
- First login shows a QR (`otpauth_uri`) and asks for the first code.
- States: wrong password (generic message, never "user not found"), locked (show unlock time),
  rate-limited.

### 3 · Dashboard (role-aware)
Content comes from `DashboardSummary.kpis`, so each role sees different cards without
frontend branching:

| Role | KPI cards | Below the cards |
|---|---|---|
| INVESTIGATOR | My open cases · Docs uploaded this week · Pending my action · Shares expiring | My cases table, recent activity |
| SUPERVISOR | Cases in jurisdiction · Approvals waiting · Open alerts · Break-glass to review | Approvals list, alerts list, cases-by-status chart |
| PROSECUTOR | Cases under trial · Next hearings (7 days) · Docs shared with me · Certificates issued | Hearing calendar list, my cases |
| FORENSIC_EXPERT | Exhibits in my custody · Transfers to accept · Reports submitted | Custody list |
| AUDITOR | Encrypted files · Verified integrity · Chain status · Open alerts | Integrity gauge, recent denials, documents-by-type chart |

The slide-2 numbers (1,248 encrypted / 1,203 verified / 31 pending / 14 alerts) come from here.

### 6 · Case workspace
- Header: case number, FIR no./date, station, category, offence sections, status pill with
  "Change status" (allowed transitions only), victim-protected banner when applicable
  ("Victim identity protected under BNS §72 — originals restricted").
- Documents tab: table with doc number, title, type, sensitivity badge, version, custodian,
  integrity dot, updated. Filters by type & sensitivity. Primary action **Upload document**.
- Timeline tab: vertical chain-of-custody timeline; each event shows actor, action, purpose,
  time, and a hash chip linking to the audit event.

### 7 · Upload wizard (the core demo moment)
1. **Choose file** — drag & drop; type/size checked client-side (server re-checks).
2. **Fingerprint** — SHA-256 computed in-browser with a progress bar; hash shown.
3. **Describe** — title, type, sensitivity (min = case default), tags. OCR suggestions appear
   later on the document page, not here.
4. **Submit** → **live pipeline**: one row per `ProcessingStep` flipping
   pending → running → done/skipped/failed, with detail ("ClamAV · CLEAN", "AES-256-GCM ·
   kek-2026-01", "Locked until 02 Oct 2036", "Signed · sys-manifest-2026-01"). Critical vs
   best-effort steps visually grouped.
5. **Receipt** — doc number, version, SHA-256, manifest hash, audit seq; buttons: open document,
   upload another.

States: hash mismatch (T6) → red "Upload rejected: file changed in transit"; quarantined →
red with signature name; ClamAV skipped → amber.

### 8 · Document view
- Left: PDF/image viewer with **diagonal tiled watermark** from `ContentAccessGrant.watermark`.
  If `access.view = REDACTED`, a purple bar: "You are viewing a redacted copy".
- Right: tabbed side panel 8a–8e.
- **8a Integrity**: "Verify now" → nine checks list with ✓/✗, expected vs actual on failure;
  manifest viewer (pretty JSON + canonical bytes + signature + key id).
- **8b Versions**: vertical list v3 → v1, each with hash, uploader, change note, lock status;
  "Upload new version" (requires change note). Text: "Earlier versions are immutable."
- **8c Sharing & custody**: active shares with countdown to expiry + revoke; "Request share"
  dialog (grantee search, scope limited by sensitivity, expiry capped); "Transfer custody".
- **8d Entities & redaction**: entity chips grouped by type, PII highlighted; "Create redacted
  copy" (auto or selected).
- **8e Certificates**: issued certificates; "Generate §63 certificate" dialog (signatory name,
  designation, purpose) → certificate card with QR, download PDF. Wording: "pre-filled for
  signature".
- Purpose dialog (428 `PURPOSE_REQUIRED`): presets + free text. Step-up dialog
  (428 `STEP_UP_REQUIRED`): OTP input. Both handled globally.
- Header actions (shown only if in `access.actions`): Download, Legal hold, Change sensitivity,
  Withdraw, Submit for review.

### 9 · Inbox
Tabs Inbox / Outbox; filter by type. Each request card shows what is being asked
(share X with Y as VIEW until date / transfer custody / review charge-sheet v2 / release legal
hold), reason, requester, and Approve / Reject (reject needs a note). `can_decide = false` →
read-only with explanation ("You raised this request").

### 10 · Public verification (no login, separate minimal layout)
- `/verify` — enter the 12-character code (or scan QR).
- `/verify/:code` — certificate facts (cert no., case no., doc type, version, SHA-256, issued,
  status). Drop zone: "Your file stays on this device — only its fingerprint is checked."
- Result: large green **MATCH** or red **MISMATCH** with both hashes side by side; revoked
  certificates show a red banner regardless.

### 11 · Audit explorer
- Filter bar (case, document, actor, action, outcome, date range); table with seq, time, actor,
  action, outcome, target, hash chip.
- Row drawer: canonical JSON, prev_hash → event_hash, checkpoint that seals it.
- **Verify chain** button → animated progress, then green "Chain valid · 1,248 events ·
  13 checkpoints" or red "Broken at seq 412 — EVENT_HASH" with a link to the row.
- Checkpoints tab: list with Merkle root, range, signature, WORM copy status.
- Export CSV.

### 12 · Alerts
Severity-sorted list; filter by status/type; acknowledge / resolve with note; link to case,
document and the audit event that triggered it.

### 13 · Search
Query box + mode toggle (Keyword / Fuzzy / Semantic*); filters (case, type, date). Each hit:
document title, case, type, sensitivity, page number, snippet with highlights, "redacted
snippet" tag where applicable, match type. *Semantic disabled with tooltip until stretch lands.

### 16 · Admin · users
Table + create/edit drawer; disable; reset MFA. Admin sees no cases or documents anywhere.

### 17 · Demo control panel
Cards for T2–T5, each with target picker, "Run", the result message and a "What to show next"
link (e.g. → Audit explorer). "Reset demo data" with confirm. Health of each component.

## Shared components (build once)

`AppShell` · `KpiCard` · `DataTable` (TanStack Table) · `StatusPill` · `SensitivityBadge` ·
`IntegrityBadge` · `HashChip` · `UserChip` · `Timeline` · `PipelineSteps` · `CheckList` ·
`PurposeDialog` · `StepUpDialog` · `OtpInput` · `FileDrop` (with WebCrypto hashing) ·
`Watermark` · `DocumentViewer` · `EmptyState` · `ErrorState` · `ConfirmDialog` ·
`CountdownChip`.

## Every screen must handle

Loading (skeletons, not spinners), empty, error (problem+json `detail`), 403 (with deny reason
in plain language), and 428 (global dialogs).
