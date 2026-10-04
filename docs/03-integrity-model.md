# 03 · Integrity Model

Each mechanism solves **one** problem. Keep them separate in code, UI and the pitch.

| Mechanism | Solves | Does **not** solve |
|---|---|---|
| AES-256-GCM, one DEK per file | Confidentiality at rest; detects ciphertext tampering (auth tag) | Who uploaded it |
| SHA-256 of plaintext | "Are these the same bytes?" | Who vouches for them |
| Ed25519-signed manifest | "The platform recorded *these* bytes, from *this* officer, at *this* time" | Legal signature (→ DSC / eSign in production) |
| WORM object lock + versioning | Stored bytes cannot be overwritten or deleted | Insider editing the database |
| Hash-chained audit log | Any edit to a past event breaks every later link | Insider recomputing the *whole* chain |
| Signed checkpoints stored WORM | Whole-chain rewrite no longer matches sealed checkpoints | — |
| Merkle anchoring (stretch) | Third-party timestamp of checkpoints | — |

## 1. Upload pipeline

```
 Browser                          API (sync, ≤ 1 s)                      Worker (async)
 ───────                          ─────────────────                      ──────────────
 pick file
 SHA-256 via WebCrypto ──┐
 metadata form           │
                         ▼
             POST multipart ──► RECEIVE  stream to quarantine area
                                HASH_MATCH server SHA-256 == client SHA-256
                                          ✗ → 422, HASH_MISMATCH_ON_UPLOAD event + alert
                                VALIDATE  magic bytes ∈ allowlist, size ≤ 50 MB,
                                          extension matches detected type,
                                          filename sanitised
                                write documents/version rows (RECEIVED)
                                audit DOCUMENT_UPLOADED
            ◄── 202 {document_id, version_id}
 poll /processing every 1 s                                       ──► MALWARE_SCAN  ClamAV INSTREAM
                                                                         INFECTED → QUARANTINED,
                                                                         alert MALWARE_DETECTED, stop
                                                                     ENCRYPT       new DEK, AES-256-GCM
                                                                     STORE_WORM    PUT to cfv-evidence,
                                                                                   object lock, pin version id
                                                                     SIGN_MANIFEST build + sign manifest
                                                                     AUDIT_ANCHOR  VERSION_CREATED event
                                                                                   carrying manifest_sha256
                                                                     OCR           OCRmyPDF -l eng+hin
                                                                     EXTRACT       regex + NER, PII flags
                                                                     INDEX         tsvector chunks
                                                                     EMBED         (stretch)
                                                                     → READY, VERSION_READY event
```

