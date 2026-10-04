"""The single place access is decided (docs/01-roles-permissions.md).

capacity on the case + system role + document sensitivity + action → allow / deny / obligations.
Routers never check roles themselves.
"""

from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from .models import Case, CaseMember, Document, Share, Unit, User, utcnow

KEY_CAPACITIES = {"LEAD_IO", "SUPERVISOR", "PROSECUTOR"}
LEGAL_TYPES = {"COURT_ORDER", "LEGAL_NOTICE", "JUDGMENT", "COURT_FILING"}
REVIEWABLE_TYPES = {"CHARGESHEET", "INVESTIGATION_REPORT"}
SENSITIVITY_ORDER = ["INTERNAL", "CONFIDENTIAL", "RESTRICTED", "VICTIM_PROTECTED"]
SHARE_MAX_DAYS = {"INTERNAL": 30, "CONFIDENTIAL": 14, "RESTRICTED": 7, "VICTIM_PROTECTED": 7}
SHARE_SCOPES_ALLOWED = {
    "INTERNAL": ["VIEW_REDACTED", "VIEW", "DOWNLOAD"],
    "CONFIDENTIAL": ["VIEW"],
    "RESTRICTED": ["VIEW"],
    "VICTIM_PROTECTED": ["VIEW_REDACTED"],
}

CASE_TRANSITIONS = {
    "REGISTERED": ["UNDER_INVESTIGATION"],
    "UNDER_INVESTIGATION": ["CHARGESHEET_FILED", "FINAL_REPORT_FILED"],
    "CHARGESHEET_FILED": ["UNDER_TRIAL"],
    "FINAL_REPORT_FILED": ["CLOSED"],
    "UNDER_TRIAL": ["DISPOSED"],
    "DISPOSED": ["CLOSED"],
    "CLOSED": [],
}

ADMIN_ROLES = {"SUPER_ADMIN", "ADMIN"}          # manage accounts; never case content
NO_CONTENT_ROLES = ADMIN_ROLES | {"AUDITOR"}    # may never open a document

# Seeded into iam.roles / iam.permissions / iam.role_permissions by app/seed.py.
ROLES = [  # code, title, tier, administrative, sees content, description
    ("SUPER_ADMIN", "Super Administrator", 1, True, False,
     "State-level. Creates administrators and units, sets security policy. Never sees case content."),
    ("ADMIN", "Administrator", 2, True, False,
     "District / unit level. Creates and manages officer accounts in their units. Never sees case content."),
    ("SUPERVISOR", "Supervising Officer", 3, False, True,
     "SHO / DSP. Oversees every case in their jurisdiction; approves shares, reviews and legal-hold release."),
    ("INVESTIGATOR", "Investigating Officer", 4, False, True,
     "SI / Inspector. Registers cases, uploads evidence, works the cases they are assigned to."),
    ("PROSECUTOR", "Public Prosecutor", 4, False, True,
     "Works assigned cases for trial; legal documents, legal hold."),
    ("FORENSIC_EXPERT", "Forensic Expert", 5, False, True,
     "FSL scientist. Sees only exhibits in their custody or assigned to them; files forensic reports."),
    ("AUDITOR", "Auditor", 5, False, False,
     "NCRB / vigilance audit cell. Reads the audit ledger, verifies integrity. Never sees document content."),
]

PERMISSIONS = {
    "case:create": "Register a new case (FIR)",
    "search": "Search documents the user is allowed to see",
    "request:decide": "Approve or reject requests addressed to them",
    "alert:read": "See and resolve security alerts",
    "audit:read_case": "Read the ledger for cases in their scope",
    "audit:read_all": "Read the whole audit ledger",
    "audit:verify_chain": "Run full ledger verification",
    "audit:export": "Export the ledger as CSV",
    "user:manage": "Create, disable and reset officer accounts in their units",
    "admin:manage": "Create and manage administrators",
    "unit:manage": "Create and change organisational units",
    "demo:tamper": "Run the tamper lab (demo mode only)",
}

SYSTEM_PERMISSIONS = {
    "SUPER_ADMIN": ["user:manage", "admin:manage", "unit:manage", "demo:tamper"],
    "INVESTIGATOR": ["case:create", "search"],
    "SUPERVISOR": ["case:create", "search", "request:decide", "alert:read", "audit:read_case"],
    "PROSECUTOR": ["search", "request:decide"],
    "FORENSIC_EXPERT": ["search", "request:decide"],
    "AUDITOR": ["search", "audit:read_all", "audit:verify_chain", "audit:export", "alert:read"],
    "ADMIN": ["user:manage"],
}


