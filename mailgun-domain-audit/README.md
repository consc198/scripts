# Mailgun Domain Audit

Read-only Python utility to audit Mailgun domains and report DNS authentication status, including SPF, DKIM, and DMARC.

## Requirements

- Python 3.9+
- `requests`

Install the dependency:

```bash
python3 -m pip install requests
```

## Configure

Set your Mailgun API key in the environment. Do not hard-code or commit API keys.

```bash
export MAILGUN_API_KEY='your-mailgun-api-key'
```

The script defaults to Mailgun's EU API:

`https://api.eu.mailgun.net`

To override the API base URL for another region:

```bash
export MAILGUN_API_BASE='https://api.mailgun.net'
```

## Run

From this directory:

```bash
python3 mailgun_domain_audit.py
```

The report is written to `mailgun_domain_audit.csv`. Set `MAILGUN_AUDIT_CSV` to choose another output path.

## Status meanings

- `PASS`: the API response explicitly indicates success.
- `FAIL`: the API response explicitly indicates a failure or unconfigured DMARC record.
- `UNKNOWN`: the script could not confidently classify the response; review before taking action.
- `REVIEW`: at least one check is unknown.
- `ACTION_REQUIRED`: at least one check failed or the domain is not active.
- `ERROR`: the API call for that domain failed.

This is an initial audit helper, not a substitute for validating the results against your account's live Mailgun API responses. It does not change DNS or Mailgun configuration.
