# RunCloud PHP Upgrader

**Current version: 1.1.0**

Find RunCloud web applications running selected PHP version(s) and change them to a target PHP version.

## Requirements

- Python 3.9+
- A RunCloud API token with permission to read servers/webapps and change webapp PHP settings.

## Setup

1. Install the dependency:

   ```bash
   python3 -m pip install requests
   ```

2. Create `token.txt` in this directory and put your RunCloud API token in it. Keep this file private; it is excluded by `.gitignore`.

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

The canonical version is recorded in `VERSION` and should match the script's `VERSION` constant. Each release should have a matching Git tag such as `v1.1.0`.

See [CHANGELOG.md](CHANGELOG.md) for release history.
