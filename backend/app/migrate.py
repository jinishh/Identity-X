"""Apply database/migrations/*.sql in order, as the schema owner.

    python -m app.migrate            apply pending migrations
    python -m app.migrate --reset    drop every schema and rebuild from scratch (demo reset)

The running API never connects as the owner; it uses the restricted cfv_app role.
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from . import config

MIGRATIONS = config.BASE_DIR.parent / "database" / "migrations"
SCHEMAS = ["demo", "alerts", "audit", "collab", "docs", "cases", "iam", "org"]


def owner_engine():
    return create_engine(config.OWNER_DATABASE_URL)


def migrate(verbose: bool = True) -> list[str]:
    """Each migration file runs in its own transaction: it applies completely or not at all."""
    eng = owner_engine()
    done = []
    with eng.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS public.schema_migrations (
            version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"""))
        have = set(conn.execute(text("SELECT version FROM public.schema_migrations")).scalars())
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.stem in have:
            continue
        with eng.begin() as conn:
            # raw driver call, no parameters: the SQL file is sent exactly as written
            conn.connection.driver_connection.execute(path.read_text())
            conn.execute(text("INSERT INTO public.schema_migrations(version) VALUES (:v)"), {"v": path.stem})
        done.append(path.stem)
        if verbose:
            print(f"applied {path.name}")
    eng.dispose()
    return done


def reset() -> None:
    """Drop all application schemas (the owner may, the app may not) and rebuild."""
    eng = owner_engine()
    with eng.begin() as conn:
        for s in SCHEMAS:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {s} CASCADE"))
        conn.execute(text("DROP FUNCTION IF EXISTS public.forbid_change() CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.schema_migrations"))
    eng.dispose()
    migrate(verbose=False)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
        print("database rebuilt from migrations")
    else:
        print("\n".join(migrate()) or "up to date")
