# Changelog

All notable changes to the RunCloud deployment script are documented here. Versions follow [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-11-09

- Added a journald configuration drop-in at `/etc/systemd/journald.conf.d/99-runcloud-apt-updater.conf` with `SystemMaxUse=500M`.
- Restarted `systemd-journald` after applying the journald limit and verified that the service is active.

## [1.0.0] - 2026-11-09

- Initial versioned release.
- Added RunCloud API server discovery with pagination and interactive or ID-based server selection.
- Added SSH deployment to a selected server using existing root SSH access.
- Added an operating-system precheck supporting Ubuntu 24.04 and Ubuntu 26.04; unsupported versions are rejected before installation.
- Added installation of the Zabbix 7.4 agent using the matching official Ubuntu repository package.
- Added deployment of the repository's `zabbix_agentd.conf`, followed by a 60-second wait, agent restart, active-state verification, and enablement at boot.
