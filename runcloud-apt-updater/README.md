# RunCloud APT Updater

**Current version:** `1.0.0` — see [`CHANGELOG.md`](CHANGELOG.md) for release history.

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
python3 runcloud_updater.py --all --apply
~~~

`--list` only lists servers. `--check` refreshes APT indexes and simulates upgrades without installing them. `--apply` installs available upgrades. Servers are processed sequentially. SSH strict host-key checking is enabled, so confirm `known_hosts` is populated before running.

The script expects the API response to contain a list of servers and common ID/name/IP fields. Confirm `--list` output against your RunCloud account before applying upgrades. Test on one non-production server before using `--all --apply`.

The script does not reboot servers automatically. Review upgrade output and plan any required reboots separately.

## Versioning and changelog

The script version is defined in `runcloud_updater.py` and displayed by `--version`. For each release, update that version and add a dated entry to `CHANGELOG.md`. Versions follow Semantic Versioning (`MAJOR.MINOR.PATCH`).
