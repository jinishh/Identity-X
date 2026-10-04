"""Hash-chained, append-only audit log with signed checkpoints sealed outside the database.

event_hash = SHA-256( prev_hash_bytes ‖ JCS(canonical_event) )
Every CHECKPOINT_EVERY events, the range is sealed: Merkle root + head hash, Ed25519-signed,
written to the DB *and* to a read-only file. Rewriting the whole chain (which keeps links
consistent) still fails against the sealed copies.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import config, crypto
from .db import AUDIT_CHAIN_LOCK, write_lock
from .models import Alert, AuditCheckpoint, AuditEvent, User, new_id, utcnow

GENESIS = "0" * 64


@dataclass
class Ctx:
    """Who is acting, from where."""

    user: User | None = None
    ip: str | None = None
    user_agent: str | None = None


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if dt else None


def canonical(ev: AuditEvent) -> dict:
    return {
        "seq": ev.seq,
        "id": ev.id,
        "occurred_at": iso(ev.occurred_at),
        "actor_user_id": ev.actor_user_id,
        "actor_role": ev.actor_role,
        "action": ev.action,
        "outcome": ev.outcome,
        "reason_code": ev.reason_code,
        "case_id": ev.case_id,
        "document_id": ev.document_id,
        "version_id": ev.version_id,
        "target_user_id": ev.target_user_id,
        "request_id": ev.request_id,
        "purpose": ev.purpose,
        "summary": ev.summary,
        "details": ev.details or {},
    }


def compute_hash(prev_hash: str, ev: AuditEvent) -> str:
    return crypto.sha256_hex(bytes.fromhex(prev_hash) + crypto.jcs(canonical(ev)))


def record(
    db: Session,
    ctx: Ctx,
    action: str,
    summary: str,
    *,
    outcome: str = "SUCCESS",
    reason_code: str | None = None,
    case_id: str | None = None,
    document_id: str | None = None,
    version_id: str | None = None,
    target_user_id: str | None = None,
    request_id: str | None = None,
    purpose: str | None = None,
    details: dict | None = None,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    """Append an event and COMMIT the session — so the action and its audit record land in
    the same transaction. Call it after staging the action's changes."""
    with write_lock:
        # Serialise "read head → insert next" across every process, inside this transaction.
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_CHAIN_LOCK})
        head = db.execute(
            select(AuditEvent.seq, AuditEvent.event_hash).order_by(AuditEvent.seq.desc()).limit(1)
        ).first()
        seq, prev = (head[0] + 1, head[1]) if head else (1, GENESIS)
        user = ctx.user
        ev = AuditEvent(
            seq=seq,
            id=new_id(),
            occurred_at=occurred_at or utcnow(),
            actor_user_id=user.id if user else None,
            actor_role=user.role if user else "SYSTEM",
            actor_service_id=user.service_id if user else None,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            action=action,
            outcome=outcome,
            reason_code=reason_code,
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
            target_user_id=target_user_id,
            request_id=request_id,
            purpose=purpose,
            summary=summary,
            details=details or {},
            prev_hash=prev,
        )
        ev.event_hash = compute_hash(prev, ev)
        db.add(ev)
        if action == "ACCESS_DENIED" and user:
            _maybe_denied_burst(db, ev)
        db.commit()

        if seq % config.CHECKPOINT_EVERY == 0:
            _seal_checkpoint(db, seq, ev.occurred_at)
        return ev


def _maybe_denied_burst(db: Session, ev: AuditEvent) -> None:
    since = ev.occurred_at - timedelta(minutes=10)
    count = db.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.actor_user_id == ev.actor_user_id,
            AuditEvent.action == "ACCESS_DENIED",
            AuditEvent.occurred_at >= since,
        )
    )  # autoflush has already inserted ev, so it is included
    recent = db.scalar(
        select(func.count()).select_from(Alert).where(
            Alert.actor_user_id == ev.actor_user_id,
            Alert.type == "ACCESS_DENIED_BURST",
            Alert.created_at >= since,
        )
    )
    if count >= 3 and not recent:
        db.add(Alert(
            type="ACCESS_DENIED_BURST", severity="MEDIUM",
            title="Repeated access denials",
            message=f"{ev.actor_service_id} was denied access {count} times in 10 minutes.",
            case_id=ev.case_id, actor_user_id=ev.actor_user_id, audit_seq=ev.seq,
            created_at=ev.occurred_at,
        ))


def _checkpoint_body(cp: AuditCheckpoint) -> dict:
    return {
        "schema": "cfv.checkpoint/1",
        "from_seq": cp.from_seq,
        "to_seq": cp.to_seq,
        "head_hash": cp.head_hash,
        "merkle_root": cp.merkle_root,
        "event_count": cp.event_count,
        "created_at": iso(cp.created_at),
    }


