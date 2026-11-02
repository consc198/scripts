#!/usr/bin/env python3
"""Upgrade RunCloud webapp PHP and optionally server PHP-CLI versions.

Place your RunCloud API token in token.txt beside this script.
The token file is intentionally ignored by Git. API calls are made with curl.
"""

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

VERSION = "1.8.0"
BASE_URL = "https://manage.runcloud.io/api/v3"
DEFAULT_SOURCE_PHP = ["php80rc", "php81rc"]
DEFAULT_TARGET_PHP = "php82rc"
PER_PAGE = 40
TOKEN_FILE = Path(__file__).with_name("token.txt")


class APIError(RuntimeError):
    """Raised when curl or the RunCloud API request fails."""


def read_token():
    if not TOKEN_FILE.is_file():
        raise SystemExit(
            f"Missing {TOKEN_FILE.name}. Create it beside this script "
            "and put your RunCloud API token in it."
        )
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit(f"{TOKEN_FILE.name} is empty.")
    return token


def curl_request(method, url, token, params=None, json_body=None):
    """Make an HTTP request with curl and return the decoded JSON response."""
    if params:
        url = f"{url}?{urlencode(params)}"

    command = [
        "curl", "--silent", "--show-error", "--location",
        "--write-out", "\\n%{http_code}",
        "--request", method,
        "--header", f"Authorization: Bearer {token}",
        "--header", "Accept: application/json",
        "--header", "Content-Type: application/json",
        "--connect-timeout", "15",
        "--max-time", "30",
        url,
    ]
    if json_body is not None:
        command.extend(["--data-binary", json.dumps(json_body)])

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise APIError(f"Could not run curl: {exc}") from exc

    body, separator, status_text = result.stdout.rpartition("\n")
    if not separator:
        body, status_text = result.stdout, ""

    if result.returncode != 0:
        detail = result.stderr.strip() or body.strip() or "unknown curl error"
        raise APIError(f"curl failed: {detail}")

    try:
        status = int(status_text.strip())
    except ValueError as exc:
        raise APIError("Could not determine HTTP status from curl response.") from exc

    if not 200 <= status < 300:
        detail = body.strip() or "request failed"
        if len(detail) > 500:
            detail = detail[:500] + "... [response truncated]"
        raise APIError(f"HTTP {status}: {detail}")

    if not body.strip():
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise APIError("RunCloud API returned invalid JSON.") from exc


def get_all_pages(token, endpoint):
    """Fetch all pages from a paginated RunCloud API endpoint."""
    results = []
    page = 1
    while True:
        payload = curl_request(
            "GET", f"{BASE_URL}{endpoint}", token,
            params={"page": page, "perPage": PER_PAGE},
        )
        if isinstance(payload, list):
            return results + payload
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected API response for {endpoint}")

        items = payload.get("data", [])
        if not isinstance(items, list):
            raise ValueError(f"Unexpected data format for {endpoint}")
        results.extend(items)

        pagination = payload.get("meta", {}).get("pagination", {})
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            if page >= int(total_pages):
                break
        elif len(items) < PER_PAGE:
            break
        page += 1
    return results





def get_webapps_with_retry(token, server_id, server_name, max_attempts=5):
    """Retry transient webapp-list failures, including rate limits and server errors."""
    endpoint = f"/servers/{server_id}/webapps"
    for attempt in range(1, max_attempts + 1):
        try:
            return get_all_pages(token, endpoint)
        except APIError as exc:
            message = str(exc)
            retryable = any(
                code in message
                for code in ("HTTP 429:", "HTTP 500:", "HTTP 502:", "HTTP 503:", "HTTP 504:")
            )
            if not retryable or attempt >= max_attempts:
                raise
            delay = 15 * (2 ** (attempt - 1))
            print(
                f"  [RETRY] Could not list webapps for {server_name} "
                f"(attempt {attempt}/{max_attempts}): {message.splitlines()[0]} "
                f"Retrying in {delay} seconds...",
                flush=True,
            )
            time.sleep(delay)


