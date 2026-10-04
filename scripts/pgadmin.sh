#!/usr/bin/env bash
# pgAdmin 4 in desktop mode (no pgAdmin login), pre-connected to the project database.
#   scripts/pgadmin.sh        → http://127.0.0.1:5050
# Two connections are registered:
#   "Case-File Vault — read only"  as cfv_readonly (cannot see password hashes or 2FA secrets)
#   "Case-File Vault — owner"      as cfv_owner    (shows that even the owner can't edit the ledger)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
VENV=$ROOT/.pgadmin
DATA=$ROOT/.pgadmin/data
PORT=${PGADMIN_PORT:-5050}

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q pgadmin4==9.18
fi
PKG=$("$VENV/bin/python" -c "import site; print(site.getsitepackages()[0])")/pgadmin4
mkdir -p "$DATA/storage" "$DATA/sessions"

cat > "$PKG/config_local.py" <<PY
SERVER_MODE = False
DEFAULT_SERVER = '127.0.0.1'
DEFAULT_SERVER_PORT = $PORT
DATA_DIR = '$DATA'
LOG_FILE = '$DATA/pgadmin4.log'
SQLITE_PATH = '$DATA/pgadmin4.db'
SESSION_DB_PATH = '$DATA/sessions'
STORAGE_DIR = '$DATA/storage'
MASTER_PASSWORD_REQUIRED = False
UPGRADE_CHECK_ENABLED = False
PY

# local development credentials (see scripts/db.sh)
printf '127.0.0.1:5433:*:cfv_readonly:cfv_read_dev\n127.0.0.1:5433:*:cfv_owner:cfv_owner_dev\n' > "$DATA/pgpass"
chmod 600 "$DATA/pgpass"
cat > "$DATA/servers.json" <<JSON
{ "Servers": {
  "1": { "Name": "Case-File Vault — read only", "Group": "SIH 26190", "Host": "127.0.0.1", "Port": 5433,
         "MaintenanceDB": "case_file_vault", "Username": "cfv_readonly", "PassFile": "$DATA/pgpass", "SSLMode": "disable" },
  "2": { "Name": "Case-File Vault — owner", "Group": "SIH 26190", "Host": "127.0.0.1", "Port": 5433,
         "MaintenanceDB": "case_file_vault", "Username": "cfv_owner", "PassFile": "$DATA/pgpass", "SSLMode": "disable" }
} }
JSON

if [ ! -f "$DATA/.servers-loaded" ]; then
  (cd "$PKG" && "$VENV/bin/python" setup.py setup-db >/dev/null 2>&1 || true)
  (cd "$PKG" && "$VENV/bin/python" setup.py load-servers "$DATA/servers.json" >/dev/null) && touch "$DATA/.servers-loaded"
fi

echo "pgAdmin on http://127.0.0.1:$PORT"
cd "$PKG" && exec "$VENV/bin/python" pgAdmin4.py
