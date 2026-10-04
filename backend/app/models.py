"""SQLAlchemy mappings onto the PostgreSQL schema in database/migrations/.

The SQL migrations are the source of truth (constraints, triggers, grants live there); these
classes only map onto them. Application code works in naive UTC datetimes; the UTC type below
stores them as timestamptz.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary,
                        SmallInteger, String, Text, TypeDecorator, Uuid)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# The seeder sets this to replay two months of history in order; None = real time.
clock_override: datetime | None = None


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return clock_override or datetime.now(timezone.utc).replace(tzinfo=None)


class UTC(TypeDecorator):
    """timestamptz in the database, naive UTC in Python."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value is not None else None


ID = Uuid(as_uuid=False)


def FK(target: str, **kw):
    return mapped_column(ID, ForeignKey(target), **kw)


# ───────────── org ─────────────
class Unit(Base):
    __tablename__ = "units"
    __table_args__ = {"schema": "org"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    parent_id: Mapped[str | None] = FK("org.units.id")
    district: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)


# ───────────── iam ─────────────
class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "iam"}
    code: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(SmallInteger)
    is_administrative: Mapped[bool] = mapped_column(Boolean)
    sees_case_content: Mapped[bool] = mapped_column(Boolean)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "iam"}
    code: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = {"schema": "iam"}
    role_code: Mapped[str] = mapped_column(ForeignKey("iam.roles.code"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("iam.permissions.code"), primary_key=True)


class TotpCredential(Base):
    __tablename__ = "totp_credentials"
    __table_args__ = {"schema": "iam"}
    user_id: Mapped[str] = mapped_column(ID, ForeignKey("iam.users.id"), primary_key=True)
    secret_enc: Mapped[bytes] = mapped_column(LargeBinary)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTC)
    last_used_counter: Mapped[int | None] = mapped_column(BigInteger)


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "iam"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(String)
    full_name: Mapped[str] = mapped_column(String)
    rank: Mapped[str | None] = mapped_column(String)
    role: Mapped[str] = mapped_column("role_code", ForeignKey("iam.roles.code"))
    unit_id: Mapped[str] = FK("org.units.id")
    email: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="INVITED")
    password_hash: Mapped[str | None] = mapped_column(String)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTC)
    step_up_until: Mapped[datetime | None] = mapped_column(UTC)
    activated_at: Mapped[datetime | None] = mapped_column(UTC)
    last_login_at: Mapped[datetime | None] = mapped_column(UTC)
    created_by: Mapped[str | None] = FK("iam.users.id")
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)

    unit: Mapped[Unit] = relationship(lazy="joined")
    totp: Mapped[TotpCredential | None] = relationship(lazy="joined", uselist=False)
    role_ref: Mapped[Role] = relationship(lazy="joined", foreign_keys=[role])

    @property
    def mfa_enabled(self) -> bool:
        return bool(self.totp and self.totp.confirmed_at)


class ActivationCode(Base):
    __tablename__ = "activation_codes"
    __table_args__ = {"schema": "iam"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    user_id: Mapped[str] = FK("iam.users.id")
    code_hash: Mapped[str] = mapped_column(String)
    issued_by: Mapped[str | None] = FK("iam.users.id")
    issued_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTC)
    used_at: Mapped[datetime | None] = mapped_column(UTC)


class FaceTemplate(Base):
    __tablename__ = "face_templates"
    __table_args__ = {"schema": "iam"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    user_id: Mapped[str] = FK("iam.users.id")
    template_enc: Mapped[bytes] = mapped_column(LargeBinary)
    model: Mapped[str] = mapped_column(String)
    dims: Mapped[int] = mapped_column(SmallInteger)
    samples: Mapped[int] = mapped_column(SmallInteger)
    quality: Mapped[float | None] = mapped_column()
    enrolled_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTC)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "iam"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    user_id: Mapped[str] = FK("iam.users.id")
    first_factor: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTC)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTC)
    revoked_at: Mapped[datetime | None] = mapped_column(UTC)
    ip: Mapped[str | None] = mapped_column(String)
    user_agent: Mapped[str | None] = mapped_column(String)


