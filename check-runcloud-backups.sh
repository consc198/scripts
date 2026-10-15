#!/usr/bin/env bash
# Audit all RunCloud web applications for active backup configurations.
# Requires curl and jq. Keep token.txt beside this script.
# Creates/overwrites missing-backups.csv beside this script on each run.
# This checks configuration, not whether the latest backup snapshot succeeded.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_FILE="${SCRIPT_DIR}/token.txt"
REPORT_FILE="${SCRIPT_DIR}/missing-backups.csv"

[[ -r "${TOKEN_FILE}" ]] || { echo "ERROR: Missing/unreadable token file: ${TOKEN_FILE}" >&2; exit 1; }
RUNCLOUD_TOKEN="$(tr -d '\r\n' < "${TOKEN_FILE}")"
[[ -n "${RUNCLOUD_TOKEN}" ]] || { echo "ERROR: Token file is empty." >&2; exit 1; }

API_BASE="https://manage.runcloud.io/api/v3"
AUTH_HEADER="Authorization: Bearer ${RUNCLOUD_TOKEN}"
missing=0
checked=0
skipped=0
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

# Start a fresh report for this run. CSV quoting is handled by jq @csv.
printf 'server,server_id,application,application_id,application_type\n' > "${REPORT_FILE}"

api_get() {
  curl --fail --silent --show-error --retry 2 --retry-delay 1 \
    -H "${AUTH_HEADER}" -H "Accept: application/json" "${API_BASE}${1}"
}

# Write paginated records as newline-delimited JSON; avoid huge shell variables.
fetch_all_to_file() {
  local endpoint="$1" output_file="$2" page=1 response total_pages separator
  : > "${output_file}"

  while true; do
    separator='?'
    [[ "${endpoint}" == *'?'* ]] && separator='&'
    response="$(api_get "${endpoint}${separator}page=${page}&perPage=40")"

    jq -e '.data | type == "array"' >/dev/null <<< "${response}" || {
      echo "ERROR: Unexpected API response from ${endpoint} (page ${page})." >&2
      return 1
    }

    jq -c '.data[]' <<< "${response}" >> "${output_file}"
    total_pages="$(jq -r '.meta.pagination.total_pages // .meta.pagination.totalPages // 1' <<< "${response}")"
    [[ "${total_pages}" =~ ^[0-9]+$ ]] || {
      echo "ERROR: Could not read pagination metadata for ${endpoint}." >&2
      return 1
    }
    (( page >= total_pages )) && break
    ((page += 1))
  done
}

servers_file="${WORK_DIR}/servers.jsonl"
backups_file="${WORK_DIR}/backups.jsonl"

echo "Fetching all RunCloud servers..."
fetch_all_to_file "/servers" "${servers_file}"
if [[ ! -s "${servers_file}" ]]; then
  echo "ERROR: RunCloud returned no servers; refusing to report success." >&2
  exit 2
fi

echo "Fetching backup configurations..."
fetch_all_to_file "/backups" "${backups_file}"

while IFS=$'\t' read -r server_id server_name; do
  [[ -n "${server_id}" ]] || continue
  echo
  echo "Server: ${server_name} (ID ${server_id})"

  apps_file="${WORK_DIR}/apps-${server_id}.jsonl"
  fetch_all_to_file "/servers/${server_id}/webapps" "${apps_file}"

  while IFS=$'\t' read -r app_id app_name app_type; do
    [[ -n "${app_id}" ]] || continue

    # RunCloud identifies phpMyAdmin by Application Type.
    if [[ "${app_type,,}" == "phpmyadmin" ]]; then
      printf 'SKIP    %s (ID %s; type: %s) — phpMyAdmin excluded\n' "${app_name}" "${app_id}" "${app_type}"
      ((skipped += 1))
      continue
    fi

    ((checked += 1))

    if jq -s -e --argjson id "${app_id}" '
      any(.[]?;
        ((.items.webApplicationId // .webApplicationId // .web_application_id) == $id)
        and ((.status // "") == "active")
      )
    ' "${backups_file}" >/dev/null; then
      printf 'OK      %s (ID %s)\n' "${app_name}" "${app_id}"
    else
      printf 'MISSING %s (ID %s)\n' "${app_name}" "${app_id}"
      jq -cn --arg server "${server_name}" --arg server_id "${server_id}" \
        --arg app "${app_name}" --arg app_id "${app_id}" --arg type "${app_type}" \
        '[$server, $server_id, $app, $app_id, $type] | @csv' >> "${REPORT_FILE}"
      ((missing += 1))
    fi
  done < <(jq -r '[.id, (.name // "unnamed"), (.applicationType // .application_type // .appType // .type // "")] | @tsv' "${apps_file}")
done < <(jq -r '[.id, (.name // "unnamed")] | @tsv' "${servers_file}")

echo
echo "Applications checked: ${checked}"
echo "phpMyAdmin applications skipped: ${skipped}"
echo "Applications without an active backup configuration: ${missing}"
echo "Missing-backup report: ${REPORT_FILE}"

if (( checked == 0 )); then
  echo "ERROR: No applications were checked; refusing to report success." >&2
  exit 2
fi
if (( missing > 0 )); then exit 1; fi
echo "All audited applications have an active backup configuration."
