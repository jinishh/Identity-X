#!/usr/bin/env bash
# Project-local PostgreSQL 16 server (no sudo, separate from any system Postgres).
#   scripts/db.sh init     create the cluster, roles and database (once)
#   scripts/db.sh start | stop | status
#   scripts/db.sh psql [role]   open psql as cfv_owner (default), cfv_app or postgres
set -euo pipefail
cd "$(dirname "$0")/.."

PGBIN=${PGBIN:-/usr/lib/postgresql/16/bin}
PGDATA=${PGDATA:-$PWD/backend/.pgdata}
PGPORT=${PGPORT:-5433}
LOG="$PGDATA/server.log"
# local development credentials only — see database/README.md
SUPER_PW=${CFV_PG_SUPER_PASSWORD:-cfv_super_dev}
OWNER_PW=${CFV_PG_OWNER_PASSWORD:-cfv_owner_dev}
APP_PW=${CFV_PG_APP_PASSWORD:-cfv_app_dev}
READ_PW=${CFV_PG_READ_PASSWORD:-cfv_read_dev}

psql_as() { PGPASSWORD="$2" psql -h 127.0.0.1 -p "$PGPORT" -U "$1" -d "${3:-case_file_vault}" -v ON_ERROR_STOP=1 "${@:4}"; }

case "${1:-}" in
  init)
    if [ -f "$PGDATA/PG_VERSION" ]; then echo "cluster already exists at $PGDATA"; exit 0; fi
    mkdir -p "$PGDATA"
    pwfile=$(mktemp); echo "$SUPER_PW" > "$pwfile"
    "$PGBIN/initdb" -D "$PGDATA" -U postgres --pwfile="$pwfile" --auth=scram-sha-256 -E UTF8 --locale=C.UTF-8 >/dev/null
    rm -f "$pwfile"
    cat >> "$PGDATA/postgresql.conf" <<CONF
listen_addresses = '127.0.0.1'
port = $PGPORT
unix_socket_directories = ''
timezone = 'UTC'
log_statement = 'ddl'
shared_buffers = 64MB
CONF
    "$PGBIN/pg_ctl" -D "$PGDATA" -l "$LOG" -w start >/dev/null
    psql_as postgres "$SUPER_PW" postgres -q <<SQL
CREATE ROLE cfv_owner LOGIN PASSWORD '$OWNER_PW';
CREATE ROLE cfv_app LOGIN PASSWORD '$APP_PW';
CREATE ROLE cfv_readonly LOGIN PASSWORD '$READ_PW';
COMMENT ON ROLE cfv_owner IS 'Owns every schema and runs migrations. Never used by the running app.';
COMMENT ON ROLE cfv_app IS 'What the API connects as. No DELETE anywhere on evidence; INSERT/SELECT only on the audit ledger.';
COMMENT ON ROLE cfv_readonly IS 'Read-only, for inspection in pgAdmin and for auditors.';
CREATE DATABASE case_file_vault OWNER cfv_owner ENCODING 'UTF8';
REVOKE ALL ON DATABASE case_file_vault FROM PUBLIC;
GRANT CONNECT ON DATABASE case_file_vault TO cfv_app, cfv_readonly;
SQL
    psql_as postgres "$SUPER_PW" case_file_vault -q -c "REVOKE CREATE ON SCHEMA public FROM PUBLIC;"
    echo "cluster ready on 127.0.0.1:$PGPORT (database case_file_vault)"
    ;;
  start)  "$PGBIN/pg_ctl" -D "$PGDATA" -l "$LOG" -w start ;;
  stop)   "$PGBIN/pg_ctl" -D "$PGDATA" -w stop ;;
  status) "$PGBIN/pg_ctl" -D "$PGDATA" status ;;
  psql)
    case "${2:-owner}" in
      owner) psql_as cfv_owner "$OWNER_PW" case_file_vault "${@:3}" ;;
      app) psql_as cfv_app "$APP_PW" case_file_vault "${@:3}" ;;
      read) psql_as cfv_readonly "$READ_PW" case_file_vault "${@:3}" ;;
      postgres) psql_as postgres "$SUPER_PW" case_file_vault "${@:3}" ;;
    esac ;;
  *) echo "usage: $0 init|start|stop|status|psql [owner|app|read|postgres]"; exit 1 ;;
esac