def _seal_checkpoint(db: Session, to_seq: int, at: datetime) -> None:
    last = db.scalar(select(func.max(AuditCheckpoint.to_seq))) or 0
    hashes = db.scalars(
        select(AuditEvent.event_hash).where(AuditEvent.seq > last, AuditEvent.seq <= to_seq)
        .order_by(AuditEvent.seq)
    ).all()
    cp_id = (db.scalar(select(func.max(AuditCheckpoint.id))) or 0) + 1
    cp = AuditCheckpoint(
        id=cp_id, from_seq=last + 1, to_seq=to_seq, head_hash=hashes[-1],
        merkle_root=crypto.merkle_root(hashes), event_count=len(hashes), created_at=at,
        signing_key_id=crypto.SIGNING_KEY_IDS["CHECKPOINT"], sealed_path=f"cp-{cp_id:06d}.json",
    )
    body = _checkpoint_body(cp)
    cp.signature, _ = crypto.sign("CHECKPOINT", body)
    path = config.CHECKPOINTS_DIR / cp.sealed_path
    path.write_text(json.dumps({"checkpoint": body, "signature": crypto.b64(cp.signature),
                                "kid": cp.signing_key_id}, indent=2))
    path.chmod(0o444)  # sealed: production → object storage under COMPLIANCE lock
    db.add(cp)
    db.commit()
    record(db, Ctx(), "CHECKPOINT_CREATED",
           f"Sealed checkpoint #{cp.id} over events {cp.from_seq}–{cp.to_seq}",
           details={"checkpoint_id": cp.id, "merkle_root": cp.merkle_root}, occurred_at=at)


def verify_chain(db: Session) -> dict:
    started = time.perf_counter()
    first_break = None
    expected_prev = GENESIS
    expected_seq = 1
    count = 0
    head_hash = GENESIS
    stored_hash_by_seq: dict[int, str] = {}

    for ev in db.scalars(select(AuditEvent).order_by(AuditEvent.seq)).yield_per(500):
        count += 1
        stored_hash_by_seq[ev.seq] = ev.event_hash
        if first_break is None:
            if ev.seq != expected_seq:
                first_break = {"seq": expected_seq, "check": "SEQ_GAP",
                               "expected": str(expected_seq), "actual": str(ev.seq)}
            elif ev.prev_hash != expected_prev:
                first_break = {"seq": ev.seq, "check": "PREV_HASH_LINK",
                               "expected": expected_prev, "actual": ev.prev_hash}
            else:
                recomputed = compute_hash(ev.prev_hash, ev)
                if recomputed != ev.event_hash:
                    first_break = {"seq": ev.seq, "check": "EVENT_HASH",
                                   "expected": recomputed, "actual": ev.event_hash}
        expected_prev = ev.event_hash
        expected_seq = ev.seq + 1
        head_hash = ev.event_hash

    cps = db.scalars(select(AuditCheckpoint).order_by(AuditCheckpoint.id)).all()
    cp_break = None
    for cp in cps:
        hashes = [stored_hash_by_seq.get(s, "") for s in range(cp.from_seq, cp.to_seq + 1)]
        body = _checkpoint_body(cp)
        sealed_path = config.CHECKPOINTS_DIR / cp.sealed_path
        sealed = json.loads(sealed_path.read_text()) if sealed_path.exists() else None
        problem = None
        if not crypto.verify("CHECKPOINT", body, cp.signature):
            problem = ("CHECKPOINT_SIGNATURE", "valid signature", "invalid")
        elif sealed is None or sealed["checkpoint"] != body:
            problem = ("CHECKPOINT_WORM_COPY", "sealed copy identical", "differs or missing")
        elif hashes[-1] != cp.head_hash:
            problem = ("CHECKPOINT_HEAD", cp.head_hash, hashes[-1])
        elif crypto.merkle_root(hashes) != cp.merkle_root:
            problem = ("CHECKPOINT_MERKLE", cp.merkle_root, crypto.merkle_root(hashes))
        if problem:
            cp_break = {"seq": cp.to_seq, "check": problem[0], "expected": problem[1],
                        "actual": problem[2], "checkpoint_id": cp.id}
            break

    if first_break is None or (cp_break and cp_break["seq"] < first_break["seq"]):
        first_break = cp_break or first_break

    return {
        "status": "BROKEN" if first_break else "VALID",
        "events_checked": count,
        "checkpoints_checked": len(cps),
        "head_seq": expected_seq - 1,
        "head_hash": head_hash,
        "first_break": first_break,
        "verified_at": iso(utcnow()),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
