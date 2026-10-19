# RunCloud WordPress Plugin Installer

Discovers WordPress web applications through the RunCloud API and force-installs and activates the repository-hosted plugin ZIP on eligible sites using root SSH and WP-CLI.

## What it does

1. Lists RunCloud servers (all servers by default, or one selected with `--server`).
2. Finds WordPress web apps and resolves each app's RunCloud system user.
3. Connects to each selected server as `root` over SSH port `22`.
4. Runs WP-CLI as the app's Linux user using `sudo -u`.
5. Optionally checks the site's WordPress version and skips sites below a specified minimum.
6. Installs and activates the plugin:

```bash
wp plugin install /tmp/conversal-admin-3.0.4.zip --force --activate (after download and SHA-256 verification)
```

## Requirements

- Python 3
- `curl` and `sha256sum` on the target servers (for downloading and verifying the plugin ZIP)
- RunCloud API v3 token
- Root SSH key access to the target servers
- WP-CLI and `sudo` on the servers

Store the API token in a local `token.txt` file next to the script, with only the token on the first line:

```text
YOUR_RUNCLOUD_API_TOKEN
```

The script checks for credentials in this order: `--token`, the `RUNCloud_API_TOKEN` environment variable, then `token.txt` beside the script. Keep `token.txt` private; it is excluded from Git by `.gitignore`.

## Choose servers

Process all servers:

```bash
python3 install_runcloud_plugin.py
```

Process one server by RunCloud ID or exact name:

```bash
python3 install_runcloud_plugin.py --server 12345
python3 install_runcloud_plugin.py --server "Production Server"
```

## Choose one web app

Use `--webapp` to target a single WordPress web app by its RunCloud web app ID or exact name. This option installs only to the matching site, not every WordPress site on the server. If a name matches more than one site, the script stops and asks you to use a unique web app ID.

```bash
python3 install_runcloud_plugin.py --webapp 67890
python3 install_runcloud_plugin.py --webapp "example.com"
python3 install_runcloud_plugin.py --server 12345 --webapp 67890 --min-wp-version 6.4.2 --dry-run
```

When using `--server` and `--webapp` together, the web app must belong to the selected server.

## Minimum WordPress version

Use `--min-wp-version` to set the minimum WordPress version required for installation. Sites with an older version are skipped without installing or activating the plugin.

```bash
python3 install_runcloud_plugin.py --min-wp-version 6.4.2
python3 install_runcloud_plugin.py --server 12345 --min-wp-version 6.4.2 --dry-run
```

Version comparison is numeric, so `6.10` is newer than `6.9`. If the script cannot determine a site's WordPress version when a minimum is set, it fails that site safely rather than installing the plugin without checking.

## Dry run

```bash
python3 install_runcloud_plugin.py --dry-run
```

A dry run does not install the plugin. With a minimum version specified, it reports that the version check would be performed; run without `--dry-run` to actually check versions and install eligible sites.

## Reports

The script prints counts for successful installations, version-based skips, and failures. It writes a JSON report to `runcloud-plugin-install.json` by default and exits with code `2` if any site fails.

The installer downloads `conversal-admin-3.0.4.zip` from this public repository and verifies its pinned SHA-256 checksum before installation. If the downloaded file does not match the expected checksum, installation stops. To update the plugin ZIP, upload the replacement and update `PLUGIN_SHA256` in the script to the replacement file's independently computed SHA-256.

Existing plugin installations are overwritten because `--force` is used. The plugin is activated automatically on sites that meet the version requirement.
