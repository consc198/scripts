# RunCloud PHP Upgrader

**Current version: 1.0.0**

Finds RunCloud web applications using PHP 8.0 or PHP 8.1 and upgrades them to PHP 8.2.

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

Preview matching webapps first (no changes are made):

```bash
python3 upgrade_runcloud_php.py
```

Apply upgrades:

```bash
python3 upgrade_runcloud_php.py --apply
```

Limit the run to one server:

```bash
python3 upgrade_runcloud_php.py --server-id 123
python3 upgrade_runcloud_php.py --server-id 123 --apply
```

The script only targets webapps whose API response has `phpVersion` equal to `php80rc` or `php81rc`. It targets `php82rc`. Back up production sites and check application compatibility before applying changes.

## Versioning

This project uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR**: incompatible behavior or usage changes.
- **MINOR**: backward-compatible functionality.
- **PATCH**: backward-compatible bug fixes.

The canonical version is recorded in `VERSION` and should match the script's `VERSION` constant. Each release should have a matching Git tag such as `v1.0.0`.

See [CHANGELOG.md](CHANGELOG.md) for release history.
