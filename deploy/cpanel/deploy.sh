#!/usr/bin/env bash
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "$PROJECT_ROOT"

echo "[1/4] Checking Django configuration"
"$PYTHON_BIN" manage.py check --deploy

echo "[2/4] Applying database migrations"
"$PYTHON_BIN" manage.py migrate --noinput

echo "[3/4] Collecting static assets"
"$PYTHON_BIN" manage.py collectstatic --noinput

echo "[4/4] Deployment completed"
echo "Restart the Python application from cPanel Setup Python App."
