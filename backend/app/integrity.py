"""Document verification (docs/03-integrity-model.md §5) and demo tamper scenarios (§7)."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import audit, config, crypto, storage
from .audit import compute_hash, iso
from .db import owner_engine, write_lock
from .models import AuditEvent, DocumentVersion, utcnow
from .pipeline import aad_for


def _check(name, ok, expected=None, actual=None, detail=None, skipped=False):
    return {"name": name, "status": "SKIPPED" if skipped else ("PASS" if ok else "FAIL"),
            "expected": expected, "actual": actual, "detail": detail}


def verify_version(db: Session, v: DocumentVersion) -> dict:
    checks = []
    present = bool(v.storage_key) and storage.exists(config.OBJECTS_DIR, v.storage_key)
    checks.append(_check("object_present", present, detail=v.storage_key))
    checks.append(_check("object_locked", present and storage.is_locked(config.OBJECTS_DIR, v.storage_key),
                         detail=f"write-once, retain until {iso(v.retain_until)}"))

    ct = storage.get(config.OBJECTS_DIR, v.storage_key) if present else b""
    ct_hash = crypto.sha256_hex(ct) if present else None
    checks.append(_check("ciphertext_hash_match", ct_hash == v.ciphertext_sha256,
                         v.ciphertext_sha256, ct_hash))

    plaintext = None
    try:
        plaintext = crypto.decrypt_file(ct, v.enc_nonce, v.wrapped_dek, aad_for(v))
        checks.append(_check("decrypts", True, detail="AES-256-GCM tag valid"))
    except Exception:
        checks.append(_check("decrypts", False, detail="AES-256-GCM authentication failed"))

    pt_hash = crypto.sha256_hex(plaintext) if plaintext is not None else None
    checks.append(_check("plaintext_hash_match", pt_hash == v.sha256, v.sha256, pt_hash,
                         skipped=plaintext is None))

    m_hash = crypto.sha256_hex(crypto.jcs(v.manifest)) if v.manifest else None
    checks.append(_check("manifest_hash_match", m_hash == v.manifest_sha256, v.manifest_sha256, m_hash))
    checks.append(_check("signature_valid",
                         bool(v.signature) and crypto.verify("MANIFEST", v.manifest, v.signature),
                         detail=f"Ed25519 · {v.signing_key_id}"))

    anchor = db.scalar(select(AuditEvent).where(
        AuditEvent.version_id == v.id, AuditEvent.action == "VERSION_CREATED"))
    anchored = bool(anchor) and (anchor.details or {}).get("manifest_sha256") == v.manifest_sha256 \
        and compute_hash(anchor.prev_hash, anchor) == anchor.event_hash
    checks.append(_check("audit_anchored", anchored,
                         detail=f"audit event #{anchor.seq}" if anchor else "no anchor event"))

    if v.parent_version_id:
        parent = db.get(DocumentVersion, v.parent_version_id)
        checks.append(_check("version_link_valid", parent and parent.sha256 == v.prev_version_sha256
                             and (v.manifest or {}).get("prev_version_sha256") == parent.sha256,
                             v.prev_version_sha256, parent.sha256 if parent else None))
    else:
        checks.append(_check("version_link_valid", True, detail="first version", skipped=True))

    overall = "VERIFIED" if all(c["status"] != "FAIL" for c in checks) else "FAILED"
    return {"version_id": v.id, "overall": overall, "checks": checks, "verified_at": iso(utcnow())}


# ───────────── demo tamper scenarios (DEMO_MODE only) ─────────────

# T3 / T4 play a rogue database administrator: they connect as the schema OWNER (the app role
# could not do this at all), switch off the append-only trigger, edit, and switch it back on.
def _as_rogue_dba(statements: list[tuple[str, dict]]) -> None:
    eng = owner_engine()
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE audit.events DISABLE TRIGGER events_append_only"))
        for sql, params in statements:
            conn.execute(text(sql), params)
        conn.execute(text("ALTER TABLE audit.events ENABLE TRIGGER events_append_only"))
    eng.dispose()


def tamper_overwrite_object(v: DocumentVersion) -> dict:
    try:
        storage.put(config.OBJECTS_DIR, v.storage_key, b"forged")
        return {"executed": True, "message": "Object overwritten (this should not happen)."}
    except storage.WormViolation:
        return {"executed": False,
                "message": f"Refused by write-once storage: {v.storage_key} is locked until "
                           f"{iso(v.retain_until)[:10]}.",
                "next_step": "Nothing changed — open the document and run Verify."}


def tamper_replace_ciphertext(v: DocumentVersion) -> dict:
    """Simulates an attacker with filesystem root bypassing the lock."""
    path = config.OBJECTS_DIR / v.storage_key
    path.chmod(0o644)
    data = bytearray(path.read_bytes())
    for i in range(16, min(len(data), 64)):
        data[i] ^= 0xFF
    path.write_bytes(bytes(data))
    path.chmod(0o444)
    return {"executed": True,
            "message": f"Flipped bytes inside the stored ciphertext of {v.storage_key} "
                       "(simulating root access that bypasses the lock).",
            "next_step": "Open the document → Integrity → Verify now."}


def tamper_edit_audit_row(db: Session, seq: int) -> dict:
    """Simulates a DB admin who disables the append-only trigger and edits one event."""
    with write_lock:
        _as_rogue_dba([("UPDATE audit.events SET summary = summary || ' [edited]', "
                        "purpose = 'Routine check' WHERE seq = :s", {"s": seq})])
    db.expire_all()
    return {"executed": True,
            "message": f"Audit event #{seq} edited directly in PostgreSQL by the schema owner "
                       "(append-only trigger switched off, then back on).",
            "next_step": "Audit → Verify chain."}


def tamper_rewrite_chain(db: Session, seq: int) -> dict:
    """Edits event `seq` and recomputes every later hash so all links look valid again."""
    with write_lock:
        # compute the forged chain first (reading is allowed), then write it as the owner
        prev = db.scalar(select(AuditEvent.event_hash).where(AuditEvent.seq == seq - 1)) or audit.GENESIS
        statements = [("UPDATE audit.events SET summary = summary || ' [rewritten]', "
                       "purpose = 'Routine check' WHERE seq = :s", {"s": seq})]
        for ev in db.scalars(select(AuditEvent).where(AuditEvent.seq >= seq).order_by(AuditEvent.seq)).all():
            if ev.seq == seq:
                ev.summary, ev.purpose = ev.summary + " [rewritten]", "Routine check"
            new_hash = compute_hash(prev, ev)
            statements.append(("UPDATE audit.events SET prev_hash=:p, event_hash=:h WHERE seq=:s",
                               {"p": prev, "h": new_hash, "s": ev.seq}))
            prev = new_hash
        db.expunge_all()
        _as_rogue_dba(statements)
    db.expire_all()
    return {"executed": True,
            "message": f"Event #{seq} edited and every later hash recomputed — the chain links "
                       "are consistent again.",
            "next_step": "Audit → Verify chain (watch the sealed checkpoints)."}
