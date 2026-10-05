#!/usr/bin/env bash
set -euo pipefail

: "${SECURITY_MONITOR_URL:?Set SECURITY_MONITOR_URL}"
: "${ENROLLMENT_TOKEN:?Set ENROLLMENT_TOKEN}"

HOSTNAME_VALUE="${HOSTNAME_VALUE:-$(hostname -f 2>/dev/null || hostname)}"
SITE_URL="${SITE_URL:-}"
AGENT_VERSION="${AGENT_VERSION:-1.0.0}"

payload=$(python3 - <<'PY'
import json, os
print(json.dumps({
    "hostname": os.environ.get("HOSTNAME_VALUE", ""),
    "site_url": os.environ.get("SITE_URL", ""),
    "agent_version": os.environ.get("AGENT_VERSION", ""),
}))
PY
)

response=$(curl --fail-with-body --silent --show-error \
  --tlsv1.2 \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${ENROLLMENT_TOKEN}" \
  -d "$payload" \
  "${SECURITY_MONITOR_URL%/}/v1/enroll")

printf '%s\n' "$response"
