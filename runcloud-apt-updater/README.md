# RunCloud APT Updater

Discover servers from the RunCloud API using curl, then optionally connect over SSH to refresh APT indexes and upgrade Debian/Ubuntu packages. The Python script uses only the standard library for orchestration; it does not use the requests library.

## Requirements

- Python 3
- curl and ssh installed on the machine running the script
- A RunCloud API token with permission to list servers
- SSH access to each target server, with host keys already trusted in ~/.ssh/known_hosts
- The configured SSH user must be allowed to run apt-get with non-interactive sudo

## Configure credentials

Export the API token and SSH username. Use a key already loaded into ssh-agent or provide its path.

~~~bash
export RUNCLOUD_API_TOKEN='your-runcloud-api-token'
export RUNCLOUD_SSH_USER='your-ssh-user'
export RUNCLOUD_SSH_KEY="$HOME/.ssh/id_ed25519" # optional if ssh-agent/default key is used
~~~

Do not commit API tokens or private SSH keys to this repository.

## Usage

List the API's server inventory without connecting over SSH:

~~~bash
python3 runcloud_updater.py --list
~~~

Inspect the pending package upgrades on one server. This refreshes APT indexes and simulates the upgrade; it does not install upgrades:

~~~bash
python3 runcloud_updater.py --server SERVER_ID --check
~~~

Apply upgrades to one server:

~~~bash
python3 runcloud_updater.py --server SERVER_ID --apply
~~~

Apply upgrades to all servers returned by the API, sequentially:

~~~bash
python3 runcloud_updater.py --all --apply
~~~

Optional settings:

- --api-url URL: override the server-list endpoint. Defaults to https://manage.runcloud.io/api/v3/servers. RUNCLOUD_API_URL can also set this.
- --ssh-user USER: override RUNCLOUD_SSH_USER.
- --ssh-key PATH: override RUNCLOUD_SSH_KEY.
- --timeout SECONDS: per-server SSH command timeout (default 1800 seconds).

## Safety notes

- The script does not install packages unless --apply is explicitly provided.
- --check still runs apt-get update, which changes local package-index data, but only simulates package upgrades.
- Servers are processed one at a time. A failure on one server is reported and the script continues to the next server.
- SSH strict host-key checking is enabled. Verify and populate known_hosts before running.
- The script uses sudo -n; it will fail rather than prompt for a password.
- apt-get upgrade -y does not automatically remove installed packages to satisfy upgrades. Review output and plan reboots separately.
- Test with one non-production server before using --all --apply.

## API response compatibility

The script expects the server-list endpoint to return a JSON array, or an object containing a list under a common key such as data, servers, items, or result. It looks for common server ID, name, and IP/hostname field names. Run --list first and confirm that the API response fields match your RunCloud account's response. If your response uses different field names or pagination, adjust server_items() and get_server_host() accordingly before applying upgrades.
