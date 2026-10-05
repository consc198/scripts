#!/usr/bin/env bash
set -euo pipefail

: "${SECURITY_MONITOR_URL:?Set SECURITY_MONITOR_URL}"
: "${ENROLLMENT_TOKEN:?Set ENROLLMENT_TOKEN}"
: "${SITE_ROOT:?Set SITE_ROOT}"

HOSTNAME_VALUE="${HOSTNAME_VALUE:-$(hostname -f 2>/dev/null || hostname)}"
SITE_URL="${SITE_URL:-}"
AGENT_VERSION="${AGENT_VERSION:-0.3}"
CONFIG_DIR="${CONFIG_DIR:-/etc/security-monitor}"
CONFIG_FILE="${CONFIG_FILE:-${CONFIG_DIR}/agent.json}"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

payload=$(python3 - <<'PY'
import json, os
print(json.dumps({
    "hostname": os.environ["HOSTNAME_VALUE"],
    "site_url": os.environ.get("SITE_URL") or None,
    "agent_version": os.environ.get("AGENT_VERSION"),
}))
PY
)

response=$(curl --fail-with-body --silent --show-error \
  --tlsv1.2 \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${ENROLLMENT_TOKEN}" \
  -d "$payload" \
  "${SECURITY_MONITOR_URL%/}/v1/enroll")

python3 - "$response" "$CONFIG_FILE" <<'PY'
import json, os, sys
response = json.loads(sys.argv[1])
config_file = sys.argv[2]
config = {
    "api_url": os.environ["SECURITY_MONITOR_URL"],
    "agent_id": response["agent_id"],
    "token": response["token"],
    "site_url": os.environ.get("SITE_URL") or None,
    "site_root": os.environ["SITE_ROOT"],
    "full_scan_timeout": 3600,
}
tmp = config_file + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(config, f, separators=(",", ":"))
os.chmod(tmp, 0o600)
os.replace(tmp, config_file)
print(json.dumps({"agent_id": response["agent_id"], "config_file": config_file}))
PY