@lru_cache(maxsize=256)
def _ancestors(unit_id: str, units_snapshot: tuple) -> frozenset[str]:
    parents = dict(units_snapshot)
    chain, cur = set(), unit_id
    while cur:
        chain.add(cur)
        cur = parents.get(cur)
    return frozenset(chain)


def unit_ancestors(db: Session, unit_id: str) -> frozenset[str]:
    snapshot = tuple(sorted(db.execute(select(Unit.id, Unit.parent_id)).all()))
    return _ancestors(unit_id, snapshot)


def jurisdiction_unit_ids(db: Session, user: User) -> set[str]:
    """Units a supervisor oversees: their own unit and all descendants."""
    rows = db.execute(select(Unit.id, Unit.parent_id)).all()
    children: dict[str | None, list[str]] = {}
    for uid, pid in rows:
        children.setdefault(pid, []).append(uid)
    out, stack = set(), [user.unit_id]
    while stack:
        u = stack.pop()
        out.add(u)
        stack.extend(children.get(u, []))
    return out


def capacities(db: Session, user: User, case: Case) -> set[str]:
    now = utcnow()
    caps = set(db.scalars(
        select(CaseMember.capacity).where(
            CaseMember.case_id == case.id, CaseMember.user_id == user.id,
            CaseMember.removed_at.is_(None),
            or_(CaseMember.expires_at.is_(None), CaseMember.expires_at > now),
        )
    ).all())
    if user.role == "SUPERVISOR" and user.unit_id in unit_ancestors(db, case.unit_id):
        caps.add("SUPERVISOR")
    return caps


def visible_case_ids_query(db: Session, user: User):
    """SELECT of case ids the user may list."""
    if user.role == "AUDITOR":
        return select(Case.id)
    if user.role in ADMIN_ROLES:
        return select(Case.id).where(false())
    member = select(CaseMember.case_id).where(
        CaseMember.user_id == user.id, CaseMember.removed_at.is_(None))
    conds = [Case.id.in_(member)]
    if user.role == "SUPERVISOR":
        conds.append(Case.unit_id.in_(jurisdiction_unit_ids(db, user)))
    return select(Case.id).where(or_(*conds))


def case_permissions(user: User, caps: set[str], case: Case) -> list[str]:
    perms = []
    if caps or user.role == "AUDITOR":
        perms.append("case:read")
    closed = case.status == "CLOSED"
    if not closed:
        if caps & {"LEAD_IO", "SUPERVISOR"}:
            perms += ["case:update", "case:change_status", "case:manage_members"]
        if caps & {"LEAD_IO", "CO_IO", "SUPERVISOR", "PROSECUTOR", "FORENSIC"}:
            perms.append("document:upload")
    if caps & {"LEAD_IO", "SUPERVISOR"} or user.role == "AUDITOR":
        perms.append("audit:read_case")
    return perms


def allowed_upload_types(caps: set[str]) -> set[str] | None:
    """None = any type."""
    if caps & {"LEAD_IO", "CO_IO", "SUPERVISOR"}:
        return None
    types: set[str] = set()
    if "PROSECUTOR" in caps:
        types |= LEGAL_TYPES
    if "FORENSIC" in caps:
        types.add("FORENSIC_REPORT")
    return types


def active_share(db: Session, user: User, doc: Document) -> Share | None:
    return db.scalar(select(Share).where(
        Share.document_id == doc.id, Share.grantee_user_id == user.id,
        Share.revoked_at.is_(None), Share.expires_at > utcnow(),
    ).order_by(Share.created_at.desc()))


@dataclass
class Access:
    view: str = "NONE"           # ORIGINAL | REDACTED | NONE
    download: str = "NONE"
    view_needs_purpose: bool = False
    download_needs_purpose: bool = False
    download_needs_step_up: bool = False
    via: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    caps: set[str] = field(default_factory=set)
    share: Share | None = None

    def as_dict(self) -> dict:
        obligations = ["WATERMARK"]
        if self.view_needs_purpose or self.download_needs_purpose:
            obligations.insert(0, "PURPOSE")
        if self.download_needs_step_up:
            obligations.insert(-1, "STEP_UP")
        return {"view": self.view, "download": self.download, "obligations": obligations,
                "via": self.via, "actions": self.actions}


