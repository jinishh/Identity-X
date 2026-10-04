# 06 · Demo Story & Seed World

Everything here is **fictional**: the state ("Navagarh", code `NV`), districts, stations,
people, phone numbers and vehicle numbers. Seed passwords and TOTP secrets live only in the
seed file (`infra/seed/`), never in docs or slides.

## Organisation

```
NV State HQ (STATE_HQ)
├── Navagarh District HQ (DISTRICT_HQ)
│   ├── Shantinagar Police Station      NV-PS-SHN   ← hero case
│   ├── Mahila Police Station Navagarh  NV-PS-MPN
│   └── Rampur Police Station           NV-PS-RMP
├── Navagarh Regional FSL (FSL)         NV-FSL-01
├── Navagarh Prosecution Office         NV-PRO-01
└── NCRB Audit Cell (NCRB_CELL)         NV-NCRB-AUD
```

## Cast

| Service ID | Name | Rank | Role | Unit | Demo purpose |
|---|---|---|---|---|---|
| `NV-IO-1045` | Anjali Verma | Sub-Inspector | INVESTIGATOR | Shantinagar PS | Lead IO of the hero case |
| `NV-IO-1088` | Rohit Kumar | ASI | INVESTIGATOR | Shantinagar PS | Co-IO; sees only redacted victim docs |
| `NV-SHO-201` | Meera Nair | Inspector (SHO) | SUPERVISOR | Shantinagar PS | Approves shares, reviews charge-sheet |
| `NV-DSP-031` | Vikram Rao | DSP | SUPERVISOR | District HQ | Second approver (legal-hold release) |
| `NV-APP-077` | Farhan Siddiqui | APP | PROSECUTOR | Prosecution Office | Legal hold, certificate in court |
| `NV-FSL-512` | Dr. Kavya Iyer | Scientific Officer | FORENSIC_EXPERT | Regional FSL | Receives phone extraction by custody transfer |
| `NV-AUD-009` | Suresh Patil | Audit Officer | AUDITOR | NCRB Audit Cell | Verifies chain, sees alerts |
| `NV-ADM-001` | Neha Joshi | System Admin | ADMIN | State HQ | Users; runs demo tamper panel |
| `NV-IO-2210` | Arjun Mehta | Sub-Inspector | INVESTIGATOR | Rampur PS | **Outsider** — gets ACCESS DENIED, then break-glass |

## Hero case

**`NV/SHN/0142/2026`** — FIR 0142/2026, dated 14 Aug 2026, Shantinagar PS.
Category `CRIME_AGAINST_WOMEN`, sections **BNS 74, BNS 78, BNS 351(2)** (assault with intent to
outrage modesty, stalking, criminal intimidation). Victim-protected; victim pseudonym `V-1`.
Story: the victim was followed for weeks; on 12 Aug a **white SUV `NV 01 AB 4521`** was seen near
the incident spot; the accused's phone was seized and sent to FSL.

| Doc | Type | Sensitivity | Versions | Notes |
|---|---|---|---|---|
| FIR 0142/2026 (scanned, Hindi + English) | FIR | VICTIM_PROTECTED | 1 | OCR demo (eng+hin) |
| Statement of V-1 | VICTIM_STATEMENT | VICTIM_PROTECTED | 1 | Co-IO sees redacted only |
| Medical examination report | MEDICAL_REPORT | VICTIM_PROTECTED | 1 | Purpose + step-up to download |
| Witness statement WS-1 (shopkeeper) | WITNESS_STATEMENT | CONFIDENTIAL | 2 | **Search hit: "white SUV … near the bus stand"**; v2 = corrected date |
| Witness statement WS-2 (auto driver) | WITNESS_STATEMENT | CONFIDENTIAL | 1 | Mentions vehicle number |
| CCTV still — bus stand camera 3 | CCTV_STILL | CONFIDENTIAL | 1 | Image evidence |
| Seizure memo — accused's phone | SEIZURE_MEMO | RESTRICTED | 1 | |
| Forensic report — phone extraction | FORENSIC_REPORT | RESTRICTED | 1 | Uploaded by FSL after custody transfer |
| Charge-sheet draft | CHARGESHEET | VICTIM_PROTECTED | 2 | v1 returned, v2 approved by SHO |

Members: Anjali (LEAD_IO), Rohit (CO_IO), Meera (SUPERVISOR, implicit), Farhan (PROSECUTOR),
Kavya (FORENSIC, time-boxed).

