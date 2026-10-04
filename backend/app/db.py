import threading
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


# The API connects as cfv_app: no DELETE anywhere, INSERT/SELECT only on the audit ledger.
engine = create_engine(config.DATABASE_URL, pool_size=10, max_overflow=10, pool_pre_ping=True,
                       connect_args={"options": "-c timezone=UTC"})

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Background pipeline threads and request threads both append to the ledger. Postgres
# serialises appends with an advisory lock (see audit.record); this in-process lock just
# avoids needless contention.
write_lock = threading.RLock()

AUDIT_CHAIN_LOCK = 26190  # pg_advisory_xact_lock key for "read head → insert next"


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def owner_engine():
    """Schema owner connection — migrations, demo reset and the 'rogue DBA' tamper demo only."""
    return create_engine(config.OWNER_DATABASE_URL, connect_args={"options": "-c timezone=UTC"})


def database_ready() -> bool:
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT to_regclass('iam.users') IS NOT NULL")).scalar()
    except Exception:
        return False
