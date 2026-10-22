# RunCloud ↔ StatusCake Monitor Audit

**Current version:** `1.0.0` · See [CHANGELOG.md](CHANGELOG.md) for release history.

A read-only Python script that checks every RunCloud web app against StatusCake uptime monitors and writes web apps without a matching monitor to a text report.

## Requirements

- Python 3.10 or newer
- `curl` installed and available on your `PATH`
- A RunCloud API v3 bearer token with permission to list servers, web apps, and domains
- A StatusCake API token with permission to list uptime checks
- Network access to both APIs

No third-party Python packages are required. All API HTTP requests are made with the system `curl` command; the script does not use Python `requests` or Python's built-in HTTP clients.

## Configure tokens

Put the RunCloud bearer token on its own line in `token.txt` and the StatusCake API token on its own line in `statuscaketoken.txt` in the directory from which you run the script.

Keep both files private. They are deliberately not included in this repository. Do not commit tokens to Git.

## Run

From this directory:

```bash
python3 audit_monitors.py
```

The report is written to `webapps_missing_statuscake.txt`. The script prints counts and any API errors to the terminal. To print the current version, run `python3 audit_monitors.py --version`.

You can override the token and report paths:

```bash
python3 audit_monitors.py \
  --runcloud-token-file /secure/path/token.txt \
  --statuscake-token-file /secure/path/statuscaketoken.txt \
  --output /secure/path/webapps_missing_statuscake.txt
```

## Matching logic

1. Fetches all RunCloud servers, each server's web apps, and each web app's configured domains.
2. Fetches all StatusCake **uptime** checks.
3. Normalizes hostnames (case-insensitive, ignores a leading `www.`) and matches RunCloud domains against the monitor URL hostname.
4. If no domain matches, falls back to an exact case-insensitive match between the RunCloud web app name/alias and the StatusCake monitor name.
5. Writes unmatched web apps, with server name, IDs, and known domains, to the report.

A monitor only counts as a match when it is an uptime check. Page Speed or SSL-only checks are not included. Review the report before making monitoring changes; names and domains may differ intentionally.

The script never creates, edits, or deletes monitors. If an API request fails (other than an individual domain lookup, which is warned about and falls back to available web-app fields), the audit stops rather than presenting a potentially misleading complete report.

## API references

- [RunCloud API v3 — List Servers](https://runcloud.io/docs/api/v3/api-8617075)
- [RunCloud API v3 — List Web Applications](https://runcloud.io/docs/api/v3/api-8617093)
- [RunCloud API v3 — List Domain Names](https://runcloud.io/docs/api/v3/api-8617112)
- [StatusCake API — Uptime checks](https://developers.statuscake.com/api/)
