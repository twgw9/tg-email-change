#!/usr/bin/env bash
# Alwaysdata / kisi bhi server par chalane ka wrapper.
# Istemaal:  ./alwaysdata_run.sh --status
#            ./alwaysdata_run.sh --temp
#            echo "..." | ./alwaysdata_run.sh --email aap@mail.com
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] && set -a && . ./.env && set +a

PY="./venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

exec "$PY" tg_email_change_own.py "$@"
