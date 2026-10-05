#!/usr/bin/env bash

# Audit WordPress administrator accounts across all RunCloud servers/apps.
#
# Requirements:
#   - curl
#   - jq
#   - ssh
#   - WP-CLI on each WordPress RunCloud app
#
# Authentication:
#   Put the RunCloud API token in token.txt in the same directory as this script.
#
# SSH:
#   SSH is ALWAYS performed as root. The WordPress command is then executed
#   as the application's RunCloud system user.
#
# Optional:
#   export SSH_KEY="$HOME/.ssh/id_rsa"
#   export SSH_PORT="22"
#   export EXCLUDED_USERS='conversal'
#   export DEBUG=1

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_FILE="${TOKEN_FILE:-${SCRIPT_DIR}/token.txt}"
RUNCLOUD_API="https://manage.runcloud.io/api/v3"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_PORT="${SSH_PORT:-22}"
EXCLUDED_USERS="${EXCLUDED_USERS:-conversal}"
DEBUG="${DEBUG:-0}"

# Deliberately hard-coded. The SSH connection must always be root.
SSH_USER="root"

if [[ ! -f "$TOKEN_FILE" ]]; then
    echo "ERROR: RunCloud API token file not found: $TOKEN_FILE" >&2
    echo "Create it with the token on a single line." >&2
    exit 1
fi

RUNCLOUD_TOKEN="$(<"$TOKEN_FILE")"
RUNCLOUD_TOKEN="${RUNCLOUD_TOKEN//$'\r'/}"
RUNCLOUD_TOKEN="${RUNCLOUD_TOKEN//$'\n'/}"

if [[ -z "$RUNCLOUD_TOKEN" ]]; then
    echo "ERROR: RunCloud API token file is empty: $TOKEN_FILE" >&2
    exit 1
fi

for command in curl jq ssh; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: $command" >&2
        exit 1
    fi
done

rc_get() {
    local endpoint="$1"

    curl --fail --silent --show-error --location \
        -H "Authorization: Bearer ${RUNCLOUD_TOKEN}" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        "${RUNCLOUD_API}${endpoint}"
}

rc_all_pages() {
    local endpoint="$1"
    local page=1
    local total_pages=1
    local response

    while (( page <= total_pages )); do
        if [[ "$endpoint" == *\?* ]]; then
            response="$(rc_get "${endpoint}&page=${page}")" || return 1
        else
            response="$(rc_get "${endpoint}?page=${page}")" || return 1
        fi

        echo "$response" | jq -c '.data[]?' || return 1

        total_pages="$(echo "$response" | jq -r '.meta.pagination.total_pages // 1')"
        [[ "$total_pages" =~ ^[0-9]+$ ]] || total_pages=1
        ((page++))
    done
}

is_excluded() {
    local username="${1,,}"
    local excluded

    IFS=',' read -ra excluded_users <<< "$EXCLUDED_USERS"
    for excluded in "${excluded_users[@]}"; do
        excluded="${excluded,,}"
        if [[ "$username" == "$excluded" ]]; then
            return 0
        fi
    done

    return 1
}

ssh_command() {
    local host="$1"
    local command="$2"
    local stderr_file="$3"

    local ssh_args=(
        -i "$SSH_KEY"
        -p "$SSH_PORT"
        -o BatchMode=yes
        -o ConnectTimeout=10
        -o StrictHostKeyChecking=accept-new
    )

    if [[ "$DEBUG" == "1" ]]; then
        ssh_args+=( -v )
    fi

    # IMPORTANT: SSH_USER is hard-coded to root above.
    ssh "${ssh_args[@]}" \
        "root@${host}" \
        "$command" \
        2>"$stderr_file"
}

printf '%-20s %-16s %-28s %-24s %-32s %s\n' \
    "SERVER" "IP" "APP" "USERNAME" "EMAIL" "REGISTERED"
printf '%s\n' "$(printf '%0.s-' {1..150})"

server_count=0
finding_count=0

