import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit, config, pipeline, policy, serial
from ..db import get_db
from ..errors import ApiError, conflict, deny, not_found
from ..models import AuditEvent, Case, CaseMember, Document, Unit, User, new_id, utcnow
from ..security import ctx_for, current_user

router = APIRouter(tags=["Cases"])

VICTIM_CATEGORIES = {"CRIME_AGAINST_WOMEN", "CRIME_AGAINST_CHILDREN"}


def page_args(page: int = 1, page_size: int = 20) -> tuple[int, int]:
    return max(page, 1), min(max(page_size, 1), 100)


def load_case(db: Session, request: Request, user: User, case_id: str,
              need: str = "case:read") -> tuple[Case, set[str]]:
    case = db.get(Case, case_id)
    if not case:
        raise not_found("Case")
    caps = policy.capacities(db, user, case)
    perms = policy.case_permissions(user, caps, case)
    if need not in perms:
        reason = "NOT_A_CASE_MEMBER" if not caps and user.role != "AUDITOR" else (
            "CASE_CLOSED" if case.status == "CLOSED" else "ACTION_NOT_PERMITTED")
        raise deny(db, ctx_for(request, user), reason,
                   f"Denied {need} on {case.case_number}", case_id=case.id)
    return case, caps


class CaseCreateIn(BaseModel):
    fir_number: str = Field(pattern=r"^[0-9]{1,5}/[0-9]{4}$")
    fir_date: date
    unit_id: str
    title: str = Field(min_length=5, max_length=200)
    category: str
    offence_sections: list[str] = Field(min_length=1)
    description: str | None = None
    lead_io_id: str | None = None


class CaseUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    offence_sections: list[str] | None = None
    description: str | None = None
    court_name: str | None = None
    next_hearing_date: date | None = None


class StatusIn(BaseModel):
    status: str
    note: str = Field(min_length=5, max_length=2000)


class MemberIn(BaseModel):
    user_id: str
    capacity: str
    expires_at: str | None = None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


@router.get("/cases")
def list_cases(request: Request, page: int = 1, page_size: int = 20, q: str | None = None,
               status: str | None = None, category: str | None = None, mine: bool = False,
               sort: str = "updated_desc", user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    page, page_size = page_args(page, page_size)
    stmt = select(Case).where(Case.id.in_(policy.visible_case_ids_query(db, user)))
    if mine:
        stmt = stmt.where(Case.id.in_(select(CaseMember.case_id).where(
            CaseMember.user_id == user.id, CaseMember.removed_at.is_(None))))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Case.case_number.ilike(like), Case.fir_number.ilike(like),
                              Case.title.ilike(like)))
    if status:
        stmt = stmt.where(Case.status == status)
    if category:
        stmt = stmt.where(Case.category == category)
    order = {"created_desc": Case.created_at.desc(), "fir_date_desc": Case.fir_date.desc(),
             "hearing_asc": Case.next_hearing_date.asc()}.get(sort, Case.updated_at.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [serial.case_summary(db, c, policy.capacities(db, user, c)) for c in rows],
            "total": total, "page": page, "page_size": page_size}