## Background world (for realistic dashboards)

- ~24 more cases across the three stations, all categories and statuses.
- ~1,250 document versions total (metadata + small generated PDFs/images), ~40 still
  processing/pending, a handful quarantined (EICAR) and 2–3 shares expiring this week.
- ~3,000 audit events spread over the last 60 days with realistic working-hour patterns,
  ~30 checkpoints.
- Open alerts: one `ACCESS_DENIED_BURST`, a few `VICTIM_RECORD_ACCESSED` (INFO), one
  `OFF_HOURS_ACCESS`.

## The 5-minute judge demo

Two browser windows side by side (officer / supervisor-or-auditor) + a phone for the QR.

| # | Time | Who | Do | Say (one line) |
|---|---|---|---|---|
| 1 | 0:00 | Anjali | Log in → OTP | "No access without 2FA, ever." |
| 2 | 0:15 | Anjali | Dashboard → hero case | "Everything is organised around the case, not folders." |
| 3 | 0:30 | Anjali | Upload WS-3 (scanned PDF) → watch the pipeline | "Fingerprinted in the browser, re-checked on the server, scanned, encrypted with its own key, WORM-locked, signed, chained into the audit log." |
| 4 | 1:15 | Anjali | Search *"white SUV near bus stand"* → hit in WS-1, page 2 | "Scanned paper becomes searchable — in Hindi too." |
| 5 | 1:35 | Rohit | Open victim statement → redacted copy | "Co-IO sees the facts, not the victim's identity — BNS §72." |
| 6 | 1:55 | Anjali | Open original → purpose prompt → watermarked view | "Every view of a victim record needs a reason and is watermarked to the viewer." |
| 7 | 2:15 | Anjali | Upload WS-1 v3 → versions panel | "v1 and v2 can't be changed or deleted — locked until 2036." |
| 8 | 2:35 | Arjun | Try to open the case → **ACCESS DENIED** | "Wrong station? Denied — and the attempt itself is on the record." |
| 9 | 2:50 | Anjali → Meera | Request share to Farhan → Meera approves in inbox | "Sharing is approved, scoped and expires automatically." |
| 10 | 3:15 | Farhan | Generate §63 certificate → PDF with QR | "Pre-filled certificate with the hash — ready for signature." |
| 11 | 3:35 | Judge's phone | Scan QR → drop original → **MATCH**; drop edited copy → **MISMATCH** | "The court checks integrity without ever uploading the file." |
| 12 | 4:05 | Neha → Suresh | Demo panel T3 (edit one audit row in the DB) → Suresh: Verify chain → **broken at seq N** | "Even a database admin can't quietly change history." |
| 13 | 4:30 | Neha → Suresh | T4 (rewrite the whole chain) → **checkpoint mismatch** | "And rewriting everything doesn't work either — sealed checkpoints are WORM-locked." |
| 14 | 4:50 | Suresh | Alerts page | "Protect, prove, trace, verify, certify." |

**Backup:** a recorded screen capture of the full run, and `POST /demo/reset` between runs.

## Likely judge questions — prepared answers

| Question | Answer |
|---|---|
| Where is the blockchain? | Hash-chained audit log + signed Merkle checkpoints sealed in WORM storage; anchoring checkpoints to a permissioned ledger (Fabric) is the production step. We put proofs on the ledger, not documents. |
| Is the digital signature legally valid? | The prototype signature is the platform's attestation (Ed25519). Legally valid signatures come through a CCA-licensed DSC / Aadhaar eSign adapter in production. |
| Does a hash make evidence admissible? | No. It proves the bytes are unchanged. Admissibility needs the §63 certificate signed by the person in charge and an expert — we pre-fill it. |
| What if the server key leaks? | Envelope encryption: each file has its own key, wrapped by a master key that belongs in Vault/HSM in production; rotation only re-wraps keys. |
| What if the admin goes rogue? | Admin can't read documents or edit the audit log (DB permissions + trigger); any tampering breaks the chain or the sealed checkpoints. |
| How does this fit CCTNS / ICJS / e-Sakshya? | API-first (OpenAPI); those systems become sources/consumers through adapters. We complement them with integrity and controlled sharing. |
| Scale? | Stateless API + workers scale horizontally; S3-compatible storage; Postgres partitions for audit. |
