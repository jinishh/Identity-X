import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, certpdf, config, content, crypto, integrity, pipeline, policy, serial
from ..db import get_db
from ..errors import ApiError, conflict, deny, not_found, precondition
from ..models import (Alert, AuditEvent, Certificate, Derivative, Document, DocumentVersion,
                      Entity, ProcessingStep, Request as Req, User, new_id, utcnow)
from ..security import ctx_for, current_user, step_up_valid

router = APIRouter(tags=["Documents"])

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


class ReasonIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class DocUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    doc_type: str | None = None
    tags: list[str] | None = None


class SensitivityIn(BaseModel):
    sensitivity: str
    reason: str = Field(min_length=10)


class AccessIn(BaseModel):
    variant: str = Field(pattern="^(ORIGINAL|REDACTED)$")
    disposition: str = Field(pattern="^(inline|attachment)$")
    purpose: str | None = Field(default=None, max_length=500)


class ShareIn(BaseModel):
    grantee_user_id: str
    scope: str
    expires_at: datetime
    reason: str = Field(min_length=10)


class CustodyIn(BaseModel):
    to_user_id: str
    reason: str = Field(min_length=10)


class ReviewIn(BaseModel):
    note: str | None = None


class CertificateIn(BaseModel):
    signatory_name: str = Field(min_length=3)
    signatory_designation: str = Field(min_length=2)
    purpose: str | None = None


class RedactionIn(BaseModel):
    mode: str = "AUTO"


# ───────────── loaders ─────────────

def load_doc(db: Session, request: Request, user: User, doc_id: str,
             action: str | None = None) -> tuple[Document, policy.Access]:
    doc = db.get(Document, doc_id)
    if not doc:
        raise not_found("Document")
    acc = policy.document_access(db, user, doc)
    visible = acc.caps or acc.via or user.role == "AUDITOR"
    if not visible:
        raise deny(db, ctx_for(request, user), "NOT_A_CASE_MEMBER",
                   f"Denied opening {doc.doc_number}", case_id=doc.case_id, document_id=doc.id)
    if action and action not in acc.actions:
        reason = ("LEGAL_HOLD" if doc.retention_state == "LEGAL_HOLD" and "legal_hold" not in action
                  else "CASE_CLOSED" if doc.case.status == "CLOSED" else "ACTION_NOT_PERMITTED")
        raise deny(db, ctx_for(request, user), reason, f"Denied {action} on {doc.doc_number}",
                   case_id=doc.case_id, document_id=doc.id)
    return doc, acc


def load_version(db: Session, request: Request, user: User, version_id: str,
                 action: str | None = None):
    v = db.get(DocumentVersion, version_id)
    if not v:
        raise not_found("Version")
    doc, acc = load_doc(db, request, user, v.document_id, action)
    return v, doc, acc


# ───────────── documents ─────────────

