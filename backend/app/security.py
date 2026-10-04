"""Passwords, authenticator codes, sessions, and the request dependencies that resolve the caller."""

import os
import re
import time
from datetime import timedelta
from functools import lru_cache

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import config, crypto
from .audit import Ctx
from .db import get_db
from .errors import ApiError
from .models import Session, User, utcnow

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def check_password(hashed: str | None, pw: str) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def password_problems(pw: str) -> list[str]:
    problems = []
    if len(pw) < 12:
        problems.append("at least 12 characters")
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        problems.append("letters and numbers")
    if not re.search(r"[^A-Za-z0-9]", pw):
        problems.append("a symbol")
    return problems


# ───────────── who is signing in ─────────────

def normalise_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    return None


def find_user(db: DbSession, identifier: str) -> User | None:
    """Email, Indian mobile number, or service ID — whichever the officer typed."""
    ident = identifier.strip()
    if "@" in ident:
        return db.scalar(select(User).where(func.lower(User.email) == ident.lower()))
    phone = normalise_phone(ident)
    if phone:
        return db.scalar(select(User).where(User.phone == phone))
    return db.scalar(select(User).where(User.service_id == ident.upper()))


# ───────────── authenticator (TOTP) ─────────────

def totp_for(user: User) -> pyotp.TOTP:
    return pyotp.TOTP(crypto.unseal(user.totp.secret_enc).decode())


def check_totp(db: DbSession, user: User, code: str) -> bool:
    """Accept the current code (±1 step for clock drift), and never the same step twice."""
    if not user.totp:
        return False
    t = totp_for(user)
    now_counter = int(time.time()) // t.interval
    for counter in (now_counter, now_counter - 1, now_counter + 1):
        if t.generate_otp(counter) == code:
            if user.totp.last_used_counter is not None and counter <= user.totp.last_used_counter:
                raise ApiError(401, "OTP_REUSED", "Code already used",
                               "That code has been used once already. Wait for the next one.")
            user.totp.last_used_counter = counter
            db.flush()
            return True
    return False


# ───────────── tokens & sessions ─────────────

@lru_cache
def _jwt_secret() -> bytes:
    path = config.KEYS_DIR / "jwt.key"
    if not path.exists():
        path.write_bytes(os.urandom(32))
        path.chmod(0o400)
    return path.read_bytes()


def reset_secret_cache() -> None:
    _jwt_secret.cache_clear()


def make_token(user: User, typ: str, minutes: int, **extra) -> str:
    now = utcnow()
    claims = {"sub": user.id, "typ": typ, "iat": now, "exp": now + timedelta(minutes=minutes), **extra}
    return jwt.encode(claims, _jwt_secret(), algorithm="HS256")


def read_claims(token: str, typ: str) -> dict:
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHENTICATED", "Session expired or invalid", "Please sign in again.")
    if claims.get("typ") != typ:
        raise ApiError(401, "UNAUTHENTICATED", "Wrong token type")
    return claims


def read_token(token: str, typ: str) -> str:
    return read_claims(token, typ)["sub"]


def open_session(db: DbSession, user: User, first_factor: str, request: Request) -> tuple[Session, str]:
    s = Session(user_id=user.id, first_factor=first_factor,
                expires_at=utcnow() + timedelta(minutes=config.ACCESS_TOKEN_MINUTES),
                ip=request.client.host if request.client else None,
                user_agent=(request.headers.get("user-agent") or "")[:300])
    db.add(s)
    db.flush()
    return s, make_token(user, "access", config.ACCESS_TOKEN_MINUTES, sid=s.id)


def current_session(request: Request, db: DbSession = Depends(get_db)) -> tuple[User, Session]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "Not signed in")
    claims = read_claims(header[7:], "access")
    sess = db.get(Session, claims.get("sid")) if claims.get("sid") else None
    if not sess or sess.revoked_at or sess.expires_at <= utcnow():
        raise ApiError(401, "UNAUTHENTICATED", "Session ended", "Please sign in again.")
    user = db.get(User, claims["sub"])
    if not user or user.status != "ACTIVE":
        raise ApiError(401, "UNAUTHENTICATED", "Account not active")
    if not sess.last_seen_at or utcnow() - sess.last_seen_at > timedelta(minutes=1):
        sess.last_seen_at = utcnow()
        db.commit()
    return user, sess


def current_user(pair: tuple[User, Session] = Depends(current_session)) -> User:
    return pair[0]


def ctx_for(request: Request, user: User | None) -> Ctx:
    ip = request.client.host if request.client else None
    return Ctx(user=user, ip=ip, user_agent=request.headers.get("user-agent"))


def step_up_valid(user: User) -> bool:
    return bool(user.step_up_until and user.step_up_until > utcnow())
