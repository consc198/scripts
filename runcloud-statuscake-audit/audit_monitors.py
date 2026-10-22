#!/usr/bin/env python3
"""Audit RunCloud web applications against StatusCake uptime monitors.

Reads API credentials from token.txt and statuscaketoken.txt in the current
working directory (or paths supplied with command-line options). Writes
webapps_missing_statuscake.txt containing web apps with no matching monitor.

Matching is hostname-first using RunCloud web-app domains and StatusCake
website_url values. Exact web-app name/alias to monitor-name matching is a
fallback. This script is read-only: it never creates or changes monitors.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

RUNcloud_BASE = "https://manage.runcloud.io/api/v3"
STATUSCAKE_BASE = "https://api.statuscake.com/v1"


class ApiError(RuntimeError):
    pass


def read_token(path: Path, label: str) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ApiError(f"Cannot read {label} token file '{path}': {exc}") from exc
    if not token:
        raise ApiError(f"The {label} token file '{path}' is empty.")
    return token


def request_json(url: str, headers: dict[str, str], *, retries: int = 3) -> dict[str, Any]:
    for attempt in range(retries):
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                if not isinstance(payload, dict):
                    raise ApiError(f"Expected a JSON object from {url}")
                return payload
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(f"API request failed ({exc.code}) for {url}: {body}") from exc
        except URLError as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(f"Network error calling {url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ApiError(f"Invalid JSON returned by {url}") from exc
    raise ApiError(f"Request failed after retries: {url}")


def get_data(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", [])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def pagination_pages(payload: dict[str, Any]) -> int:
    meta = payload.get("meta") or payload.get("metadata") or {}
    pagination = meta.get("pagination") or meta
    try:
        return max(1, int(pagination.get("total_pages", 1)))
    except (TypeError, ValueError, AttributeError):
        return 1


def runcloud_get(token: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{RUNcloud_BASE}{path}"
    if params:
        url += "?" + urlencode(params)
    return request_json(url, {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })


def statuscake_get(token: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{STATUSCAKE_BASE}{path}"
    if params:
        url += "?" + urlencode(params)
    return request_json(url, {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })


def fetch_runcloud_collection(token: str, path: str) -> list[dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = runcloud_get(token, path, {"page": page, "perPage": 100})
        items = get_data(payload)
        all_items.extend(items)
        pages = pagination_pages(payload)
        if page >= pages or not items:
            break
        page += 1
    return all_items


def fetch_statuscake_monitors(token: str) -> list[dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = statuscake_get(token, "/uptime", {"page": page, "limit": 100, "nouptime": "true"})
        items = get_data(payload)
        all_items.extend(items)
        pages = pagination_pages(payload)
        if page >= pages or not items:
            break
        page += 1
    return all_items


def normalize_hostname(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if "://" not in value:
        value = "//" + value
    try:
        host = urlparse(value).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def monitor_hostnames(monitors: list[dict[str, Any]]) -> set[str]:
    hosts: set[str] = set()
    for monitor in monitors:
        for field in ("website_url", "url", "domain", "hostname"):
            host = normalize_hostname(monitor.get(field))
            if host:
                hosts.add(host)
    return hosts


def monitor_names(monitors: list[dict[str, Any]]) -> set[str]:
    return {
        str(monitor.get(field)).strip().casefold()
        for monitor in monitors
        for field in ("name",)
        if monitor.get(field) is not None and str(monitor.get(field)).strip()
    }


def webapp_domains(token: str, server_id: Any, app: dict[str, Any]) -> set[str]:
    domains: set[str] = set()
    # The domains endpoint is available on RunCloud's server/webapp API.
    # If unavailable for a particular account/API version, use fields from the
    # web-app object and name/alias matching instead.
    app_id = app.get("id")
    if app_id is not None:
        try:
            payload = runcloud_get(token, f"/servers/{server_id}/webapps/{app_id}/domains", {"page": 1, "perPage": 100})
            entries = get_data(payload)
            for entry in entries:
                for field in ("name", "domainName", "domain", "hostname"):
                    host = normalize_hostname(entry.get(field))
                    if host:
                        domains.add(host)
            for page in range(2, pagination_pages(payload) + 1):
                more = runcloud_get(token, f"/servers/{server_id}/webapps/{app_id}/domains", {"page": page, "perPage": 100})
                for entry in get_data(more):
                    for field in ("name", "domainName", "domain", "hostname"):
                        host = normalize_hostname(entry.get(field))
                        if host:
                            domains.add(host)
        except ApiError as exc:
            print(f"Warning: couldn't retrieve domains for web app {app.get('name', app_id)}: {exc}", file=sys.stderr)

    for field in ("domainName", "domain", "url", "hostname", "alias"):
        host = normalize_hostname(app.get(field))
        if host:
            domains.add(host)
    return domains


def main() -> int:
    parser = argparse.ArgumentParser(description="Find RunCloud web apps without a matching StatusCake uptime monitor.")
    parser.add_argument("--runcloud-token-file", default="token.txt", help="RunCloud API v3 bearer token file (default: token.txt)")
    parser.add_argument("--statuscake-token-file", default="statuscaketoken.txt", help="StatusCake API token file (default: statuscaketoken.txt)")
    parser.add_argument("--output", default="webapps_missing_statuscake.txt", help="Output text file (default: webapps_missing_statuscake.txt)")
    args = parser.parse_args()

    try:
        runcloud_token = read_token(Path(args.runcloud_token_file), "RunCloud")
        statuscake_token = read_token(Path(args.statuscake_token_file), "StatusCake")

        print("Fetching RunCloud servers...")
        servers = fetch_runcloud_collection(runcloud_token, "/servers")
        print(f"Found {len(servers)} RunCloud server(s).")

        apps: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for server in servers:
            server_id = server.get("id")
            if server_id is None:
                continue
            server_name = str(server.get("name") or f"Server {server_id}")
            print(f"Fetching web apps for {server_name}...")
            try:
                server_apps = fetch_runcloud_collection(runcloud_token, f"/servers/{server_id}/webapps")
            except ApiError as exc:
                raise ApiError(f"Could not list web apps for server {server_name} (ID {server_id}): {exc}") from exc
            for app in server_apps:
                apps.append((server, app))

        print("Fetching StatusCake uptime monitors...")
        monitors = fetch_statuscake_monitors(statuscake_token)
        hosts = monitor_hostnames(monitors)
        names = monitor_names(monitors)
        print(f"Found {len(apps)} RunCloud web app(s) and {len(monitors)} StatusCake uptime monitor(s).")

        missing: list[str] = []
        for server, app in apps:
            app_name = str(app.get("name") or f"Web app {app.get('id', 'unknown')}")
            domains = webapp_domains(runcloud_token, server.get("id"), app)
            matched = bool(domains & hosts)
            if not matched:
                aliases = {
                    str(value).strip().casefold()
                    for value in (app.get("name"), app.get("alias"))
                    if value is not None and str(value).strip()
                }
                matched = bool(aliases & names)
            if not matched:
                server_name = str(server.get("name") or f"Server {server.get('id', 'unknown')}")
                domain_text = ", ".join(sorted(domains)) if domains else "(no domain returned by RunCloud)"
                missing.append(f"{app_name} | Server: {server_name} (ID {server.get('id')}) | Web app ID: {app.get('id', 'unknown')} | Domains: {domain_text}")

        output_path = Path(args.output)
        output_path.write_text(
            "RunCloud web apps without a matching StatusCake uptime monitor\n"
            f"Audit completed: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"RunCloud web apps checked: {len(apps)}\n"
            f"StatusCake uptime monitors checked: {len(monitors)}\n"
            f"Missing monitor count: {len(missing)}\n"
            + ("-" * 72) + "\n"
            + ("\n".join(missing) + "\n" if missing else "None. Every web app matched a StatusCake monitor.\n"),
            encoding="utf-8",
        )
        print(f"Audit complete. {len(missing)} web app(s) need review.")
        print(f"Report written to: {output_path.resolve()}")
        return 0
    except (ApiError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
