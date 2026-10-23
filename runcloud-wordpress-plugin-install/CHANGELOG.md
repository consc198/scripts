# Changelog

Notable changes to the RunCloud WordPress Plugin Installer are documented here.

This project uses [Semantic Versioning](https://semver.org/). Release tags use the format `vMAJOR.MINOR.PATCH`.

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
