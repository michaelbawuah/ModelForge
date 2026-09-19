#!/bin/sh
set -eu

PORT="${PORT:-8000}"
MODELFORGE_WORKERS="${MODELFORGE_WORKERS:-1}"
MODELFORGE_FORWARDED_ALLOW_IPS="${MODELFORGE_FORWARDED_ALLOW_IPS:-127.0.0.1}"

# Fail before serving traffic if a production deployment is incomplete or unsafe.
modelforge config-check >/dev/null

if [ "${MODELFORGE_RUN_MIGRATIONS:-false}" = "true" ]; then
  python -m modelforge.core.database_ready
  alembic upgrade head
fi

exec uvicorn modelforge.api.app:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$MODELFORGE_WORKERS" \
  --proxy-headers \
  --forwarded-allow-ips "$MODELFORGE_FORWARDED_ALLOW_IPS"
