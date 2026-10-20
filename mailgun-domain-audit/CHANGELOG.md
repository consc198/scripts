# Changelog

All notable changes to this project are documented here.

This project follows [Semantic Versioning](https://semver.org/) where practical and uses the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

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
