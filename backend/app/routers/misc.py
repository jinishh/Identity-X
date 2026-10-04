import csv
import hashlib
import io
import re
import secrets
import time
from datetime import datetime, timedelta

import pyotp
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .. import audit, config, crypto, integrity, policy, serial
from ..db import get_db
from ..errors import ApiError, conflict, deny, not_found
from ..models import (Alert, AuditCheckpoint, AuditEvent, Case, CaseMember, Certificate, Document,
                      DocumentVersion, Request as Req, Share, Unit, User, new_id, utcnow)
from ..security import ctx_for, current_user, normalise_phone, totp_for
from .cases import page_args

router = APIRouter()


class ReasonIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str | None = Field(default=None, max_length=2000)


class NoteIn(BaseModel):
    note: str = Field(min_length=5, max_length=2000)


class PublicVerifyIn(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class TamperIn(BaseModel):
    scenario: str
    version_id: str | None = None
    seq: int | None = None


class UserCreateIn(BaseModel):
    service_id: str = Field(pattern=r"^[A-Z]{2}-[A-Z]{2,4}-[0-9]{3,6}$")
    full_name: str = Field(min_length=3)
    rank: str | None = None
    role: str
    unit_id: str
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str


class UnitCreateIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z]{2}-[A-Z]{2,4}(-[A-Z0-9]{2,5})?$")
    name: str = Field(min_length=3)
    type: str
    parent_id: str


class UserUpdateIn(BaseModel):
    full_name: str | None = None
    rank: str | None = None
    role: str | None = None
    unit_id: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None


def require_role(db: Session, request: Request, user: User, *roles: str):
    if user.role not in roles:
        raise deny(db, ctx_for(request, user), "ROLE_NOT_PERMITTED",
                   f"Denied {request.method} {request.url.path}")


# ───────────── system ─────────────

@router.get("/health", tags=["System"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "demo_mode": config.DEMO_MODE,
            "components": {"database": "ok", "object_store": "ok", "queue": "disabled",
                           "malware_scanner": "degraded"}}


# ───────────── dashboard ─────────────

def _count(db, stmt) -> int:
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


@router.get("/dashboard/summary", tags=["Dashboard"])
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = utcnow()
    visible = policy.visible_case_ids_query(db, user)
    my_cases_q = select(Case).where(Case.id.in_(select(CaseMember.case_id).where(
        CaseMember.user_id == user.id, CaseMember.removed_at.is_(None))))
    if user.role == "SUPERVISOR":
        my_cases_q = select(Case).where(Case.id.in_(visible))
    my_cases = db.scalars(my_cases_q.where(Case.status != "CLOSED")
                          .order_by(Case.updated_at.desc()).limit(6)).all()

    ready = select(DocumentVersion).where(DocumentVersion.processing_status == "READY")
    if user.role != "AUDITOR":
        ready = ready.join(Document, Document.id == DocumentVersion.document_id).where(
            Document.case_id.in_(visible))
    encrypted = _count(db, ready)
    verified = _count(db, ready.where(DocumentVersion.last_verification == "VERIFIED"))
    pending_requests = [r for r in db.scalars(select(Req).where(Req.status == "PENDING"))
                        if policy.can_decide(db, user, r)]
    alerts_q = select(Alert).where(Alert.status != "RESOLVED")
    if user.role == "SUPERVISOR":
        alerts_q = alerts_q.where(or_(Alert.case_id.in_(visible), Alert.case_id.is_(None)))
    open_alerts = _count(db, alerts_q)

    def k(key, label, value, tone="neutral", hint=None, href=None):
        if not value and tone in ("good", "warn"):
            tone = "neutral"  # nothing to celebrate or worry about
        return {"key": key, "label": label, "value": value, "tone": tone, "hint": hint, "href": href}

    role = user.role
    if role == "INVESTIGATOR":
        week = now - timedelta(days=7)
        kpis = [
            k("my_open_cases", "My open cases", _count(db, my_cases_q.where(Case.status != "CLOSED")),
              href="/cases?mine=true"),
            k("uploads_week", "Uploaded this week", _count(db, select(DocumentVersion).where(
                DocumentVersion.uploaded_by == user.id, DocumentVersion.uploaded_at >= week)),
              tone="good"),
            k("pending_action", "Pending my action", len(pending_requests),
              tone="warn" if pending_requests else "neutral", href="/inbox"),
            k("in_custody", "Documents in my custody", _count(db, select(Document).where(
                Document.custodian_id == user.id, Document.status == "ACTIVE"))),
        ]
    elif role == "SUPERVISOR":
        kpis = [
            k("jurisdiction_cases", "Cases in jurisdiction", _count(db, select(Case).where(
                Case.id.in_(visible), Case.status != "CLOSED")), href="/cases"),
            k("approvals", "Approvals waiting", len(pending_requests),
              tone="warn" if pending_requests else "neutral", href="/inbox"),
            k("open_alerts", "Open security alerts", open_alerts,
              tone="bad" if open_alerts else "good", href="/alerts"),
            k("verified", "Verified integrity", verified, tone="good",
              hint=f"of {encrypted} encrypted files"),
        ]
    elif role == "PROSECUTOR":
        soon = now.date() + timedelta(days=14)
        kpis = [
            k("trial_cases", "Cases under trial", _count(db, my_cases_q.where(
                Case.status == "UNDER_TRIAL"))),
            k("hearings", "Hearings in 14 days", _count(db, my_cases_q.where(
                Case.next_hearing_date >= now.date(), Case.next_hearing_date <= soon)),
              tone="warn"),
            k("shared", "Shared with me", _count(db, select(Share).where(
                Share.grantee_user_id == user.id, Share.revoked_at.is_(None),
                Share.expires_at > now)), href="/shared"),
            k("pending_action", "Pending my action", len(pending_requests), href="/inbox"),
        ]
    elif role == "FORENSIC_EXPERT":
        kpis = [
            k("in_custody", "Exhibits in my custody", _count(db, select(Document).where(
                Document.custodian_id == user.id, Document.status == "ACTIVE"))),
            k("transfers", "Transfers to accept", len(pending_requests),
              tone="warn" if pending_requests else "neutral", href="/inbox"),
            k("reports", "Reports submitted", _count(db, select(DocumentVersion).where(
                DocumentVersion.uploaded_by == user.id))),
            k("cases", "Assigned cases", _count(db, my_cases_q)),
        ]
    else:  # AUDITOR / ADMIN — the slide-2 metrics
        all_pending = _count(db, select(Req).where(Req.status == "PENDING"))
        kpis = [
            k("encrypted_files", "Encrypted files", encrypted),
            k("verified_integrity", "Verified integrity", verified, tone="good",
              hint=f"{(verified * 100 // encrypted) if encrypted else 0}% of files"),
            k("pending_actions", "Pending actions", all_pending, tone="warn"),
            k("security_alerts", "Security alerts", open_alerts,
              tone="bad" if open_alerts else "good", href="/alerts"),
        ]

    recent_q = select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(8)
    if role not in policy.NO_CONTENT_ROLES:
        recent_q = recent_q.where(AuditEvent.case_id.in_(visible))
    doc_scope = select(Document).where(Document.status == "ACTIVE")
    if role not in policy.NO_CONTENT_ROLES:
        doc_scope = doc_scope.where(Document.case_id.in_(visible))
    ds = doc_scope.subquery()
    by_type = db.execute(select(ds.c.doc_type, func.count()).group_by(ds.c.doc_type)).all()
    case_scope = select(Case) if role in policy.NO_CONTENT_ROLES else select(Case).where(Case.id.in_(visible))
    cs = case_scope.subquery()
    by_status = db.execute(select(cs.c.status, func.count()).group_by(cs.c.status)).all()
    last_check = db.scalar(select(AuditEvent).where(AuditEvent.action.in_(
        ["CHAIN_VERIFIED", "CHAIN_BROKEN"])).order_by(AuditEvent.seq.desc()))
    return {
        "role": role, "kpis": kpis,
        "my_cases": [serial.case_summary(db, c, policy.capacities(db, user, c)) for c in my_cases],
        "recent_activity": serial.audit_events(db, db.scalars(recent_q).all()),
        "documents_by_type": [{"key": t, "count": n} for t, n in sorted(by_type, key=lambda r: -r[1])],
        "cases_by_status": [{"key": s, "count": n} for s, n in by_status],
        "integrity": {"versions_total": encrypted, "versions_verified": verified,
                      "last_chain_check": {"at": audit.iso(last_check.occurred_at),
                                           "status": "VALID" if last_check.action == "CHAIN_VERIFIED" else "BROKEN",
                                           "events_checked": (last_check.details or {}).get("events_checked", 0)}
                      if last_check else None},
    }


# ───────────── directory / admin ─────────────

@router.get("/units", tags=["Directory"])
def units(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": u.id, "code": u.code, "name": u.name, "type": u.type, "parent_id": u.parent_id,
             "district": u.district, "state": u.state}
            for u in db.scalars(select(Unit).order_by(Unit.code))]


