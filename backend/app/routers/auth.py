"""Sign-in.

  first time   identifier + activation code (from the admin) → set password → link authenticator
  every time   identifier + password  ─┐
               face (camera)          ─┴→ authenticator code (always) → session
Face is only available once the officer has registered it from Settings.
"""

import hashlib
from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import audit, config, crypto, face, serial
from ..db import get_db
from ..errors import ApiError, precondition
from ..models import ActivationCode, FaceTemplate, Session, TotpCredential, User, utcnow
from ..security import (check_password, check_totp, ctx_for, current_session, current_user,
                        find_user, hash_password, make_token, open_session, password_problems,
                        read_claims, step_up_valid)

router = APIRouter(tags=["Auth"])


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, description="Email, mobile number or service ID")
    password: str


class FaceIn(BaseModel):
    identifier: str | None = None
    samples: list[list[float]]
    liveness: dict


class MfaIn(BaseModel):
    mfa_token: str
    code: str = Field(pattern=r"^[0-9]{6}$")


class ActivateIn(BaseModel):
    identifier: str
    activation_code: str = Field(min_length=6, max_length=20)


class ActivationPasswordIn(BaseModel):
    activation_token: str
    password: str


class ActivationConfirmIn(BaseModel):
    activation_token: str
    code: str = Field(pattern=r"^[0-9]{6}$")


class StepUpIn(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


def _token_response(db: DbSession, user: User, first_factor: str, request: Request) -> dict:
    sess, token = open_session(db, user, first_factor, request)
    return {"access_token": token, "expires_in": config.ACCESS_TOKEN_MINUTES * 60,
            "user": serial.me(db, user), "first_factor": first_factor}


def _register_failure(db: DbSession, request: Request, user: User | None, action: str, why: str,
                      details: dict | None = None):
    if user:
        user.failed_logins += 1
        if user.failed_logins >= 5:
            user.locked_until = utcnow() + timedelta(minutes=15)
    audit.record(db, ctx_for(request, user), action, f"Sign-in failed: {why}", outcome="FAILED",
                 details={"service_id": user.service_id if user else None, **(details or {})})


def _check_locked(user: User | None):
    if user and user.locked_until and user.locked_until > utcnow():
        raise ApiError(423, "LOCKED", "Account temporarily locked",
                       f"Too many failed attempts. Try again after {audit.iso(user.locked_until)}.")


# ───────────── first factor ─────────────

@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: DbSession = Depends(get_db)):
    user = find_user(db, body.identifier)
    _check_locked(user)
    if user and user.status == "INVITED":
        raise ApiError(409, "ACTIVATION_REQUIRED", "Account not activated yet",
                       "Use the activation code your administrator gave you.")
    if not user or user.status != "ACTIVE" or not check_password(user.password_hash, body.password):
        _register_failure(db, request, user, "AUTH_LOGIN_FAILED", "wrong identifier or password")
        raise ApiError(401, "BAD_CREDENTIALS", "Sign-in failed",
                       "That email / mobile number and password don't match.")
    return {"mfa_token": make_token(user, "mfa", config.MFA_TOKEN_MINUTES, ff="PASSWORD"),
            "first_factor": "PASSWORD", "user": serial.user_summary(user)}


@router.post("/auth/login/face")
def login_face(body: FaceIn, request: Request, db: DbSession = Depends(get_db)):
    claimed = find_user(db, body.identifier) if body.identifier else None
    if body.identifier and not claimed:
        raise ApiError(401, "FACE_NOT_RECOGNISED", "Face not recognised")
    _check_locked(claimed)
    probe = face.clean_samples(body.samples, body.liveness)
    user, distance = face.match(db, probe, claimed)
    if not user or user.status != "ACTIVE":
        _register_failure(db, request, claimed, "AUTH_FACE_FAILED", "face did not match",
                          {"distance": round(distance, 3) if distance is not None else None,
                           "mode": "1:1" if claimed else "1:N"})
        raise ApiError(401, "FACE_NOT_RECOGNISED", "Face not recognised",
                       "Try again in better light, or sign in with your password.")
    _check_locked(user)
    audit.record(db, ctx_for(request, user), "AUTH_FACE_MATCHED",
                 f"Face matched for {user.full_name} — authenticator code still required",
                 details={"distance": round(distance, 3), "mode": "1:1" if claimed else "1:N",
                          "model": face.MODEL})
    return {"mfa_token": make_token(user, "mfa", config.MFA_TOKEN_MINUTES, ff="FACE"),
            "first_factor": "FACE", "user": serial.user_summary(user)}


# ───────────── second factor: always the authenticator ─────────────

