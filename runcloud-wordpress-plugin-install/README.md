# RunCloud WordPress Plugin Installer

Discovers WordPress web applications through the RunCloud API and force-installs and activates a plugin ZIP on each site using SSH and WP-CLI.

## What it does

1. Lists RunCloud servers.
2. Lists web apps for each server.
3. Selects web apps whose type is `wordpress`.
4. Reads the web app's `server_user_id`.
5. Resolves that ID through RunCloud's system-user API and automatically obtains the Linux username.
6. Uses the RunCloud-provided `rootPath`.
7. Connects over SSH as that system user.
8. Runs:

```bash
wp plugin install https://conversal.be/admin-menu-editor-pro-2.37.zip --force --activate
```

The plugin is installed and activated automatically.

## Requirements

- Python 3
- `requests`
- RunCloud API v3 token
- SSH access to each RunCloud server
- WP-CLI installed on the servers
- SSH authentication configured for the resolved RunCloud system users

Install the Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

## Credentials

Set the RunCloud API token:

```bash
export RUNCloud_API_TOKEN='YOUR_RUNCLOUD_API_TOKEN'
```

You no longer need to set `RC_SSH_USER` in the normal case. The script automatically resolves each WordPress web app's RunCloud system user from its `server_user_id`.

If you want to override automatic detection for testing or a special SSH setup, you can still use:

```bash
export RC_SSH_USER='YOUR_SSH_USER'
```

Or:

```bash
python3 install_runcloud_plugin.py --ssh-user YOUR_SSH_USER
```

The SSH port remains configurable:

```bash
export RC_SSH_PORT='22'
```

Do not commit credentials to Git.

## Dry run

Always inspect discovery first:

```bash
python3 install_runcloud_plugin.py --dry-run
```

The dry run shows which SSH username will be used for each WordPress site.

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
- the affected server, site, SSH user, and WordPress path when available

A machine-readable JSON report is also written to `runcloud-plugin-install.json`.

The script exits with code `2` if one or more sites fail, making failures detectable from automation or CI systems.

## Notes

- The script continues after individual site failures.
- Existing plugin installations are overwritten because `--force` is used.
- The plugin is activated automatically after installation.
- SSH key authentication is recommended.
- The automatically detected username is the RunCloud system user associated with each web app; it is not guessed from the domain name or filesystem path.
- Review the ZIP source and permissions before running against production sites.
