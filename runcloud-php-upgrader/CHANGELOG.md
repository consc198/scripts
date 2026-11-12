# Changelog

## [1.10.0] - 2026-11-12

### Added
- Added read-only `--audit-webapp-traffic` to aggregate client IP request counts across all selected servers' RunCloud Nginx webapp access logs for the last 48 hours.
- Reports the top 20 IPs across all webapps, including request counts and the number of webapps and servers each IP appeared on.
- Includes active access logs and rotated compressed access logs, and supports restricting the audit with `--server-id`.


## [1.9.1] - 2026-11-05

### Added
- Added `--since-hours HOURS` to filter PHP-FPM max_children scan results to warnings within a recent lookback window.
- The filter also applies to `--update-hit-max-children`, so only recently affected pools are considered for preview or updates.


All notable changes to this project are documented here.

This project follows [Semantic Versioning](https://semver.org/).

## [1.9.0] - 2026-11-02

### Added
- Added `--scan-max-children` to scan PHP-FPM logs over SSH for `max_children` warnings.
- Added aggregation of warnings by server, PHP-FPM pool, and configured `max_children` limit, including warning count and latest timestamp.
- Added `--update-hit-max-children FROM TO` to identify webapps associated with pools that hit their limit and preview or update their PHP-FPM `processManagerMaxChildren` setting.
- Added safeguards that verify the current API setting still matches the scanned limit before an update is applied.
- Added pool-to-webapp matching using exact normalized webapp names and available pool metadata; ambiguous or unmatched pools are skipped.
- Added SSH connection handling for root access to selected servers.

### Notes
- SSH must allow non-interactive root login and the server host key must already be trusted.
- The scan checks current matching `/var/log/php*rc-fpm.log` files; rotated/archive files are not included.
- Use `--apply` to make changes; otherwise the update operation is a dry run.

## [1.8.0] - 2026-11-02

### Added
- Added `--update-pm-max-children FROM TO` to bulk-update webapps whose current PHP-FPM `processManagerMaxChildren` exactly matches the supplied FROM value.
- Added dry-run preview by default and `--apply` to perform updates.
- Preserved the other PHP-FPM settings when updating `processManagerMaxChildren`.
- Supported the existing server and webapp-file filters, plus batching, for these updates.

## [1.7.2] - 2026-10-22

### Changed
- Added retries when listing webapps after transient RunCloud API errors, including HTTP 429, 500, 502, 503, and 504 responses.
- Added increasing retry delays, up to five total attempts.

## [1.7.1] - 2026-10-22

### Added
- Added a URL/domain column to the `--list-apps-php` inventory output when the RunCloud API provides a URL or domain field.
- Displays a fallback when the API does not provide a URL/domain.

## [1.7.0] - 2026-10-22

### Added
- Added read-only `--list-apps-php VERSION` to list webapps currently using a specified PHP version.
- Inventory output includes server name, server ID, webapp name, detected application type, URL/domain when available, and webapp ID.
- Added best-effort application-type detection from API metadata and path/name hints.
- Supports filtering the inventory by `--server-id`.

## [1.6.0] - 2026-10-21

### Added
- Added `--webapps-file FILE` to limit operations to exact webapp names listed in a text file.
- Accepts one webapp name per line; blank lines and lines beginning with `#` are ignored.
- Webapp name matching is exact and case-sensitive.

## [1.5.1] - 2026-10-21

### Changed
- Added a 10-minute pause between applied webapp update batches to reduce the load and rate of changes against RunCloud.

## [1.5.0] - 2026-10-21

### Added
- Added batching for webapp PHP-version changes.
- Added `--batch-size N`, defaulting to 10 webapps per batch.

## [1.4.0] - 2026-10-21

### Added
- Added `--only-php-cli` to run only the server-level PHP-CLI update operation, without changing webapp PHP versions.

## [1.3.0] - 2026-10-21

### Added
- Added `--update-php-cli` to update the server-level PHP-CLI version in addition to webapp PHP versions.

## [1.2.0] - 2026-10-21

### Added
- Added a progress bar to show progress while processing webapps.

## [1.1.1] - 2026-10-21

### Changed
- Replaced Python `requests` API calls with `curl` subprocess calls.
- Removed the need for the Python `requests` package.

## [1.1.0] - 2026-10-21

### Added
- Added configurable source and target PHP versions instead of relying only on fixed versions.

## [1.0.0] - 2026-10-21

### Added
- Initial release of the RunCloud PHP upgrader.
- Added RunCloud API integration to enumerate servers and webapps and upgrade selected webapps from configured source PHP versions to a target PHP version.
- Added dry-run behavior by default, with `--apply` required to make changes.
- Added `--server-id` to restrict operations to a specific server.
- Added local API-token loading from `token.txt` alongside the script.