`MALWARE_SCAN` through `AUDIT_ANCHOR` are **integrity-critical**: if any fails the version is
`FAILED`, never `READY`. `OCR` onwards are **best-effort**: failure is recorded but the version
still becomes `READY` (search just won't find it).

If ClamAV is not running (low-RAM laptop), the step is `SKIPPED` and recorded as such in the
manifest — the UI shows it honestly in amber, never as green.

The plaintext in the quarantine area is deleted after `STORE_WORM` succeeds.

## 2. Encryption (envelope)

```
KEK  (32 bytes, from key file / env in prototype; Vault Transit / HSM in production)
 └─ wraps ─► DEK (32 random bytes, one per stored object)
              └─ encrypts ─► file bytes   AES-256-GCM, 96-bit random nonce
                                          AAD = version_id ‖ sha256
```

- **AAD binds ciphertext to its record.** Swapping two stored objects makes decryption fail.
- `wrapped_dek` = AES-256-GCM(KEK, DEK) with its own nonce; stored with `kek_id`.
- **KEK rotation** = re-wrap DEKs only; files are never re-encrypted.
- Prototype limit: single-shot GCM needs the whole file in memory (fine at 50 MB). Production:
  segmented streaming AEAD.

## 3. Signed manifest

Canonicalised with **RFC 8785 (JCS)** so any implementation produces identical bytes.

```json
{
  "schema": "cfv.manifest/1",
  "document_id": "0192…",
  "version_id": "0192…",
  "version_no": 2,
  "doc_number": "DOC-2026-000123",
  "case_number": "NV/SHN/0142/2026",
  "doc_type": "WITNESS_STATEMENT",
  "original_filename": "statement_ws2.pdf",
  "detected_mime": "application/pdf",
  "size_bytes": 482113,
  "sha256": "8f9b…a821",
  "prev_version_sha256": "1c3e…77d0",
  "client_sha256_matched": true,
  "uploaded_by": { "user_id": "0192…", "service_id": "NV-IO-1045" },
  "uploaded_at": "2026-10-02T12:12:41Z",
  "scan": { "engine": "ClamAV", "result": "CLEAN", "db_version": "27412" },
  "storage": { "bucket": "cfv-evidence", "object_version_id": "…", "lock_mode": "GOVERNANCE", "retain_until": "2036-10-02T00:00:00Z" },
  "encryption": { "alg": "AES-256-GCM", "kek_id": "kek-2026-01", "ciphertext_sha256": "…" }
}
```

```
manifest_sha256 = SHA-256(JCS(manifest))
signature       = Ed25519_sign(MANIFEST key, JCS(manifest))
```

`manifest_sha256` is written into the `VERSION_CREATED` audit event, so the document is
anchored into the audit chain (and transitively into the next checkpoint).

`prev_version_sha256` makes versions a hash-linked chain of their own: v1 cannot be swapped
without breaking v2's manifest.

## 4. Audit chain

```
canonical_event = JCS({seq, id, occurred_at, actor_user_id, actor_role, action, outcome,
                       reason_code, case_id, document_id, version_id, target_user_id,
                       request_id, purpose, details})

event_hash = SHA-256( hex_decode(prev_hash) ‖ canonical_event )
prev_hash(seq 1) = "0" × 64
```

- Written **in the same DB transaction** as the action it records — no action without its event.
- Serialised with `pg_advisory_xact_lock(<chain lock id>)` so `seq` and `prev_hash` never race.
- DB role `cfv_app`: `INSERT, SELECT` only; trigger rejects `UPDATE`, `DELETE`, `TRUNCATE`.

### Checkpoints

Every **100 events or 10 minutes** (whichever first):

```json
{ "schema": "cfv.checkpoint/1", "from_seq": 401, "to_seq": 500,
  "head_hash": "…", "merkle_root": "…", "event_count": 100,
  "created_at": "2026-10-02T12:30:00Z" }
```

- Merkle tree over the range's `event_hash` values (binary, SHA-256, duplicate last leaf on odd).
- Signed with the `CHECKPOINT` key (different from the manifest key).
- Written to `audit_checkpoints` **and** as an object in the `cfv-checkpoints` bucket under
  `COMPLIANCE` lock — the DB admin cannot alter it.
- Stretch: submit `merkle_root` to an external ledger and store the tx reference in `anchor`.

### Chain verification

`POST /audit/verify-chain` walks `seq` ascending and reports:

| Check | Failure means |
|---|---|
| `prev_hash` = previous `event_hash` | a row was inserted/removed |
| recomputed `event_hash` = stored | a row was edited |
| `seq` gap-free | a row was deleted |
| each checkpoint: recomputed Merkle root + head hash = WORM copy | the chain was rewritten wholesale |
| each checkpoint signature valid | checkpoint forged |

Result: `VALID`, or the **first broken seq** and which check failed.

## 5. Document verification

### Internal — `POST /versions/{id}/verify`

| Check | How |
|---|---|
| `object_present` | HEAD the pinned `storage_version_id` |
| `object_locked` | retention/legal-hold headers present and unexpired |
| `ciphertext_hash_match` | SHA-256(ciphertext) = `ciphertext_sha256` |
| `decrypts` | GCM tag verifies with AAD |
| `plaintext_hash_match` | SHA-256(plaintext) = `sha256` |
| `manifest_hash_match` | SHA-256(JCS(manifest)) = `manifest_sha256` |
| `signature_valid` | Ed25519 verify with `signing_key_id` public key |
| `audit_anchored` | a `VERSION_CREATED` event carries this `manifest_sha256` and lies in a valid chain segment |
| `version_link_valid` | `prev_version_sha256` = parent version's `sha256` |

Overall `VERIFIED` only if all pass. Any failure → `INTEGRITY_FAILED` event + `CRITICAL` alert.
Auditors can run this: the server decrypts in memory and returns results, never bytes.

### Public — court / defence / verifier

```
Certificate (PDF) ── QR ──► /verify/{verification_code}
                               shows: cert no., case no., doc type, version, SHA-256,
                                      issued at, status (ISSUED / REVOKED)
Verifier drops their copy ──► browser computes SHA-256 locally
                          ──► POST /public/verify/{code}  { "sha256": "…" }
                          ◄── MATCH / MISMATCH  (+ PUBLIC_VERIFICATION audit event)
```

The file never leaves the verifier's machine. No names, no content, no case details beyond
what is printed on the certificate. Rate-limited per IP.

## 6. BSA §63 certificate

Generated as a PDF from a version. The system fills what it can attest; humans sign.

| Section | Filled by system | Left for humans |
|---|---|---|
| Part A — particulars of the electronic record and system | case & doc numbers, file name, type, size, SHA-256, upload timestamp, system description, storage & integrity controls, chain-of-custody summary | signature of the person in charge, place, date |
| Part B — expert | SHA-256 value and algorithm for the expert to confirm | expert's name, designation, signature |

Footer: certificate number, verification code, QR → public portal, system signature
fingerprint.

**Wording rule:** the PDF and UI say *"pre-filled for signature"*. Never *"legally certified"*
or *"admissible"*.

## 7. Tamper scenarios

The demo control panel (`DEMO_MODE=true`, admin only) can trigger each; every trigger is
itself an audit event `DEMO_TAMPER_EXECUTED`.

| # | Attack | Caught by | What the judge sees |
|---|---|---|---|
| T1 | Court receives an altered copy | Public portal hash | Red **MISMATCH** on `/verify/{code}` |
| T2 | Try to overwrite / delete stored evidence | WORM lock | "Refused — object locked until 2036-10-02" |
| T3 | Insider edits one audit row in Postgres | Chain verify | "Chain broken at seq 412 — event hash mismatch" |
| T4 | Insider recomputes the entire chain after editing | Checkpoint vs WORM copy | "Checkpoint #5 does not match sealed copy" |
| T5 | Ciphertext replaced (lock bypassed with governance override) | GCM tag + ciphertext hash | Document integrity: ✗ decrypts, ✗ ciphertext hash |
| T6 | File altered in transit during upload | Client vs server hash | Upload rejected, `HASH_MISMATCH_ON_UPLOAD` alert |

`POST /demo/reset` restores a clean state from the seed snapshot.

## 8. Honest limits (have answers ready)

- Prototype keys live in a key file; production → Vault Transit / HSM, separation of key custodians.
- Manifest signature is the **platform's** attestation. Uploader-held keys (WebCrypto) are stretch;
  legal signatures are a DSC / Aadhaar eSign adapter in production.
- `GOVERNANCE` lock in the demo so we can reset; production uses `COMPLIANCE`.
- A hash match proves sameness of bytes, not authorship, truthfulness or admissibility.
