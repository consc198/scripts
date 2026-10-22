#!/usr/bin/env python3
"""Discover RunCloud servers via curl and optionally update Debian/Ubuntu packages over SSH.

Requires: Python 3, curl, ssh, an authorized SSH key, and a RunCloud API token.
The script never executes package upgrades unless --apply is supplied.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

API_BASE = "https://manage.runcloud.io"
DEFAULT_ENDPOINT = "/api/v3/servers"


class UpdaterError(RuntimeError):
    pass


def curl_json(url: str, token: str, timeout: int) -> Any:
    command = [
        "curl", "--fail", "--silent", "--show-error",
        "--connect-timeout", "10", "--max-time", str(timeout),
        "--header", f"Authorization: Bearer {token}",
        "--header", "Accept: application/json",
        url,
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() or f"curl exited with status {result.returncode}"
        raise UpdaterError(f"RunCloud API request failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UpdaterError(f"RunCloud API returned invalid JSON: {exc}") from exc


def server_items(payload: Any) -> list[dict[str, Any]]:
    """Accept common API response envelopes while requiring server objects."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for key in ("data", "servers", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
            if isinstance(value, dict):
                for nested_key in ("data", "servers", "items"):
                    if isinstance(value.get(nested_key), list):
                        items = value[nested_key]
                        break
                if items is not None:
                    break
        if items is None:
            raise UpdaterError(
                "Could not find a server list in the API response. "
                "Check the RunCloud API response format and update server_items()."
            )
    else:
        raise UpdaterError("Unexpected RunCloud API response type.")
    return [item for item in items if isinstance(item, dict)]


def get_server_host(server: dict[str, Any]) -> str | None:
    for key in ("ip", "ipAddress", "ip_address", "publicIp", "public_ip", "hostname", "host"):
        value = server.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def get_server_id(server: dict[str, Any]) -> str:
    for key in ("id", "serverId", "server_id"):
        value = server.get(key)
        if value is not None:
            return str(value)
    return ""


def get_server_name(server: dict[str, Any]) -> str:
    for key in ("name", "label", "hostname"):
        value = server.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return get_server_id(server) or "unnamed-server"


def validate_target(value: str) -> str:
    # Prevent option injection and shell-like syntax in SSH destinations.
    if not re.fullmatch(r"[A-Za-z0-9_.:@-]+", value):
        raise UpdaterError(f"Unsafe SSH destination value: {value!r}")
    return value


def ssh_run(host: str, remote_command: str, timeout: int, connect_timeout: int) -> int:
    destination = validate_target(f"root@{host}")
    command = [
        "ssh", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"ConnectTimeout={connect_timeout}",
    ]
    command.extend(["--", destination, f"sh -lc {shlex.quote(remote_command)}"])
    print(f"  SSH: {destination}", flush=True)
    try:
        result = subprocess.run(command, timeout=timeout, check=False)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"  ERROR: SSH command timed out after {timeout}s", file=sys.stderr)
        return 124


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list servers only; do not SSH")
    parser.add_argument("--server", help="target a single RunCloud server ID")
    parser.add_argument("--all", action="store_true", help="target all servers returned by the API")
    parser.add_argument("--check", action="store_true",
                        help="refresh APT indexes and simulate upgrades; do not install upgrades")
    parser.add_argument("--apply", action="store_true",
                        help="refresh APT indexes and install available upgrades")
    parser.add_argument("--api-url", default=os.getenv("RUNCLOUD_API_URL", API_BASE + DEFAULT_ENDPOINT),
                        help="server-list endpoint (default: RunCloud v3 servers endpoint)")
    parser.add_argument("--timeout", type=int, default=1800, help="per-server command timeout in seconds")
    parser.add_argument("--connect-timeout", type=int, default=10, help="SSH connection timeout in seconds")
    args = parser.parse_args()

    if args.apply and args.check:
        parser.error("--apply and --check are mutually exclusive")
    if not args.list and not args.server and not args.all:
        parser.error("choose --list, --server ID, or --all")
    if args.server and args.all:
        parser.error("--server and --all are mutually exclusive")

    token_path = Path(__file__).resolve().with_name("token.txt")
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"ERROR: could not read {token_path}: {exc}", file=sys.stderr)
        return 2
    if not token:
        print(f"ERROR: {token_path} is empty.", file=sys.stderr)
        return 2

    try:
        payload = curl_json(args.api_url, token, timeout=60)
        servers = server_items(payload)
    except UpdaterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not servers:
        print("No servers found in the API response.")
        return 0

    for server in servers:
        sid = get_server_id(server)
        if args.server and sid != args.server:
            continue
        name = get_server_name(server)
        host = get_server_host(server)
        print(f"{name}\tID={sid or 'unknown'}\tHOST={host or 'not-found'}")

    if args.list:
        return 0

    selected = [s for s in servers if args.all or get_server_id(s) == args.server]
    if args.server and not selected:
        print(f"ERROR: server ID {args.server!r} was not found.", file=sys.stderr)
        return 1

    if not args.check and not args.apply:
        print("Inventory only. Use --check to simulate upgrades or --apply to install them.")
        return 0

    remote_command = (
        "set -eu; "
        "apt-get update; "
        + ("apt-get -s upgrade" if args.check
           else "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y")
    )
    failures = 0
    for server in selected:
        name = get_server_name(server)
        host = get_server_host(server)
        if not host:
            print(f"[{name}] ERROR: no SSH host/IP found in API object; skipping.", file=sys.stderr)
            failures += 1
            continue
        print(f"[{name}] starting {'simulation' if args.check else 'upgrade'}", flush=True)
        rc = ssh_run(host, remote_command, args.timeout, args.connect_timeout)
        if rc == 0:
            print(f"[{name}] SUCCESS", flush=True)
        else:
            print(f"[{name}] FAILED (exit {rc})", file=sys.stderr, flush=True)
            failures += 1
    print(f"Finished: {len(selected) - failures} succeeded, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