while IFS= read -r server; do
    [[ -z "$server" ]] && continue

    server_count=$((server_count + 1))

    server_id="$(jq -r '.id' <<< "$server")"
    server_name="$(jq -r '.name // "Unknown"' <<< "$server")"
    server_ip="$(jq -r '.ipAddress // empty' <<< "$server")"

    if [[ -z "$server_ip" ]]; then
        echo "WARN: ${server_name}: no IP address; skipping." >&2
        continue
    fi

    while IFS= read -r app; do
        [[ -z "$app" ]] && continue

        app_id="$(jq -r '.id' <<< "$app")"
        app_name="$(jq -r '.name // "Unknown"' <<< "$app")"
        app_path="$(jq -r '.publicPath // .rootPath // empty' <<< "$app")"
        system_user_id="$(jq -r '.server_user_id // empty' <<< "$app")"

        if [[ -z "$app_path" || -z "$system_user_id" ]]; then
            echo "WARN: ${server_name}/${app_name}: missing application path or system user." >&2
            echo "      App ID: ${app_id}" >&2
            echo "      Path: ${app_path:-<empty>}" >&2
            echo "      System user ID: ${system_user_id:-<empty>}" >&2
            continue
        fi

        user_json="$(rc_get "/servers/${server_id}/users/${system_user_id}")" || {
            echo "WARN: ${server_name}/${app_name}: unable to retrieve system user ${system_user_id}." >&2
            continue
        }

        runcloud_user="$(jq -r '.username // empty' <<< "$user_json")"

        if [[ -z "$runcloud_user" ]]; then
            echo "WARN: ${server_name}/${app_name}: system user has no username." >&2
            continue
        fi

        quoted_path="$(printf '%q' "$app_path")"
        quoted_user="$(printf '%q' "$runcloud_user")"

        remote_command="sudo -u ${quoted_user} -- /bin/bash -lc 'cd ${quoted_path} && wp user list --role=administrator --fields=ID,user_login,user_email,user_registered --format=csv --skip-plugins --skip-themes'"

        if [[ "$DEBUG" == "1" ]]; then
            echo >&2
            echo "DEBUG: server=${server_name}" >&2
            echo "DEBUG: IP=${server_ip}" >&2
            echo "DEBUG: app=${app_name}" >&2
            echo "DEBUG: SSH user=root (hard-coded)" >&2
            echo "DEBUG: RunCloud app user=${runcloud_user}" >&2
            echo "DEBUG: path=${app_path}" >&2
            echo "DEBUG: command=${remote_command}" >&2
        fi

        stderr_file="$(mktemp)"
        admin_csv="$(ssh_command "$server_ip" "$remote_command" "$stderr_file")"
        ssh_status=$?
        ssh_error="$(cat "$stderr_file")"
        rm -f "$stderr_file"

        if (( ssh_status != 0 )); then
            echo "WARN: ${server_name}/${app_name}: SSH/WP-CLI query failed." >&2
            echo "      Server:       ${server_ip}" >&2
            echo "      SSH user:     root" >&2
            echo "      App user:     ${runcloud_user}" >&2
            echo "      App path:     ${app_path}" >&2
            echo "      Exit code:    ${ssh_status}" >&2

            if [[ -n "$ssh_error" ]]; then
                echo "      Error:" >&2
                while IFS= read -r error_line; do
                    echo "        ${error_line}" >&2
                done <<< "$ssh_error"
            else
                echo "      Error: no SSH/WP-CLI error output was returned." >&2
            fi

            if (( ssh_status == 255 )); then
                echo "      Hint: exit code 255 usually indicates an SSH connection or authentication problem." >&2
            elif (( ssh_status == 126 )); then
                echo "      Hint: the command could not be executed. Check sudo permissions, bash, or WP-CLI." >&2
            elif (( ssh_status == 127 )); then
                echo "      Hint: a command was not found. Check that bash, sudo, and WP-CLI are available." >&2
            fi

            continue
        fi

        [[ -z "$admin_csv" ]] && continue

        while IFS=',' read -r user_id username email registered; do
            [[ "$user_id" == "ID" || -z "$username" ]] && continue

            if is_excluded "$username"; then
                continue
            fi

            finding_count=$((finding_count + 1))

            printf '%-20s %-16s %-28s %-24s %-32s %s\n' \
                "$server_name" \
                "$server_ip" \
                "$app_name" \
                "$username" \
                "$email" \
                "$registered"
        done <<< "$admin_csv"

    done < <(rc_all_pages "/servers/${server_id}/webapps?type=wordpress")

done < <(rc_all_pages "/servers")

echo
echo "Servers scanned:           $server_count"
echo "Non-excluded admins found: $finding_count"
echo "Excluded users:             $EXCLUDED_USERS"
