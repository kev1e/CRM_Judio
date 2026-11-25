#!/bin/sh
# Smoke check of a running compose stack: API readiness, web page, and a task
# that travels API container -> Redis -> worker container -> PostgreSQL.
set -eu

cd "$(dirname "$0")/.."

API_URL="${API_URL:-http://127.0.0.1:8000}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3000}"

echo "1/3 API readiness"
curl --fail --silent --show-error "${API_URL}/api/v1/ready" | grep -q '"status":"ok"'

echo "2/3 Web page"
curl --fail --silent --show-error "${WEB_URL}/login" | grep -q 'lang="ru"'

echo "3/3 Worker executes a task"
component="smoke-$(date +%s)"
docker compose exec -T api python - "$component" <<'PY'
import sys
import time

import django

django.setup()

from crm.system.models import Heartbeat
from crm.system.tasks import record_heartbeat

component = sys.argv[1]
record_heartbeat.delay(component)
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    if Heartbeat.objects.filter(component=component, beats=1).exists():
        sys.exit(0)
    time.sleep(0.5)
sys.exit("The worker did not execute the task within 30 seconds.")
PY

echo "Smoke check passed."
