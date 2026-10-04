"""Upload pipeline (docs/03-integrity-model.md §1).

Synchronous part (in the request): RECEIVE → HASH_MATCH → VALIDATE, then 202.
Background part: MALWARE_SCAN → ENCRYPT → STORE_WORM → SIGN_MANIFEST → AUDIT_ANCHOR are
integrity-critical; OCR → EXTRACT_ENTITIES → REDACT → INDEX → EMBED are best-effort.
"""

import json
import re
import threading
import time
import unicodedata
from datetime import timedelta

import pymupdf
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import audit, config, crypto, storage
from .audit import Ctx, iso
from .db import SessionLocal
from .errors import ApiError
from .models import (Alert, Case, Derivative, Document, DocumentVersion, Entity, ProcessingStep,
                     User, new_id, utcnow)

STEPS = [
    ("RECEIVE", True), ("HASH_MATCH", True), ("VALIDATE", True), ("MALWARE_SCAN", True),
    ("ENCRYPT", True), ("STORE_WORM", True), ("SIGN_MANIFEST", True), ("AUDIT_ANCHOR", True),
    ("OCR", False), ("EXTRACT_ENTITIES", False), ("REDACT", False), ("INDEX", False),
    ("EMBED", False),
]

MAGIC = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]
EXTENSIONS = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/tiff": {".tif", ".tiff"},
}
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

