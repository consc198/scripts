# RunCloud WordPress Plugin Installer

Discovers WordPress web applications through the RunCloud API and force-installs and activates a plugin ZIP on each site using root SSH and WP-CLI.

## What it does

1. Lists RunCloud servers.
2. Lists web apps for each server.
3. Selects web apps whose type is `wordpress`.
4. Reads the web app's `server_user_id`.
5. Resolves that ID through RunCloud's system-user API and obtains the Linux username.
6. Uses the RunCloud-provided `rootPath`.
7. Connects to each server over SSH as `root` on port `22`.
8. Uses `sudo -u <web-app-user>` so WP-CLI runs as the WordPress site's Linux user.
9. Runs:

```bash
wp plugin install https://conversal.be/admin-menu-editor-pro-2.37.zip --force --activate
```

The plugin is installed and activated automatically.

## Requirements

- Python 3
- `requests`
- RunCloud API v3 token
- SSH access to each RunCloud server as `root`
- WP-CLI installed on the servers
- `sudo` available on the servers

Install the Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

## Credentials

Set the RunCloud API token:

```bash
export RUNCloud_API_TOKEN='YOUR_RUNCLOUD_API_TOKEN'
```

No `RC_SSH_USER` or `RC_SSH_PORT` variable is required. SSH always connects as `root` on port `22`. The WordPress Linux user is resolved automatically from RunCloud and used with `sudo -u` for the WP-CLI command.

SSH key authentication is recommended. The machine running this script must have a root SSH key accepted by the target RunCloud servers.

Do not commit credentials to Git.

## Dry run

Always inspect discovery first:

```bash
python3 install_runcloud_plugin.py --dry-run
```

The dry run shows the root SSH connection and the detected WordPress user that WP-CLI will run as.

## Install

After verifying the dry-run output:

```bash
python3 install_runcloud_plugin.py
```

At the end, the script prints a summary containing:

- total servers discovered
- total WordPress sites found
- successful installations/activations
- failed sites
- the exact failure reason returned by RunCloud, SSH, or WP-CLI
- the affected server, site, root SSH target, run-as user, and WordPress path when available

A machine-readable JSON report is also written to `runcloud-plugin-install.json`.

The script exits with code `2` if one or more sites fail, making failures detectable from automation or CI systems.

## Notes

- The script continues after individual site failures.
- Existing plugin installations are overwritten because `--force` is used.
- The plugin is activated automatically after installation.
- SSH always uses `root@server-ip:22`.
- WP-CLI runs as the RunCloud system user associated with each web app via `sudo -u`.
- Review the ZIP source and permissions before running against production sites.
