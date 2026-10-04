# 01 · Roles & Permissions

Access is decided by **four things together**, never by role alone:

```
system role  +  capacity on this case  +  document sensitivity  +  action
```

Plus two state gates (case status, retention state) and obligations (purpose, step-up MFA,
watermark) that can be attached to an ALLOW.

## 1. System roles

A user has exactly one system role. It decides what *kinds* of things they may do and which
case capacities they can hold.

| Role | Real-world holder | Can hold case capacity | Sees document content? |
|---|---|---|---|
| `INVESTIGATOR` | SI / Inspector (IO) | `LEAD_IO`, `CO_IO` | Yes, per rules |
| `SUPERVISOR` | SHO / DSP / SP | `SUPERVISOR` (+ implicit over their jurisdiction) | Yes, per rules |
| `PROSECUTOR` | APP / Public Prosecutor | `PROSECUTOR` | Yes, per rules |
| `FORENSIC_EXPERT` | FSL scientist | `FORENSIC` | Only documents in their custody / shared |
| `AUDITOR` | NCRB / vigilance audit cell | — (never a member) | **No.** Metadata, audit, integrity results only |
| `ADMIN` | System administrator | — (never a member) | **No.** Users, units, keys status only |

Courts and defence have **no account**. They use the certificate + public verification portal.

## 2. Case capacity

Membership rows (`case_members`) give a user a capacity on one case, optionally time-boxed.

| Capacity | Granted by | Typical holder |
|---|---|---|
| `LEAD_IO` | case creator / SUPERVISOR | Investigator who registered or was assigned the case (exactly one active) |
| `CO_IO` | LEAD_IO, SUPERVISOR | Assisting investigator |
| `SUPERVISOR` | automatic (jurisdiction) or SUPERVISOR | SHO of the station, or DSP above it |
| `PROSECUTOR` | SUPERVISOR | APP handling the trial |
| `FORENSIC` | LEAD_IO, SUPERVISOR | FSL scientist analysing exhibits |

**Implicit supervisor capacity:** a `SUPERVISOR` user has `SUPERVISOR` capacity on every case
whose police-station unit is their own unit or a descendant of it.

Capacity can also come from:
- **Share** — a scoped, time-limited grant on one document (see §6).
- **Custody** — the current custodian of a document can view it (see §5).
- **Break-glass** — emergency, time-boxed, alerted (see §7).

## 3. Sensitivity levels

Three **separate** axes on each document. Do not merge them.

| Axis | Values |
|---|---|
| Sensitivity | `INTERNAL` · `CONFIDENTIAL` · `RESTRICTED` · `VICTIM_PROTECTED` |
| Type | `FIR`, `WITNESS_STATEMENT`, `FORENSIC_REPORT`, … (see data model) |
| Retention | `ACTIVE` · `LEGAL_HOLD` · `ARCHIVED` |

### Sensitivity rules

Legend — **M** any case member · **K** key capacities (`LEAD_IO`, `SUPERVISOR`, `PROSECUTOR`) ·
**C** current custodian · **S** active share of that scope · 🅿 purpose required ·
🔐 step-up MFA required

| Level | Metadata | View original | View redacted | Download original | Share outside case |
|---|---|---|---|---|---|
| `INTERNAL` | M | M, C, S | — | M, C, S(download) | Approval; any scope; ≤ 30 days |
| `CONFIDENTIAL` | M | M, C, S | — | K, C 🅿 | Approval; `VIEW` only; ≤ 14 days |
| `RESTRICTED` | M | K, C, S 🅿 | — | K 🅿 🔐 | Approval; `VIEW` only; ≤ 7 days |
| `VICTIM_PROTECTED` | M (title pseudonymised) | K, C 🅿 | M, S | K 🅿 🔐 | Approval; **`VIEW_REDACTED` only**; ≤ 7 days |

Rules that sit on top:
- **Victim-protected case** (`cases.is_victim_protected = true`, set automatically for
  crimes-against-women categories): new documents default to `VICTIM_PROTECTED`.