def get_webapp_url(app):
    """Return a URL/domain exposed in the webapp API data, if available."""
    for key in ("url", "URL", "domain", "primaryDomain", "webappUrl", "siteUrl"):
        value = app.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if key.lower() == "domain" or "://" not in value:
                return "https://" + value
            return value

    for key in ("domains", "websites", "hosts"):
        values = app.get(key)
        if isinstance(values, list) and values:
            first = values[0]
            if isinstance(first, str) and first.strip():
                value = first.strip()
                return value if "://" in value else "https://" + value
            if isinstance(first, dict):
                for nested_key in ("url", "domain", "name", "host"):
                    value = first.get(nested_key)
                    if isinstance(value, str) and value.strip():
                        value = value.strip()
                        return value if "://" in value else "https://" + value
        elif isinstance(values, str) and values.strip():
            value = values.strip()
            return value if "://" in value else "https://" + value

    return "Not provided"


def classify_webapp(app):
    """Best-effort app type label using fields returned by the RunCloud API."""
    explicit_fields = (
        "webappType", "applicationType", "appType", "type",
        "framework", "stack", "deploymentType",
    )
    explicit_values = []
    for key in explicit_fields:
        value = app.get(key)
        if isinstance(value, str) and value.strip():
            explicit_values.append(value.strip())

    text_values = list(explicit_values)
    for key in ("name", "rootPath", "path", "appPath", "documentRoot", "publicPath"):
        value = app.get(key)
        if isinstance(value, str) and value.strip():
            text_values.append(value.strip())

    combined = " ".join(text_values).lower()
    if "wordpress" in combined or "wp-content" in combined or "wp-includes" in combined:
        return "WordPress"
    if "laravel" in combined or "/artisan" in combined or "artisan" in combined:
        return "Laravel"

    for value in explicit_values:
        normalized = value.lower().replace("_", " ").replace("-", " ")
        if "custom" in normalized:
            return "Custom"
        if "wordpress" in normalized:
            return "WordPress"
        if "laravel" in normalized:
            return "Laravel"

    return explicit_values[0] if explicit_values else "Unknown"


def run_pm_max_children_update(token, servers, args, requested_names):
    """Preview or update webapps whose current PHP-FPM max children equals a value."""
    matches = []
    processed = 0
    for index, server in enumerate(servers, 1):
        server_id = server["id"]
        server_name = server.get("name", str(server_id))
        print(f"Fetching webapps for server {index}/{len(servers)}: {server_name}...", flush=True)
        try:
            apps = get_webapps_with_retry(token, server_id, server_name)
        except (APIError, ValueError) as exc:
            print(f"  [ERROR] Could not list webapps: {exc}")
            continue
        for app in apps:
            processed += 1
            app_name = app.get("name", f"Webapp {app.get('id', '')}")
            if requested_names is not None and app_name not in requested_names:
                continue
            app_id = app.get("id")
            if app_id is None:
                print(f"  [SKIP] {server_name} / {app_name}: missing webapp ID")
                continue
            try:
                settings = curl_request(
                    "GET", f"{BASE_URL}/servers/{server_id}/webapps/{app_id}/settings", token
                )
                if not isinstance(settings, dict):
                    raise APIError("Unexpected webapp settings response.")
                current = settings.get("processManagerMaxChildren")
                if current is not None and str(current) == str(args.update_pm_max_children[0]):
                    matches.append((server, app, settings, current))
            except APIError as exc:
                print(f"  [ERROR] Could not read settings for {server_name} / {app_name}: {exc}")

    old_value, new_value = args.update_pm_max_children
    print(f"\nScanned {processed} webapp(s); found {len(matches)} with pm.max_children={old_value}.")
    print(f"Target value: {new_value}")
    print("Mode:", "LIVE CHANGES" if args.apply else "DRY RUN")
    batch_count = (len(matches) + args.batch_size - 1) // args.batch_size
    updated = failed = 0
    for batch_index, offset in enumerate(range(0, len(matches), args.batch_size), 1):
        batch = matches[offset:offset + args.batch_size]
        print(f"\nBatch {batch_index}/{batch_count} ({len(batch)} webapp(s))")
        for server, app, settings, current in batch:
            server_id = server["id"]
            app_id = app["id"]
            server_name = server.get("name", str(server_id))
            app_name = app.get("name", f"Webapp {app_id}")
            print(f"  {server_name} / {app_name} (ID {app_id}): {current} -> {new_value}")
            if not args.apply:
                continue
            payload = dict(settings)
            payload["stack"] = app.get("stack")
            payload["stackMode"] = app.get("stackMode")
            if "publicPath" in app:
                payload["publicPath"] = app.get("publicPath")
            payload["processManagerMaxChildren"] = new_value
            try:
                curl_request(
                    "PATCH",
                    f"{BASE_URL}/servers/{server_id}/webapps/{app_id}/settings/fpmnginx",
                    token,
                    json_body=payload,
                )
                print("    [OK] PHP-FPM settings update request accepted.")
                updated += 1
            except APIError as exc:
                print(f"    [ERROR] PHP-FPM settings update failed: {exc}")
                failed += 1
            time.sleep(0.25)
        if batch_index < batch_count and args.apply:
            print(f"Batch {batch_index}/{batch_count} complete; pausing 10 minutes before the next batch...")
            time.sleep(600)

    print("\n--- PHP-FPM max children summary ---")
    print(f"Webapps scanned: {processed}")
    print(f"Matching webapps: {len(matches)}")
    if args.apply:
        print(f"Accepted update requests: {updated}")
        print(f"Failures: {failed}")
    else:
        print("No changes made. Review the matches, then add --apply to update them.")




