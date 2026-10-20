# Changelog

All notable changes to this project are documented here.

This project follows [Semantic Versioning](https://semver.org/) where practical and uses the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [0.3.3] - 2026-10-20

### Changed
- Normalize `.conversalmail.be` and `.conversalhosting.be` Mailgun domains to their first label for RunCloud comparison (for example, `floorsandmore.conversalmail.be` becomes `floorsandmore`).

## [0.3.2] - 2026-10-20

### Fixed
- Recognize Mailgun DNS record verification values such as `valid: "valid"` and `valid: "invalid"`, correctly classifying SPF, DKIM, and tracking CNAME records.

## [0.3.1] - 2026-10-20

### Changed
- Always read the RunCloud API token from `runcloud_apikey.txt`; ignore `RUNCLOUD_API_KEY`.

## [0.3.0] - 2026-10-20

### Added
- Add optional `--runcloud-check` to compare Mailgun domains against domains configured on RunCloud servers and web applications.
- Read the RunCloud API token from `runcloud_apikey.txt`, with `RUNCLOUD_API_KEY` as an environment-variable override.
- Write missing domains to `mailgun_domains_missing_in_runcloud.csv` (customizable with `RUNCLOUD_MISSING_CSV`).

## [0.2.0] - 2026-10-20

### Added
- Add `--version` to print the script name and version from `VERSION`, without requiring an API key.

## [0.1.1] - 2026-10-20

### Changed
- Read the Mailgun API key from `apikey.txt` in the project directory by default.
- Keep `MAILGUN_API_KEY` as an optional override; the environment variable takes precedence over the file.

### Security
- Ignore `apikey.txt` and the generated CSV report via the project `.gitignore`.

## [0.1.0] - 2026-10-20

### Added
- Initial read-only Mailgun domain audit utility.
- EU Mailgun API as the default endpoint, overridable with `MAILGUN_API_BASE`.
- CSV report for Mailgun domain state and SPF, DKIM, tracking, and DMARC status.
- Basic retry handling for rate limits and transient server errors.
- Project README and environment-based API key configuration.

### Notes
- Initial release; live account validation and broader response-shape testing are still needed.
- `UNKNOWN` results require review and should not be treated as confirmed failures.
