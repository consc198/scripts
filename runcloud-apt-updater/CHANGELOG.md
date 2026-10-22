# Changelog

All notable changes to RunCloud APT Updater are documented here.

## [1.3.0] - 2026-10-22

### Added
- Add `--packages-only` mode to check or upgrade only `nano`, `ubuntu-advantage-tools`, `ubuntu-pro-client`, and `ubuntu-pro-client-l10n`.
- Use APT `--only-upgrade` so the targeted mode does not install these packages if they are absent.
- Keep the existing full-system update behavior unchanged when `--packages-only` is not supplied.


## [1.2.0] - 2026-10-22

### Added
- Run package checks and upgrades concurrently across multiple servers.
- Add `--workers` to configure concurrency (default 5, allowed range 1–100).
- Report a final succeeded/failed count across all worker tasks.


## [1.1.0] - 2026-10-22

### Fixed
- Fetch all RunCloud server pages instead of stopping at the default first page (typically 15 servers).
- Request up to 40 servers per page and report page-fetch progress.
- Deduplicate servers by ID across returned pages.


This project follows [Semantic Versioning](https://semver.org/): MAJOR for incompatible changes, MINOR for backward-compatible functionality, and PATCH for backward-compatible fixes.

## [1.0.0] - 2026-10-22

### Added
- Initial versioned release.
- List RunCloud servers using the RunCloud API via `curl`.
- Read the API token from local `token.txt`.
- Run package checks or upgrades over SSH as `root`, using the machine's existing SSH configuration.
- Add `--version` to print the installed script version.
- Keep upgrades opt-in via `--apply`; `--check` simulates upgrades.