@router.post("/cases", status_code=201)
def create_case(body: CaseCreateIn, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    ctx = ctx_for(request, user)
    if user.role not in ("INVESTIGATOR", "SUPERVISOR"):
        raise deny(db, ctx, "ROLE_NOT_PERMITTED", "Denied case:create")
    unit = db.get(Unit, body.unit_id)
    if not unit or unit.type != "POLICE_STATION":
        raise ApiError(422, "BAD_UNIT", "Choose a police station")
    lead_id = user.id if user.role == "INVESTIGATOR" else body.lead_io_id
    lead = db.get(User, lead_id) if lead_id else None
    if not lead or lead.role != "INVESTIGATOR":
        raise ApiError(422, "LEAD_IO_REQUIRED", "Assign an investigator as lead IO")
    year = body.fir_number.split("/")[1]
    number = f"NV/{unit.code.split('-')[-1]}/{body.fir_number.split('/')[0].zfill(4)}/{year}"
    if db.scalar(select(Case.id).where(Case.case_number == number)):
        raise conflict("DUPLICATE_CASE", f"{number} already exists")
    victim = body.category in VICTIM_CATEGORIES
    case = Case(id=new_id(), case_number=number, fir_number=body.fir_number, fir_date=body.fir_date,
                unit_id=unit.id, title=body.title, category=body.category,
                offence_sections=body.offence_sections, status="REGISTERED",
                is_victim_protected=victim, victim_pseudonym="V-1" if victim else None,
                default_sensitivity="VICTIM_PROTECTED" if victim else "CONFIDENTIAL",
                lead_io_id=lead.id, description=body.description, created_by=user.id)
    db.add(case)
    db.add(CaseMember(case_id=case.id, user_id=lead.id, capacity="LEAD_IO", added_by=user.id))
    audit.record(db, ctx, "CASE_CREATED", f"Registered {number}: {body.title}", case_id=case.id,
                 details={"category": body.category, "victim_protected": victim})
    return serial.case_full(db, case, user, policy.capacities(db, user, case))


@router.get("/cases/{case_id}")
def get_case(case_id: str, request: Request, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    case, caps = load_case(db, request, user, case_id)
    return serial.case_full(db, case, user, caps)


@router.patch("/cases/{case_id}")
def update_case(case_id: str, body: CaseUpdateIn, request: Request,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, caps = load_case(db, request, user, case_id, "case:update")
    changed = body.model_dump(exclude_unset=True)
    for k, v in changed.items():
        setattr(case, k, v)
    case.updated_at = utcnow()
    audit.record(db, ctx_for(request, user), "CASE_UPDATED", f"Updated {case.case_number}",
                 case_id=case.id, details={"fields": sorted(changed)})
    return serial.case_full(db, case, user, caps)


@router.post("/cases/{case_id}/status")
def change_status(case_id: str, body: StatusIn, request: Request,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, caps = load_case(db, request, user, case_id, "case:change_status")
    if body.status not in policy.CASE_TRANSITIONS.get(case.status, []):
        raise conflict("BAD_TRANSITION", f"{case.status} → {body.status} is not allowed")
    old = case.status
    case.status, case.updated_at = body.status, utcnow()
    if body.status == "CLOSED":
        case.closed_at = utcnow()
    audit.record(db, ctx_for(request, user), "CASE_STATUS_CHANGED",
                 f"{case.case_number}: {old} → {body.status}", case_id=case.id,
                 details={"from": old, "to": body.status, "note": body.note})
    return serial.case_full(db, case, user, caps)


@router.get("/cases/{case_id}/members")
def list_members(case_id: str, request: Request, include_removed: bool = False,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, _ = load_case(db, request, user, case_id)
    stmt = select(CaseMember).where(CaseMember.case_id == case.id)
    if not include_removed:
        stmt = stmt.where(CaseMember.removed_at.is_(None))
    rows = [serial.member(m) for m in db.scalars(stmt.order_by(CaseMember.added_at))]
    member_ids = {r["user"]["id"] for r in rows}
    for sup in db.scalars(select(User).where(User.role == "SUPERVISOR", User.status == "ACTIVE")):
        if sup.id not in member_ids and sup.unit_id in policy.unit_ancestors(db, case.unit_id):
            rows.append({"id": f"jurisdiction-{sup.id}", "user": serial.user_summary(sup),
                         "capacity": "SUPERVISOR", "implicit": True, "added_by": None,
                         "added_at": audit.iso(case.created_at), "expires_at": None,
                         "active": True, "removed_at": None, "removal_reason": None})
    return rows


@router.post("/cases/{case_id}/members", status_code=201)
def add_member(case_id: str, body: MemberIn, request: Request,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, caps = load_case(db, request, user, case_id, "case:manage_members")
    allowed_by_role = {"LEAD_IO": "INVESTIGATOR", "CO_IO": "INVESTIGATOR",
                       "SUPERVISOR": "SUPERVISOR", "PROSECUTOR": "PROSECUTOR",
                       "FORENSIC": "FORENSIC_EXPERT"}
    target = db.get(User, body.user_id)
    if not target or allowed_by_role.get(body.capacity) != target.role:
        raise ApiError(422, "BAD_CAPACITY", "That user cannot hold this capacity")
    if "SUPERVISOR" not in caps and body.capacity not in ("CO_IO", "FORENSIC"):
        raise deny(db, ctx_for(request, user), "ACTION_NOT_PERMITTED",
                   f"Denied adding {body.capacity} to {case.case_number}", case_id=case.id)
    if body.capacity == "LEAD_IO":
        raise conflict("LEAD_IO_EXISTS", "A case has exactly one lead IO")
    if db.scalar(select(CaseMember.id).where(CaseMember.case_id == case.id,
                                             CaseMember.user_id == target.id,
                                             CaseMember.removed_at.is_(None))):
        raise conflict("ALREADY_MEMBER", f"{target.full_name} is already on this case")
    m = CaseMember(id=new_id(), case_id=case.id, user_id=target.id, capacity=body.capacity,
                   added_by=user.id)
    db.add(m)
    audit.record(db, ctx_for(request, user), "CASE_MEMBER_ADDED",
                 f"Added {target.full_name} as {body.capacity}", case_id=case.id,
                 target_user_id=target.id, details={"capacity": body.capacity})
    db.refresh(m)
    return serial.member(m)


@router.post("/cases/{case_id}/members/{member_id}/remove", status_code=204)
def remove_member(case_id: str, member_id: str, body: ReasonIn, request: Request,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, _ = load_case(db, request, user, case_id, "case:manage_members")
    m = db.get(CaseMember, member_id)
    if not m or m.case_id != case.id or m.removed_at:
        raise not_found("Member")
    if m.capacity == "LEAD_IO":
        raise conflict("LEAD_IO_REQUIRED", "Reassign the lead IO before removing them")
    m.removed_at, m.removed_by, m.removal_reason = utcnow(), user.id, body.reason
    audit.record(db, ctx_for(request, user), "CASE_MEMBER_REMOVED",
                 f"Removed {m.user.full_name} ({m.capacity})", case_id=case.id,
                 target_user_id=m.user_id, details={"reason": body.reason})


@router.get("/cases/{case_id}/timeline")
def case_timeline(case_id: str, request: Request, page: int = 1, page_size: int = 50,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, _ = load_case(db, request, user, case_id)
    page, page_size = page_args(page, page_size)
    stmt = select(AuditEvent).where(AuditEvent.case_id == case.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditEvent.seq.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": serial.audit_events(db, rows), "total": total, "page": page,
            "page_size": page_size}


@router.post("/cases/{case_id}/break-glass")
def break_glass(case_id: str):
    raise ApiError(501, "NOT_IN_THIS_BUILD", "Break-glass access is on the roadmap")


@router.get("/cases/{case_id}/documents")
def list_documents(case_id: str, request: Request, page: int = 1, page_size: int = 50,
                   doc_type: str | None = None, sensitivity: str | None = None,
                   include_withdrawn: bool = False, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    case, _ = load_case(db, request, user, case_id)
    page, page_size = page_args(page, page_size)
    stmt = select(Document).where(Document.case_id == case.id)
    if not include_withdrawn:
        stmt = stmt.where(Document.status == "ACTIVE")
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if sensitivity:
        stmt = stmt.where(Document.sensitivity == sensitivity)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Document.created_at.asc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [serial.document_summary(db, x) for x in rows], "total": total,
            "page": page, "page_size": page_size}


def next_doc_number(db: Session) -> str:
    n = db.scalar(select(func.count()).select_from(Document)) + 1
    return f"DOC-{utcnow().year}-{n:06d}"


@router.post("/cases/{case_id}/documents", status_code=202)
async def upload_document(case_id: str, request: Request, file: UploadFile = File(...),
                          metadata: str = Form(...), user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    case, caps = load_case(db, request, user, case_id, "document:upload")
    try:
        meta = json.loads(metadata)
        title, doc_type, client_sha = meta["title"].strip(), meta["doc_type"], meta["client_sha256"]
    except (ValueError, KeyError, AttributeError):
        raise ApiError(422, "BAD_METADATA", "metadata must include title, doc_type, client_sha256")
    types = policy.allowed_upload_types(caps)
    if types is not None and doc_type not in types:
        raise deny(db, ctx_for(request, user), "ACTION_NOT_PERMITTED",
                   f"Denied uploading {doc_type} to {case.case_number}", case_id=case.id)
    sensitivity = meta.get("sensitivity") or case.default_sensitivity
    order = policy.SENSITIVITY_ORDER
    if sensitivity not in order:
        raise ApiError(422, "BAD_SENSITIVITY", "Unknown sensitivity")
    if order.index(sensitivity) < order.index(case.default_sensitivity):
        raise ApiError(422, "SENSITIVITY_TOO_LOW",
                       f"This case requires at least {case.default_sensitivity}")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    doc = Document(id=new_id(), doc_number=next_doc_number(db), case_id=case.id, title=title,
                   doc_type=doc_type, sensitivity=sensitivity, custodian_id=user.id,
                   created_by=user.id, tags=meta.get("tags") or [])
    v = pipeline.intake(db, ctx_for(request, user), doc, data, file.filename or "upload",
                        client_sha, None, is_new=True)
    case.updated_at = utcnow()
    db.commit()
    pipeline.start_background(v.id)
    return {"document_id": doc.id, "version_id": v.id, "version_no": v.version_no,
            "sha256": v.sha256, "processing_url": f"/api/v1/versions/{v.id}/processing"}
