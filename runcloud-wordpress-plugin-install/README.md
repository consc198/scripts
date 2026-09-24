# RunCloud WordPress Plugin Installer

Discovers WordPress web applications through the RunCloud API and force-installs a plugin ZIP on each site using SSH and WP-CLI.

## What it does

1. Lists RunCloud servers.
2. Lists web apps for each server.
3. Selects web apps whose type is `wordpress`.
4. Uses the RunCloud-provided `rootPath`.
5. Connects over SSH.
6. Runs:

```bash
wp plugin install https://conversal.be/admin-menu-editor-pro-2.37.zip --force
```

The plugin is installed but **not activated automatically**.

## Requirements

- Python 3
- `requests`
- RunCloud API v3 token
- SSH access to each RunCloud server
- WP-CLI installed on the servers
- An SSH account that can access the WordPress web-app paths

Install the Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

## Credentials

Set these environment variables:

```bash
export RUNCloud_API_TOKEN='YOUR_RUNCLOUD_API_TOKEN'
export RC_SSH_USER='YOUR_SSH_USER'
export RC_SSH_PORT='22'
```

Do not commit credentials to Git.

## Dry run

Always inspect discovery first:

```bash
python3 install_runcloud_plugin.py --dry-run
```

## Install

After verifying the dry-run output:

```bash
python3 install_runcloud_plugin.py
```

Results are written to `runcloud-plugin-install.json`.

## Notes

- The script continues after individual site failures.
- Existing plugin installations are overwritten because `--force` is used.
- The script does not activate the plugin.
- SSH key authentication is recommended.
- Review the ZIP source and permissions before running against production sites.
