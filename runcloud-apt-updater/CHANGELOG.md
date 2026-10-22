# Changelog

All notable changes to RunCloud APT Updater are documented here.

This project follows [Semantic Versioning](https://semver.org/): MAJOR for incompatible changes, MINOR for backward-compatible functionality, and PATCH for backward-compatible fixes.

## [1.0.0] - 2026-10-22

### Added
- Initial versioned release.
- List RunCloud servers using the RunCloud API via `curl`.
- Read the API token from local `token.txt`.
- Run package checks or upgrades over SSH as `root`, using the machine's existing SSH configuration.
- Add `--version` to print the installed script version.
- Keep upgrades opt-in via `--apply`; `--check` simulates upgrades.
