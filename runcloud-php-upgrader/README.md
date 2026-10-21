# RunCloud PHP Upgrader

**Current version: 1.4.0**

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

### Update server PHP-CLI too\n\nPHP-CLI is a server-level setting, separate from each webapp's PHP version. Add `--update-php-cli` to also update a server's PHP-CLI version when its current version matches `--source-php`; it will be changed to `--target-php`. For example, to update both webapps and PHP-CLI from PHP 8.1 to PHP 8.2:\n\n```bash\npython3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --update-php-cli\npython3 upgrade_runcloud_php.py --source-php php81rc --target-php php82rc --update-php-cli --apply\n```\n\nThe script checks the server's `phpCLIVersion` field and calls `PATCH /servers/{serverId}/php/cli` for matching servers. Since this setting applies to the whole server, it is evaluated once per server, not once per webapp.\n\n
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

The canonical version is recorded in `VERSION` and should match the script's `VERSION` constant. Each release should have a matching Git tag such as `v1.4.0`.

See [CHANGELOG.md](CHANGELOG.md) for release history.