class SigningKey(Base):
    __tablename__ = "signing_keys"
    __table_args__ = {"schema": "iam"}
    id: Mapped[str] = mapped_column("kid", String, primary_key=True)
    purpose: Mapped[str] = mapped_column(String)
    algorithm: Mapped[str] = mapped_column(String, default="Ed25519")
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    retired_at: Mapped[datetime | None] = mapped_column(UTC)


class DemoPersona(Base):
    """Demo-mode only: which seeded accounts to offer on the sign-in page, and why."""

    __tablename__ = "personas"
    __table_args__ = {"schema": "demo"}
    user_id: Mapped[str] = mapped_column(ID, ForeignKey("iam.users.id"), primary_key=True)
    sort: Mapped[int] = mapped_column(SmallInteger)
    headline: Mapped[str] = mapped_column(String)
    shows: Mapped[str] = mapped_column(Text)
    activation_code: Mapped[str | None] = mapped_column(String)
    demo_password: Mapped[str | None] = mapped_column(String)
    totp_secret: Mapped[str | None] = mapped_column(String)


# ───────────── cases ─────────────
class Case(Base):
    __tablename__ = "cases"
    __table_args__ = {"schema": "cases"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    case_number: Mapped[str] = mapped_column(String)
    fir_number: Mapped[str] = mapped_column(String)
    fir_date: Mapped[date] = mapped_column(Date)
    unit_id: Mapped[str] = FK("org.units.id")
    title: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    offence_sections: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    status: Mapped[str] = mapped_column(String, default="REGISTERED")
    is_victim_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    victim_pseudonym: Mapped[str | None] = mapped_column(String)
    victim_identifiers_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    default_sensitivity: Mapped[str] = mapped_column(String, default="CONFIDENTIAL")
    lead_io_id: Mapped[str] = FK("iam.users.id")
    court_name: Mapped[str | None] = mapped_column(String)
    next_hearing_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = FK("iam.users.id")
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(UTC)

    unit: Mapped[Unit] = relationship(lazy="joined")
    lead_io: Mapped[User] = relationship(foreign_keys=[lead_io_id], lazy="joined")
    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="joined")


class CaseMember(Base):
    __tablename__ = "case_members"
    __table_args__ = {"schema": "cases"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    case_id: Mapped[str] = FK("cases.cases.id")
    user_id: Mapped[str] = FK("iam.users.id")
    capacity: Mapped[str] = mapped_column(String)
    added_by: Mapped[str] = FK("iam.users.id")
    added_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UTC)
    removed_by: Mapped[str | None] = FK("iam.users.id")
    removed_at: Mapped[datetime | None] = mapped_column(UTC)
    removal_reason: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    adder: Mapped[User] = relationship(foreign_keys=[added_by], lazy="joined")


# ───────────── docs ─────────────
class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "docs"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    doc_number: Mapped[str] = mapped_column(String)
    case_id: Mapped[str] = FK("cases.cases.id")
    title: Mapped[str] = mapped_column(String)
    doc_type: Mapped[str] = mapped_column(String)
    sensitivity: Mapped[str] = mapped_column(String)
    retention_state: Mapped[str] = mapped_column(String, default="ACTIVE")
    legal_hold_reason: Mapped[str | None] = mapped_column(Text)
    legal_hold_by: Mapped[str | None] = FK("iam.users.id")
    legal_hold_at: Mapped[datetime | None] = mapped_column(UTC)
    status: Mapped[str] = mapped_column(String, default="ACTIVE")
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_by: Mapped[str | None] = FK("iam.users.id")
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTC)
    custodian_id: Mapped[str] = FK("iam.users.id")
    current_version_id: Mapped[str | None] = mapped_column(ID, ForeignKey("docs.versions.id", use_alter=True))
    tags: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    created_by: Mapped[str] = FK("iam.users.id")
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)

    case: Mapped[Case] = relationship(lazy="joined")
    custodian: Mapped[User] = relationship(foreign_keys=[custodian_id], lazy="joined")
    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="joined")


