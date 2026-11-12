# RunCloud PHP Upgrader

**Current version: 1.10.0**

Find RunCloud web applications running selected PHP version(s) and change them to a target PHP version. HTTP requests are made using the `curl` command-line tool; Python's `requests` package is not required. A terminal progress bar shows webapp scan progress. The optional `--update-php-cli` flag also updates the server-level PHP-CLI version using the same source and target version options.

## Requirements

- Python 3.9+
- `curl` installed and available in `PATH`
- A RunCloud API token with permission to read servers/webapps and change webapp PHP settings.

## Setup

1. Create `token.txt` in this directory and put your RunCloud API token in it. Keep this file private; it is excluded by `.gitignore`.

## Usage

Show the installed script version:

```bash
python3 upgrade_runcloud_php.py --version
```

### Preview (dry run)

By default, the script previews webapps on PHP 8.0 or 8.1 that would be changed to PHP 8.2:

```bash
python3 upgrade_runcloud_php.py
```

Specify one source version and one target version:

```bash
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc
```

Specify multiple source versions:

```bash
python3 upgrade_runcloud_php.py --source-php php80rc php81rc --target-php php82rc
```

Apply changes by adding `--apply`:

```bash
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --apply
```

### List webapps by PHP version and app type

Use `--list-apps-php` to print a read-only inventory of webapps currently running a specific PHP version, including server name, webapp name, detected app type, URL/domain when returned by the API, and IDs:

```bash
python3 upgrade_runcloud_php.py --list-apps-php php81rc
```

Optionally limit the inventory to one server:

```bash
python3 upgrade_runcloud_php.py --list-apps-php php81rc --server-id 123
```

This mode makes no changes and cannot be combined with update flags. Temporary webapp-listing failures (HTTP 429 and common 5xx errors) are retried up to five attempts with increasing waits. App type is inferred from the metadata and paths returned by the API; if those fields don't identify WordPress, Laravel, or another type, it reports `Unknown`.

### Select specific webapps from a text file

Create a text file such as `webapps.txt` with one exact webapp name per line. Blank lines and lines starting with `#` are ignored. Names are matched exactly and are case-sensitive.

```text
Production Site
Customer Portal
Staging App
```

Preview changes for only those listed webapps:

```bash
python3 upgrade_runcloud_php.py --webapps-file webapps.txt --source-php php81rc --target-php php82rc
```

Apply the changes after reviewing the preview:

```bash
python3 upgrade_runcloud_php.py --webapps-file webapps.txt --source-php php81rc --target-php php82rc --apply
```

The script reports listed names that were not found and listed webapps that do not use one of the selected source PHP versions. If the same exact webapp name exists on multiple servers, each matching webapp is eligible. The text-file filter selects webapps only; if you explicitly add `--update-php-cli`, server-level PHP-CLI updates are still handled separately. The file is read from the path you provide.

### Audit the busiest client IPs across all webapps

Use `--audit-webapp-traffic` to scan every selected server's RunCloud Nginx webapp access logs and report the 20 client IP addresses with the most requests across all webapps combined, limited to the last 48 hours:

```bash
python3 upgrade_runcloud_php.py --audit-webapp-traffic
```

The audit reads active logs matching `/home/*/logs/nginx/*_access.log` and rotated compressed access logs matching `*_access.log-*.gz`, so requests from the full 48-hour window are included when logs have rotated. It parses each request timestamp and counts the IP in the first field of the access-log line. The summary ranks IPs by total requests across all scanned webapps and shows how many distinct webapps and servers each IP appeared on.

You can restrict the audit to one RunCloud server:

```bash
python3 upgrade_runcloud_php.py --audit-webapp-traffic --server-id 123
```

This is a read-only operation; it does not change webapp settings or log files. It requires the same non-interactive root SSH access used by `--scan-max-children`, and Python 3 on each server. If a server uses a reverse proxy, the reported address depends on the client IP value written into the first access-log field (for example, whether Nginx real-IP handling is configured).

### Scan PHP-FPM logs for max_children limit hits

The script can SSH to every selected RunCloud server as `root@SERVER_IP` and scan matching files under `/var/log/php*rc-fpm.log` for warnings such as:

```text
[27-Oct-2026 09:41:39] WARNING: [pool modulehome] server reached max_children setting (10), consider raising it
```

Run a read-only report:

```bash
python3 upgrade_runcloud_php.py --scan-max-children

# Show only warnings recorded in the last 24 hours
python3 upgrade_runcloud_php.py --scan-max-children --since-hours 24
```

The optional `--since-hours HOURS` filter limits results to warnings recorded within the specified lookback period (for example, `--since-hours 24` for the last 24 hours). Without it, all matching warnings currently present in the scanned log files are included. The time filter compares log timestamps with the local time on the machine running the script. The report groups warnings by server, PHP-FPM pool, and configured limit. It shows the server/IP, pool name, current limit from the log warning, number of matching warning lines, and latest timestamp found in the scanned log files.

