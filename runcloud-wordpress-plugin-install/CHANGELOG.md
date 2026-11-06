# Changelog

## [1.9.1] - 2026-11-06

### Fixed
- Condense RunCloud API failures so Cloudflare 429 challenge HTML no longer floods terminal output.
- Include the HTTP status and failed API endpoint in concise error messages; limit other response details to a short snippet.

### Notes
- This is an output/readability change; it does not bypass Cloudflare rate limits or change API retry behavior.
- Live RunCloud API testing has not been performed as part of this change.

## [1.9.0] - 2026-11-05

### Added
- Append every verified successful plugin/site update to a persistent tab-separated `plugin-update-history.txt` audit log.
- Record UTC timestamp, server and web-app IDs, domain, plugin file, and versions before and after the update.
- Add `--update-history-file` to choose a custom history file path.
- Ignore the local history file in Git.

### Notes
- Only updates verified by an installed-version change are logged; dry-runs, failures, exclusions, and already-current plugins are omitted.
- Live RunCloud API and WordPress server testing has not been performed as part of this change.

## [1.8.0] - 2026-11-05

### Added
- Add an optional persistent `plugin-exclusions.txt` file for per-webapp, per-domain, per-plugin update exclusions.
- Add `--exclusions-file` to select an alternate exclusions file.
- Skip excluded plugin/site combinations before WP-CLI update work and report them as `excluded`.
- Apply exclusions to dry-runs and leave non-excluded plugins eligible for batched updates.

### Notes
- Exclusion rows use three tab-separated fields: RunCloud web-app ID, domain, and plugin slug or plugin file path.
- The default local exclusions file is gitignored; a tracked example template documents the format.
- Live RunCloud API and WordPress server testing has not been performed as part of this change.

## [1.7.0] - 2026-11-05

### Added
- Batch all requested plugin updates into a single WP-CLI `plugin update` command per web app.
- Process plugin-update web apps concurrently with a configurable global worker pool.
- Add `--workers` with a default of 10; values below 1 are rejected.
- Preserve per-plugin before/after version checks and individual JSON report records after batch updates.

### Notes
- Plugin-update mode uses one plugin-list call before the batch update and one after it for verification.
- Use `--workers 1` for sequential operation or lower concurrency if servers are under load.
- Live RunCloud API and WordPress server testing has not been performed as part of this change.

## [1.6.0] - 2026-11-04

### Added
- Add `--update-core` to update WordPress core to the latest version available through WP-CLI.
- Require `--current-wp-version` and update only sites whose installed core version matches the supplied version.
- Add dry-run preview, before/after version reporting, and a dedicated `runcloud-core-update.json` report.

### Notes
- Core updates run as the WordPress app's RunCloud Linux user with plugins and themes skipped during WP-CLI execution.
- Live RunCloud API and WordPress server testing has not been performed as part of this change.

## [1.5.2] - 2026-11-04

### Fixed
- Resolve numeric web-app IDs by listing web apps per server once and matching IDs against those records.
- Remove the per-ID/per-server endpoint probing that generated hundreds of API requests and triggered Cloudflare 429 challenges.
- Keep exact-name and numeric-ID targeting on the same server-scoped resolution path.

### Notes
- Targeted resolution still retrieves server web-app lists, but does so once per server with the existing retry behavior.
- Live RunCloud API and WordPress server testing has not been performed as part of this change.


## [1.5.1] - 2026-11-04

### Fixed
- Include both stderr and response-body details in RunCloud API errors.
- Show the server IDs checked and the last API error when a numeric web-app ID cannot be resolved.

### Notes
- This is a diagnostic improvement to help distinguish an ID/server mismatch from API permission or endpoint errors.
- Live RunCloud API testing has not been performed as part of this change.

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
