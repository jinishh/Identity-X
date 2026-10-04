"""Generate database/ERD.md (Mermaid) from the live PostgreSQL catalogue.

    backend/.venv/bin/python scripts/erd.py
"""

from pathlib import Path

import psycopg

DSN = "host=127.0.0.1 port=5433 dbname=case_file_vault user=cfv_readonly password=cfv_read_dev"
SCHEMAS = ("org", "iam", "cases", "docs", "collab", "audit", "alerts", "demo")
OUT = Path(__file__).resolve().parent.parent / "database" / "ERD.md"

with psycopg.connect(DSN) as conn:
    cols = conn.execute("""
        SELECT c.table_schema, c.table_name, c.column_name, c.data_type,
               EXISTS (SELECT 1 FROM information_schema.table_constraints tc
                       JOIN information_schema.key_column_usage k USING (constraint_schema, constraint_name)
                       WHERE tc.constraint_type = 'PRIMARY KEY' AND k.table_schema = c.table_schema
                         AND k.table_name = c.table_name AND k.column_name = c.column_name) AS pk
        FROM information_schema.columns c
        JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = ANY(%s) AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_schema, c.table_name, c.ordinal_position""", (list(SCHEMAS),)).fetchall()
    fks = conn.execute("""
        SELECT DISTINCT cl.relnamespace::regnamespace::text AS src_schema, cl.relname AS src,
               rf.relnamespace::regnamespace::text AS dst_schema, rf.relname AS dst, con.conname
        FROM pg_constraint con
        JOIN pg_class cl ON cl.oid = con.conrelid
        JOIN pg_class rf ON rf.oid = con.confrelid
        WHERE con.contype = 'f' AND cl.relnamespace::regnamespace::text = ANY(%s)
        ORDER BY 1, 2, 3, 4""", (list(SCHEMAS),)).fetchall()

def ent(schema, table):
    return f"{schema}_{table}"

lines = ["# Entity-relationship diagram", "",
         "Generated from the live database by `scripts/erd.py` — it always matches the migrations.",
         "Entities are named `schema_table`. Audit tables deliberately have no foreign keys: the ledger must outlive what it mentions.",
         "", "```mermaid", "erDiagram"]
seen = set()
for src_s, src, dst_s, dst, name in fks:
    key = (src_s, src, dst_s, dst)
    if key in seen or (src_s, src) == (dst_s, dst):
        continue
    seen.add(key)
    lines.append(f"  {ent(dst_s, dst)} ||--o{{ {ent(src_s, src)} : \"{name.replace('_fkey', '').replace(src + '_', '')}\"")
current = None
for schema, table, column, dtype, pk in cols:
    if (schema, table) != current:
        if current:
            lines.append("  }")
        current = (schema, table)
        lines.append(f"  {ent(schema, table)} {{")
    dtype = dtype.replace("timestamp with time zone", "timestamptz").replace("character varying", "varchar") \
                 .replace("USER-DEFINED", "citext").replace("ARRAY", "text_array").replace(" ", "_")
    lines.append(f"    {dtype} {column}{' PK' if pk else ''}")
lines += ["  }", "```", ""]
OUT.write_text("\n".join(lines))
print(f"wrote {OUT} ({len({(c[0], c[1]) for c in cols})} tables, {len(seen)} relationships)")
