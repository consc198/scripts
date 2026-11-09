#!/usr/bin/env bash
# RunCloud Deployment Script
# Deploys the Zabbix 7.4 agent to one selected RunCloud server over SSH.
# Requires: curl, jq, ssh; token.txt beside this script; root SSH access.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_FILE="${SCRIPT_DIR}/token.txt"
API_BASE="https://manage.runcloud.io/api/v3"
CONFIG_URL="https://raw.githubusercontent.com/consc198/scripts/main/runcloud-deployment-script/zabbix_agentd.conf"
ZABBIX_DEB_URL="https://repo.zabbix.com/zabbix/7.4/release/ubuntu/pool/main/z/zabbix-release/zabbix-release_latest_7.4+ubuntu24.04_all.deb"

usage() {
  cat <<'USAGE'
RunCloud Deployment Script

Usage:
  ./runcloud-deployment.sh --list
  ./runcloud-deployment.sh
  ./runcloud-deployment.sh --server SERVER_ID

Without --server, an interactive server selection menu is shown.
USAGE
}

die() { echo "ERROR: $*" >&2; exit 1; }

for cmd in curl jq ssh; do
  command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: $cmd"
done

[[ -r "$TOKEN_FILE" ]] || die "Missing or unreadable token file: $TOKEN_FILE"
RUNCLOUD_TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
[[ -n "$RUNCLOUD_TOKEN" ]] || die "The token file is empty."

api_get() {
  curl --fail --silent --show-error --connect-timeout 10 --max-time 60 \
    --retry 5 --retry-delay 2 --retry-max-time 180 \
    -H "Authorization: Bearer ${RUNCLOUD_TOKEN}" \
    -H "Accept: application/json" "${API_BASE}${1}"
}

fetch_servers() {
  local page=1 response total_pages
  SERVERS_JSONL="$(mktemp)"
  while :; do
    response="$(api_get "/servers?page=${page}&perPage=40")"
    jq -e '.data | type == "array"' >/dev/null <<< "$response" ||
      die "Unexpected RunCloud API response while fetching servers."
    jq -c '.data[]' <<< "$response" >> "$SERVERS_JSONL"
    total_pages="$(jq -r '.meta.pagination.total_pages // .meta.pagination.totalPages // 1' <<< "$response")"
    [[ "$total_pages" =~ ^[0-9]+$ ]] || die "Could not read RunCloud pagination metadata."
    (( page >= total_pages )) && break
    ((page += 1))
    (( page <= 1000 )) || die "Stopped after 1000 API pages."
  done
  [[ -s "$SERVERS_JSONL" ]] || die "RunCloud returned no servers."
}

server_id() { jq -r '.id // .serverId // .server_id // empty' <<< "$1"; }
server_name() { jq -r '.name // .label // .hostname // .id // "Unnamed server"' <<< "$1"; }
server_host() {
  jq -r '.ip // .ipAddress // .ip_address // .publicIp // .public_ip // .hostname // .host // empty' <<< "$1"
}

list_servers() {
  printf '%-12s %-32s %s\n' "SERVER ID" "SERVER NAME" "SSH HOST"
  while IFS= read -r server; do
    printf '%-12s %-32s %s\n' "$(server_id "$server")" "$(server_name "$server")" "$(server_host "$server")"
  done < "$SERVERS_JSONL"
}

deploy_zabbix() {
  local host="$1" name="$2"
  [[ "$host" =~ ^[A-Za-z0-9._:-]+$ ]] || die "Unsafe or unsupported SSH host value: $host"

  echo
  echo "Target: $name ($host)"
  echo "Connecting as root using your existing SSH access..."

  ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 \
    -- "root@${host}" 'bash -s' "${ZABBIX_DEB_URL}" "${CONFIG_URL}" <<'REMOTE_SCRIPT'
set -Eeuo pipefail
ZABBIX_DEB_URL="$1"
CONFIG_URL="$2"

echo "[1/6] Checking operating system..."
if [[ ! -r /etc/os-release ]]; then
  echo "Cannot identify operating system." >&2
  exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
  echo "This Zabbix repository package is specifically for Ubuntu 24.04; found ${PRETTY_NAME:-unknown}." >&2
  exit 1
fi

echo "[2/6] Downloading and installing Zabbix 7.4 repository package..."
tmp_deb="$(mktemp /tmp/zabbix-release.XXXXXX.deb)"
trap 'rm -f "$tmp_deb"' EXIT
curl --fail --location --silent --show-error --retry 3 \
  -o "$tmp_deb" "$ZABBIX_DEB_URL"
dpkg -i "$tmp_deb"

echo "[3/6] Updating APT and installing Zabbix Agent..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y zabbix-agent

echo "[4/6] Installing the Zabbix agent configuration..."
curl --fail --location --silent --show-error --retry 3 \
  -o /etc/zabbix/zabbix_agentd.conf "$CONFIG_URL"
chown root:root /etc/zabbix/zabbix_agentd.conf
chmod 0644 /etc/zabbix/zabbix_agentd.conf

echo "[5/6] Waiting 60 seconds before restarting the agent..."
sleep 60

echo "[6/6] Restarting and verifying Zabbix Agent..."
systemctl restart zabbix-agent
systemctl is-active --quiet zabbix-agent
systemctl enable zabbix-agent
echo "Zabbix Agent installation completed successfully."

  echo "SUCCESS: Zabbix Agent deployed on $name ($host)"
}

server_arg=""
list_only=false
while (($#)); do
  case "$1" in
    --server)
      (($# >= 2)) || die "--server requires a server ID"
      server_arg="$2"; shift 2 ;;
    --list) list_only=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1 (use --help)" ;;
  esac
done

fetch_servers
trap 'rm -f "${SERVERS_JSONL:-}"' EXIT

if $list_only; then
  list_servers
  exit 0
fi

selected=""
if [[ -n "$server_arg" ]]; then
  while IFS= read -r server; do
    if [[ "$(server_id "$server")" == "$server_arg" ]]; then
      selected="$server"; break
    fi
  done < "$SERVERS_JSONL"
  [[ -n "$selected" ]] || die "RunCloud server ID $server_arg was not found."
else
  echo "RunCloud servers:"
  mapfile -t server_rows < "$SERVERS_JSONL"
  for i in "${!server_rows[@]}"; do
    printf '  %d) %s (ID: %s, host: %s)\n' \
      "$((i + 1))" "$(server_name "${server_rows[$i]}")" \
      "$(server_id "${server_rows[$i]}")" "$(server_host "${server_rows[$i]}")"
  done
  read -r -p "Select the server to deploy Zabbix to: " choice
  [[ "$choice" =~ ^[0-9]+$ ]] || die "Please enter a server number."
  (( choice >= 1 && choice <= ${#server_rows[@]} )) || die "Selection out of range."
  selected="${server_rows[$((choice - 1))]}"
fi

target_id="$(server_id "$selected")"
target_name="$(server_name "$selected")"
target_host="$(server_host "$selected")"
[[ -n "$target_id" && -n "$target_host" ]] || die "Selected server is missing an ID or SSH host/IP in the RunCloud API response."

echo "About to install Zabbix Agent 7.4 on:"
echo "  Server: $target_name"
echo "  ID:     $target_id"
echo "  Host:   $target_host"
read -r -p "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 0; }

deploy_zabbix "$target_host" "$target_name"
