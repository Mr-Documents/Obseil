#!/bin/sh
# Wait for PostgreSQL, apply migrations, then hand over to the CMD process.
set -e

echo "[obseil] waiting for database..."
python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text

url = os.environ.get("OBSEIL_DATABASE_URL", "")
if not url:
    print("[obseil] OBSEIL_DATABASE_URL is not set", file=sys.stderr)
    sys.exit(1)

deadline = time.time() + 60
last_error = None
while time.time() < deadline:
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[obseil] database is ready")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        time.sleep(1.5)

print(f"[obseil] database unreachable after 60s: {last_error}", file=sys.stderr)
sys.exit(1)
PY

echo "[obseil] applying migrations..."
alembic upgrade head

echo "[obseil] starting: $*"
exec "$@"
