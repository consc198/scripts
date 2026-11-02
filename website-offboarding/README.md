# Website Offboarding

A cautious, resumable offboarding tool for RunCloud-hosted WordPress websites.

## Agreed scope

1. Resolve a domain to its RunCloud server and web application.
2. Back up the complete application files and WordPress database.
3. Upload the backup to Box and verify the uploaded object.
4. Remove associated StatusCake and Mailgun entries.
5. Disconnect Wordfence Central and remove the site from ManageWP **only through supported/verified interfaces**.
6. Write a per-domain audit report.

**Explicitly out of scope:** taking the website offline, changing DNS, and deleting or modifying the RunCloud application. A human performs any RunCloud application deletion manually.

## Safety model

- Discovery and planning are read-only.
- Destructive provider cleanup must be separately confirmed.
- No provider cleanup should begin until the backup has been uploaded and verified.
- Unknown or ambiguous matches are reported for manual review; the tool must never guess.
- Secrets are read from local files/environment variables and must never be committed.
- Wordfence Central and ManageWP automation are not enabled until a supported API/action has been verified. No scraping or undocumented endpoint is used as a fallback.

## Current status

This is the initial project scaffold. It currently supports RunCloud inventory discovery and domain matching in `--plan` mode. Backup, Box upload, and provider cleanup adapters will be added and tested as their credentials and account-specific details are confirmed. The current version does not delete or modify anything.

## Requirements

- Python 3.10+
- `requests`
- `ssh` and `scp` (for the backup phase)
- Root SSH access from the controller to the RunCloud servers

Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## RunCloud token

Place the RunCloud API v3 bearer token in `token.txt` beside `offboard.py` (or set `RUNCLOUD_TOKEN_FILE`). This matches the convention used by the other scripts in this repository.

The token file is ignored by Git. Never commit it.

## Usage

Plan an offboarding by domain:

```bash
python3 offboard.py example.com --plan
```

List RunCloud servers and applications:

```bash
python3 offboard.py --inventory
```

The plan mode is read-only. It resolves the domain and displays the matched server/application, SSH address and application paths. It does not create a backup or remove anything yet.

## Credentials planned for subsequent adapters

| Service | Local credential convention |
|---|---|
| RunCloud | `token.txt` |
| StatusCake | `statuscaketoken.txt` (existing repository convention) |
| Mailgun | `apikey.txt` (existing repository convention; EU API by default) |
| Box | To be configured (OAuth access/refresh token or supported service-account auth) |
| Wordfence Central | Pending supported integration/authentication confirmation |
| ManageWP | Pending supported integration/authentication confirmation |

## Backup design

The intended backup is a single dated archive containing:
- The entire RunCloud application root (including hidden files).
- A WordPress database export made using WP-CLI where available, or a safely extracted database configuration fallback.
- A SHA-256 checksum manifest.

The backup is staged outside the live document root. It is retained locally until Box confirms the uploaded file and the remote file size/checksum can be verified. Database credentials must not appear in process arguments or logs.

## Manual final step

After the automation completes, an operator reviews the report and, if appropriate, deletes the RunCloud application manually. The script will never call a RunCloud delete endpoint.
