#!/usr/bin/env python3
"""Discover WordPress apps in RunCloud and force-install + activate a plugin ZIP via SSH/WP-CLI."""

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

RUN_CLOUD_API = "https://manage.runcloud.io/api/v3"
PLUGIN_URL = "https://conversal.be/admin-menu-editor-pro-2.37.zip"


def api_get(token, path, params=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}
    response = requests.get(f"{RUN_CLOUD_API}{path}", headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


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
    """Resolve the RunCloud system-user username owning the web app."""
    user_id = webapp.get("server_user_id")
    if user_id is None:
        raise RuntimeError(f"Web app {webapp.get('name', webapp.get('id'))} has no server_user_id")
    user = api_get(token, f"/servers/{server_id}/users/{user_id}")
    username = user.get("username")
    if not username:
        raise RuntimeError(f"RunCloud user {user_id} has no username")
    return username


def ssh_run(host, user, command, port=22):
    return subprocess.run([
        "ssh", "-p", str(port), "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15", f"{user}@{host}", command
    ], text=True, capture_output=True)


def install_plugin(server, webapp, ssh_user, ssh_port, dry_run):
    host = server.get("ipAddress")
    root_path = webapp.get("rootPath")
    if not host:
        return False, "No server IP address"
    if not root_path:
        return False, "No web-app rootPath"

    # --force replaces an existing copy; --activate activates it after installation.
    command = (
        f"cd {shlex.quote(root_path)} && "
        f"wp plugin install {shlex.quote(PLUGIN_URL)} --force --activate"
    )
    server_name = server.get("name", f"server-{server['id']}")
    webapp_name = webapp.get("name", f"webapp-{webapp['id']}")

    if dry_run:
        print(f"[DRY-RUN] {server_name} / {webapp_name}\n          SSH: {ssh_user}@{host}:{ssh_port}\n          Path: {root_path}\n          CMD:  {command}")
        return True, "dry-run"

    print(f"[INSTALL+ACTIVATE] {server_name} / {webapp_name} ({host}) as {ssh_user} -> {root_path}")
    result = ssh_run(host, ssh_user, command, ssh_port)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        return False, f"exit code {result.returncode}"
    return True, "installed and activated"


def main():
    parser = argparse.ArgumentParser(description="Discover RunCloud WordPress sites and force-install + activate a remote plugin ZIP.")
    parser.add_argument("--dry-run", action="store_true", help="Discover sites without executing WP-CLI.")
    parser.add_argument("--ssh-user", default=os.getenv("RC_SSH_USER"), help="Optional SSH override. If omitted, resolve each web app's RunCloud system user automatically.")
    parser.add_argument("--ssh-port", type=int, default=int(os.getenv("RC_SSH_PORT", "22")))
    parser.add_argument("--token", default=os.getenv("RUNCloud_API_TOKEN"))
    parser.add_argument("--output", default="runcloud-plugin-install.json")
    args = parser.parse_args()

    if not args.token:
        parser.error("Set RUNCloud_API_TOKEN or use --token.")

    try:
        print(f"RunCloud API: {api_get(args.token, '/ping')}")
        servers = get_all_pages(args.token, "/servers")
    except Exception as exc:
        print(f"RunCloud API error: {exc}")
        sys.exit(1)

    print(f"Found {len(servers)} server(s).")
    results = []
    wordpress_count = 0

    for server in servers:
        server_id = server["id"]
        server_name = server.get("name", f"server-{server_id}")
        print(f"\n[{server_name}] ({server.get('ipAddress', 'unknown IP')})")
        try:
            webapps = get_all_pages(args.token, f"/servers/{server_id}/webapps")
        except Exception as exc:
            print(f"  ERROR listing web apps: {exc}")
            results.append({"server_id": server_id, "server": server_name, "status": "webapp_discovery_failed", "error": str(exc)})
            continue

        wordpress_apps = [app for app in webapps if app.get("type") == "wordpress"]
        print(f"  Found {len(webapps)} web app(s), {len(wordpress_apps)} WordPress.")

        for app in wordpress_apps:
            wordpress_count += 1
            try:
                ssh_user = args.ssh_user or get_webapp_ssh_user(args.token, server_id, app)
                ok, message = install_plugin(server, app, ssh_user, args.ssh_port, args.dry_run)
            except Exception as exc:
                ok, message = False, str(exc)
                ssh_user = args.ssh_user
                print(f"  ERROR resolving/processing {app.get('name', app.get('id'))}: {exc}")

            results.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "server_id": server_id,
                "server": server_name,
                "server_ip": server.get("ipAddress"),
                "webapp_id": app.get("id"),
                "webapp": app.get("name"),
                "server_user_id": app.get("server_user_id"),
                "ssh_user": ssh_user,
                "rootPath": app.get("rootPath"),
                "status": "success" if ok else "failed",
                "message": message,
            })

    Path(args.output).write_text(json.dumps(results, indent=2), encoding="utf-8")
    successes = sum(r.get("status") == "success" for r in results)
    failures = sum(r.get("status") == "failed" for r in results)
    print("\n" + "=" * 60)
    print(f"Servers discovered:       {len(servers)}")
    print(f"WordPress sites found:    {wordpress_count}")
    print("Mode:                     DRY RUN" if args.dry_run else f"Successful installations: {successes}\nFailed installations:     {failures}")
    print(f"Results:                  {args.output}")
    if failures:
        sys.exit(2)


if __name__ == "__main__":
    main()