- Anyone who can upload may **raise** sensitivity. Only `SUPERVISOR` may **lower** it, with a
  reason, and never on their own upload.
- Search results and snippets obey the same table: if you may only see the redacted copy, you
  only get redacted snippets.
- Every view of a `VICTIM_PROTECTED` original raises an `INFO` alert to the case supervisor.

## 4. Permission matrix

✅ allowed · ◐ allowed with condition (see note) · — denied.
Columns are **case capacities** for case-scoped actions and **system roles** for the last two.

### Cases

| Action | LEAD_IO | CO_IO | SUPERVISOR | PROSECUTOR | FORENSIC | AUDITOR | ADMIN |
|---|---|---|---|---|---|---|---|
| `case:create` | ✅¹ | ✅¹ | ✅ | — | — | — | — |
| `case:read` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅² | — |
| `case:update` | ✅ | — | ✅ | — | — | — | — |
| `case:change_status` | ◐³ | — | ✅ | — | — | — | — |
| `case:manage_members` | ◐⁴ | — | ✅ | — | — | — | — |
| `case:break_glass` | ◐⁵ | ◐⁵ | ◐⁵ | — | — | — | — |

1. Any `INVESTIGATOR` may register a case; they become `LEAD_IO`.
2. Metadata only, all cases.
3. Forward transitions except `CHARGESHEET_FILED`, which requires an approved charge-sheet review.
4. May add `CO_IO` and `FORENSIC` only.
5. Requires *not* already having access; see §7.

### Documents

| Action | LEAD_IO | CO_IO | SUPERVISOR | PROSECUTOR | FORENSIC | AUDITOR | ADMIN |
|---|---|---|---|---|---|---|---|
| `document:upload` / `new_version` | ✅ | ✅ | ✅ | ◐⁶ | ◐⁶ | — | — |
| `document:read_meta` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `document:view` / `download` | per §3 | per §3 | per §3 | per §3 | per §3 | — | — |
| `document:raise_sensitivity` | ✅ | ✅ | ✅ | ✅ | — | — | — |
| `document:lower_sensitivity` | — | — | ◐⁷ | — | — | — | — |
| `document:redact` | ✅ | — | ✅ | ✅ | — | — | — |
| `document:legal_hold_set` | — | — | ✅ | ✅ | — | — | — |
| `document:legal_hold_release` | — | — | ◐⁸ | — | — | — | — |
| `document:withdraw` | — | — | ◐⁹ | — | — | — | — |
| `document:share_request` | ✅ | — | ✅ | ✅ | — | — | — |
| `document:custody_transfer` | ◐¹⁰ | ◐¹⁰ | ◐¹⁰ | ◐¹⁰ | ◐¹⁰ | — | — |
| `document:verify` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `document:review_submit` | ✅ | ✅ | — | — | — | — | — |
| `document:review_decide` | — | — | ◐¹¹ | — | — | — | — |
| `certificate:issue` | ✅ | — | ✅ | — | — | — | — |

6. Prosecutor: `COURT_ORDER`, `LEGAL_NOTICE`, `JUDGMENT`, `COURT_FILING` only. Forensic: `FORENSIC_REPORT` only.
7. Reason required; not on own upload; not while on `LEGAL_HOLD`.
8. Raises a request that a *different* supervisor or the prosecutor must approve.
9. Soft withdrawal only (nothing is ever deleted). Reason required. Blocked on `LEGAL_HOLD`.
10. Only the current custodian may initiate; the recipient must accept.
11. For `CHARGESHEET` and `INVESTIGATION_REPORT`; cannot decide on own submission.

### System-wide

| Action | INVESTIGATOR | SUPERVISOR | PROSECUTOR | FORENSIC_EXPERT | AUDITOR | ADMIN |
|---|---|---|---|---|---|---|
| `search` | ✅ (filtered) | ✅ (filtered) | ✅ (filtered) | ✅ (filtered) | metadata only | — |
| `request:decide` | — | ✅ | ◐¹² | ◐¹³ | — | — |
| `audit:read_case` | own cases as LEAD_IO | jurisdiction | — | — | ✅ all | — |
| `audit:read_all` / `export` | — | — | — | — | ✅ | — |
| `audit:verify_chain` | — | — | — | — | ✅ | — |
| `alert:read` / `ack` | — | jurisdiction | — | — | ✅ all | — |
| `break_glass:review` | — | jurisdiction | — | — | ✅ | — |
| `user:manage`, `unit:manage` | — | — | — | — | — | ✅ |
| `demo:tamper` / `reset` | — | — | — | — | — | ◐¹⁴ |

