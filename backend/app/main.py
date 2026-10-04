from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import config
from . import migrate
from .db import SessionLocal
from .errors import ApiError, api_error_handler, validation_error_handler
from .models import User
from .routers import auth, cases, documents, misc

app = FastAPI(
    title="Case-File Vault API",
    version="0.1.0",
    description="SIH26190 — secure document management for legal & investigation documents. "
                "Contract: contracts/openapi.yaml",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

for r in (auth.router, cases.router, documents.router, misc.router):
    app.include_router(r, prefix="/api/v1")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


@app.on_event("startup")
def startup() -> None:
    config.ensure_dirs()
    migrate.migrate(verbose=False)  # dev convenience: apply pending SQL migrations as the owner
    with SessionLocal() as db:
        empty = db.scalar(select(User.id).limit(1)) is None
    if empty:
        from .seed import seed
        seed()