def get_server_ip(server):
    """Find a public/reachable server address in the RunCloud server record."""
    for key in ("ipAddress", "ip", "publicIp", "publicIP", "ip_address", "address"):
        value = server.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def scan_server_max_children_logs(server):
    """SSH to a server and return parsed max_children warning records."""
    server_name = server.get("name", str(server.get("id", "unknown")))
    server_ip = get_server_ip(server)
    if not server_ip:
        raise RuntimeError("No server IP address was present in the RunCloud server record.")

    remote_command = (
        "grep -hE '^\\\\[[^]]+\\\\] WARNING: \\\\[pool [^]]+\\\\] "
        "server reached max_children setting \\\\([0-9]+\\\\)' "
        "/var/log/php*rc-fpm.log 2>/dev/null || true"
    )
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2",
        f"root@{server_ip}", remote_command,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"SSH scan failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"ssh exited with status {result.returncode}"
        raise RuntimeError(detail[:500])

    pattern = re.compile(
        r"^\\[([^]]+)\\]\\s+WARNING:\\s+\\[pool\\s+([^]]+)\\]\\s+"
        r"server reached max_children setting\\s+\\((\\d+)\\)"
    )
    hits = []
    for line in result.stdout.splitlines():
        match = pattern.search(line.strip())
        if match:
            hits.append({
                "server_name": server_name,
                "server_id": str(server.get("id", "")),
                "server_ip": server_ip,
                "timestamp": match.group(1),
                "pool": match.group(2).strip(),
                "limit": int(match.group(3)),
            })
    return hits


