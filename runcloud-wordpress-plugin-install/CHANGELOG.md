# Changelog

This project uses [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH. Release tags should use the `v` prefix (for example, `v1.1.0`).

## [1.1.0] - 2026-10-20

### Added
- `--version` prints the script version without requiring RunCloud credentials.
- Every JSON report entry includes `script_version`.
- Plugin update reports include `plugin_version_before` and `plugin_version_after`, obtained from WP-CLI.
- Plugin updates distinguish `updated` from `current` when both versions are known.

### Notes
- This changelog records the intended release version; a Git tag and GitHub Release still need to be published separately.
- Plugin version fields can be `null` when WP-CLI cannot retrieve a version.