class DocumentVersion(Base):
    __tablename__ = "versions"
    __table_args__ = {"schema": "docs"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    document_id: Mapped[str] = FK("docs.documents.id")
    version_no: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[str | None] = FK("docs.versions.id")
    change_note: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String)
    detected_mime: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String)
    client_sha256: Mapped[str] = mapped_column(String)
    prev_version_sha256: Mapped[str | None] = mapped_column(String)
    ciphertext_sha256: Mapped[str | None] = mapped_column(String)
    storage_key: Mapped[str | None] = mapped_column(String)
    enc_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary)
    kek_id: Mapped[str | None] = mapped_column(String)
    manifest: Mapped[dict | None] = mapped_column(JSONB)
    manifest_sha256: Mapped[str | None] = mapped_column(String)
    signature: Mapped[bytes | None] = mapped_column(LargeBinary)
    signing_key_id: Mapped[str | None] = mapped_column(String, ForeignKey("iam.signing_keys.kid"))
    processing_status: Mapped[str] = mapped_column(String, default="RECEIVED")
    scan_result: Mapped[str] = mapped_column(String, default="PENDING")
    scan_detail: Mapped[str | None] = mapped_column(String)
    page_count: Mapped[int | None] = mapped_column(Integer)
    ocr_status: Mapped[str] = mapped_column(String, default="PENDING")
    review_status: Mapped[str] = mapped_column(String, default="NOT_REQUIRED")
    retain_until: Mapped[datetime | None] = mapped_column(UTC)
    uploaded_by: Mapped[str] = FK("iam.users.id")
    uploaded_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(UTC)
    last_verification: Mapped[str | None] = mapped_column(String)

    uploader: Mapped[User] = relationship(lazy="joined")


class ProcessingStep(Base):
    __tablename__ = "processing_steps"
    __table_args__ = {"schema": "docs"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = FK("docs.versions.id")
    step: Mapped[str] = mapped_column(String)
    seq: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    critical: Mapped[bool] = mapped_column(Boolean, default=True)
    started_at: Mapped[datetime | None] = mapped_column(UTC)
    finished_at: Mapped[datetime | None] = mapped_column(UTC)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = {"schema": "docs"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = FK("docs.versions.id")
    type: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(String)
    page_no: Mapped[int] = mapped_column(Integer)
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False)
    is_victim_identifier: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(default=1.0)
    source: Mapped[str] = mapped_column(String, default="REGEX")


class Derivative(Base):
    __tablename__ = "derivatives"
    __table_args__ = {"schema": "docs"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    source_version_id: Mapped[str] = FK("docs.versions.id")
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="READY")
    mime: Mapped[str] = mapped_column(String, default="application/pdf")
    storage_key: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    enc_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    kek_id: Mapped[str] = mapped_column(String)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[str] = FK("iam.users.id")
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)

    creator: Mapped[User] = relationship(lazy="joined")


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = {"schema": "docs"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    cert_number: Mapped[str] = mapped_column(String)
    version_id: Mapped[str] = FK("docs.versions.id")
    verification_code: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    part_a: Mapped[dict] = mapped_column(JSONB)
    part_b: Mapped[dict] = mapped_column(JSONB)
    signatory_name: Mapped[str] = mapped_column(String)
    signatory_designation: Mapped[str] = mapped_column(String)
    purpose: Mapped[str | None] = mapped_column(Text)
    pdf_derivative_id: Mapped[str | None] = FK("docs.derivatives.id")
    signature: Mapped[bytes] = mapped_column(LargeBinary)
    signing_key_id: Mapped[str] = mapped_column(String, ForeignKey("iam.signing_keys.kid"))
    status: Mapped[str] = mapped_column(String, default="ISSUED")
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(UTC)
    issued_by: Mapped[str] = FK("iam.users.id")
    issued_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)

    issuer: Mapped[User] = relationship(lazy="joined")
    version: Mapped[DocumentVersion] = relationship(lazy="joined")


