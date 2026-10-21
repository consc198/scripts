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
