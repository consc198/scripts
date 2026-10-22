#!/usr/bin/env python3
"""Upgrade RunCloud webapp PHP and optionally server PHP-CLI versions.

Place your RunCloud API token in token.txt beside this script.
The token file is intentionally ignored by Git. API calls are made with curl.
"""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

VERSION = "1.7.1"
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
        raise APIError(f"HTTP {status}: {body.strip() or 'request failed'}")

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
        "--server-id",
        help="Only process a single server ID (default: all accessible servers).",
    )
    args = parser.parse_args()
    if args.only_php_cli:
        args.update_php_cli = True
    if args.only_php_cli and args.webapps_file:
        parser.error("--webapps-file cannot be used with --only-php-cli.")
    if args.list_apps_php and (args.apply or args.update_php_cli or args.only_php_cli or args.webapps_file):
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
                    apps = get_all_pages(token, f"/servers/{server_id}/webapps")
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
                    apps = get_all_pages(token, f"/servers/{server_id}/webapps")
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
