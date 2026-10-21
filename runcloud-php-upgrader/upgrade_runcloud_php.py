#!/usr/bin/env python3
"""Upgrade RunCloud webapps from a selected PHP version to another.

Place your RunCloud API token in token.txt beside this script.
The token file is intentionally ignored by Git. API calls are made with curl.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

VERSION = "1.2.0"
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
        description="Upgrade RunCloud webapps from selected source PHP version(s) to a target version."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply changes. Without this flag, the script only previews them.",
    )
    parser.add_argument(
        "--source-php", nargs="+", default=DEFAULT_SOURCE_PHP, metavar="VERSION",
        help="Source PHP version(s), e.g. php80rc php81rc (default: php80rc php81rc).",
    )
    parser.add_argument(
        "--target-php", default=DEFAULT_TARGET_PHP, metavar="VERSION",
        help="Target PHP version identifier, e.g. php82rc (default: php82rc).",
    )
    parser.add_argument(
        "--server-id",
        help="Only process a single server ID (default: all accessible servers).",
    )
    args = parser.parse_args()
    source_versions = set(args.source_php)
    target_version = args.target_php
    if not source_versions:
        parser.error("Specify at least one source PHP version.")
    if target_version in source_versions:
        parser.error("Target PHP version must differ from all source versions.")
    if not shutil.which("curl"):
        raise SystemExit("curl is required but was not found in PATH.")

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
        print("Mode:", "LIVE CHANGES" if args.apply else "DRY RUN")
        print("Source PHP version(s): " + ", ".join(sorted(source_versions)))
        print(f"Target PHP version: {target_version}")

        # Fetch webapps first so the progress bar has a reliable total.
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
        print(f"Processing {total_apps} webapp(s)...")
        matched = upgraded = failed = processed = 0

        for server, apps in server_apps:
            server_id = server["id"]
            server_name = server.get("name", str(server_id))
            if apps is None:
                failed += 1
                continue

            print(f"\nServer: {server_name} (ID {server_id})")
            for app in apps:
                app_id = app.get("id")
                app_name = app.get("name", f"Webapp {app_id}")
                current_php = app.get("phpVersion", "")
                processed += 1

                if current_php in source_versions:
                    matched += 1
                    print(
                        f"\n  {app_name} (ID {app_id}): "
                        f"{current_php} -> {target_version}"
                    )
                    if args.apply:
                        try:
                            curl_request(
                                "PATCH",
                                f"{BASE_URL}/servers/{server_id}/webapps/{app_id}/settings/php",
                                token,
                                json_body={"phpVersion": target_version},
                            )
                            print("    [OK] Upgrade request accepted.")
                            upgraded += 1
                            time.sleep(0.25)
                        except APIError as exc:
                            print(f"    [ERROR] Upgrade request failed: {exc}")
                            failed += 1

                show_progress(processed, total_apps, "Webapps")

        if total_apps == 0:
            print("No webapps to process.")

        print("\n--- Summary ---")
        print(f"Webapps scanned: {processed}")
        print(f"Matching webapps: {matched}")
        if args.apply:
            print(f"Accepted upgrade requests: {upgraded}")
            print(f"Failures: {failed}")
        else:
            print("No changes made. Use --apply to perform upgrades.")

    except (APIError, ValueError) as exc:
        raise SystemExit(f"RunCloud API request failed: {exc}") from exc


if __name__ == "__main__":
    main()
