#!/usr/bin/env python3
"""Discover RunCloud WordPress apps and force-install + activate a plugin ZIP."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUN_CLOUD_API = "https://manage.runcloud.io/api/v3"
PLUGIN_URL = "https://raw.githubusercontent.com/consc198/scripts/main/runcloud-wordpress-plugin-install/conversal-admin-3.0.4.zip"
PLUGIN_SHA256 = "1e2e98cbcd8fa20da8f996f82f91ca58feac210e434461f1c2b01cdd7c003ff6"
SCRIPT_VERSION = "1.1.0"
SSH_PORT = 22
SSH_USER = "root"
SERVER_DISCOVERY_ATTEMPTS = 3
SCRIPT_VERSION = "1.1.0"


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

def get_server_webapps_with_retries(token, server_id, server_name):
    """Retry one server's web-app discovery up to three total attempts."""
    for attempt in range(1, SERVER_DISCOVERY_ATTEMPTS + 1):
        try:
            return get_all_pages(token, f"/servers/{server_id}/webapps")
        except Exception as exc:
            if attempt >= SERVER_DISCOVERY_ATTEMPTS:
                raise RuntimeError(
                    f"Web-app discovery failed after {SERVER_DISCOVERY_ATTEMPTS} attempts: {exc}"
                ) from exc
            delay = 2 ** attempt
            print(
                f"  API error listing web apps for {server_name} "
                f"(attempt {attempt}/{SERVER_DISCOVERY_ATTEMPTS}): {exc}. "
                f"Retrying in {delay}s..."
            )
            time.sleep(delay)


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


def plugin_version(host, user, root, slug):
    """Read the installed plugin version; return None if unavailable."""
    try:
        return run_as_webapp_user(host, user, root, f"plugin get {shlex.quote(slug)} --field=version --skip-plugins --skip-themes") or None
    except Exception:
        return None


def get_plugin_records(host, webapp_user, root_path):
    """Return WP-CLI plugin records, including installed and available versions."""
    output = run_as_webapp_user(
        host, webapp_user, root_path,
        "plugin list --format=json --fields=name,version,update,update_version --skip-plugins --skip-themes",
    )
    try:
        records = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"WP-CLI returned invalid plugin JSON: {output[:300]}") from exc
    if not isinstance(records, list):
        raise RuntimeError("WP-CLI plugin list did not return a JSON array")
    return records


def update_plugin(server, webapp, webapp_user, plugin_slug, dry_run):
    """Update an installed plugin and report versions before and after."""
    host = server.get("ipAddress")
    root_path = webapp.get("rootPath")
    if not host:
        return "failed", "No server IP address", None, None, None, None
    if not root_path:
        return "failed", "No web-app rootPath", None, None, None, None

    server_name = server.get("name", f"server-{server['id']}")
    webapp_name = webapp.get("name", f"webapp-{webapp['id']}")
    try:
        records = get_plugin_records(host, webapp_user, root_path)
    except Exception as exc:
        return "failed", f"Could not list installed plugins and versions: {exc}", None, None, None, None

    matched_record = next(
        (
            record for record in records
            if record.get("name") == plugin_slug
            or ("/" not in plugin_slug and str(record.get("name", "")).split("/", 1)[0] == plugin_slug)
        ),
        None,
    )
    if not matched_record:
        print(f"[NOT FOUND] {server_name} / {webapp_name}: {plugin_slug}")
        return "not_found", "Plugin is not installed", None, None, None, None

    matched_plugin = matched_record.get("name")
    installed_before = matched_record.get("version")
    update_state = str(matched_record.get("update") or "").lower()
    raw_update_version = matched_record.get("update_version")
    available_version = (
        raw_update_version
        if raw_update_version and str(raw_update_version).lower() not in {"none", "false", "0"}
        and update_state not in {"", "none", "false", "0"}
        else None
    )
    has_update = available_version is not None or update_state == "available"

    if dry_run:
        if has_update:
            print(
                f"[DRY-RUN] Would update {matched_plugin} on {server_name} / {webapp_name}: "
                f"{installed_before or 'unknown'} -> {available_version or 'latest available'}"
            )
            return "would_update", "Update available; dry-run did not change the plugin", matched_plugin, installed_before, available_version, installed_before
        print(f"[CURRENT] {server_name} / {webapp_name}: {matched_plugin} {installed_before or '(version unknown)'}")
        return "already_current", "No plugin update is currently available", matched_plugin, installed_before, available_version, installed_before

    try:
        output = run_as_webapp_user(
            host, webapp_user, root_path,
            f"plugin update {shlex.quote(matched_plugin)} --skip-plugins --skip-themes",
        )
    except Exception as exc:
        return "failed", f"Plugin {matched_plugin} ({installed_before or 'unknown version'}) update failed: {exc}", matched_plugin, installed_before, available_version, None

    try:
        after_records = get_plugin_records(host, webapp_user, root_path)
        after_record = next((record for record in after_records if record.get("name") == matched_plugin), None)
        installed_after = after_record.get("version") if after_record else None
    except Exception as exc:
        return "failed", f"Update command completed but could not verify the installed version: {exc}", matched_plugin, installed_before, available_version, None

    if installed_after and installed_after != installed_before:
        status = "updated"
        message = f"Plugin version changed from {installed_before} to {installed_after}"
        print(f"[UPDATED] {server_name} / {webapp_name}: {matched_plugin} {installed_before} -> {installed_after}")
    else:
        status = "already_current"
        message = output or f"Plugin remains at version {installed_after or installed_before or 'unknown'}; no version change was detected"
        print(f"[CURRENT] {server_name} / {webapp_name}: {matched_plugin} {installed_after or installed_before or '(version unknown)'}")
    return status, message, matched_plugin, installed_before, available_version, installed_after


