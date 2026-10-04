"""DB rows → contract-shaped dicts (contracts/openapi.yaml components/schemas)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import crypto, policy
from .audit import iso
from .models import (Alert, AuditCheckpoint, AuditEvent, Case, CaseMember, Certificate, Derivative,
                     Document, DocumentVersion, Request, Share, User)


def d(x):
    return x.isoformat() if x else None


def mask_phone(p: str | None) -> str | None:
    return f"+91 ••••• ••{p[-3:]}" if p else None


def mask_email(e: str | None) -> str | None:
    if not e or "@" not in e:
        return e
    name, domain = e.split("@", 1)
    return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}"


def user_summary(u: User | None) -> dict | None:
    if not u:
        return None
    return {"id": u.id, "service_id": u.service_id, "full_name": u.full_name, "rank": u.rank,
            "role": u.role, "unit_name": u.unit.name if u.unit else ""}


def user_full(u: User, face_enrolled: bool | None = None) -> dict:
    return {**user_summary(u), "unit_id": u.unit_id, "email": u.email,
            "phone_masked": mask_phone(u.phone), "status": u.status,
            "mfa_enabled": u.mfa_enabled, "face_enrolled": face_enrolled,
            "role_title": u.role_ref.title if u.role_ref else u.role,
            "last_login_at": iso(u.last_login_at), "activated_at": iso(u.activated_at),
            "created_at": iso(u.created_at)}


def me(db: Session, u: User) -> dict:
    from .models import FaceTemplate, RolePermission
    perms = db.scalars(select(RolePermission.permission_code)
                       .where(RolePermission.role_code == u.role)).all()
    face = db.scalar(select(FaceTemplate.id).where(FaceTemplate.user_id == u.id,
                                                   FaceTemplate.revoked_at.is_(None)))
    return {**user_full(u, face_enrolled=bool(face)), "permissions": sorted(perms),
            "step_up_valid_until": iso(u.step_up_until)}


def case_summary(db: Session, c: Case, caps: set[str] | None = None) -> dict:
    doc_count = db.scalar(select(func.count()).select_from(Document).where(
        Document.case_id == c.id, Document.status == "ACTIVE"))
    my_cap = None
    if caps:
        order = ["LEAD_IO", "SUPERVISOR", "PROSECUTOR", "CO_IO", "FORENSIC"]
        my_cap = next((o for o in order if o in caps), None)
    return {"id": c.id, "case_number": c.case_number, "fir_number": c.fir_number,
            "fir_date": d(c.fir_date), "title": c.title, "category": c.category,
            "status": c.status, "is_victim_protected": c.is_victim_protected,
            "unit_name": c.unit.name, "lead_io": user_summary(c.lead_io),
            "document_count": doc_count, "next_hearing_date": d(c.next_hearing_date),
            "my_capacity": my_cap, "updated_at": iso(c.updated_at)}


def case_full(db: Session, c: Case, user: User, caps: set[str]) -> dict:
    return {**case_summary(db, c, caps), "unit_id": c.unit_id,
            "offence_sections": c.offence_sections, "victim_pseudonym": c.victim_pseudonym,
            "default_sensitivity": c.default_sensitivity, "court_name": c.court_name,
            "description": c.description, "created_by": user_summary(c.creator),
            "created_at": iso(c.created_at), "closed_at": iso(c.closed_at),
            "break_glass_until": None,
            "my_permissions": policy.case_permissions(user, caps, c)}


def member(m: CaseMember, implicit=False) -> dict:
    return {"id": m.id, "user": user_summary(m.user), "capacity": m.capacity,
            "implicit": implicit, "added_by": user_summary(m.adder), "added_at": iso(m.added_at),
            "expires_at": iso(m.expires_at), "active": m.removed_at is None,
            "removed_at": iso(m.removed_at), "removal_reason": m.removal_reason}


def version_summary(v: DocumentVersion | None) -> dict | None:
    if not v:
        return None
    return {"id": v.id, "version_no": v.version_no, "sha256": v.sha256,
            "size_bytes": v.size_bytes, "detected_mime": v.detected_mime,
            "page_count": v.page_count, "processing_status": v.processing_status,
            "uploaded_by": user_summary(v.uploader), "uploaded_at": iso(v.uploaded_at)}


def version_full(v: DocumentVersion) -> dict:
    return {**version_summary(v), "document_id": v.document_id,
            "parent_version_id": v.parent_version_id, "prev_version_sha256": v.prev_version_sha256,
            "change_note": v.change_note, "original_filename": v.original_filename,
            "scan_result": v.scan_result, "scan_detail": v.scan_detail,
            "ocr_status": v.ocr_status, "ocr_languages": None, "review_status": v.review_status,
            "manifest_sha256": v.manifest_sha256, "signing_key_id": v.signing_key_id,
            "object_lock": {"mode": "WRITE_ONCE" if v.storage_key else None,
                            "retain_until": iso(v.retain_until), "legal_hold": False},
            "last_verification": ({"at": iso(v.last_verified_at), "overall": v.last_verification}
                                  if v.last_verified_at else None)}


def document_summary(db: Session, doc: Document) -> dict:
    cur = db.get(DocumentVersion, doc.current_version_id) if doc.current_version_id else None
    if cur is None:  # still processing: show the newest version instead
        cur = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                        .order_by(DocumentVersion.version_no.desc()))
    count = db.scalar(select(func.count()).select_from(DocumentVersion).where(
        DocumentVersion.document_id == doc.id))
    return {"id": doc.id, "doc_number": doc.doc_number, "case_id": doc.case_id,
            "case_number": doc.case.case_number, "title": doc.title, "doc_type": doc.doc_type,
            "sensitivity": doc.sensitivity, "retention_state": doc.retention_state,
            "status": doc.status, "version_count": count, "current_version": version_summary(cur),
            "custodian": user_summary(doc.custodian), "tags": doc.tags or [],
            "updated_at": iso(doc.updated_at)}


def document_full(db: Session, doc: Document, access: policy.Access) -> dict:
    hold_by = db.get(User, doc.legal_hold_by) if doc.legal_hold_by else None
    wd_by = db.get(User, doc.withdrawn_by) if doc.withdrawn_by else None
    return {**document_summary(db, doc),
            "legal_hold": ({"reason": doc.legal_hold_reason, "by": user_summary(hold_by),
                            "at": iso(doc.legal_hold_at)} if doc.retention_state == "LEGAL_HOLD" else None),
            "withdrawn": ({"reason": doc.withdrawn_reason, "by": user_summary(wd_by),
                           "at": iso(doc.withdrawn_at)} if doc.status == "WITHDRAWN" else None),
            "created_by": user_summary(doc.creator), "created_at": iso(doc.created_at),
            "access": access.as_dict()}


def audit_event(db: Session, ev: AuditEvent, users: dict | None = None,
                cases: dict | None = None, docs: dict | None = None) -> dict:
    users = users if users is not None else {}
    actor = users.get(ev.actor_user_id) if ev.actor_user_id in users else (
        db.get(User, ev.actor_user_id) if ev.actor_user_id else None)
    target = db.get(User, ev.target_user_id) if ev.target_user_id else None
    case = (cases or {}).get(ev.case_id) or (db.get(Case, ev.case_id) if ev.case_id else None)
    doc = (docs or {}).get(ev.document_id) or (db.get(Document, ev.document_id) if ev.document_id else None)
    return {"seq": ev.seq, "id": ev.id, "occurred_at": iso(ev.occurred_at),
            "actor": user_summary(actor), "actor_role": ev.actor_role, "action": ev.action,
            "outcome": ev.outcome, "reason_code": ev.reason_code, "case_id": ev.case_id,
            "case_number": case.case_number if case else None, "document_id": ev.document_id,
            "document_title": doc.title if doc else None, "version_id": ev.version_id,
            "target_user": user_summary(target), "purpose": ev.purpose, "summary": ev.summary,
            "details": ev.details or {}, "prev_hash": ev.prev_hash, "event_hash": ev.event_hash}


def audit_events(db: Session, events: list[AuditEvent]) -> list[dict]:
    uids = {e.actor_user_id for e in events if e.actor_user_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(uids)))} if uids else {}
    cids = {e.case_id for e in events if e.case_id}
    cases = {c.id: c for c in db.scalars(select(Case).where(Case.id.in_(cids)))} if cids else {}
    dids = {e.document_id for e in events if e.document_id}
    docs = {x.id: x for x in db.scalars(select(Document).where(Document.id.in_(dids)))} if dids else {}
    return [audit_event(db, e, users, cases, docs) for e in events]


def checkpoint(cp: AuditCheckpoint) -> dict:
    return {"id": cp.id, "from_seq": cp.from_seq, "to_seq": cp.to_seq, "head_hash": cp.head_hash,
            "merkle_root": cp.merkle_root, "event_count": cp.event_count,
            "created_at": iso(cp.created_at), "signing_key_id": cp.signing_key_id,
            "signature": crypto.b64(cp.signature), "worm_object_key": cp.sealed_path,
            "anchor": None}


def alert(a: Alert, case_number: str | None = None) -> dict:
    return {"id": a.id, "type": a.type, "severity": a.severity, "title": a.title,
            "message": a.message, "case_id": a.case_id, "case_number": case_number,
            "document_id": a.document_id, "actor": user_summary(a.actor),
            "audit_seq": a.audit_seq, "status": a.status,
            "acknowledged_by": user_summary(a.acknowledger),
            "acknowledged_at": iso(a.acknowledged_at), "resolved_at": iso(a.resolved_at),
            "resolution_note": a.resolution_note, "created_at": iso(a.created_at)}


def share(s: Share) -> dict:
    from .models import utcnow
    return {"id": s.id, "document_id": s.document_id, "document_title": s.document.title,
            "case_number": s.document.case.case_number, "grantee": user_summary(s.grantee),
            "scope": s.scope, "expires_at": iso(s.expires_at), "created_by": user_summary(s.creator),
            "approved_by": user_summary(s.approver), "created_at": iso(s.created_at),
            "active": s.revoked_at is None and s.expires_at > utcnow(),
            "revoked_at": iso(s.revoked_at), "revoke_reason": s.revoke_reason}


def request(db: Session, r: Request, viewer: User) -> dict:
    payload = dict(r.payload or {})
    for key in ("grantee_user_id", "to_user_id", "from_user_id"):
        if key in payload:
            payload[key.replace("_user_id", "")] = user_summary(db.get(User, payload[key]))
    return {"id": r.id, "type": r.type, "status": r.status, "case_id": r.case_id,
            "case_number": r.case.case_number, "document_id": r.document_id,
            "document_title": r.document.title if r.document else None,
            "version_id": r.version_id, "requested_by": user_summary(r.requester),
            "assigned_to": user_summary(r.assignee), "payload": payload, "reason": r.reason,
            "decided_by": user_summary(r.decider), "decided_at": iso(r.decided_at),
            "decision_note": r.decision_note, "created_at": iso(r.created_at),
            "can_decide": policy.can_decide(db, viewer, r)}


def derivative(x: Derivative) -> dict:
    return {"id": x.id, "source_version_id": x.source_version_id, "kind": x.kind,
            "status": x.status, "sha256": x.sha256, "summary": x.summary or {},
            "created_by": user_summary(x.creator), "created_at": iso(x.created_at)}


def certificate(c: Certificate, verify_base: str, pdf_url: str | None = None) -> dict:
    v = c.version
    doc = v.manifest or {}
    return {"id": c.id, "cert_number": c.cert_number, "verification_code": c.verification_code,
            "verify_url": f"{verify_base}/{c.verification_code}", "version_id": c.version_id,
            "document_id": v.document_id, "doc_number": doc.get("doc_number"),
            "case_number": doc.get("case_number"), "sha256": c.sha256, "part_a": c.part_a,
            "part_b": c.part_b, "signatory_name": c.signatory_name,
            "signatory_designation": c.signatory_designation, "pdf_url": pdf_url,
            "status": c.status, "issued_by": user_summary(c.issuer), "issued_at": iso(c.issued_at),
            "revoked_at": iso(c.revoked_at), "revoked_reason": c.revoked_reason}
