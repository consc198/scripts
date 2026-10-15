#!/usr/bin/env bash
# Check every RunCloud web application for an active backup configuration.
# Requirements: curl, jq, and a RunCloud API v3 token.
#
# Usage:
#   export RUNCLOUD_TOKEN="..."
#   bash check-runcloud-backups.sh
#
# Read-only: checks configuration status, not whether the latest backup succeeded.

set -Eeuo pipefail

: "${RUNCLOUD_TOKEN:?Set RUNCLOUD_TOKEN to your RunCloud API token first}"

API_BASE="https://manage.runcloud.io/api/v3"
AUTH_HEADER="Authorization: Bearer ${RUNCLOUD_TOKEN}"
missing=0
checked=0

api_get() {
  curl --fail --silent --show-error --retry 2 --retry-delay 1 \
    -H "${AUTH_HEADER}" -H "Accept: application/json" "${API_BASE}${1}"
}

# Combine the .data arrays from every page of a paginated endpoint.
fetch_all() {
  local endpoint="$1" page=1 response total_pages separator result='[]'
  while true; do
    separator='?'
    [[ "${endpoint}" == *'?'* ]] && separator='&'
    response="$(api_get "${endpoint}${separator}page=${page}&perPage=40")"

    jq -e '.data | type == "array"' >/dev/null <<< "${response}" || {
      echo "Unexpected API response from ${endpoint} (page ${page})." >&2
      return 1
    }

    result="$(jq -cn --argjson old "${result}" \
      --argjson new "$(jq '.data' <<< "${response}")" '$old + $new')"
    total_pages="$(jq -r '.meta.pagination.total_pages // .meta.pagination.totalPages // 1' <<< "${response}")"
    [[ "${total_pages}" =~ ^[0-9]+$ ]] || {
      echo "Could not read pagination metadata for ${endpoint}." >&2
      return 1
    }
    (( page >= total_pages )) && break
    ((page += 1))
  done
  printf '%s\n' "${result}"
}

echo "Fetching all RunCloud servers..."
servers="$(fetch_all "/servers")"
echo "Fetching backup configurations..."
backups="$(fetch_all "/backups")"

while IFS=$'\t' read -r server_id server_name; do
  [[ -n "${server_id}" ]] || continue
  echo
  echo "Server: ${server_name} (ID ${server_id})"
  apps="$(fetch_all "/servers/${server_id}/webapps")"

  while IFS=$'\t' read -r app_id app_name; do
    [[ -n "${app_id}" ]] || continue
    ((checked += 1))
    if jq -e --argjson id "${app_id}" '
      any(.[]?;
        ((.items.webApplicationId // .webApplicationId // .web_application_id) == $id)
        and ((.status // "") == "active")
      )
    ' >/dev/null <<< "${backups}"; then
      printf 'OK      %s (ID %s)\n' "${app_name}" "${app_id}"
    else
      printf 'MISSING %s (ID %s)\n' "${app_name}" "${app_id}"
      ((missing += 1))
    fi
  done < <(jq -r '.[] | [.id, (.name // "unnamed")] | @tsv' <<< "${apps}")
done < <(jq -r '.[] | [.id, (.name // "unnamed")] | @tsv' <<< "${servers}")

echo
echo "Applications checked: ${checked}"
echo "Applications without an active backup configuration: ${missing}"
if (( missing > 0 )); then exit 1; fi
echo "All applications have an active backup configuration."
