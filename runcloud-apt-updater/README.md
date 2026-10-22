# RunCloud APT Updater

**Current version:** `1.3.2` — see [`CHANGELOG.md`](CHANGELOG.md) for release history.

Discover RunCloud servers using curl, then optionally connect over SSH as root to update Debian/Ubuntu packages. The script uses Python's standard library only; it does not use the requests library.

## Requirements

- Python 3, curl, and ssh
- A RunCloud API token stored in `token.txt` in this directory
- Root SSH access to each server, with host keys already trusted in `~/.ssh/known_hosts`

Create `token.txt` containing only your RunCloud API token. The repository's `.gitignore` excludes this filename; do not force-add the token file.

## Usage

Run from this directory:

~~~bash
python3 runcloud_updater.py --version
python3 runcloud_updater.py --list
python3 runcloud_updater.py --server SERVER_ID --check
python3 runcloud_updater.py --server SERVER_ID --apply
python3 runcloud_updater.py --all --check --workers 5
python3 runcloud_updater.py --all --apply --workers 5
python3 runcloud_updater.py --all --check --packages-only --workers 5
python3 runcloud_updater.py --all --apply --packages-only --workers 5
~~~

`--packages-only` restricts package operations to `nano`, `ubuntu-advantage-tools`, `ubuntu-pro-client`, and `ubuntu-pro-client-l10n`; it must be combined with `--check` or `--apply`. It uses APT `--only-upgrade`, so it will not install any of those packages if they are absent. Without this flag, the regular full-system behavior is unchanged. `--workers N` sets the maximum number of servers processed concurrently (default `5`; allowed range `1`–`100`). Start conservatively, for example with `--workers 5`, to avoid overwhelming servers or network capacity. `--list` only lists servers. `--check` refreshes APT indexes and simulates upgrades without installing them. `--apply` installs available upgrades. Servers are processed sequentially. SSH strict host-key checking is enabled, so confirm `known_hosts` is populated before running.

The script appends failures only to `failures.log` in this directory, with timestamps; successful operations are not logged. The log is append-only across runs. It retries transient API failures (including HTTP 429 rate limits) up to five times per request, with a delay and a retry time limit. It requests up to 40 servers per API page and follows RunCloud pagination until all pages are fetched. It reports page-fetch progress. The script expects the API response to contain a list of servers and common ID/name/IP fields. Confirm `--list` output against your RunCloud account before applying upgrades. Test on one non-production server before using `--all --apply`.

The script does not reboot servers automatically. Review upgrade output and plan any required reboots separately.

## Versioning and changelog

The script version is defined in `runcloud_updater.py` and displayed by `--version`. For each release, update that version and add a dated entry to `CHANGELOG.md`. Versions follow Semantic Versioning (`MAJOR.MINOR.PATCH`).