@router.get("/documents/{doc_id}")
def get_document(doc_id: str, request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    doc, acc = load_doc(db, request, user, doc_id)
    return serial.document_full(db, doc, acc)


@router.patch("/documents/{doc_id}")
def update_document(doc_id: str, body: DocUpdateIn, request: Request,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, acc = load_doc(db, request, user, doc_id, "document:new_version")
    changed = body.model_dump(exclude_unset=True)
    for k, v in changed.items():
        setattr(doc, k, v)
    doc.updated_at = utcnow()
    audit.record(db, ctx_for(request, user), "CASE_UPDATED", f"Edited details of {doc.doc_number}",
                 case_id=doc.case_id, document_id=doc.id, details={"fields": sorted(changed)})
    return serial.document_full(db, doc, policy.document_access(db, user, doc))


@router.post("/documents/{doc_id}/sensitivity")
def change_sensitivity(doc_id: str, body: SensitivityIn, request: Request,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = policy.SENSITIVITY_ORDER
    if body.sensitivity not in order:
        raise ApiError(422, "BAD_SENSITIVITY", "Unknown sensitivity")
    doc, _ = load_doc(db, request, user, doc_id)
    lowering = order.index(body.sensitivity) < order.index(doc.sensitivity)
    action = "document:lower_sensitivity" if lowering else "document:raise_sensitivity"
    doc, _ = load_doc(db, request, user, doc_id, action)
    if lowering and not step_up_valid(user):
        raise precondition("STEP_UP_REQUIRED", "Re-enter your 2FA code to lower sensitivity.")
    old, doc.sensitivity, doc.updated_at = doc.sensitivity, body.sensitivity, utcnow()
    audit.record(db, ctx_for(request, user), "SENSITIVITY_CHANGED",
                 f"{doc.doc_number}: {old} → {body.sensitivity}", case_id=doc.case_id,
                 document_id=doc.id, details={"from": old, "to": body.sensitivity,
                                              "reason": body.reason})
    return serial.document_full(db, doc, policy.document_access(db, user, doc))


@router.get("/documents/{doc_id}/versions")
def list_versions(doc_id: str, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id)
    rows = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                      .order_by(DocumentVersion.version_no.desc()))
    return [serial.version_full(v) for v in rows]


@router.post("/documents/{doc_id}/versions", status_code=202)
async def upload_version(doc_id: str, request: Request, file: UploadFile = File(...),
                         client_sha256: str = Form(...), change_note: str = Form(...),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id, "document:new_version")
    if len(change_note.strip()) < 5:
        raise ApiError(422, "CHANGE_NOTE_REQUIRED", "Describe what changed (at least 5 characters)")
    busy = db.scalar(select(DocumentVersion.id).where(
        DocumentVersion.document_id == doc.id,
        DocumentVersion.processing_status.in_(["RECEIVED", "PROCESSING"])))
    if busy:
        raise conflict("VERSION_PROCESSING", "Wait for the previous version to finish processing")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    v = pipeline.intake(db, ctx_for(request, user), doc, data, file.filename or "upload",
                        client_sha256, change_note.strip(), is_new=False)
    pipeline.start_background(v.id)
    return {"document_id": doc.id, "version_id": v.id, "version_no": v.version_no,
            "sha256": v.sha256, "processing_url": f"/api/v1/versions/{v.id}/processing"}


@router.post("/documents/{doc_id}/legal-hold")
def set_legal_hold(doc_id: str, body: ReasonIn, request: Request,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id, "document:legal_hold_set")
    doc.retention_state, doc.legal_hold_reason = "LEGAL_HOLD", body.reason
    doc.legal_hold_by, doc.legal_hold_at = user.id, utcnow()
    audit.record(db, ctx_for(request, user), "LEGAL_HOLD_SET", f"Legal hold on {doc.doc_number}",
                 case_id=doc.case_id, document_id=doc.id, details={"reason": body.reason})
    return serial.document_full(db, doc, policy.document_access(db, user, doc))


@router.post("/documents/{doc_id}/legal-hold/release", status_code=201)
def request_hold_release(doc_id: str, body: ReasonIn, request: Request,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id, "document:legal_hold_release")
    r = Req(id=new_id(), type="LEGAL_HOLD_RELEASE", case_id=doc.case_id, document_id=doc.id,
            requested_by=user.id, reason=body.reason, payload={})
    db.add(r)
    audit.record(db, ctx_for(request, user), "REQUEST_CREATED",
                 f"Requested release of legal hold on {doc.doc_number}", case_id=doc.case_id,
                 document_id=doc.id, request_id=r.id)
    return serial.request(db, r, user)


@router.post("/documents/{doc_id}/withdraw")
def withdraw(doc_id: str, body: ReasonIn, request: Request, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id, "document:withdraw")
    doc.status, doc.withdrawn_reason = "WITHDRAWN", body.reason
    doc.withdrawn_by, doc.withdrawn_at = user.id, utcnow()
    audit.record(db, ctx_for(request, user), "DOCUMENT_WITHDRAWN",
                 f"Withdrew {doc.doc_number} (retained, not deleted)", case_id=doc.case_id,
                 document_id=doc.id, details={"reason": body.reason})
    return serial.document_full(db, doc, policy.document_access(db, user, doc))


@router.get("/documents/{doc_id}/timeline")
def doc_timeline(doc_id: str, request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id)
    rows = db.scalars(select(AuditEvent).where(AuditEvent.document_id == doc.id)
                      .order_by(AuditEvent.seq)).all()
    return serial.audit_events(db, rows)


@router.get("/documents/{doc_id}/shares")
def list_shares(doc_id: str, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    from ..models import Share
    doc, _ = load_doc(db, request, user, doc_id)
    rows = db.scalars(select(Share).where(Share.document_id == doc.id)
                      .order_by(Share.created_at.desc()))
    return [serial.share(s) for s in rows]


@router.post("/documents/{doc_id}/shares", status_code=201)
def request_share(doc_id: str, body: ShareIn, request: Request,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id, "document:share_request")
    grantee = db.get(User, body.grantee_user_id)
    if not grantee or grantee.role in policy.NO_CONTENT_ROLES or grantee.id == user.id:
        raise ApiError(422, "BAD_GRANTEE", "Choose an officer, prosecutor or forensic expert")
    allowed = policy.SHARE_SCOPES_ALLOWED[doc.sensitivity]
    if body.scope not in allowed:
        raise ApiError(422, "SCOPE_NOT_ALLOWED",
                       f"{doc.sensitivity} documents can only be shared as {', '.join(allowed)}")
    expires = body.expires_at.replace(tzinfo=None)
    max_days = policy.SHARE_MAX_DAYS[doc.sensitivity]
    if expires > utcnow() + timedelta(days=max_days, hours=1) or expires <= utcnow():
        raise ApiError(422, "BAD_EXPIRY", f"Expiry must be within {max_days} days")
    r = Req(id=new_id(), type="SHARE", case_id=doc.case_id, document_id=doc.id,
            requested_by=user.id, reason=body.reason,
            payload={"grantee_user_id": grantee.id, "scope": body.scope,
                     "expires_at": audit.iso(expires)})
    db.add(r)
    audit.record(db, ctx_for(request, user), "REQUEST_CREATED",
                 f"Requested to share {doc.doc_number} with {grantee.full_name} ({body.scope})",
                 case_id=doc.case_id, document_id=doc.id, request_id=r.id,
                 target_user_id=grantee.id)
    return serial.request(db, r, user)


@router.post("/documents/{doc_id}/custody-transfers", status_code=201)
def custody_transfer(doc_id: str, body: CustodyIn, request: Request,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = load_doc(db, request, user, doc_id, "document:custody_transfer")
    to = db.get(User, body.to_user_id)
    if not to or to.role in policy.NO_CONTENT_ROLES or to.id == user.id:
        raise ApiError(422, "BAD_RECIPIENT", "Choose another officer or expert")
    r = Req(id=new_id(), type="CUSTODY_TRANSFER", case_id=doc.case_id, document_id=doc.id,
            requested_by=user.id, assigned_to=to.id, reason=body.reason,
            payload={"from_user_id": user.id, "to_user_id": to.id})
    db.add(r)
    audit.record(db, ctx_for(request, user), "REQUEST_CREATED",
                 f"Initiated custody transfer of {doc.doc_number} to {to.full_name}",
                 case_id=doc.case_id, document_id=doc.id, request_id=r.id, target_user_id=to.id)
    return serial.request(db, r, user)


# ───────────── versions ─────────────

@router.get("/versions/{version_id}")
def get_version(version_id: str, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    v, _, _ = load_version(db, request, user, version_id)
    return serial.version_full(v)


@router.get("/versions/{version_id}/processing")
def processing(version_id: str, request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    v, _, _ = load_version(db, request, user, version_id)
    steps = db.scalars(select(ProcessingStep).where(ProcessingStep.version_id == v.id)
                       .order_by(ProcessingStep.seq))
    return {"version_id": v.id, "status": v.processing_status,
            "steps": [{"step": s.step, "seq": s.seq, "status": s.status, "critical": s.critical,
                       "started_at": audit.iso(s.started_at), "finished_at": audit.iso(s.finished_at),
                       "detail": s.detail or {}} for s in steps]}


def _watermark(user: User, case_number: str) -> str:
    ist = utcnow() + timedelta(hours=5, minutes=30)
    return f"{user.full_name} · {user.service_id} · {ist:%d-%m-%Y %H:%M} IST · {case_number}"


@router.post("/versions/{version_id}/access")
def request_access(version_id: str, body: AccessIn, request: Request,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    v, doc, acc = load_version(db, request, user, version_id)
    ctx = ctx_for(request, user)
    if v.processing_status != "READY":
        raise conflict("NOT_READY", f"This version is {v.processing_status.lower()}")
    download = body.disposition == "attachment"
    allowed = acc.download if download else acc.view
    variant = body.variant
    if variant == "ORIGINAL" and allowed == "REDACTED":
        variant = "REDACTED"  # all the caller may see
    if allowed == "NONE" or (variant == "ORIGINAL" and allowed != "ORIGINAL"):
        raise deny(db, ctx, "SENSITIVITY",
                   f"Denied {'download' if download else 'view'} of {doc.doc_number} "
                   f"({doc.sensitivity})", case_id=doc.case_id, document_id=doc.id,
                   version_id=v.id)
    if variant == "ORIGINAL":
        needs_purpose = acc.download_needs_purpose if download else acc.view_needs_purpose
        if needs_purpose and len((body.purpose or "").strip()) < 10:
            raise precondition("PURPOSE_REQUIRED",
                               "State the purpose of access (at least 10 characters).")
        if download and acc.download_needs_step_up and not step_up_valid(user):
            raise precondition("STEP_UP_REQUIRED", "Re-enter your 2FA code to download the original.")

    if variant == "REDACTED":
        der = db.scalar(select(Derivative).where(Derivative.source_version_id == v.id,
                                                 Derivative.kind == "REDACTED")
                        .order_by(Derivative.created_at.desc()))
        if not der:
            raise conflict("NO_REDACTED_COPY", "No redacted copy exists for this version yet")
        token, exp = content.issue("DERIVATIVE", der.id, der.mime,
                                   f"{doc.doc_number}-v{v.version_no}-redacted.pdf", body.disposition)
        action = "REDACTED_VIEWED"
    else:
        ext = v.original_filename.rsplit(".", 1)[-1] if "." in v.original_filename else "bin"
        token, exp = content.issue("VERSION", v.id, v.detected_mime,
                                   f"{doc.doc_number}-v{v.version_no}.{ext}", body.disposition)
        action = "DOCUMENT_DOWNLOADED" if download else "DOCUMENT_VIEWED"

    verb = {"REDACTED_VIEWED": "Viewed redacted copy of", "DOCUMENT_DOWNLOADED": "Downloaded",
            "DOCUMENT_VIEWED": "Viewed"}[action]
    if doc.sensitivity == "VICTIM_PROTECTED" and variant == "ORIGINAL":
        db.add(Alert(type="VICTIM_RECORD_ACCESSED", severity="INFO",
                     title="Victim-protected original accessed",
                     message=f"{user.full_name} {verb.lower()} {doc.doc_number} — purpose: "
                             f"{(body.purpose or '').strip()}",
                     case_id=doc.case_id, document_id=doc.id, actor_user_id=user.id))
    ev = audit.record(db, ctx, action, f"{verb} {doc.title} (v{v.version_no})",
                      case_id=doc.case_id, document_id=doc.id, version_id=v.id,
                      purpose=(body.purpose or "").strip() or None,
                      details={"variant": variant, "via": acc.via})
    return {"url": f"/api/v1/content/{token}", "expires_at": audit.iso(exp), "variant": variant,
            "watermark": _watermark(user, doc.case.case_number), "audit_seq": ev.seq}


@router.get("/content/{token}")
def get_content(token: str, db: Session = Depends(get_db)):
    g = content.redeem(token)
    if not g:
        raise ApiError(410, "TOKEN_EXPIRED", "Link expired", "Request access again.")
    if g.kind == "VERSION":
        data = pipeline.decrypt_version(db.get(DocumentVersion, g.object_id))
    else:
        data = pipeline.decrypt_derivative(db.get(Derivative, g.object_id))
    return Response(data, media_type=g.mime, headers={
        "Content-Disposition": f'{g.disposition}; filename="{g.filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/versions/{version_id}/manifest")
def manifest(version_id: str, request: Request, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    v, _, _ = load_version(db, request, user, version_id)
    if not v.manifest:
        raise conflict("NOT_READY", "Manifest not yet signed")
    return {"manifest": v.manifest, "canonical": crypto.jcs(v.manifest).decode(),
            "manifest_sha256": v.manifest_sha256, "signature": crypto.b64(v.signature),
            "signing_key_id": v.signing_key_id, "algorithm": "Ed25519"}


@router.post("/versions/{version_id}/verify")
def verify(version_id: str, request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    v, doc, _ = load_version(db, request, user, version_id, "document:verify")
    if v.processing_status != "READY":
        raise conflict("NOT_READY", f"This version is {v.processing_status.lower()}")
    result = integrity.verify_version(db, v)
    v.last_verified_at, v.last_verification = utcnow(), result["overall"]
    ok = result["overall"] == "VERIFIED"
    failed = [c["name"] for c in result["checks"] if c["status"] == "FAIL"]
    if not ok:
        db.add(Alert(type="INTEGRITY_FAILED", severity="CRITICAL",
                     title="Document integrity check failed",
                     message=f"{doc.doc_number} v{v.version_no}: {', '.join(failed)}",
                     case_id=doc.case_id, document_id=doc.id, actor_user_id=user.id))
    ev = audit.record(db, ctx_for(request, user),
                      "INTEGRITY_VERIFIED" if ok else "INTEGRITY_FAILED",
                      f"Integrity {'verified' if ok else 'FAILED'}: {doc.title} v{v.version_no}",
                      outcome="SUCCESS" if ok else "FAILED", case_id=doc.case_id,
                      document_id=doc.id, version_id=v.id, details={"failed_checks": failed})
    return {**result, "audit_seq": ev.seq}


@router.get("/versions/{version_id}/entities")
def entities(version_id: str, request: Request, type: str | None = None,
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    v, doc, acc = load_version(db, request, user, version_id)
    stmt = select(Entity).where(Entity.version_id == v.id)
    if type:
        stmt = stmt.where(Entity.type == type)
    out = []
    for e in db.scalars(stmt.order_by(Entity.page_no, Entity.id)):
        value = e.value
        if (e.is_pii or e.is_victim_identifier) and acc.view != "ORIGINAL":
            value = "█" * 6 + (value[-4:] if e.type in ("PHONE", "AADHAAR") else "")
        out.append({"id": e.id, "type": e.type, "value": value, "page_no": e.page_no,
                    "is_pii": e.is_pii, "is_victim_identifier": e.is_victim_identifier,
                    "confidence": e.confidence, "source": e.source})
    return out


@router.get("/versions/{version_id}/redactions")
def list_redactions(version_id: str, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    v, _, _ = load_version(db, request, user, version_id)
    rows = db.scalars(select(Derivative).where(Derivative.source_version_id == v.id,
                                               Derivative.kind == "REDACTED"))
    return [serial.derivative(x) for x in rows]


@router.post("/versions/{version_id}/redactions", status_code=202)
def create_redaction(version_id: str, body: RedactionIn, request: Request,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    v, doc, _ = load_version(db, request, user, version_id, "document:redact")
    if v.detected_mime != "application/pdf" or v.processing_status != "READY":
        raise conflict("NOT_REDACTABLE", "Automatic redaction works on processed PDFs only")
    values = pipeline._victim_identifiers(doc.case) + [
        e.value for e in db.scalars(select(Entity).where(Entity.version_id == v.id))
        if e.type in pipeline.REDACTABLE or e.is_victim_identifier]
    red, spans = pipeline.redact_pdf(pipeline.decrypt_version(v), values)
    der = pipeline.store_derivative(db, v, "REDACTED", red, "application/pdf",
                                    {"redacted_spans": spans, "auto": True}, user.id)
    audit.record(db, ctx_for(request, user), "REDACTION_CREATED",
                 f"Created redacted copy of {doc.title} v{v.version_no} ({spans} spans)",
                 case_id=doc.case_id, document_id=doc.id, version_id=v.id,
                 details={"derivative_id": der.id, "spans": spans})
    return serial.derivative(der)


@router.post("/versions/{version_id}/review", status_code=201)
def submit_review(version_id: str, body: ReviewIn, request: Request,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    v, doc, _ = load_version(db, request, user, version_id, "document:review_submit")
    if v.review_status == "PENDING":
        raise conflict("ALREADY_PENDING", "This version is already awaiting review")
    v.review_status = "PENDING"
    r = Req(id=new_id(), type="REVIEW", case_id=doc.case_id, document_id=doc.id,
            version_id=v.id, requested_by=user.id, reason=body.note or "Please review",
            payload={"version_no": v.version_no, "note": body.note})
    db.add(r)
    audit.record(db, ctx_for(request, user), "REVIEW_SUBMITTED",
                 f"Submitted {doc.title} v{v.version_no} for review", case_id=doc.case_id,
                 document_id=doc.id, version_id=v.id, request_id=r.id)
    return serial.request(db, r, user)


# ───────────── certificates ─────────────

def _cert_pdf_url(db: Session, cert: Certificate) -> str | None:
    if not cert.pdf_derivative_id:
        return None
    der = db.get(Derivative, cert.pdf_derivative_id)
    token, _ = content.issue("DERIVATIVE", der.id, "application/pdf",
                             f"{cert.cert_number}.pdf", "inline")
    return f"/api/v1/content/{token}"


@router.get("/versions/{version_id}/certificates")
def list_certificates(version_id: str, request: Request, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    v, _, _ = load_version(db, request, user, version_id)
    rows = db.scalars(select(Certificate).where(Certificate.version_id == v.id)
                      .order_by(Certificate.issued_at.desc()))
    return [serial.certificate(c, config.PUBLIC_VERIFY_BASE, _cert_pdf_url(db, c)) for c in rows]


def issue_certificate(db: Session, ctx: audit.Ctx, v: DocumentVersion, doc: Document,
                      signatory_name: str, signatory_designation: str,
                      purpose: str | None) -> Certificate:
    case = doc.case
    year = utcnow().year
    n = db.scalar(select(func.count()).select_from(Certificate))
    custody = db.scalars(select(AuditEvent).where(AuditEvent.document_id == doc.id)
                         .order_by(AuditEvent.seq)).all()
    ist = v.uploaded_at + timedelta(hours=5, minutes=30)
    part_a = {
        "case_number": case.case_number, "fir": f"{case.fir_number} dated {case.fir_date:%d-%m-%Y}",
        "document": f"{doc.title} ({doc.doc_type.replace('_', ' ').title()})",
        "doc_number": doc.doc_number, "version_no": v.version_no,
        "file_name": v.original_filename, "mime": v.detected_mime, "size_bytes": v.size_bytes,
        "received_at": f"{ist:%d %b %Y, %H:%M} IST", "uploaded_by":
            f"{v.uploader.full_name}, {v.uploader.rank} ({v.uploader.service_id})",
        "system": "Case-File Vault — secure document management system, "
                  f"{case.unit.name}",
        "controls": "SHA-256 fingerprint at intake (browser and server), AES-256-GCM encryption, "
                    "write-once storage, Ed25519-signed manifest, hash-chained audit log",
        "custody_summary": f"{len(custody)} recorded events from upload to certification; "
                           f"full trail available on request",
        "purpose": purpose,
    }
    part_b = {"algorithm": "SHA-256", "hash": v.sha256}
    cert = Certificate(id=new_id(), cert_number=f"CFV-63-{year}-{n + 1:06d}", version_id=v.id,
                       verification_code="".join(secrets.choice(ALPHABET) for _ in range(12)),
                       sha256=v.sha256, part_a=part_a, part_b=part_b,
                       signatory_name=signatory_name, signatory_designation=signatory_designation,
                       purpose=purpose, issued_by=ctx.user.id, signature=b"",
                       signing_key_id=crypto.SIGNING_KEY_IDS["CERTIFICATE"])
    cert.version = v
    body = {"cert_number": cert.cert_number, "verification_code": cert.verification_code,
            "version_id": v.id, "sha256": v.sha256, "part_a": part_a}
    cert.signature, _ = crypto.sign("CERTIFICATE", body)
    url = f"{config.PUBLIC_VERIFY_BASE}/{cert.verification_code}"
    pdf = certpdf.render(cert, url, crypto.sha256_hex(cert.signature)[:24])
    der = pipeline.store_derivative(db, v, "CERTIFICATE_PDF", pdf, "application/pdf",
                                    {"cert_number": cert.cert_number}, ctx.user.id)
    cert.pdf_derivative_id = der.id
    db.add(cert)
    audit.record(db, ctx, "CERTIFICATE_ISSUED",
                 f"Issued §63 certificate {cert.cert_number} for {doc.title} v{v.version_no}",
                 case_id=doc.case_id, document_id=doc.id, version_id=v.id,
                 details={"cert_number": cert.cert_number, "sha256": v.sha256})
    return cert


@router.post("/versions/{version_id}/certificates", status_code=201)
def create_certificate(version_id: str, body: CertificateIn, request: Request,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    v, doc, _ = load_version(db, request, user, version_id, "certificate:issue")
    if v.processing_status != "READY":
        raise conflict("NOT_READY", "Only processed versions can be certified")
    cert = issue_certificate(db, ctx_for(request, user), v, doc, body.signatory_name,
                             body.signatory_designation, body.purpose)
    return serial.certificate(cert, config.PUBLIC_VERIFY_BASE, _cert_pdf_url(db, cert))


@router.get("/certificates/{cert_id}")
def get_certificate(cert_id: str, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    cert = db.get(Certificate, cert_id)
    if not cert:
        raise not_found("Certificate")
    load_version(db, request, user, cert.version_id)
    return serial.certificate(cert, config.PUBLIC_VERIFY_BASE, _cert_pdf_url(db, cert))


@router.post("/certificates/{cert_id}/revoke")
def revoke_certificate(cert_id: str, body: ReasonIn, request: Request,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    cert = db.get(Certificate, cert_id)
    if not cert:
        raise not_found("Certificate")
    v, doc, _ = load_version(db, request, user, cert.version_id, "certificate:issue")
    if cert.status == "REVOKED":
        raise conflict("ALREADY_REVOKED", "Certificate already revoked")
    cert.status, cert.revoked_reason, cert.revoked_at = "REVOKED", body.reason, utcnow()
    audit.record(db, ctx_for(request, user), "CERTIFICATE_REVOKED",
                 f"Revoked certificate {cert.cert_number}", case_id=doc.case_id,
                 document_id=doc.id, version_id=v.id, details={"reason": body.reason})
    return serial.certificate(cert, config.PUBLIC_VERIFY_BASE, _cert_pdf_url(db, cert))
