# RunCloud PHP Upgrader

**Current version: 1.7.1**

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

This mode makes no changes and cannot be combined with update flags. App type is inferred from the metadata and paths returned by the API; if those fields don't identify WordPress, Laravel, or another type, it reports `Unknown`.

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

The canonical version is recorded in `VERSION` and should match the script's `VERSION` constant. Each release should have a matching Git tag such as `v1.7.1`.

See [CHANGELOG.md](CHANGELOG.md) for release history.