def normalize_pool_name(value):
    """Normalize pool and webapp labels for conservative exact matching."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def find_webapp_for_pool(apps, pool_name):
    """Match a log pool to a webapp using exact normalized metadata labels."""
    target = normalize_pool_name(pool_name)
    if not target:
        return None
    for app in apps:
        candidates = [app.get("name")]
        for key in ("pool", "poolName", "phpFpmPool", "phpFpmPoolName"):
            candidates.append(app.get(key))
        if any(value and normalize_pool_name(value) == target for value in candidates):
            return app
    return None


def run_max_children_log_report(token, servers, args):
    """Scan PHP-FPM logs and optionally raise limits only for reported webapps."""
    all_hits = []
    apps_by_server = {}
    for index, server in enumerate(servers, 1):
        server_name = server.get("name", str(server.get("id", "unknown")))
        print(f"Scanning PHP-FPM logs on server {index}/{len(servers)}: {server_name}...", flush=True)
        try:
            hits = scan_server_max_children_logs(server)
            all_hits.extend(hits)
            print(f"  Found {len(hits)} max_children warning(s).")
        except RuntimeError as exc:
            print(f"  [ERROR] {server_name}: {exc}")

    # Aggregate repeated warnings for the same server/pool/limit.
    aggregated = {}
    for hit in all_hits:
        key = (hit["server_id"], hit["pool"], hit["limit"])
        if key not in aggregated:
            aggregated[key] = dict(hit, occurrences=0)
        aggregated[key]["occurrences"] += 1
        aggregated[key]["timestamp"] = hit["timestamp"]

    rows = sorted(aggregated.values(), key=lambda row: (row["server_name"].lower(), row["pool"].lower(), row["limit"]))
    print("\n--- PHP-FPM max_children log report ---")
    if not rows:
        print("No max_children limit warnings were found in /var/log/php*rc-fpm.log.")
        return

    headers = ("SERVER", "SERVER IP", "POOL / WEBAPP", "CURRENT LIMIT", "HITS", "LATEST LOG TIME")
    values = [
        (r["server_name"], r["server_ip"], r["pool"], str(r["limit"]),
         str(r["occurrences"]), r["timestamp"])
        for r in rows
    ]
    widths = [max(len(headers[i]), *(len(row[i]) for row in values)) for i in range(len(headers))]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in values:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    print(f"\nFound {len(rows)} server/pool/limit combination(s), across {sum(r['occurrences'] for r in rows)} warning line(s).")

    if not args.update_hit_max_children:
        print("Read-only report. To raise a selected limit, rerun with --update-hit-max-children FROM TO.")
        return

    from_limit, to_limit = args.update_hit_max_children
    print(f"\nPreparing updates for reported pools at limit {from_limit}: {from_limit} -> {to_limit}")
    server_lookup = {str(server.get("id", "")): server for server in servers}
    candidates = []
    for row in rows:
        if row["limit"] != from_limit:
            continue
        server = server_lookup.get(row["server_id"])
        if server is None:
            continue
        server_id = row["server_id"]
        if server_id not in apps_by_server:
            try:
                apps_by_server[server_id] = get_webapps_with_retry(
                    token, server_id, row["server_name"]
                )
            except (APIError, ValueError) as exc:
                print(f"  [ERROR] Could not retrieve webapps for {row['server_name']}: {exc}")
                apps_by_server[server_id] = None
        apps = apps_by_server[server_id]
        if apps is None:
            continue
        app = find_webapp_for_pool(apps, row["pool"])
        if app is None:
            print(f"  [UNMATCHED] {row['server_name']} / pool '{row['pool']}': no exact webapp-name/pool metadata match.")
            continue
        app_id = app.get("id")
        try:
            settings = curl_request(
                "GET", f"{BASE_URL}/servers/{server_id}/webapps/{app_id}/settings", token
            )
            if not isinstance(settings, dict):
                raise APIError("Unexpected webapp settings response.")
            current = settings.get("processManagerMaxChildren")
            if current is None or int(current) != from_limit:
                print(
                    f"  [SKIP] {row['server_name']} / {app.get('name', app_id)}: "
                    f"current API setting is {current!r}, not {from_limit}."
                )
                continue
            candidates.append((row, server, app, settings))
        except (APIError, TypeError, ValueError) as exc:
            print(f"  [ERROR] Could not verify {row['server_name']} / {app.get('name', app_id)}: {exc}")

    print(f"\nVerified {len(candidates)} webapp(s) with a log hit at {from_limit} and a current setting of {from_limit}.")
    print("Mode:", "LIVE CHANGES" if args.apply else "DRY RUN")
    for row, server, app, settings in candidates:
        print(
            f"  {row['server_name']} / {app.get('name', '(unnamed)')} "
            f"(pool {row['pool']}, webapp ID {app.get('id')}): {from_limit} -> {to_limit}"
        )
        if not args.apply:
            continue
        payload = dict(settings)
        payload["stack"] = app.get("stack")
        payload["stackMode"] = app.get("stackMode")
        if "publicPath" in app:
            payload["publicPath"] = app.get("publicPath")
        payload["processManagerMaxChildren"] = to_limit
        try:
            curl_request(
                "PATCH",
                f"{BASE_URL}/servers/{server['id']}/webapps/{app['id']}/settings/fpmnginx",
                token,
                json_body=payload,
            )
            print("    [OK] PHP-FPM settings update request accepted.")
        except APIError as exc:
            print(f"    [ERROR] PHP-FPM settings update failed: {exc}")
        time.sleep(0.25)

    if args.apply:
        print(f"\nSubmitted {len(candidates)} PHP-FPM settings update request(s).")
    else:
        print("\nNo changes made. Review the verified webapps, then add --apply to update them.")


def show_progress(done, total, label="Processing"):
    """Render a compact terminal progress bar."""
    width = 30
    fraction = done / total if total else 1
    filled = int(width * fraction)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r{label}: [{bar}] {done}/{total} ({fraction:.0%})", end="", flush=True)
    if done >= total:
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Upgrade RunCloud webapp PHP and optionally server PHP-CLI versions."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply changes. Without this flag, the script only previews them.",
    )
    parser.add_argument(
        "--source-php", nargs="+", default=DEFAULT_SOURCE_PHP, metavar="VERSION",
        help="Source PHP version(s) for webapps and, if enabled, PHP-CLI (default: php80rc php81rc).",
    )
    parser.add_argument(
        "--target-php", default=DEFAULT_TARGET_PHP, metavar="VERSION",
        help="Target PHP version for webapps and, if enabled, PHP-CLI (default: php82rc).",
    )
    parser.add_argument(
        "--update-php-cli", action="store_true",
        help="Also update each server's PHP-CLI version when it matches --source-php, using --target-php.",
    )
    parser.add_argument(
        "--only-php-cli", action="store_true",
        help="Update only server PHP-CLI versions; do not inspect or change webapp PHP versions.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=10, metavar="N",
        help="Number of matching webapps to update per batch (default: 10).",
    )
    parser.add_argument(
        "--webapps-file", type=Path, metavar="FILE",
        help="Only process webapps whose exact names appear in this text file (one name per line).",
    )
    parser.add_argument(
        "--list-apps-php", metavar="VERSION",
        help="List webapps running this PHP version and show their detected app type; makes no changes.",
    )
    parser.add_argument(
        "--scan-max-children", action="store_true",
        help="SSH to every selected server and report PHP-FPM max_children limit warnings.",
    )
    parser.add_argument(
        "--update-hit-max-children", nargs=2, type=int, metavar=("FROM", "TO"),
        help="Scan logs, then raise only reported webapps whose current limit equals FROM.",
    )
    parser.add_argument(
        "--update-pm-max-children", nargs=2, type=int, metavar=("FROM", "TO"),
        help="Bulk-change PHP-FPM pm.max_children only where its current value exactly equals FROM.",
    )
    parser.add_argument(
        "--server-id",
        help="Only process a single server ID (default: all accessible servers).",
    )
    args = parser.parse_args()
    if args.only_php_cli:
        args.update_php_cli = True
    if args.update_hit_max_children:
        from_limit, to_limit = args.update_hit_max_children
        if from_limit < 1 or to_limit < 1 or from_limit == to_limit:
            parser.error("Log-based PHP-FPM limits must be positive and different.")
        args.scan_max_children = True
        if args.update_pm_max_children or args.update_php_cli or args.only_php_cli or args.list_apps_php:
            parser.error("--update-hit-max-children cannot be combined with other update or inventory modes.")
    if args.scan_max_children and (args.update_pm_max_children or args.update_php_cli or args.only_php_cli or args.list_apps_php):
        parser.error("--scan-max-children cannot be combined with PHP-version, PHP-CLI, or inventory update modes.")
    if args.update_pm_max_children:
        old_children, new_children = args.update_pm_max_children
        if old_children < 1 or new_children < 1:
            parser.error("PHP-FPM max children values must be positive integers.")
        if old_children == new_children:
            parser.error("The source and target pm.max_children values must differ.")
        if args.update_php_cli or args.only_php_cli or args.list_apps_php:
            parser.error("--update-pm-max-children cannot be combined with PHP-CLI or inventory modes.")
    if args.only_php_cli and args.webapps_file:
        parser.error("--webapps-file cannot be used with --only-php-cli.")
    if args.list_apps_php and (args.apply or args.update_php_cli or args.only_php_cli or args.webapps_file or args.update_pm_max_children):
        parser.error("--list-apps-php is a read-only inventory mode and cannot be combined with update options or --webapps-file.")
    source_versions = set(args.source_php)
    target_version = args.target_php
    if not source_versions:
        parser.error("Specify at least one source PHP version.")
    if target_version in source_versions:
        parser.error("Target PHP version must differ from all source versions.")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1.")
    if not shutil.which("curl"):
        raise SystemExit("curl is required but was not found in PATH.")

    requested_webapp_names = None
    if args.webapps_file:
        if not args.webapps_file.is_file():
            parser.error(f"Webapp list file not found: {args.webapps_file}")
        try:
            requested_webapp_names = {
                line.strip()
                for line in args.webapps_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            }
        except OSError as exc:
            parser.error(f"Could not read webapp list file: {exc}")
        if not requested_webapp_names:
            parser.error(f"No webapp names found in {args.webapps_file}")
        print(f"Loaded {len(requested_webapp_names)} webapp name(s) from {args.webapps_file}.")

    token = read_token()

    try:
        print("Fetching server list...", flush=True)
        if args.server_id:
            try:
                servers = [{"id": int(args.server_id), "name": args.server_id}]
            except ValueError:
                parser.error("--server-id must be an integer.")
        else:
            servers = get_all_pages(token, "/servers")

        if not servers:
            print("No servers found.")
            return

        print(f"Found {len(servers)} server(s).")

        if args.list_apps_php:
            print(f"\nListing webapps running {args.list_apps_php} (read-only)...")
            rows = []
            for index, server in enumerate(servers, 1):
                server_id = server["id"]
                server_name = server.get("name", str(server_id))
                print(f"Fetching webapps for server {index}/{len(servers)}: {server_name}...", flush=True)
                try:
                    apps = get_webapps_with_retry(token, server_id, server_name)
                except (APIError, ValueError) as exc:
                    print(f"  [ERROR] Could not list webapps: {exc}")
                    continue
                for app in apps:
                    if app.get("phpVersion", "") == args.list_apps_php:
                        rows.append((
                            server_name,
                            str(server_id),
                            str(app.get("name", "(unnamed)")),
                            classify_webapp(app),
                            get_webapp_url(app),
                            str(app.get("id", "")),
                        ))

            if rows:
                headers = ("SERVER", "SERVER ID", "WEBAPP NAME", "APP TYPE", "URL", "WEBAPP ID")
                widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
                print()
                print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
                print("  ".join("-" * widths[i] for i in range(len(headers))))
                for row in rows:
                    print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
                print(f"\nFound {len(rows)} webapp(s) using {args.list_apps_php}.")
            else:
                print(f"No webapps found using {args.list_apps_php}.")
            print("App type is inferred from available API metadata and paths; 'Unknown' means the API response did not provide enough clues.")
            return

        if args.scan_max_children:
            run_max_children_log_report(token, servers, args)
            return

        if args.update_pm_max_children:
            run_pm_max_children_update(token, servers, args, requested_webapp_names)
            return

        print("Mode:", "LIVE CHANGES" if args.apply else "DRY RUN")
        print("Source PHP version(s): " + ", ".join(sorted(source_versions)))
        print(f"Target PHP version: {target_version}")
        if args.update_php_cli:
            print("PHP-CLI updates: enabled (server-level)")
        if args.only_php_cli:
            print("Mode: PHP-CLI only; webapp PHP will not be changed.")

        matched = upgraded = failed = 0
        cli_matched = cli_upgraded = cli_failed = 0

        # CLI version is server-level, so evaluate it once per server.
        if args.update_php_cli:
            print("\nChecking server PHP-CLI versions...")
            for server in servers:
                server_id = server["id"]
                server_name = server.get("name", str(server_id))
                current_cli = server.get("phpCLIVersion", "")
                if current_cli not in source_versions:
                    print(f"  {server_name}: PHP-CLI {current_cli or 'unknown'} — no match")
                    continue

                cli_matched += 1
                print(f"  {server_name} (ID {server_id}): PHP-CLI {current_cli} -> {target_version}")
                if args.apply:
                    try:
                        curl_request(
                            "PATCH",
                            f"{BASE_URL}/servers/{server_id}/php/cli",
                            token,
                            json_body={"phpVersion": target_version},
                        )
                        print("    [OK] PHP-CLI update request accepted.")
                        cli_upgraded += 1
                        time.sleep(0.25)
                    except APIError as exc:
                        print(f"    [ERROR] PHP-CLI update request failed: {exc}")
                        cli_failed += 1

        if not args.only_php_cli:
            # Fetch webapps first so progress totals are known before processing.
            server_apps = []
            for index, server in enumerate(servers, 1):
                server_id = server["id"]
                server_name = server.get("name", str(server_id))
                print(f"Fetching webapps for server {index}/{len(servers)}: {server_name}...", flush=True)
                try:
                    apps = get_webapps_with_retry(token, server_id, server_name)
                    server_apps.append((server, apps))
                except (APIError, ValueError) as exc:
                    print(f"  [ERROR] Could not list webapps: {exc}")
                    server_apps.append((server, None))

            total_apps = sum(len(apps) for _, apps in server_apps if apps is not None)
            matches = []
            processed = 0
            found_names = set()
            source_mismatch_names = set()
            for server, apps in server_apps:
                if apps is None:
                    failed += 1
                    continue
                for app in apps:
                    processed += 1
                    current_php = app.get("phpVersion", "")
                    app_name = app.get("name", "")
                    if requested_webapp_names is not None and app_name not in requested_webapp_names:
                        show_progress(processed, total_apps, "Scanning webapps")
                        continue
                    if requested_webapp_names is not None:
                        found_names.add(app_name)
                    if current_php in source_versions:
                        matches.append((server, app, current_php))
                    elif requested_webapp_names is not None:
                        source_mismatch_names.add(app_name)
                    show_progress(processed, total_apps, "Scanning webapps")

            matched = len(matches)
            print(f"\nScanned {processed} webapp(s); {len(matches)} match(es) found.")
            if requested_webapp_names is not None:
                missing_names = requested_webapp_names - found_names
                print(f"Names found in list: {len(found_names)}")
                if source_mismatch_names:
                    print("Listed webapps not using a selected source PHP version: " +
                          ", ".join(sorted(source_mismatch_names)))
                if missing_names:
                    print("Listed webapp names not found: " + ", ".join(sorted(missing_names)))
            if requested_webapp_names is not None:
                print("Webapp selection: names from file (exact, case-sensitive matches)")
            print(f"Webapp update batch size: {args.batch_size}")
            batch_count = (len(matches) + args.batch_size - 1) // args.batch_size

            for batch_index, offset in enumerate(range(0, len(matches), args.batch_size), 1):
                batch = matches[offset:offset + args.batch_size]
                print(f"\nBatch {batch_index}/{batch_count} ({len(batch)} webapp(s))")
                for server, app, current_php in batch:
                    server_id = server["id"]
                    server_name = server.get("name", str(server_id))
                    app_id = app.get("id")
                    app_name = app.get("name", f"Webapp {app_id}")
                    print(f"  {server_name} / {app_name} (ID {app_id}): {current_php} -> {target_version}")
                    if args.apply:
                        try:
                            curl_request(
                                "PATCH",
                                f"{BASE_URL}/servers/{server_id}/webapps/{app_id}/settings/php",
                                token,
                                json_body={"phpVersion": target_version},
                            )
                            print("    [OK] Webapp PHP update request accepted.")
                            upgraded += 1
                        except APIError as exc:
                            print(f"    [ERROR] Webapp PHP update request failed: {exc}")
                            failed += 1
                        time.sleep(0.25)
                if batch_index < batch_count and args.apply:
                    print(f"Batch {batch_index}/{batch_count} complete; pausing 10 minutes before the next batch...")
                    time.sleep(600)

            if total_apps == 0:
                print("No webapps to process.")
        else:
            print("\nSkipping webapp PHP scan because --only-php-cli was specified.")

        print("\n--- Summary ---")
        if not args.only_php_cli:
            print(f"Webapps scanned: {processed}")
            print(f"Matching webapps: {matched}")
            if args.apply:
                print(f"Accepted webapp PHP update requests: {upgraded}")
                print(f"Webapp/listing failures: {failed}")
            else:
                print("No webapp changes made. Use --apply to perform upgrades.")

        if args.update_php_cli:
            print(f"Matching server PHP-CLI versions: {cli_matched}")
            if args.apply:
                print(f"Accepted PHP-CLI update requests: {cli_upgraded}")
                print(f"PHP-CLI failures: {cli_failed}")
            else:
                print("No PHP-CLI changes made. Use --apply to perform upgrades.")

    except (APIError, ValueError) as exc:
        raise SystemExit(f"RunCloud API request failed: {exc}") from exc


if __name__ == "__main__":
    main()
