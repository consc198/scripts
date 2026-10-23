# Mailgun Domain Audit

**Current version: `0.3.20`** · Read-only audit utility for Mailgun sending domains.

The tool inventories domains in a Mailgun account and writes a CSV report with available Mailgun DNS verification and DMARC information. It does not modify Mailgun settings or DNS records.

## Features

- Lists domains from the Mailgun Domains API.
- Explicitly requests Mailgun domain DNS records and checks SPF/DKIM-related verification data.
- Checks DMARC using the Mailgun DMARC records endpoint.
- Checks whether each normalized Mailgun domain is covered by a zone in your Cloudflare account and adds a `Cloudflare` column (`Found` or `Missing`) after `Status` in the audit CSV.
- Exports results to CSV.
- Uses the **EU API by default**; the API base can be overridden through an environment variable.
- Reads the Mailgun API key from local `apikey.txt`, with an optional environment-variable override.
- Optionally compares Mailgun sending domains with domains configured across RunCloud servers and web applications. RunCloud API requests use the system `curl` command to match the working request path in environments where Cloudflare challenges Python HTTP clients.

## Requirements

- Python 3.9+
- `requests`
- `curl` (required for the Cloudflare zone check and optional RunCloud comparison)

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

### Cloudflare zone check

The DNS/DMARC audit also checks Cloudflare zones. Create `cloudflare_apikey.txt` beside the script and put a **Cloudflare API token** on one line. The token needs permission to read zones (typically the `Zone:Read` permission) and must include the zones you want to audit. This is a Cloudflare API token, not the account's Global API Key.

The audit fetches all zone pages from the Cloudflare API using `curl --ipv4`, so Cloudflare requests use IPv4 even when the machine has IPv6 connectivity issues. It removes a leading `mg.` or `mgn.` from Mailgun domain names before matching; for example, `mg.huisvoorgezondheid.be` is checked against the Cloudflare zone `huisvoorgezondheid.be`. It also ignores case, trailing dots, and a leading `www.`. A domain is marked `Found` if it exactly matches a zone or is a subdomain covered by that zone; otherwise it is marked `Missing`.

If the token is absent or Cloudflare cannot be queried, the audit stops with an error rather than marking every domain as `Missing` based on an incomplete lookup. The token file is ignored by Git.

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

The RunCloud check writes `mailgun_domains_missing_in_runcloud.csv` with any Mailgun domains that could not be found. Set `RUNCLOUD_MISSING_CSV` to change the report path. While it runs, the terminal displays a live status line showing which server, web app, and pagination page is being processed. The report also includes Mailgun's `accepted_outgoing_count` for each missing domain from the start of the current month through the report run time, with the date range shown in UTC. This metric counts outgoing send requests accepted and queued by Mailgun; batch sends can add an extra accepted event. If the Metrics API is unavailable, the report marks the count as `UNAVAILABLE` and includes the error instead of silently treating it as zero.

For normalization, a leading `mg.` or `mgn.` is removed from Mailgun domain names (so `mg.stonedesign.be` is compared as `stonedesign.be` and `mgn.gunterbroodcoorens.com` as `gunterbroodcoorens.com`). Mailgun domains ending in `.conversalmail.be` or `.conversalhosting.be` use their first label as the customer/site name (so `floorsandmore.conversalmail.be` can match a RunCloud domain named `floorsandmore` or a full domain such as `floorsandmore.be`, `floorsandmore.com`, or another TLD). For these Conversal domains only, matching accepts a RunCloud domain that is exactly the customer/site name or starts with that name followed by a dot, regardless of the suffix. If exact label matching fails, it ignores dots and hyphens when comparing the customer label against the full RunCloud domain (so `mercomachines.conversalmail.be` can match `merco-machines.com`, and `asomartinus.conversalmail.be` can match `aso.martinusasse.be`). A leading `www.` is removed from both Mailgun and RunCloud domain names, so `www.solicom-verisafe.com` matches `solicom-verisafe.com`. For non-Conversal domains, a RunCloud subdomain ending in the normalized Mailgun domain also counts as a match (so `mg.allwaves.surf` can match `old.allwaves.surf`). Other domain names are compared as provided. The comparison is read-only.

**Security:** `apikey.txt`, `runcloud_apikey.txt`, and `cloudflare_apikey.txt` contain secrets. Keep them local, do not commit them, and restrict their filesystem permissions where supported (for example, `chmod 600 apikey.txt runcloud_apikey.txt cloudflare_apikey.txt` on macOS/Linux). The repository includes `.gitignore` rules for these filenames.

### Delete selected Mailgun domains (destructive)

**Use with care:** deleting a Mailgun domain can interrupt sending and remove domain configuration. This operation is separate from the audit and RunCloud comparison. It only targets exact domain names listed in the supplied text file and confirmed to exist in the current Mailgun domain list.

Create a text file such as `domains_to_delete.txt` with one domain per line. Blank lines and lines beginning with `#` are ignored:

```text
# Domains approved for removal
old-example.com
mg.unused-example.net
```

Run the deletion mode by itself:

```bash
python3 mailgun_domain_audit.py --delete-domains domains_to_delete.txt
```

The script displays the domains it found and asks you to type the exact confirmation phrase `DELETE N`, where `N` is the number of listed domains found in Mailgun. If confirmation does not match—or standard input is unavailable—it cancels without sending delete requests. Names from the file that are not present in Mailgun are reported as `NOT_FOUND` and are not deleted.

The result is written to `mailgun_domain_deletion_report.csv`. Override the path with `MAILGUN_DELETION_CSV`. The report records each domain's outcome and any HTTP status or error message. The script uses Mailgun's documented `DELETE /v3/domains/{name}` endpoint and does not automatically retry DELETE requests, because the result can be uncertain if a network connection drops after Mailgun processes the request.

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

- `mailgun_domain_audit.py` — audit and explicitly confirmed domain-deletion script.
- `apikey.txt` — local Mailgun secret; do not commit.
- `runcloud_apikey.txt` — optional local RunCloud API token; do not commit.
- `cloudflare_apikey.txt` — local Cloudflare API token for zone checks; do not commit.
- `README.md` — setup, usage, and limitations.
- `CHANGELOG.md` — notable changes by version.
- `VERSION` — current project version.

## Safety

This utility is read-only with respect to Mailgun configuration and DNS. Treat generated CSV files as operational data; review them before sharing.
