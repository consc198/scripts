# Mailgun Domain Audit

**Current version: `0.3.8`** · Read-only audit utility for Mailgun sending domains.

The tool inventories domains in a Mailgun account and writes a CSV report with available Mailgun DNS verification and DMARC information. It does not modify Mailgun settings or DNS records.

## Features

- Lists domains from the Mailgun Domains API.
- Explicitly requests Mailgun domain DNS records and checks SPF/DKIM-related verification data.
- Checks DMARC using the Mailgun DMARC records endpoint.
- Exports results to CSV.
- Uses the **EU API by default**; the API base can be overridden through an environment variable.
- Reads the Mailgun API key from local `apikey.txt`, with an optional environment-variable override.
- Optionally compares Mailgun sending domains with domains configured across RunCloud servers and web applications. RunCloud API requests use the system `curl` command to match the working request path in environments where Cloudflare challenges Python HTTP clients.

## Requirements

- Python 3.9+
- `requests`
- `curl` (required for the optional RunCloud comparison)

Install:

```bash
python3 -m pip install requests
```

## Configure

Create a file named `apikey.txt` in this directory, next to `mailgun_domain_audit.py`. Put your Mailgun API key on a single line:

```text
key-your-mailgun-api-key
```

The script reads and trims the file contents. Alternatively, set `MAILGUN_API_KEY` in the environment; when set, the environment variable takes precedence over the file.

The default API base is `https://api.eu.mailgun.net`. For a US-region account, override it:

```bash
export MAILGUN_API_BASE='https://api.mailgun.net'
```

Optional output path:

```bash
export MAILGUN_AUDIT_CSV='mailgun_domain_audit.csv'
```

### Optional RunCloud comparison

To enable the comparison, create `runcloud_apikey.txt` beside the script and put your RunCloud API token on one line. RunCloud API access must be enabled for your account. The script always reads the token from `runcloud_apikey.txt`; `RUNCLOUD_API_KEY` is not used.

Compare Mailgun domains against RunCloud without running the DNS/DMARC audit:

```bash
python3 mailgun_domain_audit.py --runcloud-check
```

The script still retrieves the Mailgun domain list for comparison, but skips per-domain DNS and DMARC requests. To run both checks in one invocation, use:

```bash
python3 mailgun_domain_audit.py --dns-check --runcloud-check
```

The RunCloud check writes `mailgun_domains_missing_in_runcloud.csv` with any Mailgun domains that could not be found. Set `RUNCLOUD_MISSING_CSV` to change the report path.

For normalization, a leading `mg.` or `mgn.` is removed from Mailgun domain names (so `mg.stonedesign.be` is compared as `stonedesign.be` and `mgn.gunterbroodcoorens.com` as `gunterbroodcoorens.com`). Mailgun domains ending in `.conversalmail.be` or `.conversalhosting.be` are compared using only their first label (so `floorsandmore.conversalmail.be` is compared as `floorsandmore`). A leading `www.` is removed from RunCloud domain names. Other domain names are compared as provided. The comparison is read-only.

**Security:** `apikey.txt` and `runcloud_apikey.txt` contain secrets. Keep them local, do not commit them, and restrict their filesystem permissions where supported (for example, `chmod 600 apikey.txt runcloud_apikey.txt` on macOS/Linux). The repository includes `.gitignore` rules for these filenames.

## Run

Show the script version (this does not require an API key):

```bash
python3 mailgun_domain_audit.py --version
```

From this directory, run the DNS/DMARC audit explicitly:

```bash
python3 mailgun_domain_audit.py --dns-check
```

This writes `mailgun_domain_audit.csv` and prints a summary to the terminal. For backward compatibility, running the script without a check flag still runs the DNS/DMARC audit.

## Interpreting results

- **PASS** — the API response explicitly indicates success, including Mailgun DNS record values such as `valid: "valid"`.
- **FAIL** — the API response explicitly indicates failure (including `valid: "invalid"`) or reports DMARC as unconfigured.
- **UNKNOWN** — the response did not contain a status this classifier can confidently interpret.
- **REVIEW** — at least one key check is unknown.
- **ACTION_REQUIRED** — at least one key check failed or the Mailgun domain is not active.
- **ERROR** — a request failed for that domain.

**Important:** validate results against your account's actual Mailgun API responses before using the report as the sole basis for remediation. A `PASS` from this script reflects its interpretation of returned API data, not an independent DNS standards audit.

## Versioning and changelog

The project version is recorded in `VERSION`. Version history is tracked in `CHANGELOG.md`.

We aim to follow Semantic Versioning:
- **PATCH** (`0.1.x`): backward-compatible fixes.
- **MINOR** (`0.x.0`): backward-compatible features while the project is pre-1.0.
- **MAJOR** (`x.0.0`): breaking changes after 1.0.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Project files

- `mailgun_domain_audit.py` — audit script.
- `apikey.txt` — local Mailgun secret; do not commit.
- `runcloud_apikey.txt` — optional local RunCloud API token; do not commit.
- `README.md` — setup, usage, and limitations.
- `CHANGELOG.md` — notable changes by version.
- `VERSION` — current project version.

## Safety

This utility is read-only with respect to Mailgun configuration and DNS. Treat generated CSV files as operational data; review them before sharing.