@router.post("/auth/mfa/verify")
def verify_mfa(body: MfaIn, request: Request, db: DbSession = Depends(get_db)):
    claims = read_claims(body.mfa_token, "mfa")
    user = db.get(User, claims["sub"])
    if not user or user.status != "ACTIVE":
        raise ApiError(401, "UNAUTHENTICATED", "Account not active")
    _check_locked(user)
    if not check_totp(db, user, body.code):
        _register_failure(db, request, user, "AUTH_MFA_FAILED", "wrong authenticator code")
        raise ApiError(401, "BAD_OTP", "Incorrect code", "The 6-digit code did not match.")
    ff = claims.get("ff", "PASSWORD")
    user.failed_logins, user.last_login_at = 0, utcnow()
    resp = _token_response(db, user, ff, request)
    audit.record(db, ctx_for(request, user), "AUTH_LOGIN_SUCCEEDED",
                 f"{user.full_name} signed in ({'face' if ff == 'FACE' else 'password'} + authenticator)",
                 details={"first_factor": ff})
    return resp


# ───────────── first-time activation ─────────────

def _activation_user(db: DbSession, token: str) -> User:
    user = db.get(User, read_claims(token, "activation")["sub"])
    if not user or user.status != "INVITED":
        raise ApiError(409, "ALREADY_ACTIVE", "This account is already active")
    return user


@router.post("/auth/activate")
def activate(body: ActivateIn, request: Request, db: DbSession = Depends(get_db)):
    user = find_user(db, body.identifier)
    code_hash = hashlib.sha256(body.activation_code.strip().upper().encode()).hexdigest()
    rec = db.scalar(select(ActivationCode).where(
        ActivationCode.user_id == (user.id if user else None), ActivationCode.used_at.is_(None),
        ActivationCode.expires_at > utcnow()).order_by(ActivationCode.issued_at.desc())) if user else None
    if not user or user.status != "INVITED" or not rec or rec.code_hash != code_hash:
        audit.record(db, ctx_for(request, user), "ACCOUNT_ACTIVATION_FAILED",
                     "Activation attempt with a wrong or expired code", outcome="FAILED",
                     details={"identifier_type": "email" if "@" in body.identifier else "phone/service id"})
        raise ApiError(401, "BAD_ACTIVATION", "Activation failed",
                       "Check the email / mobile number and the activation code from your administrator.")
    return {"activation_token": make_token(user, "activation", 15), "user": serial.user_summary(user),
            "email": user.email, "phone_masked": serial.mask_phone(user.phone)}


@router.post("/auth/activate/password")
def activation_password(body: ActivationPasswordIn, db: DbSession = Depends(get_db)):
    user = _activation_user(db, body.activation_token)
    problems = password_problems(body.password)
    if problems:
        raise ApiError(422, "WEAK_PASSWORD", "Choose a stronger password", "Use " + ", ".join(problems) + ".")
    user.password_hash = hash_password(body.password)
    secret = pyotp.random_base32()
    if user.totp:
        user.totp.secret_enc, user.totp.confirmed_at = crypto.seal(secret.encode()), None
    else:
        db.add(TotpCredential(user_id=user.id, secret_enc=crypto.seal(secret.encode())))
    db.commit()
    return {"otpauth_uri": pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name="Case-File Vault"),
            "secret": secret}


@router.post("/auth/activate/confirm")
def activation_confirm(body: ActivationConfirmIn, request: Request, db: DbSession = Depends(get_db)):
    user = _activation_user(db, body.activation_token)
    db.refresh(user)
    if not user.password_hash or not user.totp:
        raise ApiError(409, "STEP_MISSING", "Set a password first")
    if not check_totp(db, user, body.code):
        raise ApiError(401, "BAD_OTP", "Incorrect code", "Enter the code your authenticator app shows now.")
    now = utcnow()
    user.totp.confirmed_at = now
    user.status, user.activated_at, user.last_login_at = "ACTIVE", now, now
    for rec in db.scalars(select(ActivationCode).where(ActivationCode.user_id == user.id,
                                                       ActivationCode.used_at.is_(None))):
        rec.used_at = now
    resp = _token_response(db, user, "ACTIVATION", request)
    audit.record(db, ctx_for(request, user), "ACCOUNT_ACTIVATED",
                 f"{user.full_name} activated their account (password + authenticator)")
    return resp


# ───────────── signed-in housekeeping ─────────────

