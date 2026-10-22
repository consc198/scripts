# Changelog

All notable changes to this project are documented in this file.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): MAJOR for incompatible changes, MINOR for backward-compatible functionality, and PATCH for backward-compatible fixes.

## [1.0.0] - 2026-10-22

### Added
- Initial versioned release of the RunCloud–StatusCake audit script.
- Read RunCloud and StatusCake API tokens from local token files.
- Compare RunCloud web app domains and names against StatusCake uptime monitors.
- Write unmatched web apps to `webapps_missing_statuscake.txt`.
- Use the system `curl` executable for API requests, with timeouts and retry handling.
- Add command-line options for token file paths, report output path, and `--version`.
- Add README usage instructions and `.gitignore` entries for credentials and generated output.

### Security
- The script is read-only and does not create, update, or delete monitors.
- Token files and the generated report are excluded by `.gitignore`.
