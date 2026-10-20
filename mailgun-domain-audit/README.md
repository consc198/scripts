# Mailgun Domain Audit

**Current version: `0.1.0`** · Read-only audit utility for Mailgun sending domains.

The tool inventories domains in a Mailgun account and writes a CSV report with available Mailgun DNS verification and DMARC information. It does not modify Mailgun settings or DNS records.

## Features

- Lists domains from the Mailgun Domains API.
- Checks domain detail responses for SPF/DKIM-related DNS verification data.
- Checks DMARC using the Mailgun DMARC records endpoint.
- Exports results to CSV.
- Uses the **EU API by default**; the API base can be overridden through an environment variable.
- Keeps credentials out of source code.

## Requirements

- Python 3.9+
- `requests`

Install:

```bash
python3 -m pip install requests
```

## Configuration

Set your Mailgun API key in your shell:

```bash
export MAILGUN_API_KEY='your-mailgun-api-key'
```

The default API base is `https://api.eu.mailgun.net`. For a US-region account, override it:

```bash
export MAILGUN_API_BASE='https://api.mailgun.net'
```

Optional output path:

```bash
export MAILGUN_AUDIT_CSV='mailgun_domain_audit.csv'
```

Never commit your API key or other secrets.

## Run

From this directory:

```bash
python3 mailgun_domain_audit.py
```

The script writes `mailgun_domain_audit.csv` and prints a summary to the terminal.

## Interpreting results

- **PASS** — the API response explicitly indicates success.
- **FAIL** — the API response explicitly indicates failure or reports DMARC as unconfigured.
- **UNKNOWN** — the response did not contain a status this initial classifier can confidently interpret.
- **REVIEW** — at least one key check is unknown.
- **ACTION_REQUIRED** — at least one key check failed or the Mailgun domain is not active.
- **ERROR** — a request failed for that domain.

**Important:** this is an initial version. Validate results against your account's actual Mailgun API responses before using the report as the sole basis for remediation. In particular, SPF/DKIM record shapes and verification fields may vary by domain configuration. A `PASS` from this script reflects its interpretation of returned API data, not an independent DNS standards audit.

## Versioning and changelog

The project version is recorded in `VERSION`. Version history is tracked in `CHANGELOG.md`.

We aim to follow Semantic Versioning:
- **PATCH** (`0.1.x`): backward-compatible fixes.
- **MINOR** (`0.x.0`): backward-compatible features while the project is pre-1.0.
- **MAJOR** (`x.0.0`): breaking changes after 1.0.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Project files

- `mailgun_domain_audit.py` — audit script.
- `README.md` — setup, usage, and limitations.
- `CHANGELOG.md` — notable changes by version.
- `VERSION` — current project version.

## Safety

This utility is read-only with respect to Mailgun configuration and DNS. Treat generated CSV files as operational data; review them before sharing.
