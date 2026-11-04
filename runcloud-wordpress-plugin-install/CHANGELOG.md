# Changelog

## [1.5.0] - 2026-11-04

### Changed
- Resolve numeric web-app IDs through RunCloud's single-web-app endpoint instead of listing all web apps on every server.
- Keep exact-name target resolution and all-server discovery behavior unchanged.

### Notes
- ID resolution still retrieves the server list and probes the per-server web-app object endpoint until each ID is found.
- Live RunCloud API and WordPress server testing has not been performed as part of this change.

## [1.4.0] - 2026-11-04

### Changed
- Switch the default installer archive from Conversal Admin to Events Manager Pro 3.9.6.
- Pin the Events Manager Pro ZIP to its verified SHA-256 checksum.

### Notes
- The installer downloads the repository-hosted `events-manager-pro.3.9.6.zip` and verifies its SHA-256 before installing.
- Live RunCloud and WordPress server testing has not been performed as part of this change.

Notable changes to the RunCloud WordPress Plugin Installer are documented here.

This project uses [Semantic Versioning](https://semver.org/). Release tags use the format `vMAJOR.MINOR.PATCH`.

## [1.3.0] - 2026-11-04

### Added
- Add read-only `--find-plugin` mode to scan selected WordPress apps for an installed plugin.
- Export matching web-app IDs to `webapps.txt` for reuse with `--webapps-file`.
- Add dedicated JSON discovery reporting and configurable output paths.

### Notes
- Discovery uses WP-CLI as each app's RunCloud Linux user and records found, not-found, and failed results.
- Discovery does not modify WordPress sites. Live RunCloud and WordPress server testing has not been performed as part of this change.

## [1.2.0] - 2026-10-23

### Added
- Add `--purge-runcache` to run `wp runcache purge` on selected WordPress apps.
- Support dry-run preview and a dedicated `runcloud-cache-purge.json` report.
- Add `--purge-output` to customize the cache purge report path.

### Notes
- Cache purge runs as the WordPress web app's RunCloud Linux user.
- Live RunCloud and WordPress server testing has not been performed as part of this change.

## [1.1.0] - 2026-10-20

### Added
- Add `--version` so the script version can be checked without API credentials.
- Include `script_version` in JSON reports.
- Track plugin versions before and after update attempts.
- Report the update version when the configured WordPress update source provides one.
- Distinguish plugins that were updated from plugins that were already current.
- Document release tagging and the versioning policy.

### Notes
- Plugin version detection relies on WP-CLI's `plugin list` output.
- Live RunCloud and WordPress server testing has not been performed as part of this change.