@router.post("/units", status_code=201, tags=["Directory"])
def create_unit(body: UnitCreateIn, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    require_role(db, request, user, "SUPER_ADMIN")
    if body.type not in ("DISTRICT_HQ", "POLICE_STATION", "FSL", "PROSECUTION_OFFICE", "NCRB_CELL"):
        raise ApiError(422, "BAD_UNIT_TYPE", "Unknown unit type")
    parent = db.get(Unit, body.parent_id)
    if not parent:
        raise not_found("Parent unit")
    if db.scalar(select(Unit.id).where(Unit.code == body.code)):
        raise conflict("DUPLICATE_UNIT", f"{body.code} already exists")
    u = Unit(id=new_id(), code=body.code, name=body.name, type=body.type, parent_id=parent.id,
             district=parent.district, state=parent.state)
    db.add(u)
    audit.record(db, ctx_for(request, user), "UNIT_CREATED", f"Created unit {u.name} ({u.code})",
                 details={"type": u.type, "parent": parent.code})
    return {"id": u.id, "code": u.code, "name": u.name, "type": u.type, "parent_id": u.parent_id,
            "district": u.district, "state": u.state}


@router.get("/roles", tags=["Directory"])
def roles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..models import Role, RolePermission
    perms: dict[str, list[str]] = {}
    for rp in db.scalars(select(RolePermission)):
        perms.setdefault(rp.role_code, []).append(rp.permission_code)
    return [{"code": r.code, "title": r.title, "description": r.description, "tier": r.tier,
             "is_administrative": r.is_administrative, "sees_case_content": r.sees_case_content,
             "permissions": sorted(perms.get(r.code, []))}
            for r in db.scalars(select(Role).order_by(Role.tier, Role.code))]


@router.get("/directory", tags=["Directory"])
def directory(q: str, role: str | None = None, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    like = f"%{q.strip()}%"
    stmt = select(User).where(User.status == "ACTIVE", User.role.notin_(list(policy.NO_CONTENT_ROLES)),
                              or_(User.full_name.ilike(like), User.service_id.ilike(like)))
    if role:
        stmt = stmt.where(User.role == role)
    return [serial.user_summary(u) for u in db.scalars(stmt.order_by(User.full_name).limit(15))]


def _manageable(db: Session, actor: User):
    """Units whose accounts this administrator may manage (None = all)."""
    if actor.role == "SUPER_ADMIN":
        return None
    return policy.jurisdiction_unit_ids(db, actor)


def _may_manage(db: Session, request: Request, actor: User, target: User | None = None,
                role: str | None = None, unit_id: str | None = None):
    require_role(db, request, actor, "SUPER_ADMIN", "ADMIN")
    units_ok = _manageable(db, actor)
    checks = []
    if target is not None:
        checks.append(units_ok is None or target.unit_id in units_ok)
        checks.append(actor.role == "SUPER_ADMIN" or target.role not in policy.ADMIN_ROLES)
        checks.append(target.role != "SUPER_ADMIN" or target.id == actor.id)
    if role is not None:
        checks.append(role != "SUPER_ADMIN")
        checks.append(actor.role == "SUPER_ADMIN" or role not in policy.ADMIN_ROLES)
    if unit_id is not None:
        checks.append(units_ok is None or unit_id in units_ok)
    if not all(checks):
        raise deny(db, ctx_for(request, actor), "ROLE_NOT_PERMITTED",
                   f"Denied managing account {target.service_id if target else role or ''}".strip())


def _issue_activation(db: Session, actor: User, target: User) -> tuple[str, datetime]:
    from ..models import ActivationCode
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(alphabet) for _ in range(4)) + "-" + "".join(secrets.choice(alphabet) for _ in range(4))
    expires = utcnow() + timedelta(days=7)
    db.add(ActivationCode(user_id=target.id, code_hash=hashlib.sha256(code.encode()).hexdigest(),
                          issued_by=actor.id, expires_at=expires))
    return code, expires


def _with_face(db: Session, users: list[User]) -> list[dict]:
    from ..models import FaceTemplate
    enrolled = set(db.scalars(select(FaceTemplate.user_id).where(
        FaceTemplate.user_id.in_([u.id for u in users]), FaceTemplate.revoked_at.is_(None))))
    return [serial.user_full(u, face_enrolled=u.id in enrolled) for u in users]


@router.get("/users", tags=["Directory"])
def list_users(request: Request, page: int = 1, page_size: int = 100, q: str | None = None,
               role: str | None = None, status: str | None = None,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, request, user, "SUPER_ADMIN", "ADMIN")
    page, page_size = page_args(page, page_size)
    stmt = select(User)
    units_ok = _manageable(db, user)
    if units_ok is not None:
        stmt = stmt.where(User.unit_id.in_(units_ok))
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.service_id.ilike(f"%{q}%"),
                              User.email.ilike(f"%{q}%")))
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    total = _count(db, stmt)
    rows = db.scalars(stmt.order_by(User.service_id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": _with_face(db, rows), "total": total, "page": page, "page_size": page_size}


@router.post("/users", status_code=201, tags=["Directory"])
def create_user(body: UserCreateIn, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    _may_manage(db, request, user, role=body.role, unit_id=body.unit_id)
    phone = normalise_phone(body.phone)
    if not phone:
        raise ApiError(422, "BAD_PHONE", "Enter a 10-digit Indian mobile number")
    for col, val, label in ((User.service_id, body.service_id, "service ID"),
                            (func.lower(User.email), body.email.lower(), "email"), (User.phone, phone, "mobile number")):
        if db.scalar(select(User.id).where(col == val)):
            raise conflict("DUPLICATE_ACCOUNT", f"That {label} is already registered")
    u = User(id=new_id(), service_id=body.service_id, full_name=body.full_name, rank=body.rank,
             role=body.role, unit_id=body.unit_id, email=body.email.lower(), phone=phone,
             status="INVITED", created_by=user.id)
    db.add(u)
    db.flush()
    code, expires = _issue_activation(db, user, u)
    audit.record(db, ctx_for(request, user), "USER_CREATED",
                 f"Created {u.service_id} ({u.role}) — invited, activation code issued", target_user_id=u.id)
    db.refresh(u)
    return {"user": serial.user_full(u, face_enrolled=False), "activation_code": code,
            "activation_expires_at": audit.iso(expires)}


@router.get("/users/{user_id}", tags=["Directory"])
def get_user(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise not_found("User")
    return serial.user_full(u)


@router.patch("/users/{user_id}", tags=["Directory"])
def update_user(user_id: str, body: UserUpdateIn, request: Request,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise not_found("User")
    changes = body.model_dump(exclude_unset=True)
    _may_manage(db, request, user, target=u, role=changes.get("role"), unit_id=changes.get("unit_id"))
    if u.id == user.id and ("role" in changes or changes.get("status") in ("DISABLED", "LOCKED")):
        raise deny(db, ctx_for(request, user), "SELF_APPROVAL", "Denied changing own role or status")
    if "phone" in changes:
        changes["phone"] = normalise_phone(changes["phone"]) or u.phone
    for key, val in changes.items():
        setattr(u, key, val)
    if changes.get("status") == "ACTIVE":
        u.failed_logins, u.locked_until = 0, None
    action = "USER_DISABLED" if changes.get("status") == "DISABLED" else "USER_UPDATED"
    audit.record(db, ctx_for(request, user), action, f"Updated {u.service_id}",
                 target_user_id=u.id, details={"fields": sorted(changes)})
    return serial.user_full(u)


@router.post("/users/{user_id}/reset-access", tags=["Directory"])
def reset_access(user_id: str, request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """Lost phone / forgotten password: back to INVITED with a fresh activation code."""
    from ..models import FaceTemplate, Session as Sess
    u = db.get(User, user_id)
    if not u:
        raise not_found("User")
    _may_manage(db, request, user, target=u)
    if u.id == user.id:
        raise deny(db, ctx_for(request, user), "SELF_APPROVAL", "Denied resetting own access")
    u.status, u.password_hash, u.failed_logins, u.locked_until = "INVITED", None, 0, None
    if u.totp:
        u.totp.confirmed_at = None
    now = utcnow()
    for t in db.scalars(select(FaceTemplate).where(FaceTemplate.user_id == u.id, FaceTemplate.revoked_at.is_(None))):
        t.revoked_at = now
    for s_ in db.scalars(select(Sess).where(Sess.user_id == u.id, Sess.revoked_at.is_(None))):
        s_.revoked_at = now
    code, expires = _issue_activation(db, user, u)
    audit.record(db, ctx_for(request, user), "USER_MFA_RESET",
                 f"Reset sign-in for {u.service_id}: sessions ended, face removed, new activation code",
                 target_user_id=u.id)
    return {"user": serial.user_full(u, face_enrolled=False), "activation_code": code,
            "activation_expires_at": audit.iso(expires)}


# ───────────── requests / shares ─────────────

@router.get("/requests", tags=["Collaboration"])
def list_requests(box: str, page: int = 1, page_size: int = 50, status: str | None = None,
                  type: str | None = None, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    page, page_size = page_args(page, page_size)
    stmt = select(Req)
    if status:
        stmt = stmt.where(Req.status == status)
    if type:
        stmt = stmt.where(Req.type == type)
    if box == "outbox":
        rows = db.scalars(stmt.where(Req.requested_by == user.id)
                          .order_by(Req.created_at.desc())).all()
    else:
        candidates = db.scalars(stmt.where(Req.requested_by != user.id)
                                .order_by(Req.created_at.desc())).all()
        rows = []
        for r in candidates:
            caps = policy.capacities(db, user, r.case)
            if r.assigned_to == user.id or (r.assigned_to is None and r.type != "CUSTODY_TRANSFER"
                                            and caps & {"SUPERVISOR", "PROSECUTOR"}
                                            and (r.type != "SHARE" or "SUPERVISOR" in caps)
                                            and (r.type != "REVIEW" or "SUPERVISOR" in caps)):
                rows.append(r)
    total = len(rows)
    rows = rows[(page - 1) * page_size: page * page_size]
    return {"items": [serial.request(db, r, user) for r in rows], "total": total, "page": page,
            "page_size": page_size}


@router.get("/requests/{request_id}", tags=["Collaboration"])
def get_request(request_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(Req, request_id)
    if not r:
        raise not_found("Request")
    return serial.request(db, r, user)


@router.post("/requests/{request_id}/decision", tags=["Collaboration"])
def decide(request_id: str, body: DecisionIn, request: Request,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(Req, request_id)
    if not r:
        raise not_found("Request")
    ctx = ctx_for(request, user)
    if r.status != "PENDING":
        raise conflict("ALREADY_DECIDED", f"Request is {r.status.lower()}")
    if r.requested_by == user.id:
        raise deny(db, ctx, "SELF_APPROVAL", "Denied deciding own request", case_id=r.case_id,
                   document_id=r.document_id)
    if not policy.can_decide(db, user, r):
        raise deny(db, ctx, "ACTION_NOT_PERMITTED", "Denied request decision",
                   case_id=r.case_id, document_id=r.document_id)
    if body.decision == "REJECT" and not (body.note or "").strip():
        raise ApiError(422, "NOTE_REQUIRED", "Give a reason for rejecting")
    r.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    r.decided_by, r.decided_at, r.decision_note = user.id, utcnow(), body.note
    doc = r.document
    audit.record(db, ctx, f"REQUEST_{r.status}",
                 f"{r.status.title()} {r.type.replace('_', ' ').lower()} request"
                 f"{' for ' + doc.doc_number if doc else ''}", case_id=r.case_id,
                 document_id=r.document_id, request_id=r.id, details={"note": body.note})
    if r.status == "APPROVED":
        p = r.payload or {}
        if r.type == "SHARE":
            from datetime import datetime
            s = Share(id=new_id(), document_id=doc.id, grantee_user_id=p["grantee_user_id"],
                      scope=p["scope"], expires_at=datetime.fromisoformat(p["expires_at"].rstrip("Z")),
                      request_id=r.id, created_by=r.requested_by, approved_by=user.id)
            db.add(s)
            grantee = db.get(User, p["grantee_user_id"])
            audit.record(db, ctx, "SHARE_GRANTED",
                         f"Shared {doc.doc_number} with {grantee.full_name} ({p['scope']}) until "
                         f"{p['expires_at'][:10]}", case_id=r.case_id, document_id=doc.id,
                         request_id=r.id, target_user_id=grantee.id)
        elif r.type == "CUSTODY_TRANSFER":
            old = doc.custodian
            doc.custodian_id = user.id
            audit.record(db, ctx, "CUSTODY_TRANSFERRED",
                         f"Custody of {doc.doc_number}: {old.full_name} → {user.full_name}",
                         case_id=r.case_id, document_id=doc.id, request_id=r.id,
                         target_user_id=old.id, details={"from": old.service_id,
                                                         "to": user.service_id})
        elif r.type == "REVIEW":
            v = db.get(DocumentVersion, r.version_id)
            v.review_status = "APPROVED"
            audit.record(db, ctx, "REVIEW_APPROVED", f"Approved {doc.title} v{v.version_no}",
                         case_id=r.case_id, document_id=doc.id, version_id=v.id, request_id=r.id)
        elif r.type == "LEGAL_HOLD_RELEASE":
            doc.retention_state = "ACTIVE"
            audit.record(db, ctx, "LEGAL_HOLD_RELEASED", f"Released legal hold on {doc.doc_number}",
                         case_id=r.case_id, document_id=doc.id, request_id=r.id)
    elif r.type == "REVIEW":
        v = db.get(DocumentVersion, r.version_id)
        v.review_status = "RETURNED"
        audit.record(db, ctx, "REVIEW_RETURNED", f"Returned {doc.title} v{v.version_no}",
                     case_id=r.case_id, document_id=doc.id, version_id=v.id, request_id=r.id,
                     details={"note": body.note})
    return serial.request(db, r, user)


@router.post("/requests/{request_id}/cancel", tags=["Collaboration"])
def cancel(request_id: str, request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    r = db.get(Req, request_id)
    if not r:
        raise not_found("Request")
    if r.requested_by != user.id:
        raise deny(db, ctx_for(request, user), "ACTION_NOT_PERMITTED", "Denied cancelling request",
                   case_id=r.case_id)
    if r.status != "PENDING":
        raise conflict("ALREADY_DECIDED", f"Request is {r.status.lower()}")
    r.status = "CANCELLED"
    audit.record(db, ctx_for(request, user), "REQUEST_CANCELLED", "Cancelled request",
                 case_id=r.case_id, document_id=r.document_id, request_id=r.id)
    return serial.request(db, r, user)


@router.post("/shares/{share_id}/revoke", tags=["Collaboration"])
def revoke_share(share_id: str, body: ReasonIn, request: Request,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(Share, share_id)
    if not s:
        raise not_found("Share")
    caps = policy.capacities(db, user, s.document.case)
    if not (caps & {"LEAD_IO", "SUPERVISOR"} or s.created_by == user.id):
        raise deny(db, ctx_for(request, user), "ACTION_NOT_PERMITTED", "Denied revoking share",
                   case_id=s.document.case_id, document_id=s.document_id)
    s.revoked_at, s.revoked_by, s.revoke_reason = utcnow(), user.id, body.reason
    audit.record(db, ctx_for(request, user), "SHARE_REVOKED",
                 f"Revoked share of {s.document.doc_number} with {s.grantee.full_name}",
                 case_id=s.document.case_id, document_id=s.document_id,
                 target_user_id=s.grantee_user_id, details={"reason": body.reason})
    return serial.share(s)


@router.get("/shared-with-me", tags=["Collaboration"])
def shared_with_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Share).where(Share.grantee_user_id == user.id,
                                          Share.revoked_at.is_(None), Share.expires_at > utcnow())
                      .order_by(Share.expires_at))
    return [serial.share(s) for s in rows]


# ───────────── search ─────────────

# Keyword: Postgres full-text (websearch syntax, GIN index on a generated tsvector).
# Fuzzy: trigram word-similarity (pg_trgm), so "vehical" still finds "vehicle".
KEYWORD_SQL = """
SELECT document_id, version_id, page_no, redacted,
       ts_headline('simple', body, q, 'StartSel=[[, StopSel=]], MaxWords=26, MinWords=12, MaxFragments=1') AS snip,
       ts_rank_cd(tsv, q) AS score
FROM docs.text_index, websearch_to_tsquery('simple', :q) AS q
WHERE tsv @@ q
ORDER BY score DESC LIMIT 300"""

FUZZY_SQL = """
SELECT document_id, version_id, page_no, redacted,
       ts_headline('simple', body, to_tsquery('simple', :tsq), 'StartSel=[[, StopSel=]], MaxWords=26, MinWords=12, MaxFragments=1') AS snip,
       word_similarity(:q, body) AS score
FROM docs.text_index
WHERE :q <% body
ORDER BY score DESC LIMIT 300"""


@router.get("/search", tags=["Search"])
def search(request: Request, q: str, mode: str = "keyword", case_id: str | None = None,
           doc_type: str | None = None, page: int = 1, page_size: int = 20,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    started = time.perf_counter()
    page, page_size = page_args(page, page_size)
    if mode == "semantic":
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "mode": mode,
                "took_ms": 0}
    hits: dict[str, dict] = {}
    access_cache: dict[str, policy.Access] = {}

    def access(doc: Document) -> policy.Access:
        if doc.id not in access_cache:
            access_cache[doc.id] = policy.document_access(db, user, doc)
        return access_cache[doc.id]

    terms = re.findall(r"[\w\u0900-\u097F]+", q.lower())
    if mode == "fuzzy":
        rows = db.execute(text(FUZZY_SQL), {"q": q, "tsq": " | ".join(f"{t}:*" for t in terms) or "''"}).all()
    else:
        rows = db.execute(text(KEYWORD_SQL), {"q": q}).all()
    for doc_id, version_id, page_no, redacted, snip, score in rows:
        doc_id, version_id = str(doc_id), str(version_id)  # raw SQL returns UUID objects
        doc = db.get(Document, doc_id)
        if not doc or doc.status != "ACTIVE" or version_id != doc.current_version_id:
            continue
        if (case_id and doc.case_id != case_id) or (doc_type and doc.doc_type != doc_type):
            continue
        acc = access(doc)
        want_redacted = acc.view == "REDACTED"
        if acc.view == "NONE" or bool(redacted) != want_redacted:
            continue
        if doc.id in hits:
            continue
        plain, highlights, pos = "", [], 0
        for part in re.split(r"(\[\[.*?\]\])", snip.replace("\n", " ")):
            if part.startswith("[[") and part.endswith("]]"):
                word = part[2:-2]
                highlights.append({"start": len(plain), "end": len(plain) + len(word)})
                plain += word
            else:
                plain += part
        hits[doc.id] = {"document": serial.document_summary(db, doc), "version_id": version_id,
                        "page_no": int(page_no), "snippet": "…" + plain.strip() + "…", "highlights": [
                            {"start": h["start"] + 1, "end": h["end"] + 1} for h in highlights],
                        "redacted": bool(redacted), "score": round(float(score), 3),
                        "match_type": "FUZZY" if mode == "fuzzy" else "KEYWORD"}

    like = f"%{q.strip()}%"
    meta = db.scalars(select(Document).join(Case).where(
        Document.status == "ACTIVE",
        or_(Document.title.ilike(like), Document.doc_number.ilike(like),
            Case.case_number.ilike(like))).limit(100)).all()
    for doc in meta:
        if doc.id in hits or (case_id and doc.case_id != case_id) or (doc_type and doc.doc_type != doc_type):
            continue
        acc = access(doc)
        if not (acc.caps or acc.via or user.role == "AUDITOR"):
            continue
        hits[doc.id] = {"document": serial.document_summary(db, doc),
                        "version_id": doc.current_version_id, "page_no": None, "snippet": None,
                        "highlights": [], "redacted": False, "score": 0.5, "match_type": "METADATA"}

    items = sorted(hits.values(), key=lambda h: -h["score"])
    audit.record(db, ctx_for(request, user), "SEARCH_PERFORMED", f"Searched ({mode})",
                 details={"query_sha256": crypto.sha256_hex(q.encode()), "results": len(items)})
    return {"items": items[(page - 1) * page_size: page * page_size], "total": len(items),
            "page": page, "page_size": page_size, "mode": mode,
            "took_ms": int((time.perf_counter() - started) * 1000)}


# ───────────── audit ─────────────

def _audit_scope(db: Session, request: Request, user: User, case_id: str | None):
    if user.role == "AUDITOR":
        return None
    if user.role in ("SUPERVISOR", "INVESTIGATOR"):
        return policy.visible_case_ids_query(db, user)
    raise deny(db, ctx_for(request, user), "ROLE_NOT_PERMITTED", "Denied audit:read")


@router.get("/audit/events", tags=["Audit"])
def list_audit(request: Request, page: int = 1, page_size: int = 50, case_id: str | None = None,
               document_id: str | None = None, actor_user_id: str | None = None,
               action: str | None = None, outcome: str | None = None, order: str = "desc",
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    page, page_size = page_args(page, page_size)
    scope = _audit_scope(db, request, user, case_id)
    stmt = select(AuditEvent)
    if scope is not None:
        stmt = stmt.where(AuditEvent.case_id.in_(scope))
    for col, val in ((AuditEvent.case_id, case_id), (AuditEvent.document_id, document_id),
                     (AuditEvent.actor_user_id, actor_user_id), (AuditEvent.action, action),
                     (AuditEvent.outcome, outcome)):
        if val:
            stmt = stmt.where(col == val)
    total = _count(db, stmt)
    stmt = stmt.order_by(AuditEvent.seq.asc() if order == "asc" else AuditEvent.seq.desc())
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": serial.audit_events(db, rows), "total": total, "page": page,
            "page_size": page_size}


@router.get("/audit/head", tags=["Audit"])
def audit_head(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Latest link in the chain and the last sealed checkpoint — shown on every screen."""
    head = db.scalar(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1))
    cp = db.scalar(select(AuditCheckpoint).order_by(AuditCheckpoint.id.desc()).limit(1))
    return {"head_seq": head.seq if head else 0, "head_hash": head.event_hash if head else audit.GENESIS,
            "at": audit.iso(head.occurred_at) if head else None,
            "sealed_upto": cp.to_seq if cp else 0, "sealed_at": audit.iso(cp.created_at) if cp else None,
            "checkpoint_id": cp.id if cp else None}


@router.get("/audit/events/{seq}", tags=["Audit"])
def get_audit_event(seq: int, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    _audit_scope(db, request, user, None)
    ev = db.get(AuditEvent, seq)
    if not ev:
        raise not_found("Audit event")
    cp = db.scalar(select(AuditCheckpoint.id).where(AuditCheckpoint.from_seq <= seq,
                                                    AuditCheckpoint.to_seq >= seq))
    return {**serial.audit_event(db, ev), "canonical": crypto.jcs(audit.canonical(ev)).decode(),
            "ip": ev.ip, "user_agent": ev.user_agent, "checkpoint_id": cp}


@router.post("/audit/verify-chain", tags=["Audit"])
def verify_chain(request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    require_role(db, request, user, "AUDITOR")
    result = audit.verify_chain(db)
    ok = result["status"] == "VALID"
    if not ok:
        fb = result["first_break"]
        db.add(Alert(type="CHECKPOINT_MISMATCH" if fb["check"].startswith("CHECKPOINT") else "CHAIN_BROKEN",
                     severity="CRITICAL", title="Audit chain integrity failure",
                     message=f"First break at event #{fb['seq']}: {fb['check']}",
                     audit_seq=fb["seq"], actor_user_id=user.id))
    audit.record(db, ctx_for(request, user), "CHAIN_VERIFIED" if ok else "CHAIN_BROKEN",
                 f"Audit chain {'valid' if ok else 'BROKEN'} — {result['events_checked']} events, "
                 f"{result['checkpoints_checked']} checkpoints", outcome="SUCCESS" if ok else "FAILED",
                 details={"events_checked": result["events_checked"],
                          "first_break": result["first_break"]})
    return result


@router.get("/audit/checkpoints", tags=["Audit"])
def checkpoints(request: Request, page: int = 1, page_size: int = 50,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, request, user, "AUDITOR")
    page, page_size = page_args(page, page_size)
    stmt = select(AuditCheckpoint)
    total = _count(db, stmt)
    rows = db.scalars(stmt.order_by(AuditCheckpoint.id.desc())
                      .offset((page - 1) * page_size).limit(page_size))
    return {"items": [serial.checkpoint(c) for c in rows], "total": total, "page": page,
            "page_size": page_size}


@router.get("/audit/export", tags=["Audit"])
def export(request: Request, case_id: str | None = None, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    require_role(db, request, user, "AUDITOR")
    stmt = select(AuditEvent).order_by(AuditEvent.seq)
    if case_id:
        stmt = stmt.where(AuditEvent.case_id == case_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seq", "occurred_at", "actor_service_id", "actor_role", "action", "outcome",
                "reason_code", "case_id", "document_id", "purpose", "summary", "prev_hash",
                "event_hash"])
    for e in db.scalars(stmt):
        w.writerow([e.seq, audit.iso(e.occurred_at), e.actor_service_id, e.actor_role, e.action,
                    e.outcome, e.reason_code, e.case_id, e.document_id, e.purpose, e.summary,
                    e.prev_hash, e.event_hash])
    audit.record(db, ctx_for(request, user), "SEARCH_PERFORMED", "Exported audit log (CSV)",
                 case_id=case_id)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'})


# ───────────── alerts / break-glass ─────────────

@router.get("/alerts", tags=["Alerts"])
def list_alerts(request: Request, page: int = 1, page_size: int = 50, status: str | None = None,
                severity: str | None = None, type: str | None = None,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, request, user, "AUDITOR", "SUPERVISOR")
    page, page_size = page_args(page, page_size)
    stmt = select(Alert)
    if user.role == "SUPERVISOR":
        stmt = stmt.where(or_(Alert.case_id.in_(policy.visible_case_ids_query(db, user)),
                              Alert.case_id.is_(None)))
    for col, val in ((Alert.status, status), (Alert.severity, severity), (Alert.type, type)):
        if val:
            stmt = stmt.where(col == val)
    total = _count(db, stmt)
    sev = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    rows = sorted(db.scalars(stmt).all(),
                  key=lambda a: (a.status == "RESOLVED", sev.get(a.severity, 5), -a.created_at.timestamp()))
    rows = rows[(page - 1) * page_size: page * page_size]
    cases = {c.id: c.case_number for c in db.scalars(select(Case).where(
        Case.id.in_({a.case_id for a in rows if a.case_id})))}
    return {"items": [serial.alert(a, cases.get(a.case_id)) for a in rows], "total": total,
            "page": page, "page_size": page_size}


def _alert_action(db, request, user, alert_id) -> Alert:
    require_role(db, request, user, "AUDITOR", "SUPERVISOR")
    a = db.get(Alert, alert_id)
    if not a:
        raise not_found("Alert")
    return a


@router.post("/alerts/{alert_id}/acknowledge", tags=["Alerts"])
def ack(alert_id: str, request: Request, user: User = Depends(current_user),
        db: Session = Depends(get_db)):
    a = _alert_action(db, request, user, alert_id)
    if a.status == "OPEN":
        a.status, a.acknowledged_by, a.acknowledged_at = "ACKNOWLEDGED", user.id, utcnow()
        audit.record(db, ctx_for(request, user), "ALERT_ACKNOWLEDGED", f"Acknowledged: {a.title}",
                     case_id=a.case_id)
    return serial.alert(a)


@router.post("/alerts/{alert_id}/resolve", tags=["Alerts"])
def resolve(alert_id: str, body: NoteIn, request: Request, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    a = _alert_action(db, request, user, alert_id)
    a.status, a.resolved_by, a.resolved_at, a.resolution_note = "RESOLVED", user.id, utcnow(), body.note
    if not a.acknowledged_at:
        a.acknowledged_by, a.acknowledged_at = user.id, utcnow()
    audit.record(db, ctx_for(request, user), "ALERT_RESOLVED", f"Resolved: {a.title}",
                 case_id=a.case_id, details={"note": body.note})
    return serial.alert(a)


@router.get("/break-glass", tags=["Alerts"])
def break_glass_sessions(user: User = Depends(current_user)):
    return []


# ───────────── public ─────────────

def _cert_by_code(db: Session, code: str) -> Certificate:
    cert = db.scalar(select(Certificate).where(Certificate.verification_code == code.upper()))
    if not cert:
        raise not_found("Certificate")
    return cert


@router.get("/public/certificates/{code}", tags=["Public"])
def public_certificate(code: str, db: Session = Depends(get_db)):
    cert = _cert_by_code(db, code)
    v = cert.version
    m = v.manifest or {}
    return {"cert_number": cert.cert_number, "case_number": m.get("case_number"),
            "doc_type": m.get("doc_type"), "version_no": v.version_no, "sha256": cert.sha256,
            "size_bytes": v.size_bytes, "issued_at": audit.iso(cert.issued_at),
            "issuing_unit": cert.issuer.unit.name, "status": cert.status}


@router.post("/public/verify/{code}", tags=["Public"])
def public_verify(code: str, body: PublicVerifyIn, request: Request, db: Session = Depends(get_db)):
    cert = _cert_by_code(db, code)
    provided = body.sha256.lower()
    match = provided == cert.sha256
    v = cert.version
    doc = db.get(Document, v.document_id)
    if not match:
        db.add(Alert(type="INTEGRITY_FAILED", severity="MEDIUM",
                     title="Mismatched copy presented for verification",
                     message=f"A copy checked against {cert.cert_number} did not match "
                             f"({provided[:12]}… ≠ {cert.sha256[:12]}…).",
                     case_id=doc.case_id, document_id=doc.id))
    audit.record(db, ctx_for(request, None), "PUBLIC_VERIFICATION",
                 f"Public verification of {cert.cert_number}: {'MATCH' if match else 'MISMATCH'}",
                 outcome="SUCCESS" if match else "FAILED", case_id=doc.case_id,
                 document_id=doc.id, version_id=v.id,
                 details={"provided_sha256": provided, "result": "MATCH" if match else "MISMATCH"})
    return {"result": "MATCH" if match else "MISMATCH", "expected_sha256": cert.sha256,
            "provided_sha256": provided, "certificate_status": cert.status,
            "checked_at": audit.iso(utcnow())}


@router.get("/public/keys", tags=["Public"])
def public_keys():
    return [{"kid": kid, "purpose": purpose, "algorithm": "Ed25519",
             "public_key": crypto.b64(crypto.public_key_bytes(purpose)), "created_at": None,
             "retired_at": None} for purpose, kid in crypto.SIGNING_KEY_IDS.items()]


# ───────────── demo (DEMO_MODE only) ─────────────

def _demo_guard(db, request, user):
    if not config.DEMO_MODE:
        raise not_found("Endpoint")
    require_role(db, request, user, "SUPER_ADMIN")


@router.get("/demo/targets", tags=["Demo"])
def demo_targets(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Hero-case versions and suggested audit events to aim the tamper scenarios at."""
    _demo_guard(db, request, user)
    hero = db.scalar(select(Case).where(Case.case_number == "NV/SHN/0142/2026"))
    docs = db.scalars(select(Document).where(Document.case_id == hero.id, Document.status == "ACTIVE")
                      .order_by(Document.created_at)).all() if hero else []
    sealed_upto = db.scalar(select(func.max(AuditCheckpoint.to_seq))) or 0
    head = db.scalar(select(func.max(AuditEvent.seq))) or 0
    viewed = db.scalar(select(AuditEvent.seq).where(
        AuditEvent.action == "DOCUMENT_VIEWED", AuditEvent.purpose.is_not(None),
        AuditEvent.seq <= sealed_upto).order_by(AuditEvent.seq.desc()))
    return {"versions": [{"version_id": d.current_version_id, "title": d.title,
                          "doc_number": d.doc_number} for d in docs if d.current_version_id],
            "head_seq": head, "sealed_upto": sealed_upto, "suggested_seq": viewed or max(1, sealed_upto - 5)}


@router.post("/demo/tamper", tags=["Demo"])
def demo_tamper(body: TamperIn, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    _demo_guard(db, request, user)
    ctx = ctx_for(request, user)
    s = body.scenario
    if s in ("T2_OVERWRITE_STORED_OBJECT", "T5_REPLACE_CIPHERTEXT"):
        v = db.get(DocumentVersion, body.version_id or "")
        if not v or not v.storage_key:
            raise ApiError(422, "VERSION_REQUIRED", "Pick a processed version")
        audit.record(db, ctx, "DEMO_TAMPER_EXECUTED", f"Demo tamper {s}", version_id=v.id,
                     document_id=v.document_id, details={"scenario": s})
        result = (integrity.tamper_overwrite_object(v) if s.startswith("T2")
                  else integrity.tamper_replace_ciphertext(v))
    elif s in ("T3_EDIT_AUDIT_ROW", "T4_REWRITE_AUDIT_CHAIN"):
        if not body.seq:
            raise ApiError(422, "SEQ_REQUIRED", "Pick an audit event")
        audit.record(db, ctx, "DEMO_TAMPER_EXECUTED", f"Demo tamper {s}",
                     details={"scenario": s, "seq": body.seq})
        result = (integrity.tamper_edit_audit_row(db, body.seq) if s.startswith("T3")
                  else integrity.tamper_rewrite_chain(db, body.seq))
    else:
        raise ApiError(422, "UNKNOWN_SCENARIO", "Unknown scenario")
    return {"scenario": s, **result}


@router.post("/demo/reset", status_code=204, tags=["Demo"])
def demo_reset(request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    _demo_guard(db, request, user)
    db.close()
    from ..seed import reset_and_seed
    reset_and_seed()