def document_access(db: Session, user: User, doc: Document, case: Case | None = None) -> Access:
    case = case or doc.case
    caps = capacities(db, user, case)
    custodian = doc.custodian_id == user.id
    share = active_share(db, user, doc)
    a = Access(caps=caps, share=share)

    is_member = db.scalar(select(CaseMember.id).where(
        CaseMember.case_id == case.id, CaseMember.user_id == user.id,
        CaseMember.removed_at.is_(None)))
    if is_member:
        a.via.append("MEMBERSHIP")
    elif "SUPERVISOR" in caps:
        a.via.append("JURISDICTION")
    if custodian:
        a.via.append("CUSTODY")
    if share:
        a.via.append("SHARE")

    member = bool(caps)
    key = bool(caps & KEY_CAPACITIES)
    s = doc.sensitivity
    share_scope = share.scope if share else None

    if user.role in NO_CONTENT_ROLES:
        pass  # metadata only — never content
    elif s == "INTERNAL":
        if member or custodian or share_scope:
            a.view = "ORIGINAL"
        if member or custodian or share_scope == "DOWNLOAD":
            a.download = "ORIGINAL"
    elif s == "CONFIDENTIAL":
        if member or custodian or share_scope in ("VIEW", "DOWNLOAD"):
            a.view = "ORIGINAL"
        if key or custodian:
            a.download, a.download_needs_purpose = "ORIGINAL", True
    elif s == "RESTRICTED":
        if key or custodian or share_scope in ("VIEW", "DOWNLOAD"):
            a.view, a.view_needs_purpose = "ORIGINAL", True
        if key:
            a.download, a.download_needs_purpose, a.download_needs_step_up = "ORIGINAL", True, True
    elif s == "VICTIM_PROTECTED":
        if key or custodian:
            a.view, a.view_needs_purpose = "ORIGINAL", True
        elif member or share_scope:
            a.view = "REDACTED"
        if key:
            a.download, a.download_needs_purpose, a.download_needs_step_up = "ORIGINAL", True, True

    # document-level actions (drive which buttons the UI shows)
    open_case = case.status != "CLOSED"
    active = doc.status == "ACTIVE"
    if user.role not in ADMIN_ROLES and (caps or user.role == "AUDITOR" or custodian):
        a.actions.append("document:verify")
    if open_case and active:
        types = allowed_upload_types(caps)
        if caps and (types is None or doc.doc_type in types):
            a.actions.append("document:new_version")
        if caps & {"LEAD_IO", "SUPERVISOR", "PROSECUTOR"}:
            a.actions += ["document:share_request", "document:redact"]
        if caps & {"LEAD_IO", "CO_IO", "SUPERVISOR", "PROSECUTOR"}:
            a.actions.append("document:raise_sensitivity")
        if "SUPERVISOR" in caps and doc.created_by != user.id and doc.retention_state != "LEGAL_HOLD":
            a.actions.append("document:lower_sensitivity")
        if custodian:
            a.actions.append("document:custody_transfer")
        if caps & {"SUPERVISOR", "PROSECUTOR"}:
            a.actions.append("document:legal_hold_set" if doc.retention_state != "LEGAL_HOLD"
                             else "document:legal_hold_release")
        if "SUPERVISOR" in caps and doc.retention_state != "LEGAL_HOLD":
            a.actions.append("document:withdraw")
        if caps & {"LEAD_IO", "CO_IO"} and doc.doc_type in REVIEWABLE_TYPES:
            a.actions.append("document:review_submit")
    if caps & {"LEAD_IO", "SUPERVISOR"} and doc.current_version_id:
        a.actions.append("certificate:issue")
    if a.download != "NONE":
        a.actions.append("document:download")
    return a


def can_decide(db: Session, user: User, req) -> bool:
    if req.status != "PENDING" or req.requested_by == user.id:
        return False
    caps = capacities(db, user, req.case)
    if req.type == "CUSTODY_TRANSFER":
        return req.assigned_to == user.id
    if req.type in ("SHARE", "REVIEW", "MEMBERSHIP"):
        return "SUPERVISOR" in caps
    if req.type == "LEGAL_HOLD_RELEASE":
        return bool(caps & {"SUPERVISOR", "PROSECUTOR"})
    return False
