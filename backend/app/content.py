"""Short-lived content URLs. Bytes are never returned from JSON endpoints: access is decided and
audited first, then the client gets a token that streams the file for a minute."""

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import config
from .models import utcnow


@dataclass
class Grant:
    kind: str           # VERSION | DERIVATIVE
    object_id: str
    mime: str
    filename: str
    disposition: str    # inline | attachment
    expires_at: datetime


_grants: dict[str, Grant] = {}
_lock = threading.Lock()


def issue(kind: str, object_id: str, mime: str, filename: str, disposition: str) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(seconds=config.CONTENT_TOKEN_SECONDS)
    with _lock:
        now = utcnow()
        for t in [t for t, g in _grants.items() if g.expires_at < now]:
            del _grants[t]
        _grants[token] = Grant(kind, object_id, mime, filename, disposition, expires)
    return token, expires


def redeem(token: str) -> Grant | None:
    with _lock:
        g = _grants.get(token)
    return g if g and g.expires_at > utcnow() else None
