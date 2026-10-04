"""Face sign-in: template enrolment and matching.

The browser runs a face network (face-api, 128-d embeddings) on the webcam, checks for a blink,
and sends only the embeddings — never an image. The server:
  · checks the samples are consistent with each other (one person, not a swapped photo),
  · stores the averaged template encrypted under the KEK,
  · matches later attempts by Euclidean distance.
Face is a first factor only. The authenticator code is still required after a match.
"""

import math
import struct

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crypto
from .errors import ApiError
from .models import FaceTemplate, User

MODEL = "face-api/faceRecognitionNet (128-d)"
DIMS = 128
SAME_PERSON_ACROSS_FRAMES = 0.42   # max distance between samples of one enrolment / attempt
MATCH_ONE_TO_ONE = 0.50            # identifier given: is this that person?
MATCH_ONE_TO_MANY = 0.45           # no identifier: best match must be at least this close…
MARGIN_ONE_TO_MANY = 0.07          # …and clearly closer than the runner-up


def _dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def clean_samples(samples: list[list[float]], liveness: dict) -> list[float]:
    """Validate what the browser sent and return the averaged template."""
    if not liveness or not liveness.get("blink"):
        raise ApiError(422, "LIVENESS_FAILED", "Blink not detected",
                       "Look at the camera and blink once so we know it isn't a photo.")
    if not 3 <= len(samples) <= 10:
        raise ApiError(422, "BAD_FACE_SAMPLES", "Need 3 to 10 face samples")
    for s in samples:
        if len(s) != DIMS or not all(math.isfinite(x) and abs(x) < 2 for x in s):
            raise ApiError(422, "BAD_FACE_SAMPLES", "Malformed face sample")
    worst = max(_dist(a, b) for i, a in enumerate(samples) for b in samples[i + 1:])
    if worst > SAME_PERSON_ACROSS_FRAMES:
        raise ApiError(422, "FACE_INCONSISTENT", "Face changed between frames",
                       "Hold still in good light and try again.")
    return [sum(col) / len(samples) for col in zip(*samples)]


def seal_template(vec: list[float]) -> bytes:
    return crypto.seal(struct.pack(f"<{DIMS}f", *vec))


def open_template(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{DIMS}f", crypto.unseal(blob)))


def active_template(db: Session, user_id: str) -> FaceTemplate | None:
    return db.scalar(select(FaceTemplate).where(FaceTemplate.user_id == user_id,
                                                FaceTemplate.revoked_at.is_(None)))


def match(db: Session, probe: list[float], user: User | None) -> tuple[User | None, float | None]:
    """1:1 when the officer typed who they are, otherwise 1:N over everyone enrolled."""
    if user is not None:
        t = active_template(db, user.id)
        if not t:
            return None, None
        d = _dist(probe, open_template(t.template_enc))
        return (user if d <= MATCH_ONE_TO_ONE else None), d

    scored = []
    for t in db.scalars(select(FaceTemplate).where(FaceTemplate.revoked_at.is_(None))):
        scored.append((_dist(probe, open_template(t.template_enc)), t.user_id))
    if not scored:
        return None, None
    scored.sort()
    best_d, best_uid = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 9.0
    if best_d <= MATCH_ONE_TO_MANY and runner_up - best_d >= MARGIN_ONE_TO_MANY:
        return db.get(User, best_uid), best_d
    return None, best_d
