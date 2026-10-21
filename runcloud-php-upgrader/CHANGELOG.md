# Changelog

All notable changes to this project are documented here.

This project follows [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-21

### Added
- Discover accessible RunCloud servers and their web applications.
- Identify webapps using PHP 8.0 or PHP 8.1 and target PHP 8.2.
- Dry-run preview by default; use `--apply` to submit changes.
- Optional `--server-id` filter.
- Read the API token from local `token.txt`.
- Ignore `token.txt` so credentials are not committed.
- Display the script version with `--version`.

## [1.1.0] - 2026-10-21

### Added
- Configure source PHP version(s) with `--source-php`.
- Configure the target PHP version with `--target-php`.
- Keep PHP 8.0 and 8.1 as the default sources and PHP 8.2 as the default target.
- Reject a target version that is also listed as a source version.

## [1.1.1] - 2026-10-21

### Changed
- Replace Python's `requests` library with the system `curl` command for API requests.
- Remove the Python package installation step; `curl` must be installed and available in `PATH`.

## [1.2.0] - 2026-10-21

### Added
- Show progress while scanning webapps, including a percentage and completed count.
- Print status messages while fetching server and webapp lists.

## [1.3.0] - 2026-10-21

### Added
- Add `--update-php-cli` to optionally update server-level PHP-CLI versions using the configured `--source-php` and `--target-php` values.
- Use the RunCloud API v3 endpoint `PATCH /servers/{serverId}/php/cli` for PHP-CLI changes.
- Report PHP-CLI matches, accepted updates, and failures separately from webapp PHP updates.

## [1.4.0] - 2026-10-21

### Added
- Add `--only-php-cli` to update server PHP-CLI versions without listing or changing webapp PHP settings.

## [1.5.0] - 2026-10-21

### Added
- Process matching webapp PHP updates in batches of 10 by default.
- Add `--batch-size` to customize the number of webapps per batch.
- Pause 2 seconds between applied batches to spread out API requests.

## [1.5.1] - 2026-10-21

### Changed
- Pause 10 minutes (600 seconds) instead of 2 seconds between applied webapp PHP update batches.

## [1.6.0] - 2026-10-21

### Added
- Add `--webapps-file` to restrict webapp PHP updates to exact webapp names listed one per line in a text file.
- Ignore blank lines and comment lines beginning with `#`.
- Report listed webapp names that are not found and listed webapps that do not match the selected source PHP versions.
