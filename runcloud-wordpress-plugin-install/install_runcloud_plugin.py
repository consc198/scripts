#!/usr/bin/env python3
"""Discover RunCloud WordPress apps and force-install + activate a plugin ZIP."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_CLOUD_API = "https://manage.runcloud.io/api/v3"
PLUGIN_URL = "https://conversal.be/admin-menu-editor-pro-2.37.zip"
SSH_PORT = 22
SSH_USER = "root"


def api_get(token, path, params=None):
    """Call the RunCloud API using curl."""
    url = f"{RUN_CLOUD_API}{path}"
    cmd = [
        "curl", "--silent", "--show-error", "--fail-with-body",
        "--max-time", "30",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Accept: application/json",
        "-H", "Content-Type: application/json",
    ]
    if params:
        query = "&".join(
            f"{shlex.quote(str(k))}={shlex.quote(str(v))}"
            for k, v in params.items()
        )
        url = f"{url}?{query}"
    cmd.append(url)
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"curl exit code {result.returncode}"
        raise RuntimeError(f"RunCloud API request failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"RunCloud API returned invalid JSON: {result.stdout[:500]}") from exc


def get_all_pages(token, path):
    results, page = [], 1
    while True:
        data = api_get(token, path, {"page": page, "perPage": 40})
        if isinstance(data, dict):
            items = data.get("data", [])
            pagination = data.get("meta", {}).get("pagination", {})
            total_pages = pagination.get("total_pages", 1)
        else:
            items, total_pages = data, 1
        results.extend(items)
        if page >= total_pages or not items:
            break
        page += 1
    return results


def get_webapp_ssh_user(token, server_id, webapp):
    user_id = webapp.get("server_user_id")
    if user_id is None:
        raise RuntimeError(f"Web app {webapp.get('name', webapp.get('id'))} has no server_user_id")
    user = api_get(token, f"/servers/{server_id}/users/{user_id}")
    username = user.get("username")
    if not username:
        raise RuntimeError(f"RunCloud user {user_id} has no username")
    return username


def ssh_run(host, command):
    return subprocess.run([
        "ssh", "-p", str(SSH_PORT), "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15", f"{SSH_USER}@{host}", command
    ], text=True, capture_output=True)


def run_as_webapp_user(host, webapp_user, root_path, wp_args):
    inner = f"cd {shlex.quote(root_path)} && wp {wp_args}"
    command = f"sudo -u {shlex.quote(webapp_user)} -- sh -c {shlex.quote(inner)}"
    result = ssh_run(host, command)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(detail)
    return result.stdout.strip()


def version_tuple(version):
    """Compare numeric WordPress versions without requiring another dependency."""
    match = re.match(r"^\s*(\d+(?:\.\d+)*)(?:[-+].*)?\s*$", version)
    if not match:
        raise ValueError(f"Unrecognized WordPress version: {version!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def install_plugin(server, webapp, webapp_user, dry_run, minimum_version=None):
    host = server.get("ipAddress")
    root_path = webapp.get("rootPath")
    if not host:
        return "failed", "No server IP address", None
    if not root_path:
        return "failed", "No web-app rootPath", None

    server_name = server.get("name", f"server-{server['id']}")
    webapp_name = webapp.get("name", f"webapp-{webapp['id']}")

    if minimum_version:
        if dry_run:
            print(f"[DRY-RUN] {server_name} / {webapp_name}: would check WordPress version against minimum {minimum_version}")
            return "dry-run", f"Would check minimum WordPress version {minimum_version}; installation not run in dry-run mode", None
        try:
            installed_version = run_as_webapp_user(host, webapp_user, root_path, "core version")
            if version_tuple(installed_version) < version_tuple(minimum_version):
                message = f"Skipped: WordPress {installed_version} is older than minimum {minimum_version}"
                print(f"[SKIP] {server_name} / {webapp_name}: {message}")
                return "skipped", message, installed_version
        except Exception as exc:
            return "failed", f"Could not determine WordPress version safely: {exc}", None
    else:
        installed_version = None

    inner = (
        f"cd {shlex.quote(root_path)} && "
        f"wp plugin install {shlex.quote(PLUGIN_URL)} --force --activate"
    )
    command = f"sudo -u {shlex.quote(webapp_user)} -- sh -c {shlex.quote(inner)}"

    if dry_run:
        print(f"[DRY-RUN] {server_name} / {webapp_name}\n          SSH: {SSH_USER}@{host}:{SSH_PORT}\n          Run as: {webapp_user}\n          Path: {root_path}\n          CMD:  {command}")
        return "dry-run", "Installation not run in dry-run mode", installed_version

    print(f"[INSTALL+ACTIVATE] {server_name} / {webapp_name} ({host}) via root -> {webapp_user} -> {root_path}")
    result = ssh_run(host, command)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        print(f"  FAILED: {error}", file=sys.stderr)
        return "failed", error, installed_version
    return "success", "installed and activated", installed_version


def main():
    parser = argparse.ArgumentParser(description="Discover RunCloud WordPress sites and force-install + activate a plugin ZIP via root SSH.")
    parser.add_argument("--dry-run", action="store_true", help="Discover sites without executing WP-CLI.")
    parser.add_argument("--server", help="RunCloud server ID or exact server name. Omit to process all servers.")
    parser.add_argument("--min-wp-version", help="Minimum WordPress version required for installation (e.g. 6.4.2). Older sites are skipped.")
    parser.add_argument("--token", default=os.getenv("RUNCloud_API_TOKEN"))
    parser.add_argument("--output", default="runcloud-plugin-install.json")
    args = parser.parse_args()

    if args.min_wp_version:
        try:
            version_tuple(args.min_wp_version)
        except ValueError as exc:
            parser.error(str(exc))
    if not args.token:
        parser.error("Set RUNCloud_API_TOKEN or use --token.")

    try:
        print(f"RunCloud API: {api_get(args.token, '/ping')}")
        servers = get_all_pages(args.token, "/servers")
    except Exception as exc:
        print(f"RunCloud API error: {exc}")
        sys.exit(1)

    if args.server:
        matches = [s for s in servers if str(s.get("id")) == str(args.server) or s.get("name") == args.server]
        if not matches:
            print(f"No RunCloud server matched: {args.server}")
            print("Available servers:")
            for server in servers:
                print(f"  {server.get('id')} - {server.get('name', 'unnamed')}")
            sys.exit(1)
        servers = matches
        print(f"Selected server: {servers[0].get('name', servers[0].get('id'))}")
    else:
        print("Selected: all servers")

    print(f"Processing {len(servers)} server(s).")
    results = []
    wordpress_count = 0

    for server in servers:
        server_id = server["id"]
        server_name = server.get("name", f"server-{server_id}")
        print(f"\\n[{server_name}] ({server.get('ipAddress', 'unknown IP')})")
        try:
            webapps = get_all_pages(args.token, f"/servers/{server_id}/webapps")
        except Exception as exc:
            print(f"  ERROR listing web apps: {exc}")
            results.append({"server_id": server_id, "server": server_name, "status": "failed", "message": f"Web-app discovery failed: {exc}"})
            continue

        wordpress_apps = [app for app in webapps if app.get("type") == "wordpress"]
        print(f"  Found {len(webapps)} web app(s), {len(wordpress_apps)} WordPress.")

        for app in wordpress_apps:
            wordpress_count += 1
            webapp_user = None
            installed_version = None
            try:
                webapp_user = get_webapp_ssh_user(args.token, server_id, app)
                status, message, installed_version = install_plugin(
                    server, app, webapp_user, args.dry_run, args.min_wp_version
                )
            except Exception as exc:
                status, message = "failed", str(exc)
                print(f"  FAILED: {message}", file=sys.stderr)

            results.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "server_id": server_id,
                "server": server_name,
                "server_ip": server.get("ipAddress"),
                "webapp_id": app.get("id"),
                "webapp": app.get("name"),
                "server_user_id": app.get("server_user_id"),
                "ssh_user": SSH_USER,
                "run_as_user": webapp_user,
                "rootPath": app.get("rootPath"),
                "wordpress_version": installed_version,
                "minimum_wordpress_version": args.min_wp_version,
                "status": status,
                "message": message,
            })

    Path(args.output).write_text(json.dumps(results, indent=2), encoding="utf-8")
    successes = sum(r.get("status") == "success" for r in results)
    skipped = [r for r in results if r.get("status") == "skipped"]
    failures = [r for r in results if r.get("status") == "failed"]

    print("\\n" + "=" * 72)
    print("RUNCloud WORDPRESS PLUGIN INSTALLATION REPORT")
    print("=" * 72)
    print(f"Servers processed:        {len(servers)}")
    print(f"WordPress sites found:    {wordpress_count}")
    print(f"Successful:               {successes}")
    print(f"Skipped (version):        {len(skipped)}")
    print(f"Failed:                   {len(failures)}")
    print(f"Minimum WP version:       {args.min_wp_version or 'not set'}")
    print(f"Results file:             {args.output}")

    for heading, entries in (("SKIPPED SITES", skipped), ("FAILURES", failures)):
        if entries:
            print(f"\\n{heading}")
            print("-" * 72)
            for index, entry in enumerate(entries, 1):
                print(f"{index}. {entry.get('server', 'unknown server')} / {entry.get('webapp', 'unknown site')}")
                print(f"   Reason: {entry.get('message', 'Unknown')}")
                if entry.get("wordpress_version"):
                    print(f"   WordPress: {entry['wordpress_version']}")
                if entry.get("rootPath"):
                    print(f"   Path: {entry['rootPath']}")
                if entry.get("server_ip"):
                    print(f"   SSH: {SSH_USER}@{entry['server_ip']}:{SSH_PORT}")

    if not failures:
        print("\\nNo failures.")
    print("=" * 72)
    if failures:
        sys.exit(2)


if __name__ == "__main__":
    main()
