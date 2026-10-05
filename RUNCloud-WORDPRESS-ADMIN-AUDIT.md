# RunCloud WordPress Administrator Audit

Audits WordPress administrator accounts across all RunCloud servers and WordPress web applications.

The script uses the RunCloud API for inventory/discovery and SSH + WP-CLI to inspect each WordPress installation.

## Requirements

- `curl`
- `jq`
- `ssh`
- WP-CLI installed/available for each WordPress application
- SSH access from the machine running the script to the RunCloud servers
- A RunCloud API v3 bearer token

## Usage

```bash
export RUNCLOUD_TOKEN='YOUR_RUNCLOUD_API_TOKEN'
./runcloud-wp-admin-audit.sh
```

Optional configuration:

```bash
export SSH_KEY="$HOME/.ssh/id_rsa"
export SSH_PORT=22
export EXCLUDED_USERS='conversal'
```

Multiple known-good usernames can be excluded with a comma-separated value:

```bash
export EXCLUDED_USERS='conversal,another-admin'
```

The default exclusion is `conversal`.

## Output

The script reports non-excluded WordPress administrators with:

- RunCloud server
- Server IP
- RunCloud application
- WordPress username
- Email
- Registration timestamp

It exits with a summary of the number of servers scanned and non-excluded administrators found.

## Security notes

- Keep the RunCloud API token out of source control. Use an environment variable or another secret store.
- The script performs read-only WordPress queries.
- `wp user list` is run with `--skip-plugins --skip-themes` to reduce interference from application code during the audit.
- The script does not delete, disable, or modify WordPress users.

## API behavior

RunCloud API v3 responses are paginated. The script follows `meta.pagination.total_pages` for both server and web-application discovery.
