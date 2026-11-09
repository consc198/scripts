# RunCloud Deployment Script

**Current version:** `1.1.0` (see [`VERSION`](VERSION)).

Bash-based deployment helper for newly provisioned RunCloud servers. The initial deployment task installs the Zabbix 7.4 agent on Ubuntu 24.04 or Ubuntu 26.04.

## Requirements

- Bash, curl, jq and SSH on the machine running this script
- RunCloud API token in `token.txt` beside the script (one line; never commit this file)
- Root SSH access to the target server, already available through your SSH configuration/agent
- The target server's SSH host key already trusted in `~/.ssh/known_hosts`
- Ubuntu 24.04 or Ubuntu 26.04 on the target server

## Versioning

The project follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR** for incompatible changes to command-line behavior or deployment expectations.
- **MINOR** for backward-compatible deployment features.
- **PATCH** for backward-compatible fixes and documentation corrections.

The `VERSION` file is the single source of truth for the script version. Check it with `./runcloud-deployment.sh --version`. Each release should update `VERSION` and add a dated section to `CHANGELOG.md`; release tags should use the `v` prefix (for example, `v1.1.0`).

## Usage

```bash
chmod +x runcloud-deployment.sh
./runcloud-deployment.sh --version
./runcloud-deployment.sh --list
./runcloud-deployment.sh
./runcloud-deployment.sh --server SERVER_ID
```

The default mode presents an interactive server list and asks for confirmation before connecting. The script targets one server per run; it does not deploy to every server automatically.

## Zabbix deployment

The script checks the target OS before making changes, then selects the official Zabbix 7.4 repository package for Ubuntu 24.04 or Ubuntu 26.04. It installs `zabbix-agent`, downloads the included `zabbix_agentd.conf` from this repository, waits 60 seconds, restarts the service, verifies it is active, and enables it at boot. It also creates `/etc/systemd/journald.conf.d/99-runcloud-apt-updater.conf` with `SystemMaxUse=500M`, restarts `systemd-journald`, and verifies the service is active. Other OS versions are rejected before installation.

The configuration retains the existing Zabbix server addresses (`23.88.108.39`) and agent settings.

## Security notes

- Keep `token.txt` local and out of Git.
- SSH uses BatchMode and strict host-key checking; it will not prompt for a password or automatically accept an unknown host key.
- The remote connection is made as `root`, matching the required package and service operations.
