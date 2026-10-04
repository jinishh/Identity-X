"""RFC 9457 problem+json errors, plus the one helper that turns a policy denial into an
audited 403."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from . import audit


class ApiError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str | None = None,
                 deny_reason: str | None = None, errors: list | None = None):
        self.status, self.code, self.title, self.detail = status, code, title, detail
        self.deny_reason, self.errors = deny_reason, errors


def problem(status: int, code: str, title: str, detail: str | None = None, **extra) -> JSONResponse:
    body = {"type": f"https://cfv.local/problems/{code.lower()}", "title": title,
            "status": status, "code": code}
    if detail:
        body["detail"] = detail
    body.update({k: v for k, v in extra.items() if v is not None})
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def api_error_handler(_: Request, exc: ApiError):
    return problem(exc.status, exc.code, exc.title, exc.detail,
                   deny_reason=exc.deny_reason, errors=exc.errors)


async def validation_error_handler(_: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]),
               "message": e["msg"]} for e in exc.errors()]
    return problem(422, "VALIDATION_FAILED", "Invalid input", "Check the highlighted fields.",
                   errors=errors)


DENY_MESSAGES = {
    "NOT_A_CASE_MEMBER": "You are not assigned to this case.",
    "ACTION_NOT_PERMITTED": "Your role on this case does not allow this action.",
    "ROLE_NOT_PERMITTED": "Your role does not allow this action.",
    "SENSITIVITY": "The document's sensitivity level does not allow this.",
    "CASE_CLOSED": "The case is closed; it is read-only.",
    "LEGAL_HOLD": "The document is under legal hold.",
    "SELF_APPROVAL": "You cannot decide on your own request.",
}


def deny(db: Session, ctx: audit.Ctx, reason: str, summary: str, *, case_id=None,
         document_id=None, version_id=None, details=None) -> ApiError:
    """Record ACCESS_DENIED in the audit chain and return the 403 to raise."""
    audit.record(db, ctx, "ACCESS_DENIED", summary, outcome="DENIED", reason_code=reason,
                 case_id=case_id, document_id=document_id, version_id=version_id,
                 details=details)
    return ApiError(403, reason, "Access denied", DENY_MESSAGES.get(reason), deny_reason=reason)


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} not found")


def conflict(code: str, detail: str) -> ApiError:
    return ApiError(409, code, "Conflict", detail)


def precondition(code: str, detail: str) -> ApiError:
    return ApiError(428, code, "Precondition required", detail)