ENTITY_PATTERNS = [
    ("AADHAAR", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"), True),
    ("PHONE", re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b"), True),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), True),
    ("VEHICLE_NUMBER", re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{4}\b"), False),
    ("LEGAL_SECTION", re.compile(r"\b(?:BNS|BNSS|BSA|IPC|CrPC)\s+(?:Section\s+)?\d+[A-Z]?(?:\(\d+\))?"), False),
    ("CASE_REFERENCE", re.compile(r"\bFIR\s*(?:No\.?\s*)?\d{1,5}/\d{4}\b"), False),
    ("DATE", re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|\b\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{4}\b"), False),
    ("PERSON", re.compile(r"\b(?:Shri|Smt\.?|Mr\.?|Ms\.?|Kumari|Dr\.)\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?"), True),
]
REDACTABLE = {"AADHAAR", "PHONE", "EMAIL"}  # plus victim identifiers


def detect_mime(data: bytes) -> str | None:
    return next((m for sig, m in MAGIC if data.startswith(sig)), None)


def safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ]", "_", name).strip(" .")[:120]
    return name or "upload"


# ───────────── synchronous intake ─────────────

def intake(db: Session, ctx: Ctx, doc: Document, data: bytes, filename: str,
           client_sha256: str, change_note: str | None, is_new: bool) -> DocumentVersion:
    """Hash-match and validate, create the version row, stage plaintext, audit the upload.
    Raises ApiError on rejection (after auditing it). A new document is only added to the
    session once every check has passed."""
    received_at = utcnow()
    filename = safe_filename(filename)
    sha = crypto.sha256_hex(data)
    client_sha256 = client_sha256.lower()

    if sha != client_sha256:
        audit.record(db, ctx, "HASH_MISMATCH_ON_UPLOAD",
                     f"Upload rejected: {filename} changed in transit", outcome="FAILED",
                     case_id=doc.case_id, document_id=None if is_new else doc.id,
                     details={"client_sha256": client_sha256, "server_sha256": sha})
        db.add(Alert(type="HASH_MISMATCH_ON_UPLOAD", severity="HIGH",
                     title="File changed in transit",
                     message=f"{filename}: browser fingerprint does not match the bytes received.",
                     case_id=doc.case_id, actor_user_id=ctx.user.id if ctx.user else None))
        db.commit()
        raise ApiError(422, "HASH_MISMATCH", "Upload rejected — file changed in transit",
                       f"Browser SHA-256 {client_sha256[:12]}… ≠ server SHA-256 {sha[:12]}…")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ApiError(413, "TOO_LARGE", "File too large", "The limit is 50 MB.")
    mime = detect_mime(data)
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if mime is None:
        raise ApiError(415, "UNSUPPORTED_TYPE", "Unsupported file type",
                       "Only PDF, JPEG, PNG and TIFF are accepted (checked by file signature).")
    if ext not in EXTENSIONS[mime]:
        raise ApiError(415, "EXTENSION_MISMATCH", "File extension does not match its content",
                       f"Content is {mime} but the name ends in '{ext or '(none)'}'.")

    if is_new:
        db.add(doc)
        db.flush()
    prev = None
    if doc.current_version_id:
        prev = db.get(DocumentVersion, doc.current_version_id)
    last_no = db.scalar(text("SELECT COALESCE(MAX(version_no),0) FROM docs.versions "
                             "WHERE document_id=:d"), {"d": doc.id}) or 0
    v = DocumentVersion(
        id=new_id(), document_id=doc.id, version_no=last_no + 1,
        parent_version_id=prev.id if prev else None, change_note=change_note,
        original_filename=filename, detected_mime=mime, size_bytes=len(data), sha256=sha,
        client_sha256=client_sha256, prev_version_sha256=prev.sha256 if prev else None,
        processing_status="RECEIVED", uploaded_by=ctx.user.id, uploaded_at=received_at,
        review_status="NOT_REQUIRED",
    )
    db.add(v)
    now = utcnow()
    for i, (name, critical) in enumerate(STEPS, start=1):
        st = ProcessingStep(version_id=v.id, step=name, seq=i, critical=critical,
                            status="PENDING", detail={})
        if name == "RECEIVE":
            st.status, st.started_at, st.finished_at = "DONE", received_at, now
            st.detail = {"bytes": len(data), "filename": filename}
        elif name == "HASH_MATCH":
            st.status, st.started_at, st.finished_at = "DONE", now, now
            st.detail = {"sha256": sha, "client_sha256": client_sha256, "match": True}
        elif name == "VALIDATE":
            st.status, st.started_at, st.finished_at = "DONE", now, now
            st.detail = {"detected_mime": mime, "size_ok": True, "extension_ok": True}
        db.add(st)
    (config.QUARANTINE_DIR / f"{v.id}.upload").write_bytes(data)
    audit.record(db, ctx, "DOCUMENT_UPLOADED",
                 f"Uploaded {'v' + str(v.version_no) + ' of ' if v.version_no > 1 else ''}"
                 f"{doc.title} ({filename})",
                 case_id=doc.case_id, document_id=doc.id, version_id=v.id,
                 details={"sha256": sha, "size_bytes": len(data), "version_no": v.version_no,
                          "mime": mime})
    return v


def start_background(version_id: str, delay_ms: int | None = None) -> None:
    threading.Thread(target=run, args=(version_id, delay_ms), daemon=True).start()


# ───────────── background processing ─────────────

def _victim_identifiers(case: Case) -> list[str]:
    if not case.victim_identifiers_enc:
        return []
    return json.loads(crypto.unseal(case.victim_identifiers_enc))


def build_manifest(v: DocumentVersion, doc: Document, uploader: User) -> dict:
    return {
        "schema": "cfv.manifest/1",
        "document_id": doc.id,
        "version_id": v.id,
        "version_no": v.version_no,
        "doc_number": doc.doc_number,
        "case_number": doc.case.case_number,
        "doc_type": doc.doc_type,
        "original_filename": v.original_filename,
        "detected_mime": v.detected_mime,
        "size_bytes": v.size_bytes,
        "sha256": v.sha256,
        "prev_version_sha256": v.prev_version_sha256,
        "client_sha256_matched": v.client_sha256 == v.sha256,
        "uploaded_by": {"user_id": uploader.id, "service_id": uploader.service_id},
        "uploaded_at": iso(v.uploaded_at),
        "scan": {"engine": "built-in signature scan", "result": v.scan_result},
        "storage": {"object": v.storage_key, "lock": "write-once", "retain_until": iso(v.retain_until)},
        "encryption": {"alg": "AES-256-GCM", "kek_id": v.kek_id,
                       "ciphertext_sha256": v.ciphertext_sha256},
    }


def aad_for(v: DocumentVersion) -> bytes:
    return f"{v.id}|{v.sha256}".encode()


def decrypt_version(v: DocumentVersion) -> bytes:
    ct = storage.get(config.OBJECTS_DIR, v.storage_key)
    return crypto.decrypt_file(ct, v.enc_nonce, v.wrapped_dek, aad_for(v))


def store_derivative(db: Session, v: DocumentVersion, kind: str, data: bytes, mime: str,
                     summary: dict, created_by: str) -> Derivative:
    d = Derivative(id=new_id(), source_version_id=v.id, kind=kind, mime=mime,
                   storage_key="", sha256=crypto.sha256_hex(data), summary=summary,
                   created_by=created_by, enc_nonce=b"", wrapped_dek=b"", kek_id=crypto.KEK_ID)
    d.storage_key = f"{d.id}.bin"
    ct, d.enc_nonce, d.wrapped_dek = crypto.encrypt_file(data, f"{d.id}|{d.sha256}".encode())
    storage.put(config.DERIVATIVES_DIR, d.storage_key, ct)
    db.add(d)
    return d


def decrypt_derivative(d: Derivative) -> bytes:
    ct = storage.get(config.DERIVATIVES_DIR, d.storage_key)
    return crypto.decrypt_file(ct, d.enc_nonce, d.wrapped_dek, f"{d.id}|{d.sha256}".encode())


def _mask(text_: str, values: list[str]) -> str:
    for val in sorted(set(values), key=len, reverse=True):
        if val.strip():
            text_ = re.sub(re.escape(val), "█" * min(len(val), 12), text_, flags=re.IGNORECASE)
    return text_


def redact_pdf(data: bytes, values: list[str]) -> tuple[bytes, int]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    spans = 0
    for page in doc:
        for val in set(values):
            for rect in page.search_for(val):
                page.add_redact_annot(rect, fill=(0, 0, 0))
                spans += 1
        page.apply_redactions()
        page.insert_text((36, 20), "REDACTED COPY · victim identity protected (BNS §72)",
                         fontsize=8, color=(0.45, 0.2, 0.6))
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out, spans


def run(version_id: str, delay_ms: int | None = None) -> None:
    delay = (config.PIPELINE_STEP_DELAY_MS if delay_ms is None else delay_ms) / 1000
    db = SessionLocal()
    try:
        _run(db, version_id, delay)
    except Exception as exc:  # never leave a version stuck in PROCESSING
        db.rollback()
        v = db.get(DocumentVersion, version_id)
        if v and v.processing_status not in ("READY", "QUARANTINED"):
            v.processing_status = "FAILED"
            for st in db.query(ProcessingStep).filter_by(version_id=version_id, status="RUNNING"):
                st.status, st.finished_at, st.detail = "FAILED", utcnow(), {"error": str(exc)[:200]}
            db.commit()
        raise
    finally:
        db.close()


def _run(db: Session, version_id: str, delay: float) -> None:
    v = db.get(DocumentVersion, version_id)
    doc = db.get(Document, v.document_id)
    case = doc.case
    uploader = db.get(User, v.uploaded_by)
    ctx = Ctx(user=uploader)
    staged = config.QUARANTINE_DIR / f"{v.id}.upload"
    data = staged.read_bytes()
    steps = {s.step: s for s in db.query(ProcessingStep).filter_by(version_id=v.id)}
    v.processing_status = "PROCESSING"
    db.commit()

    def begin(name):
        st = steps[name]
        st.status = "RUNNING"
        db.commit()
        if delay:  # demo pacing so the UI can show each step; not counted as work time
            time.sleep(delay)
        st.started_at = utcnow()
        return st

    def finish(st, status="DONE", **detail):
        st.status, st.finished_at, st.detail = status, utcnow(), detail
        db.commit()

    # MALWARE_SCAN
    st = begin("MALWARE_SCAN")
    if EICAR in data:
        v.scan_result, v.scan_detail = "INFECTED", "Eicar-Test-Signature"
        v.processing_status = "QUARANTINED"
        finish(st, "FAILED", engine="built-in signature scan", result="INFECTED",
               signature="Eicar-Test-Signature", note="ClamAV in production")
        for name, _ in STEPS[STEPS.index(("MALWARE_SCAN", True)) + 1:]:
            steps[name].status = "SKIPPED"
        db.add(Alert(type="MALWARE_DETECTED", severity="HIGH", title="Malware blocked at upload",
                     message=f"{v.original_filename} matched Eicar-Test-Signature and was quarantined.",
                     case_id=case.id, document_id=doc.id, actor_user_id=uploader.id))
        audit.record(db, ctx, "VERSION_QUARANTINED",
                     f"Quarantined {v.original_filename}: Eicar-Test-Signature",
                     outcome="FAILED", case_id=case.id, document_id=doc.id, version_id=v.id,
                     details={"signature": "Eicar-Test-Signature", "sha256": v.sha256})
        return
    v.scan_result = "CLEAN"
    finish(st, engine="built-in signature scan", result="CLEAN", note="ClamAV in production")

    # ENCRYPT
    st = begin("ENCRYPT")
    ct, v.enc_nonce, v.wrapped_dek = crypto.encrypt_file(data, aad_for(v))
    v.kek_id = crypto.KEK_ID
    v.ciphertext_sha256 = crypto.sha256_hex(ct)
    finish(st, alg="AES-256-GCM", key="fresh 256-bit DEK, wrapped by " + crypto.KEK_ID,
           aad="version_id ‖ sha256", ciphertext_sha256=v.ciphertext_sha256)

    # STORE_WORM
    st = begin("STORE_WORM")
    v.storage_key = f"{v.id}.bin"
    storage.put(config.OBJECTS_DIR, v.storage_key, ct)
    v.retain_until = v.uploaded_at + timedelta(days=365 * config.RETENTION_YEARS)
    finish(st, object=v.storage_key, lock="write-once", retain_until=iso(v.retain_until))

    # SIGN_MANIFEST
    st = begin("SIGN_MANIFEST")
    v.manifest = build_manifest(v, doc, uploader)
    v.manifest_sha256 = crypto.sha256_hex(crypto.jcs(v.manifest))
    v.signature, v.signing_key_id = crypto.sign("MANIFEST", v.manifest)
    finish(st, alg="Ed25519", kid=v.signing_key_id, manifest_sha256=v.manifest_sha256)

    # AUDIT_ANCHOR
    st = begin("AUDIT_ANCHOR")
    ev = audit.record(db, ctx, "VERSION_CREATED",
                      f"Sealed v{v.version_no} of {doc.title} · SHA-256 {v.sha256[:12]}…",
                      case_id=case.id, document_id=doc.id, version_id=v.id,
                      details={"version_no": v.version_no, "sha256": v.sha256,
                               "manifest_sha256": v.manifest_sha256}, occurred_at=None)
    finish(st, audit_seq=ev.seq, event_hash=ev.event_hash)

    # OCR / text extraction
    st = begin("OCR")
    pages: list[str] = []
    if v.detected_mime == "application/pdf":
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            v.page_count = pdf.page_count
            pages = [p.get_text() for p in pdf]
        if any(p.strip() for p in pages):
            v.ocr_status = "DONE"
            finish(st, method="embedded text layer", pages=len(pages),
                   chars=sum(len(p) for p in pages))
        else:
            v.ocr_status = "NOT_APPLICABLE"
            finish(st, "SKIPPED", reason="scanned PDF without text layer",
                   note="OCRmyPDF (eng+hin) in production")
    else:
        v.page_count = 1
        v.ocr_status = "NOT_APPLICABLE"
        finish(st, "SKIPPED", reason="image", note="OCR for images in production")

    # EXTRACT_ENTITIES
    st = begin("EXTRACT_ENTITIES")
    victims = _victim_identifiers(case)
    counts: dict[str, int] = {}
    for page_no, page_text in enumerate(pages, start=1):
        for etype, pattern, pii in ENTITY_PATTERNS:
            for m in pattern.finditer(page_text):
                db.add(Entity(version_id=v.id, type=etype, value=m.group(0).strip(),
                              page_no=page_no, is_pii=pii, source="REGEX"))
                counts[etype] = counts.get(etype, 0) + 1
        for name in victims:
            if name.lower() in page_text.lower():
                db.add(Entity(version_id=v.id, type="PERSON", value=name, page_no=page_no,
                              is_pii=True, is_victim_identifier=True, source="REGISTER"))
                counts["VICTIM_IDENTIFIER"] = counts.get("VICTIM_IDENTIFIER", 0) + 1
    db.flush()
    finish(st, found=counts, method="pattern rules + victim register")

    # REDACT
    st = begin("REDACT")
    sensitive = victims + [e.value for e in db.query(Entity).filter_by(version_id=v.id)
                           if e.type in REDACTABLE]
    redacted_pages = pages
    if doc.sensitivity == "VICTIM_PROTECTED":
        redacted_pages = [_mask(p, sensitive) for p in pages]
        if v.detected_mime == "application/pdf":
            red, spans = redact_pdf(data, sensitive)
            d = store_derivative(db, v, "REDACTED", red, "application/pdf",
                                 {"redacted_spans": spans, "auto": True}, uploader.id)
            finish(st, spans=spans, derivative=d.id, rule="victim register + Aadhaar/phone/email")
        else:
            finish(st, "SKIPPED", reason="image redaction needs manual review")
    else:
        finish(st, "SKIPPED", reason=f"not required for {doc.sensitivity}")

    # INDEX
    st = begin("INDEX")
    for page_no, (orig, red) in enumerate(zip(pages, redacted_pages), start=1):
        if not orig.strip():
            continue
        db.execute(text("INSERT INTO docs.text_index(body, version_id, document_id, page_no, redacted) "
                        "VALUES (:t,:v,:d,:p,false)"), {"t": orig, "v": v.id, "d": doc.id, "p": page_no})
        if doc.sensitivity == "VICTIM_PROTECTED":
            db.execute(text("INSERT INTO docs.text_index(body, version_id, document_id, page_no, redacted) "
                            "VALUES (:t,:v,:d,:p,true)"), {"t": red, "v": v.id, "d": doc.id, "p": page_no})
    finish(st, engine="PostgreSQL full-text (tsvector + GIN)", pages_indexed=sum(1 for p in pages if p.strip()))

    # EMBED
    st = begin("EMBED")
    finish(st, "SKIPPED", reason="semantic search is on the roadmap (pgvector)")

    v.processing_status = "READY"
    doc.current_version_id = v.id
    doc.updated_at = case.updated_at = utcnow()
    staged.unlink(missing_ok=True)
    audit.record(db, ctx, "VERSION_READY", f"v{v.version_no} of {doc.title} is ready",
                 case_id=case.id, document_id=doc.id, version_id=v.id)