def remove_plugin(server, webapp, webapp_user, plugin_slug, dry_run):
    """Remove a plugin if it is installed, returning a reportable status."""
    host = server.get("ipAddress")
    root_path = webapp.get("rootPath")
    if not host:
        return "failed", "No server IP address", None
    if not root_path:
        return "failed", "No web-app rootPath", None

    server_name = server.get("name", f"server-{server['id']}")
    webapp_name = webapp.get("name", f"webapp-{webapp['id']}")
    try:
        output = run_as_webapp_user(
            host, webapp_user, root_path,
            "plugin list --field=name --skip-plugins --skip-themes",
        )
    except Exception as exc:
        return "failed", f"Could not list installed plugins: {exc}", None

    installed_plugins = [line.strip() for line in output.splitlines() if line.strip()]
    matched_plugin = next(
        (
            name for name in installed_plugins
            if name == plugin_slug
            or ("/" not in plugin_slug and name.split("/", 1)[0] == plugin_slug)
        ),
        None,
    )
    if not matched_plugin:
        print(f"[NOT FOUND] {server_name} / {webapp_name}: {plugin_slug}")
        return "not_found", "Plugin is not installed", None

    if dry_run:
        print(f"[DRY-RUN] Would uninstall {matched_plugin} from {server_name} / {webapp_name}")
        return "would_remove", "Plugin is installed; dry-run did not remove it", matched_plugin

    try:
        run_as_webapp_user(
            host, webapp_user, root_path,
            f"plugin uninstall {shlex.quote(matched_plugin)} --deactivate --skip-plugins --skip-themes",
        )
    except Exception as exc:
        return "failed", f"Plugin was found ({matched_plugin}) but uninstall failed: {exc}", matched_plugin

    print(f"[REMOVED] {server_name} / {webapp_name}: {matched_plugin}")
    return "removed", "Plugin uninstalled and deactivated", matched_plugin


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

    # Download as root, verify the pinned SHA-256, then install as the site's Linux user.
    # The checksum prevents a changed/replaced public ZIP from being installed silently.
    wp_install = f"cd {shlex.quote(root_path)} && wp plugin install \"$1\" --force --activate --skip-plugins --skip-themes"
    inner = (
        "set -eu; "
        "archive=$(mktemp /tmp/conversal-admin-3.0.4.XXXXXX.zip); "
        "trap 'rm -f \"$archive\"' EXIT; "
        f"curl --fail --silent --show-error --location --max-time 120 {shlex.quote(PLUGIN_URL)} -o \"$archive\"; "
        f"printf '%s  %s\\n' {shlex.quote(PLUGIN_SHA256)} \"$archive\" | sha256sum --check --status; "
        "chmod 644 \"$archive\"; "
        f"sudo -u {shlex.quote(webapp_user)} -- sh -c {shlex.quote(wp_install)} sh \"$archive\""
    )
    command = f"sh -c {shlex.quote(inner)}"

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
    parser.add_argument("--version", action="version", version=f"%(prog)s {SCRIPT_VERSION}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {SCRIPT_VERSION}")
    parser.add_argument("--dry-run", action="store_true", help="Discover sites without executing WP-CLI.")
    parser.add_argument("--server", help="RunCloud server ID or exact server name. Omit to process all servers.")
    parser.add_argument("--webapp", action="append", help="Target a WordPress web app by RunCloud web app ID or exact name. May be repeated; names must match uniquely.")
    parser.add_argument("--webapps-file", help="Text file containing target web app IDs or exact names, one per line. Blank lines and lines starting with # are ignored.")
    parser.add_argument("--min-wp-version", help="Minimum WordPress version required for installation (e.g. 6.4.2). Older sites are skipped.")
    parser.add_argument("--remove-plugin", action="append", metavar="PLUGIN", help="Find and uninstall this plugin from selected WordPress apps (plugin slug or plugin file path). Repeat to remove multiple plugins; writes a separate JSON report.")
    parser.add_argument("--removal-output", default="runcloud-plugin-removal.json", help="JSON report path for --remove-plugin mode.")
    parser.add_argument("--update-plugin", action="append", metavar="PLUGIN", help="Update this installed plugin to the latest available version on selected WordPress apps. Repeat to update multiple plugins; writes a separate JSON report.")
    parser.add_argument("--update-output", default="runcloud-plugin-update.json", help="JSON report path for --update-plugin mode.")
    parser.add_argument("--token", help="RunCloud API token (overrides environment variable and token.txt).")
    parser.add_argument("--output", default="runcloud-plugin-install.json")
    args = parser.parse_args()

    if args.remove_plugin and args.update_plugin:
        parser.error("--remove-plugin and --update-plugin are separate modes and cannot be used together.")
    if (args.remove_plugin or args.update_plugin) and args.min_wp_version:
        parser.error("--min-wp-version applies to installation mode and cannot be combined with --remove-plugin or --update-plugin.")
    if args.min_wp_version:
        try:
            version_tuple(args.min_wp_version)
        except ValueError as exc:
            parser.error(str(exc))
    token = args.token or os.getenv("RUNCloud_API_TOKEN")
    if not token:
        token_file = Path(__file__).resolve().with_name("token.txt")
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            token = None
        except OSError as exc:
            parser.error(f"Could not read {token_file}: {exc}")
    if not token:
        parser.error("Provide --token, set RUNCloud_API_TOKEN, or put the API token in token.txt next to this script.")

    try:
        print(f"RunCloud API: {api_get(token, '/ping')}")
        servers = get_all_pages(token, "/servers")
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
    webapps_by_server = {}
    discovery_failures = []

    # Discover first so a name-based target can be checked for ambiguity before
    # any site is changed.
    for server in servers:
        server_id = server["id"]
        server_name = server.get("name", f"server-{server_id}")
        print(f"\\n[{server_name}] ({server.get('ipAddress', 'unknown IP')})")
        try:
            webapps = get_server_webapps_with_retries(token, server_id, server_name)
            webapps_by_server[server_id] = webapps
            wordpress_apps = [app for app in webapps if app.get("type") == "wordpress"]
            print(f"  Found {len(webapps)} web app(s), {len(wordpress_apps)} WordPress.")
        except Exception as exc:
            print(f"  ERROR listing web apps: {exc}")
            discovery_failures.append({"server_id": server_id, "server": server_name, "status": "failed", "message": f"Web-app discovery failed: {exc}"})

    target_names = list(args.webapp or [])
    if args.webapps_file:
        try:
            with Path(args.webapps_file).expanduser().open("r", encoding="utf-8") as handle:
                target_names.extend(
                    line.strip()
                    for line in handle
                    if line.strip() and not line.lstrip().startswith("#")
                )
        except OSError as exc:
            parser.error(f"Could not read web-app list file {args.webapps_file}: {exc}")

    if (args.webapp is not None or args.webapps_file) and not target_names:
        parser.error("The web-app target options were provided, but no targets were found. Add at least one web-app ID or exact name.")

    selected_apps_by_server = {}
    if target_names:
        if discovery_failures:
            print("Cannot safely resolve targeted web apps because web-app discovery failed for at least one selected server.")
            sys.exit(1)

        matched_by_identity = {}
        unresolved = []
        ambiguous = []
        for target in target_names:
            candidates = [
                (server, app)
                for server in servers
                for app in webapps_by_server.get(server["id"], [])
                if app.get("type") == "wordpress"
                and (str(app.get("id")) == str(target) or app.get("name") == target)
            ]
            # Multiple lines may point to the same app; treat it as one match.
            unique = {(str(server["id"]), str(app.get("id"))): (server, app) for server, app in candidates}
            candidates = list(unique.values())
            if not candidates:
                unresolved.append(target)
            elif len(candidates) > 1:
                ambiguous.append((target, candidates))
            else:
                server, app = candidates[0]
                matched_by_identity[(str(server["id"]), str(app.get("id")))] = (server, app)

        if unresolved or ambiguous:
            if unresolved:
                print("No WordPress web app matched these target entries:")
                for target in unresolved:
                    print(f"  {target}")
            if ambiguous:
                print("These target entries matched multiple web apps; use a unique web-app ID:")
                for target, candidates in ambiguous:
                    print(f"  {target}")
                    for server, app in candidates:
                        print(f"    server {server.get('id')} / web app {app.get('id')} - {app.get('name', 'unnamed')}")
            print("Available WordPress web apps:")
            for server in servers:
                for app in webapps_by_server.get(server["id"], []):
                    if app.get("type") == "wordpress":
                        print(f"  server {server.get('id')} / web app {app.get('id')} - {app.get('name', 'unnamed')}")
            sys.exit(1)

        for server, app in matched_by_identity.values():
            selected_apps_by_server.setdefault(server["id"], []).append(app)
        servers = [
            server for server in servers
            if server["id"] in selected_apps_by_server
        ]
        for server in servers:
            webapps_by_server[server["id"]] = selected_apps_by_server[server["id"]]
        print(f"Selected {len(matched_by_identity)} specific WordPress web app(s).")

    results.extend(discovery_failures)

    for server in servers:
        server_id = server["id"]
        server_name = server.get("name", f"server-{server_id}")
        wordpress_apps = [
            app for app in webapps_by_server.get(server_id, [])
            if app.get("type") == "wordpress"
        ]

        for app in wordpress_apps:
            wordpress_count += 1
            webapp_user = None
            try:
                webapp_user = get_webapp_ssh_user(token, server_id, app)
            except Exception as exc:
                requested_plugins = (args.remove_plugin or args.update_plugin) if (args.remove_plugin or args.update_plugin) else [None]
                for plugin_requested in requested_plugins:
                    results.append({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "server_id": server_id,
                        "server": server_name,
                        "server_ip": server.get("ipAddress"),
                        "webapp_id": app.get("id"),
                        "webapp": app.get("name"),
                        "server_user_id": app.get("server_user_id"),
                        "ssh_user": SSH_USER,
                        "run_as_user": None,
                        "rootPath": app.get("rootPath"),
                        "plugin_requested": plugin_requested,
                        "plugin_matched": None,
                        "wordpress_version": None,
                        "minimum_wordpress_version": args.min_wp_version,
                        "status": "failed",
                        "message": str(exc),
                    })
                print(f"  FAILED: {exc}", file=sys.stderr)
                continue

            if args.remove_plugin:
                for plugin_requested in args.remove_plugin:
                    matched_plugin = None
                    try:
                        status, message, matched_plugin = remove_plugin(
                            server, app, webapp_user, plugin_requested, args.dry_run
                        )
                    except Exception as exc:
                        status, message = "failed", str(exc)
                        print(f"  FAILED removing {plugin_requested}: {message}", file=sys.stderr)
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
                        "plugin_requested": plugin_requested,
                        "plugin_matched": matched_plugin,
                        "wordpress_version": None,
                        "minimum_wordpress_version": None,
                        "status": status,
                        "message": message,
                    })
            elif args.update_plugin:
                for plugin_requested in args.update_plugin:
                    matched_plugin = None
                    version_before = available_version = version_after = None
                    try:
                        status, message, matched_plugin, version_before, available_version, version_after = update_plugin(
                            server, app, webapp_user, plugin_requested, args.dry_run
                        )
                    except Exception as exc:
                        status, message = "failed", str(exc)
                        print(f"  FAILED updating {plugin_requested}: {message}", file=sys.stderr)
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
                        "plugin_requested": plugin_requested,
                        "plugin_matched": matched_plugin,
                        "plugin_version_before": version_before,
                        "plugin_update_available_version": available_version,
                        "plugin_version_after": version_after,
                        "script_version": SCRIPT_VERSION,
                        "wordpress_version": None,
                        "minimum_wordpress_version": None,
                        "status": status,
                        "message": message,
                    })
            else:
                installed_version = None
                try:
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
                    "plugin_requested": None,
                    "plugin_matched": None,
                    "wordpress_version": installed_version,
                    "minimum_wordpress_version": args.min_wp_version,
                    "status": status,
                    "message": message,
                })

    for entry in results:
        entry.setdefault("script_version", SCRIPT_VERSION)
    report_path = args.removal_output if args.remove_plugin else (args.update_output if args.update_plugin else args.output)
    for record in results:
        record["script_version"] = SCRIPT_VERSION
    Path(report_path).write_text(json.dumps(results, indent=2), encoding="utf-8")
    failures = [r for r in results if r.get("status") == "failed"]

    print("\n" + "=" * 72)
    if args.update_plugin:
        updated = sum(r.get("status") == "updated" for r in results)
        current = sum(r.get("status") == "current" for r in results)
        not_found = sum(r.get("status") == "not_found" for r in results)
        would_update = sum(r.get("status") == "would_update" for r in results)
        print("RUNCloud WORDPRESS PLUGIN UPDATE REPORT")
        print("=" * 72)
        print("Plugins requested:        " + ", ".join(args.update_plugin))
        print(f"Servers processed:        {len(servers)}")
        print(f"WordPress sites checked:  {wordpress_count}")
        print(f"Updated:                  {updated}")
        print(f"Already current:          {current}")
        print(f"Not installed:            {not_found}")
        print(f"Would update (dry-run):   {would_update}")
    elif args.remove_plugin:
        removed = sum(r.get("status") == "removed" for r in results)
        not_found = sum(r.get("status") == "not_found" for r in results)
        would_remove = sum(r.get("status") == "would_remove" for r in results)
        print("RUNCloud WORDPRESS PLUGIN REMOVAL REPORT")
        print("=" * 72)
        print("Plugins requested:        " + ", ".join(args.remove_plugin))
        print(f"Servers processed:        {len(servers)}")
        print(f"WordPress sites checked:  {wordpress_count}")
        print(f"Removed:                  {removed}")
        print(f"Not installed:            {not_found}")
        print(f"Would remove (dry-run):   {would_remove}")
    else:
        successes = sum(r.get("status") == "success" for r in results)
        skipped = [r for r in results if r.get("status") == "skipped"]
        print("RUNCloud WORDPRESS PLUGIN INSTALLATION REPORT")
        print("=" * 72)
        print(f"Servers processed:        {len(servers)}")
        print(f"WordPress sites found:    {wordpress_count}")
        print(f"Successful:               {successes}")
        print(f"Skipped (version):        {len(skipped)}")
        print(f"Minimum WP version:       {args.min_wp_version or 'not set'}")
    print(f"Failed:                   {len(failures)}")
    print(f"Results file:             {report_path}")

    if failures:
        print("\nFAILURES")
        print("-" * 72)
        for index, entry in enumerate(failures, 1):
            print(f"{index}. {entry.get('server', 'unknown server')} / {entry.get('webapp', 'unknown site')}")
            print(f"   Reason: {entry.get('message', 'Unknown')}")
            if entry.get("rootPath"):
                print(f"   Path: {entry['rootPath']}")
            if entry.get("server_ip"):
                print(f"   SSH: {SSH_USER}@{entry['server_ip']}:{SSH_PORT}")
    else:
        print("\nNo failures.")
    print("=" * 72)
    if failures:
        sys.exit(2)


if __name__ == "__main__":
    main()
