# RunCloud WordPress Plugin Installer

Discovers WordPress web applications through the RunCloud API and force-installs and activates the repository-hosted plugin ZIP on eligible sites using root SSH and WP-CLI.

## What it does

1. Lists RunCloud servers (all servers by default, or one selected with `--server`).
2. Finds WordPress web apps and resolves each app's RunCloud system user.
   - If listing a server's web apps fails due to a RunCloud API error, the script retries that server up to three total attempts, waiting 2 seconds and then 4 seconds between retries. After the final failure, it records the discovery error and continues to the next server.
3. Connects to each selected server as `root` over SSH port `22`.
4. Runs WP-CLI as the app's Linux user using `sudo -u`.
5. Optionally checks the site's WordPress version and skips sites below a specified minimum.
6. Installs and activates the plugin:

```bash
wp plugin install /tmp/conversal-admin-3.0.4.zip --force --activate --skip-plugins --skip-themes (after download and SHA-256 verification)
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

## Choose specific web apps

Use `--webapp` to target a WordPress web app by its RunCloud web app ID or exact name. You can repeat `--webapp` to select multiple sites. Alternatively, use `--webapps-file` with a plain-text file containing one web-app ID or exact name per line. Blank lines and lines starting with `#` are ignored.

```bash
# One web app by ID or exact name
python3 install_runcloud_plugin.py --webapp 67890
python3 install_runcloud_plugin.py --webapp "example.com"

# Multiple web apps specified directly
python3 install_runcloud_plugin.py --webapp 67890 --webapp 67891

# Multiple web apps listed in a text file
python3 install_runcloud_plugin.py --webapps-file webapps.txt

# Combine a file and individual targets, optionally limiting discovery to one server
python3 install_runcloud_plugin.py --server 12345 --webapps-file webapps.txt --webapp 67890 --min-wp-version 6.4.2 --dry-run
```

Example `webapps.txt`:

```text
# RunCloud web-app IDs or exact names, one per line
67890
67891
example.com
```

The script resolves all requested targets before installing anything. If an entry cannot be found or matches multiple sites, it stops and lists available WordPress web apps; use unique IDs to avoid ambiguity. When `--server` is supplied, targets are resolved only on that server. If no target option is supplied, the script retains its default behavior of processing all WordPress web apps on the selected server(s).

## Minimum WordPress version

Use `--min-wp-version` to set the minimum WordPress version required for installation. Sites with an older version are skipped without installing or activating the plugin.

```bash
python3 install_runcloud_plugin.py --min-wp-version 6.4.2
python3 install_runcloud_plugin.py --server 12345 --min-wp-version 6.4.2 --dry-run
```

Version comparison is numeric, so `6.10` is newer than `6.9`. If the script cannot determine a site's WordPress version when a minimum is set, it fails that site safely rather than installing the plugin without checking.

## Remove a plugin from sites

Use `--remove-plugin` to check every selected WordPress web app for a plugin and uninstall it wherever it is found. Provide the plugin slug (for example, `akismet`) or plugin file path (for example, `akismet/akismet.php`). Repeat `--remove-plugin` to remove multiple plugins in one run. By default, this checks all servers and WordPress web apps; `--server`, `--webapp`, and `--webapps-file` can narrow the targets.

```bash
# Check all WordPress apps and uninstall the plugin wherever it is installed
python3 install_runcloud_plugin.py --remove-plugin akismet

# Check one server only
python3 install_runcloud_plugin.py --server 12345 --remove-plugin akismet

# Check selected web apps only
python3 install_runcloud_plugin.py --webapps-file webapps.txt --remove-plugin akismet

# Remove multiple plugins in the same run
python3 install_runcloud_plugin.py --remove-plugin akismet --remove-plugin hello-dolly --remove-plugin wordfence

# Dry run: detect matches for each plugin and report what would be removed
python3 install_runcloud_plugin.py --remove-plugin akismet --remove-plugin hello-dolly --dry-run
```

Removal results are written to `runcloud-plugin-removal.json` by default, or to the path supplied with `--removal-output`. The JSON report contains one record for each plugin/site combination, with the requested plugin, matched plugin file (if found), status (`removed`, `not_found`, `would_remove`, or `failed`), and message. The removal command deactivates the plugin and uninstalls it. Use `--dry-run` first to verify the targets and matches.

## Dry run

```bash
python3 install_runcloud_plugin.py --dry-run
```

A dry run does not install the plugin. With a minimum version specified, it reports that the version check would be performed; run without `--dry-run` to actually check versions and install eligible sites. In `--remove-plugin` mode, a dry run checks installed plugins and records which ones would be removed, without uninstalling them.

## Reports

The script prints counts for successful installations, version-based skips, and failures. It writes a JSON report to `runcloud-plugin-install.json` by default and exits with code `2` if any site fails.

The installer downloads `conversal-admin-3.0.4.zip` from this public repository and verifies its pinned SHA-256 checksum before installation. If the downloaded file does not match the expected checksum, installation stops. To update the plugin ZIP, upload the replacement and update `PLUGIN_SHA256` in the script to the replacement file's independently computed SHA-256.

Existing plugin installations are overwritten because `--force` is used. The plugin is activated automatically on sites that meet the version requirement. The install command uses WP-CLI’s `--skip-plugins` flag so existing plugins are not loaded during the install command; this does not mean the newly installed plugin will remain inactive.