12. Legal-hold release requests only.
13. Custody transfers addressed to them only.
14. Only when the server runs with `DEMO_MODE=true`.

## 5. Custody

Each document has one `custodian` (initially the uploader). Custody moves only by a
two-party transfer: custodian initiates with a reason → recipient accepts or declines. While
pending, custody does not change. The custodian may view the original at any sensitivity
(with purpose for `RESTRICTED` / `VICTIM_PROTECTED`). This is how an FSL scientist gets the
exhibit they must analyse without becoming a full case member.

## 6. Shares

A share is a document-level grant to a user outside the case.

- Requested by LEAD_IO / SUPERVISOR / PROSECUTOR → approved by a case SUPERVISOR who is not the requester.
- Scope: `VIEW_REDACTED` · `VIEW` · `DOWNLOAD`, capped by sensitivity (§3).
- Always has `expires_at`. Revocable any time. Expiry and revocation are audited.

## 7. Break-glass

For genuine emergencies (e.g. a missing-person lead in another station's case).

- Available to INVESTIGATOR / SUPERVISOR on a case they cannot otherwise access.
- Requires a reason (≥ 20 chars) **and** step-up MFA.
- Grants read access (no download, no share) for **60 minutes**.
- Immediately raises a `HIGH` alert to the case supervisor and the audit cell.
- Must be reviewed afterwards (`JUSTIFIED` / `UNJUSTIFIED`); unjustified use is itself an alert.

## 8. Obligations

| Obligation | When |
|---|---|
| **Purpose** — preset or free text (≥ 10 chars), stored in the audit event | Any 🅿 in §3; all break-glass |
| **Step-up MFA** — TOTP entered within the last 5 minutes | Any 🔐 in §3; break-glass; lowering sensitivity |
| **Watermark** — viewer name, service ID, timestamp, case number tiled over every page | Every content view |
| **Audit** — event written in the same DB transaction as the action | Every action, including `ACCESS_DENIED` |

## 9. Decision procedure

```
decide(user, action, case, document?) → ALLOW(obligations) | DENY(reason)

 1. session valid, MFA verified, user ACTIVE                  else DENY(UNAUTHENTICATED)
 2. if system-wide action → system-role table (§4)             else DENY(ROLE_NOT_PERMITTED)
 3. capacities = membership ∪ jurisdiction ∪ custody ∪ share ∪ break_glass
    if empty                                                   → DENY(NOT_A_CASE_MEMBER)
 4. capacity table (§4) for action                             else DENY(ACTION_NOT_PERMITTED)
 5. content actions → sensitivity table (§3)                   else DENY(SENSITIVITY)
    (may downgrade to redacted variant instead of denying)
 6. case CLOSED and action is a write                          → DENY(CASE_CLOSED)
 7. document LEGAL_HOLD and action ∈ {withdraw, lower_sensitivity}
                                                               → DENY(LEGAL_HOLD)
 8. requester == approver                                      → DENY(SELF_APPROVAL)
 9. ALLOW with obligations (purpose / step-up / watermark)
```

Every `DENY` is written to the audit chain as `ACCESS_DENIED` with the reason code.
Five or more denials for one user in 10 minutes raises an `ACCESS_DENIED_BURST` alert.

## 10. Separation-of-duties invariants

- Nobody approves their own request or reviews their own submission.
- `ADMIN` cannot be a case member, cannot view content, cannot change their own role.
- `AUDITOR` never sees document content; integrity verification returns results, not bytes.
- Nothing is deleted: documents are withdrawn, shares revoked, users disabled.
- Exactly one active `LEAD_IO` per case.