# ───────────── collab ─────────────
class Request(Base):
    __tablename__ = "requests"
    __table_args__ = {"schema": "collab"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    case_id: Mapped[str] = FK("cases.cases.id")
    document_id: Mapped[str | None] = FK("docs.documents.id")
    version_id: Mapped[str | None] = FK("docs.versions.id")
    requested_by: Mapped[str] = FK("iam.users.id")
    assigned_to: Mapped[str | None] = FK("iam.users.id")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str | None] = FK("iam.users.id")
    decided_at: Mapped[datetime | None] = mapped_column(UTC)
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)

    case: Mapped[Case] = relationship(lazy="joined")
    document: Mapped[Document | None] = relationship(lazy="joined")
    requester: Mapped[User] = relationship(foreign_keys=[requested_by], lazy="joined")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to], lazy="joined")
    decider: Mapped[User | None] = relationship(foreign_keys=[decided_by], lazy="joined")


class Share(Base):
    __tablename__ = "shares"
    __table_args__ = {"schema": "collab"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    document_id: Mapped[str] = FK("docs.documents.id")
    grantee_user_id: Mapped[str] = FK("iam.users.id")
    scope: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(UTC)
    request_id: Mapped[str | None] = FK("collab.requests.id")
    created_by: Mapped[str] = FK("iam.users.id")
    approved_by: Mapped[str | None] = FK("iam.users.id")
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)
    revoked_by: Mapped[str | None] = FK("iam.users.id")
    revoked_at: Mapped[datetime | None] = mapped_column(UTC)
    revoke_reason: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(lazy="joined")
    grantee: Mapped[User] = relationship(foreign_keys=[grantee_user_id], lazy="joined")
    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="joined")
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by], lazy="joined")


# ───────────── audit ─────────────
class AuditEvent(Base):
    """Append-only, hash-chained. No foreign keys: the log must outlive anything it mentions."""

    __tablename__ = "events"
    __table_args__ = {"schema": "audit"}
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    id: Mapped[str] = mapped_column(ID, default=new_id)
    occurred_at: Mapped[datetime] = mapped_column(UTC)
    actor_user_id: Mapped[str | None] = mapped_column(ID)
    actor_role: Mapped[str | None] = mapped_column(String)
    actor_service_id: Mapped[str | None] = mapped_column(String)
    ip: Mapped[str | None] = mapped_column(String)
    user_agent: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String)
    reason_code: Mapped[str | None] = mapped_column(String)
    case_id: Mapped[str | None] = mapped_column(ID)
    document_id: Mapped[str | None] = mapped_column(ID)
    version_id: Mapped[str | None] = mapped_column(ID)
    target_user_id: Mapped[str | None] = mapped_column(ID)
    request_id: Mapped[str | None] = mapped_column(ID)
    purpose: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String)
    event_hash: Mapped[str] = mapped_column(String)


class AuditCheckpoint(Base):
    __tablename__ = "checkpoints"
    __table_args__ = {"schema": "audit"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_seq: Mapped[int] = mapped_column(BigInteger)
    to_seq: Mapped[int] = mapped_column(BigInteger)
    head_hash: Mapped[str] = mapped_column(String)
    merkle_root: Mapped[str] = mapped_column(String)
    event_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTC)
    signature: Mapped[bytes] = mapped_column(LargeBinary)
    signing_key_id: Mapped[str] = mapped_column(String, ForeignKey("iam.signing_keys.kid"))
    sealed_path: Mapped[str] = mapped_column(String)


# ───────────── alerts ─────────────
class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = {"schema": "alerts"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    case_id: Mapped[str | None] = mapped_column(ID)
    document_id: Mapped[str | None] = mapped_column(ID)
    actor_user_id: Mapped[str | None] = FK("iam.users.id")
    audit_seq: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String, default="OPEN")
    acknowledged_by: Mapped[str | None] = FK("iam.users.id")
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTC)
    resolved_by: Mapped[str | None] = FK("iam.users.id")
    resolved_at: Mapped[datetime | None] = mapped_column(UTC)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTC, default=utcnow)

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_user_id], lazy="joined")
    acknowledger: Mapped[User | None] = relationship(foreign_keys=[acknowledged_by], lazy="joined")
