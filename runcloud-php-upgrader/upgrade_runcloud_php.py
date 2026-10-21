#!/usr/bin/env python3
"""Upgrade RunCloud webapps on PHP 8.0 or 8.1 to PHP 8.2.

Place your RunCloud API token in token.txt beside this script.
The token file is intentionally ignored by Git.
"""

import argparse
import time
from pathlib import Path

import requests

VERSION = "1.0.0"
BASE_URL = "https://manage.runcloud.io/api/v3"
TARGET_PHP = "php82rc"
OLD_PHP_VERSIONS = {"php80rc", "php81rc"}
PER_PAGE = 40
TOKEN_FILE = Path(__file__).with_name("token.txt")


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


def get_all_pages(session, endpoint):
    """Fetch all pages from a paginated RunCloud API endpoint."""
    results = []
    page = 1

    while True:
        response = session.get(
            f"{BASE_URL}{endpoint}",
            params={"page": page, "perPage": PER_PAGE},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

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


def main():
    parser = argparse.ArgumentParser(
        description="Upgrade RunCloud webapps using PHP 8.0 or 8.1 to PHP 8.2."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, the script only previews them.",
    )
    parser.add_argument(
        "--server-id",
        help="Only process a single server ID (default: all accessible servers).",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {read_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )

    try:
        if args.server_id:
            servers = [{"id": int(args.server_id), "name": args.server_id}]
        else:
            servers = get_all_pages(session, "/servers")

        if not servers:
            print("No servers found.")
            return

        print(f"Found {len(servers)} server(s).")
        print("Mode:", "LIVE CHANGES" if args.apply else "DRY RUN")
        print(f"Target PHP version: {TARGET_PHP}")

        matched = upgraded = failed = 0

        for server in servers:
            server_id = server["id"]
            server_name = server.get("name", str(server_id))
            print(f"\nServer: {server_name} (ID {server_id})")

            try:
                apps = get_all_pages(session, f"/servers/{server_id}/webapps")
            except (requests.RequestException, ValueError) as exc:
                print(f"  [ERROR] Could not list webapps: {exc}")
                failed += 1
                continue

            for app in apps:
                app_id = app.get("id")
                app_name = app.get("name", f"Webapp {app_id}")
                current_php = app.get("phpVersion", "")

                if current_php not in OLD_PHP_VERSIONS:
                    continue

                matched += 1
                print(
                    f"  {app_name} (ID {app_id}): "
                    f"{current_php} -> {TARGET_PHP}"
                )

                if not args.apply:
                    continue

                try:
                    response = session.patch(
                        f"{BASE_URL}/servers/{server_id}/webapps/"
                        f"{app_id}/settings/php",
                        json={"phpVersion": TARGET_PHP},
                        timeout=30,
                    )
                    response.raise_for_status()
                    print("    [OK] Upgrade request accepted.")
                    upgraded += 1
                    time.sleep(0.25)
                except requests.RequestException as exc:
                    print(f"    [ERROR] Upgrade request failed: {exc}")
                    failed += 1

        print("\n--- Summary ---")
        print(f"Matching webapps: {matched}")
        if args.apply:
            print(f"Accepted upgrade requests: {upgraded}")
            print(f"Failures: {failed}")
        else:
            print("No changes made. Use --apply to perform upgrades.")

    except (requests.RequestException, ValueError) as exc:
        raise SystemExit(f"RunCloud API request failed: {exc}") from exc


if __name__ == "__main__":
    main()