To raise only webapps reported as hitting a current limit of 10 to 15:

```bash
python3 upgrade_runcloud_php.py --update-hit-max-children 10 15

# Only consider pools with a warning in the last 24 hours
python3 upgrade_runcloud_php.py --update-hit-max-children 10 15 --since-hours 24
```

The command scans the logs again, then verifies the current PHP-FPM setting through the RunCloud API before showing eligible changes. Add `--apply` to submit the changes:

```bash
python3 upgrade_runcloud_php.py --update-hit-max-children 10 15 --apply
```

Only pools with a warning showing the selected `FROM` limit are considered. The script matches a pool to a webapp using exact normalized webapp/pool metadata, and confirms the webapp's current `processManagerMaxChildren` value still equals `FROM`. Unmatched pools and settings that have since changed are skipped rather than guessed. If a pool is unmatched, the report still shows the server and pool so you can identify it.

SSH requirements:
- The machine running the script must be able to SSH non-interactively as `root@SERVER_IP` to each RunCloud server.
- The SSH host keys should already be trusted, and SSH must not prompt for a password or interactive confirmation.
- The RunCloud server record must expose an IP address.
- The root account must be able to read `/var/log/php*rc-fpm.log`.

This scan reads the current matching log files (not archived/rotated files with additional suffixes). It does not delete, truncate, or modify logs. Use `--server-id ID` to scan a single server. The log-based update mode is separate from PHP-version and PHP-CLI update modes.

### Bulk-update PHP-FPM pm.max_children

Use `--update-pm-max-children FROM TO` to find webapps whose current PHP-FPM `pm.max_children` value exactly matches `FROM`, then set it to `TO`. This is a separate operation from PHP-version upgrades.

Preview webapps currently set to 10 and show the proposed change to 15:

```bash
python3 upgrade_runcloud_php.py --update-pm-max-children 10 15
```

Apply the changes after reviewing the preview:

```bash
python3 upgrade_runcloud_php.py --update-pm-max-children 10 15 --apply
```

You can also restrict the operation to one server or to exact webapp names in a file:

```bash
python3 upgrade_runcloud_php.py --update-pm-max-children 10 15 --server-id 123
python3 upgrade_runcloud_php.py --update-pm-max-children 10 15 --webapps-file webapps.txt
```

The script reads each selected webapp's current settings and only targets an exact numeric match. It updates PHP-FPM settings through RunCloud's `/settings/fpmnginx` API endpoint, preserving the other settings returned by the API. The normal batch size and 10-minute pause between applied batches also apply. Dry run is the default; `--apply` is required to make changes. This mode cannot be combined with PHP-CLI update or PHP inventory modes.

### Batch webapp PHP updates

Matching webapps are processed in batches of 10 by default. After each batch, the script pauses for 10 minutes before continuing, to spread out API update requests. You can change the batch size with `--batch-size`:

```bash
# Default: batches of 10
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --apply

# Custom batch size of 20
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --batch-size 20 --apply
```

The batch option applies to webapp PHP updates. PHP-CLI updates remain server-level operations.

### Update server PHP-CLI too

PHP-CLI is a server-level setting, separate from each webapp's PHP version. Add `--update-php-cli` to update a server's PHP-CLI version when its current version matches `--source-php`; it will be changed to `--target-php`.

To preview updates to both webapp PHP and PHP-CLI from PHP 8.1 to PHP 8.2:

```bash
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --update-php-cli
```

To apply both types of updates:

```bash
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --update-php-cli --apply
```

PHP-CLI is checked once per server, using the server's `phpCLIVersion` field. Only servers whose PHP-CLI version matches the selected source version are targeted.

To update **only PHP-CLI** and leave all webapp PHP versions untouched, use `--only-php-cli`:

```bash
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --only-php-cli
python3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --only-php-cli --apply
```

The first command previews matching servers; the second applies the PHP-CLI changes. This mode skips webapp listing and updates.

Limit the run to one server:

```bash
python3 upgrade_runcloud_php.py --server-id 123
python3 upgrade_runcloud_php.py --server-id 123 --apply
```

Use the PHP version identifiers accepted by RunCloud's API (for example, `php81rc`, `php82rc`). Confirm that the requested target version is available on the server. Back up production sites and check application compatibility before applying changes.

## Versioning

This project uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR**: incompatible behavior or usage changes.
- **MINOR**: backward-compatible functionality.
- **PATCH**: backward-compatible bug fixes.

The canonical version is recorded in `VERSION` and should match the script's `VERSION` constant. Each release should have a matching Git tag such as `v1.7.2`.

See [CHANGELOG.md](CHANGELOG.md) for release history.
