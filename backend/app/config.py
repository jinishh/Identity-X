"""Runtime settings. Everything is local-first: one data directory holds the SQLite DB,
encrypted objects, sealed checkpoints and keys."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("CFV_DATA_DIR", BASE_DIR / "data"))

# PostgreSQL. The API connects as cfv_app (no DELETE, append-only ledger); migrations, demo
# reset and the "rogue DBA" tamper demo use the owner. Local dev credentials — scripts/db.sh.
DATABASE_URL = os.getenv("CFV_DATABASE_URL",
                         "postgresql+psycopg://cfv_app:cfv_app_dev@127.0.0.1:5433/case_file_vault")
OWNER_DATABASE_URL = os.getenv("CFV_OWNER_DATABASE_URL",
                               "postgresql+psycopg://cfv_owner:cfv_owner_dev@127.0.0.1:5433/case_file_vault")
OBJECTS_DIR = DATA_DIR / "objects"          # encrypted evidence (read-only after write)
DERIVATIVES_DIR = DATA_DIR / "derivatives"  # encrypted redacted copies, certificate PDFs
CHECKPOINTS_DIR = DATA_DIR / "checkpoints"  # sealed audit checkpoints (read-only)
QUARANTINE_DIR = DATA_DIR / "quarantine"    # rejected / infected uploads
KEYS_DIR = DATA_DIR / "keys"                # KEK + Ed25519 signing keys (prototype only)

DEMO_MODE = os.getenv("CFV_DEMO_MODE", "true").lower() == "true"
# Shared password of every seeded demo account. Only ever handed out by /demo/personas while
# DEMO_MODE is on; the database itself stores argon2 hashes only.
DEMO_PASSWORD = os.getenv("CFV_DEMO_PASSWORD", "Vault@2026!demo")
FRONTEND_ORIGIN = os.getenv("CFV_FRONTEND_ORIGIN", "http://localhost:5173")
PUBLIC_VERIFY_BASE = os.getenv("CFV_PUBLIC_VERIFY_BASE", f"{FRONTEND_ORIGIN}/verify")

ACCESS_TOKEN_MINUTES = 240
MFA_TOKEN_MINUTES = 5
STEP_UP_MINUTES = 5
CONTENT_TOKEN_SECONDS = 60

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
CHECKPOINT_EVERY = 50  # seal a checkpoint every N audit events

# Pause between pipeline steps so the live pipeline is watchable in the UI. 0 in seeding.
PIPELINE_STEP_DELAY_MS = int(os.getenv("CFV_PIPELINE_STEP_DELAY_MS", "450"))

RETENTION_YEARS = 10


def ensure_dirs() -> None:
    for d in (DATA_DIR, OBJECTS_DIR, DERIVATIVES_DIR, CHECKPOINTS_DIR, QUARANTINE_DIR, KEYS_DIR):
        d.mkdir(parents=True, exist_ok=True)
