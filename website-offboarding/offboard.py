#!/usr/bin/env python3
"""Website offboarding CLI — initial read-only RunCloud discovery phase.

This version deliberately performs no backup, deletion, DNS change, or
RunCloud application modification. It resolves a domain to a RunCloud
server/web application so subsequent phases can be implemented safely.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

API_BASE = "https://manage.runcloud.io/api/v3"
SCRIPT_DIR = Path(__file__).resolve().parent


class OffboardError(RuntimeError):
    pass


def read_token(path: Path) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise OffboardError(f"Cannot read RunCloud token file {path}: {exc}") from exc
    if not token:
        raise OffboardError(f"RunCloud token file is empty: {path}")
    return token


def api_get(session: requests.Session, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    try:
        response = session.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        raise OffboardError(f"RunCloud API request failed: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text[:500]
        raise OffboardError(f"RunCloud API returned HTTP {response.status_code} for {path}: {detail}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise OffboardError(f"RunCloud returned invalid JSON for {path}") from exc
    if not isinstance(payload, dict):
        raise OffboardError(f"Unexpected RunCloud response for {path}")
    return payload


def collection(session: requests.Session, path: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = api_get(session, path, {"page": page, "perPage": 100})
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise OffboardError(f"Unexpected collection response from {path}")
        results.extend(item for item in data if isinstance(item, dict))
        pagination = (payload.get("meta") or {}).get("pagination") or {}
        try:
            total_pages = int(pagination.get("total_pages", page))
        except (TypeError, ValueError):
            total_pages = page
        if page >= total_pages or not data:
            break
        page += 1
    return results


def normalize_host(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    parsed = urlparse(value if "://" in value else "//" + value)
    host = parsed.hostname
    if not host:
        return None
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def get_app_domains(session: requests.Session, server_id: int, app: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for key in ("domainName", "domain", "hostname", "url", "alias"):
        host = normalize_host(app.get(key))
        if host:
            found.add(host)

    app_id = app.get("id")
    if app_id is None:
        return found

    # RunCloud v3 exposes domains under the web application resource. If this
    # endpoint is unavailable on an account, do not silently infer a match.
    try:
        domains = collection(session, f"/servers/{server_id}/webapps/{app_id}/domains")
    except OffboardError:
        return found
    for item in domains:
        for key in ("name", "domainName", "domain", "hostname"):
            host = normalize_host(item.get(key))
            if host:
                found.add(host)
    return found


def discover(session: requests.Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    servers = collection(session, "/servers")
    for server in servers:
        server_id = server.get("id")
        if server_id is None:
            continue
        apps = collection(session, f"/servers/{server_id}/webapps")
        for app in apps:
            domains = get_app_domains(session, int(server_id), app)
            records.append({
                "server_id": server_id,
                "server_name": server.get("name") or f"Server {server_id}",
                "server_ip": server.get("ipAddress") or server.get("ip") or server.get("publicIp"),
                "app_id": app.get("id"),
                "app_name": app.get("name") or f"Web app {app.get('id')}",
                "root_path": app.get("rootPath"),
                "public_path": app.get("publicPath"),
                "domains": sorted(domains),
                "raw_type": app.get("type"),
            })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely plan website offboarding from RunCloud.")
    parser.add_argument("domain", nargs="?", help="Domain to resolve, e.g. example.com")
    parser.add_argument("--plan", action="store_true", help="Resolve and display the target (read-only).")
    parser.add_argument("--inventory", action="store_true", help="List discovered RunCloud web applications.")
    parser.add_argument("--token-file", default=os.environ.get("RUNCLOUD_TOKEN_FILE", str(SCRIPT_DIR / "token.txt")))
    args = parser.parse_args()

    if not args.inventory and not (args.domain and args.plan):
        parser.error("Specify DOMAIN --plan or --inventory. This initial version is read-only.")

    try:
        token = read_token(Path(args.token_file))
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        records = discover(session)

        if args.inventory:
            for item in records:
                print(
                    f"{item['server_name']} ({item['server_ip'] or 'no IP'}) | "
                    f"{item['app_name']} [ID {item['app_id']}] | "
                    f"{', '.join(item['domains']) or 'no domain data'}"
                )
            print(f"\nDiscovered {len(records)} application(s).")
            return 0

        target = normalize_host(args.domain)
        matches = [item for item in records if target in item["domains"]]
        if not matches:
            raise OffboardError(
                f"No exact RunCloud domain match found for {target}. "
                "No changes were made. Check the domain assignment in RunCloud."
            )
        if len(matches) > 1:
            lines = [
                f"- {m['server_name']} / {m['app_name']} (app ID {m['app_id']})"
                for m in matches
            ]
            raise OffboardError(
                f"Ambiguous domain match for {target}; refusing to choose:\n" + "\n".join(lines)
            )

        item = matches[0]
        print("READ-ONLY OFFBOARDING PLAN")
        print("==========================")
        print(f"Domain:       {target}")
        print(f"Server:       {item['server_name']} (ID {item['server_id']})")
        print(f"SSH host:     {item['server_ip'] or 'NOT RETURNED BY RUNCloud'}")
        print(f"Application:  {item['app_name']} (ID {item['app_id']})")
        print(f"Root path:    {item['root_path'] or 'NOT RETURNED'}")
        print(f"Public path:  {item['public_path'] or 'NOT RETURNED'}")
        print("\nPlanned next steps (not executed in this version):")
        print("  1. SSH backup of application files and WordPress database")
        print("  2. Upload backup to Box and verify it")
        print("  3. Remove StatusCake and Mailgun entries")
        print("  4. Disconnect Wordfence Central and ManageWP where supported")
        print("\nNot in scope: taking the site offline or deleting/modifying its RunCloud app.")
        return 0
    except (OffboardError, requests.RequestException, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