@router.post("/auth/step-up")
def step_up(body: StepUpIn, request: Request, user: User = Depends(current_user),
            db: DbSession = Depends(get_db)):
    if not check_totp(db, user, body.code):
        _register_failure(db, request, user, "AUTH_MFA_FAILED", "wrong step-up code")
        raise ApiError(401, "BAD_OTP", "Incorrect code")
    user.step_up_until = utcnow() + timedelta(minutes=config.STEP_UP_MINUTES)
    audit.record(db, ctx_for(request, user), "AUTH_STEP_UP", f"{user.full_name} re-confirmed 2FA")
    return {"step_up_valid_until": audit.iso(user.step_up_until)}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, pair=Depends(current_session), db: DbSession = Depends(get_db)):
    user, sess = pair
    sess.revoked_at = utcnow()
    audit.record(db, ctx_for(request, user), "AUTH_LOGOUT", f"{user.full_name} signed out")


@router.get("/auth/me")
def get_me(user: User = Depends(current_user), db: DbSession = Depends(get_db)):
    return {**serial.me(db, user),
            "step_up_valid_until": audit.iso(user.step_up_until) if step_up_valid(user) else None}


@router.get("/me/security", tags=["Settings"])
def my_security(pair=Depends(current_session), db: DbSession = Depends(get_db)):
    user, current = pair
    t = face.active_template(db, user.id)
    sessions = db.scalars(select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None),
                                                Session.expires_at > utcnow())
                          .order_by(Session.created_at.desc()).limit(10)).all()
    return {
        "email": user.email, "phone_masked": serial.mask_phone(user.phone),
        "authenticator": {"linked_at": audit.iso(user.totp.confirmed_at) if user.totp else None},
        "face": ({"enrolled_at": audit.iso(t.enrolled_at), "model": t.model, "samples": t.samples,
                  "quality": t.quality} if t else None),
        "sessions": [{"id": s.id, "first_factor": s.first_factor, "created_at": audit.iso(s.created_at),
                      "last_seen_at": audit.iso(s.last_seen_at), "ip": s.ip,
                      "user_agent": s.user_agent, "current": s.id == current.id} for s in sessions],
        "step_up_valid_until": audit.iso(user.step_up_until) if step_up_valid(user) else None,
    }


@router.post("/me/face", status_code=201, tags=["Settings"])
def enrol_face(body: FaceIn, request: Request, user: User = Depends(current_user),
               db: DbSession = Depends(get_db)):
    if not step_up_valid(user):
        raise precondition("STEP_UP_REQUIRED", "Re-enter your authenticator code to register your face.")
    template = face.clean_samples(body.samples, body.liveness)
    old = face.active_template(db, user.id)
    if old:
        old.revoked_at = utcnow()
        db.flush()
    quality = body.liveness.get("score")
    db.add(FaceTemplate(user_id=user.id, template_enc=face.seal_template(template), model=face.MODEL,
                        dims=face.DIMS, samples=len(body.samples),
                        quality=float(quality) if isinstance(quality, (int, float)) else None))
    audit.record(db, ctx_for(request, user), "FACE_ENROLLED",
                 f"{user.full_name} registered face sign-in ({len(body.samples)} samples, blink checked)",
                 details={"model": face.MODEL, "replaced_previous": bool(old)})
    return {"enrolled": True}


@router.post("/me/face/remove", tags=["Settings"])
def remove_face(request: Request, user: User = Depends(current_user), db: DbSession = Depends(get_db)):
    t = face.active_template(db, user.id)
    if t:
        t.revoked_at = utcnow()
        audit.record(db, ctx_for(request, user), "FACE_REMOVED", f"{user.full_name} removed face sign-in")
    return {"enrolled": False}


@router.post("/me/password", tags=["Settings"])
def change_password(body: PasswordChangeIn, request: Request, user: User = Depends(current_user),
                    db: DbSession = Depends(get_db)):
    if not check_password(user.password_hash, body.current_password):
        raise ApiError(401, "BAD_CREDENTIALS", "Current password is wrong")
    problems = password_problems(body.new_password)
    if problems:
        raise ApiError(422, "WEAK_PASSWORD", "Choose a stronger password", "Use " + ", ".join(problems) + ".")
    user.password_hash = hash_password(body.new_password)
    audit.record(db, ctx_for(request, user), "PASSWORD_CHANGED", f"{user.full_name} changed their password")
    return {"changed": True}


@router.post("/me/sessions/{session_id}/revoke", tags=["Settings"])
def revoke_session(session_id: str, request: Request, user: User = Depends(current_user),
                   db: DbSession = Depends(get_db)):
    s = db.get(Session, session_id)
    if not s or s.user_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Session not found")
    s.revoked_at = utcnow()
    audit.record(db, ctx_for(request, user), "SESSION_REVOKED", f"{user.full_name} ended a session")
    return {"revoked": True}
