#!/usr/bin/env python3
"""Read-only audit of Mailgun domain DNS authentication.

Requires:
    python -m pip install requests

Configuration:
    apikey.txt           Mailgun API key, unless MAILGUN_API_KEY is set.
    runcloud_apikey.txt  RunCloud API token for --runcloud-check.
    MAILGUN_API_BASE     Optional API base URL. Defaults to the EU endpoint.

This script reports Mailgun DNS verification and DMARC API results separately.
API responses can vary by Mailgun account/features; UNKNOWN means the script
could not confidently classify a record and should not be treated as a failure.
"""

import argparse
import csv
import json
import os
import sys
import time
import subprocess
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import quote

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_FILE = os.path.join(SCRIPT_DIR, "apikey.txt")
RUNCLOUD_API_KEY_FILE = os.path.join(SCRIPT_DIR, "runcloud_apikey.txt")
RUNCLOUD_BASE_URL = "https://manage.runcloud.io/api/v3"


def load_api_key():
    """Prefer MAILGUN_API_KEY when set; otherwise read apikey.txt beside this script."""
    env_key = os.environ.get("MAILGUN_API_KEY", "").strip()
    if env_key:
        return env_key

    try:
        with open(API_KEY_FILE, "r", encoding="utf-8") as handle:
            key = handle.read().strip()
    except FileNotFoundError:
        print(
            f"ERROR: API key not found. Create {API_KEY_FILE} with your Mailgun API key.",
            file=sys.stderr,
        )
        return None

    if not key:
        print(f"ERROR: {API_KEY_FILE} is empty.", file=sys.stderr)
        return None
    return key


API_KEY = None
BASE_URL = os.environ.get(
    "MAILGUN_API_BASE",
    "https://api.eu.mailgun.net",
).rstrip("/")
OUTPUT_FILE = os.environ.get("MAILGUN_AUDIT_CSV", "mailgun_domain_audit.csv")

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})


def api_get(path, params=None, retries=3):
    """GET a Mailgun endpoint, retrying rate limits and transient server errors."""
    url = f"{BASE_URL}{path}"
    last_error = None

    for attempt in range(retries):
        try:
            response = SESSION.get(url, params=params, timeout=30)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries - 1:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = max(1, int(retry_after)) if retry_after else 2 ** (attempt + 1)
                    except ValueError:
                        delay = 2 ** (attempt + 1)
                    print(
                        f"Temporary HTTP {response.status_code}; retrying in {delay}s...",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError(f"Request failed: {url}")


def api_post(path, json_body, retries=3):
    """POST to a Mailgun endpoint, retrying rate limits and transient server errors."""
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            response = SESSION.post(url, json=json_body, timeout=30)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries - 1:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = max(1, int(retry_after)) if retry_after else 2 ** (attempt + 1)
                    except ValueError:
                        delay = 2 ** (attempt + 1)
                    print(
                        f"Temporary HTTP {response.status_code}; retrying in {delay}s...",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"Request failed: {url}")


def current_month_utc_period():
    """Return the current month's start and current time in UTC."""
    end = datetime.now(timezone.utc)
    start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    label = (
        f"{start.strftime('%Y-%m-%d %H:%M:%S')} UTC to "
        f"{end.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    return start, end, label


def get_accepted_outgoing_by_domain():
    """Fetch accepted outgoing message counts by Mailgun domain for this month."""
    start, end, period_label = current_month_utc_period()
    counts = {}
    skip = 0
    limit = 1000

    while True:
        payload = {
            "start": format_datetime(start),
            "end": format_datetime(end),
            "resolution": "day",
            "dimensions": ["domain"],
            "metrics": ["accepted_outgoing_count"],
            "pagination": {"skip": skip, "limit": limit},
        }
        response = api_post("/v1/analytics/metrics", payload)
        items = response.get("items", [])
        if not isinstance(items, list):
            raise ValueError("Unexpected Mailgun metrics response: 'items' is not a list")

        for item in items:
            dimensions = item.get("dimensions", [])
            domain = None
            if isinstance(dimensions, dict):
                domain = dimensions.get("domain")
            elif isinstance(dimensions, list):
                for dimension in dimensions:
                    if not isinstance(dimension, dict):
                        continue
                    if dimension.get("dimension") == "domain" or dimension.get("name") == "domain":
                        domain = dimension.get("value", dimension.get("label"))
                        break
            metrics = item.get("metrics", {})
            if domain and isinstance(metrics, dict):
                value = metrics.get("accepted_outgoing_count")
                if value is not None:
                    counts[str(domain).strip().lower().rstrip(".")] = value

        pagination = response.get("pagination", {})
        total = pagination.get("total")
        if total is not None:
            skip += len(items)
            if skip >= int(total):
                break
        elif len(items) < limit:
            break
        else:
            skip += len(items)

    return counts, period_label


def get_all_domains():
    """Retrieve domains using Mailgun's skip/limit pagination."""
    domains = []
    skip = 0
    limit = 1000

    while True:
        data = api_get("/v4/domains", params={"limit": limit, "skip": skip})
        items = data.get("items", [])
        domains.extend(items)
        print(f"Retrieved {len(domains)} domain(s)...", file=sys.stderr)
        if len(items) < limit:
            break
        skip += len(items)

    return domains


def get_domain_details(domain):
    # Explicitly request DNS records; some responses omit them unless h:with_dns is set.
    data = api_get(
        f"/v4/domains/{quote(domain, safe='')}",
        params={"h:with_dns": "true"},
    )
    # Mailgun returns DNS records at the top level, alongside the nested domain object.
    details = data.get("domain", data)
    if isinstance(details, dict):
        for key in ("sending_dns_records", "receiving_dns_records"):
            if key not in details and key in data:
                details[key] = data[key]
    return details


def get_dmarc(domain):
    """Query the DMARC endpoint; report unavailable separately from missing."""
    try:
        return api_get(f"/v1/dmarc/records/{quote(domain, safe='')}")
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        return {"configured": None, "error": f"HTTP {status}"}
    except (requests.RequestException, ValueError) as exc:
        return {"configured": None, "error": str(exc)}




def load_runcloud_api_key():
    """Always read the RunCloud API token from runcloud_apikey.txt beside this script."""
    try:
        with open(RUNCLOUD_API_KEY_FILE, "r", encoding="utf-8") as handle:
            key = handle.read().strip()
    except FileNotFoundError:
        print(
            f"ERROR: RunCloud API token not found. Create {RUNCLOUD_API_KEY_FILE}.",
            file=sys.stderr,
        )
        return None
    if not key:
        print(f"ERROR: {RUNCLOUD_API_KEY_FILE} is empty.", file=sys.stderr)
        return None
    return key


def normalize_mailgun_domain(domain):
    """Map Mailgun sending domains to the corresponding RunCloud lookup name."""
    domain = str(domain).strip().lower().rstrip(".")
    # Dedicated customer subdomains use the first label as the hosted-site name.
    for suffix in (".conversalmail.be", ".conversalhosting.be"):
        if domain.endswith(suffix):
            return domain[:-len(suffix)].split(".", 1)[0]
    # Standard Mailgun sending prefixes map to their root domain.
    for prefix in ("mgn.", "mg."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
            break
    # Treat www.example.com and example.com as the same site on either side.
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def normalize_runcloud_domain(domain):
    """Normalize common host prefixes so www.example.com matches example.com."""
    domain = str(domain).strip().lower().rstrip(".")
    if domain.startswith("www."):
        return domain[4:]
    return domain


def runcloud_get(path, token, params=None, retries=3):
    """GET RunCloud through curl to match the working CLI request path.

    The server's Cloudflare layer was challenging Python requests while allowing
    curl. The token is passed through curl's stdin config, not its command line.
    """
    url = f"{RUNCLOUD_BASE_URL}{path}"
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"

    def curl_quote(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "") + '"'

    config = "\n".join([
        "silent",
        "show-error",
        f"url = {curl_quote(url)}",
        f"header = {curl_quote('Accept: application/json')}",
        f"header = {curl_quote('Content-Type: application/json')}",
        f"header = {curl_quote(f'Authorization: Bearer {token}')}",
        'write-out = "HTTPSTATUS:%{http_code}"',
        "",
    ])

    for attempt in range(retries):
        try:
            response = subprocess.run(
                ["curl", "--config", "-"],
                input=config,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Unable to run curl for RunCloud request: {exc}") from exc

        if response.returncode != 0:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            detail = response.stderr.strip() or f"curl exit code {response.returncode}"
            raise RuntimeError(f"RunCloud curl request failed: {detail}")

        body, marker, status_text = response.stdout.rpartition("HTTPSTATUS:")
        if not marker or not status_text.strip().isdigit():
            raise RuntimeError("Could not read HTTP status from RunCloud curl response.")
        status_code = int(status_text.strip())

        if status_code == 429 or status_code >= 500:
            if attempt < retries - 1:
                delay = 2 ** (attempt + 1)
                print(
                    f"RunCloud temporary HTTP {status_code}; retrying in {delay}s...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue

        if status_code < 200 or status_code >= 300:
            detail = body.strip()[:1000]
            suffix = f"; response body: {detail}" if detail else ""
            raise RuntimeError(f"RunCloud HTTP {status_code} for {url}{suffix}")

        try:
            return json.loads(body)
        except ValueError as exc:
            raise RuntimeError(f"RunCloud returned invalid JSON for {url}: {exc}") from exc

    raise RuntimeError(f"RunCloud request failed: {url}")


def progress_status(message):
    """Update one terminal status line while RunCloud data is being collected."""
    print(f"RunCloud check: {message}", end="\r", file=sys.stderr, flush=True)


def runcloud_list_all(path, token, progress_label=None):
    """Read all pages from a RunCloud list endpoint, reporting pagination progress."""
    items = []
    page = 1
    while True:
        if progress_label:
            progress_status(f"{progress_label} (page {page})")
        payload = runcloud_get(path, token, params={"page": page})
        page_items = payload.get("data", [])
        if not isinstance(page_items, list):
            raise ValueError(f"Unexpected RunCloud response for {path}: 'data' is not a list")
        items.extend(page_items)
        pagination = payload.get("meta", {}).get("pagination", {})
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            if page >= int(total_pages):
                break
        elif not page_items:
            break
        elif len(page_items) < int(pagination.get("per_page", len(page_items) or 1)):
            break
        page += 1
    return items


def get_runcloud_domains(token):
    """Collect configured domain names from every RunCloud server and web application."""
    found = set()
    progress_status("fetching server list...")
    servers = runcloud_list_all("/servers", token, "fetching server list")
    print(f"Retrieved {len(servers)} RunCloud server(s).", file=sys.stderr)

    processed_apps = 0
    for server_index, server in enumerate(servers, start=1):
        server_id = server.get("id")
        if server_id is None:
            continue
        progress_status(f"server {server_index}/{len(servers)}: fetching web apps...")
        apps = runcloud_list_all(
            f"/servers/{server_id}/webapps",
            token,
            f"server {server_index}/{len(servers)} web apps",
        )
        # App counts are discovered per server, so show the current server's count
        # while keeping the user informed about the phase and current work.
        for app_index, app in enumerate(apps, start=1):
            app_id = app.get("id")
            if app_id is None:
                continue
            processed_apps += 1
            path = f"/servers/{server_id}/webapps/{app_id}/domains"
            label = (
                f"server {server_index}/{len(servers)}, app {app_index}/{len(apps)} "
                f"(processed {processed_apps} apps): fetching domains"
            )
            for item in runcloud_list_all(path, token, label):
                name = item.get("name")
                if name:
                    found.add(normalize_runcloud_domain(name))
    print(" " * 120, end="\r", file=sys.stderr, flush=True)
    print(f"RunCloud check: collected {len(found)} unique domain(s).", file=sys.stderr)
    return found


def report_mailgun_domains_missing_from_runcloud(mailgun_domains, runcloud_domains):
    """Return Mailgun domains that have no matching normalized RunCloud domain."""
    missing = []
    conversal_suffixes = (".conversalmail.be", ".conversalhosting.be")
    for item in mailgun_domains:
        mailgun_domain = item.get("name", "")
        root_domain = normalize_mailgun_domain(mailgun_domain)

        # Dedicated Conversal Mailgun domains identify a customer by their first
        # label; RunCloud may store that site's full domain with any TLD.
        normalized_mailgun = str(mailgun_domain).strip().lower().rstrip(".")
        is_conversal_domain = any(normalized_mailgun.endswith(suffix) for suffix in conversal_suffixes)
        matched = bool(root_domain and root_domain in runcloud_domains)

        # Some Mailgun domains represent a root site while RunCloud stores a
        # subdomain, e.g. mg.allwaves.surf -> old.allwaves.surf. Keep this
        # suffix match separate from the special Conversal customer-name logic.
        if root_domain and not matched and not is_conversal_domain:
            matched = any(
                runcloud_domain.endswith("." + root_domain)
                for runcloud_domain in runcloud_domains
            )

        if root_domain and not matched and is_conversal_domain:
            # Ignore dots and hyphens in the full RunCloud domain when
            # comparing the customer label, so asomartinus can match
            # aso.martinusasse.be and mercomachines can match merco-machines.com.
            # This fallback is restricted to dedicated Conversal Mailgun domains.
            normalized_root = root_domain.replace("-", "").replace(".", "")
            matched = any(
                runcloud_domain.replace("-", "").replace(".", "").startswith(normalized_root)
                for runcloud_domain in runcloud_domains
            )

        if root_domain and not matched:
            missing.append({
                "mailgun_domain": mailgun_domain,
                "normalized_domain": root_domain,
                "mailgun_state": item.get("state", "UNKNOWN"),
            })
    return missing


def write_runcloud_report(missing, output_path="mailgun_domains_missing_in_runcloud.csv"):
    fields = [
        "mailgun_domain",
        "normalized_domain",
        "mailgun_state",
        "accepted_outgoing_count",
        "accepted_period_utc",
        "accepted_metrics_error",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(missing)
    print(f"RunCloud comparison CSV written to: {output_path}")
    if missing:
        print("\nMAILGUN DOMAINS NOT FOUND IN RUNCLOUD")
        for row in missing:
            print(f"{row['mailgun_domain']}\t=>\t{row['normalized_domain']}")
    else:
        print("All normalized Mailgun domains were found in RunCloud.")


def record_status(record):
    """Classify a Mailgun DNS record from explicit verification fields."""
    if not isinstance(record, dict):
        return "UNKNOWN"

    for key in ("valid", "verified", "is_valid"):
        if isinstance(record.get(key), bool):
            return "PASS" if record[key] else "FAIL"

    # Mailgun's sending_dns_records commonly uses valid="valid" or
    # valid="invalid" (strings, not booleans), so interpret those explicitly.
    for key in ("valid", "verified", "status", "state"):
        value = record.get(key)
        if isinstance(value, str):
            value = value.strip().lower()
            if value in {"valid", "verified", "active", "pass", "passed", "ok", "true"}:
                return "PASS"
            if value in {"invalid", "unverified", "fail", "failed", "error", "false"}:
                return "FAIL"

    return "UNKNOWN"


def classify_sending_dns(details):
    """Classify SPF/DKIM from Mailgun sending_dns_records without guessing."""
    result = {"spf": "UNKNOWN", "dkim": "UNKNOWN", "tracking": "UNKNOWN"}
    records = details.get("sending_dns_records", [])
    if not isinstance(records, list):
        return result

    for record in records:
        if not isinstance(record, dict):
            continue
        text = " ".join(str(v) for v in record.values()).lower()
        status = record_status(record)

        if "spf" in text or "v=spf1" in text:
            result["spf"] = merge_status(result["spf"], status)
        if "dkim" in text or "domainkey" in text:
            result["dkim"] = merge_status(result["dkim"], status)
        if "cname" in str(record.get("record_type", record.get("type", ""))).lower():
            if "track" in text or "mailgun" in text:
                result["tracking"] = merge_status(result["tracking"], status)

    return result


def merge_status(existing, new):
    """FAIL wins, then PASS; UNKNOWN is used only when no known result exists."""
    if existing == "FAIL" or new == "FAIL":
        return "FAIL"
    if existing == "PASS" or new == "PASS":
        return "PASS"
    return "UNKNOWN"


def overall_status(state, dns, dmarc):
    if str(state).lower() != "active":
        return "ACTION_REQUIRED"
    checks = [dns["spf"], dns["dkim"], dmarc]
    if "FAIL" in checks:
        return "ACTION_REQUIRED"
    if "UNKNOWN" in checks:
        return "REVIEW"
    return "OK"


def audit_domain(domain_obj):
    domain = domain_obj["name"]
    print(f"Checking {domain}...", file=sys.stderr)

    details = get_domain_details(domain)
    dns = classify_sending_dns(details)
    dmarc_response = get_dmarc(domain)

    configured = dmarc_response.get("configured")
    if configured is True:
        dmarc_status = "PASS"
    elif configured is False:
        dmarc_status = "FAIL"
    else:
        dmarc_status = "UNKNOWN"

    state = details.get("state", domain_obj.get("state", "UNKNOWN"))
    return {
        "domain": domain,
        "mailgun_state": state,
        "spf": dns["spf"],
        "dkim": dns["dkim"],
        "tracking": dns["tracking"],
        "dmarc": dmarc_status,
        "status": overall_status(state, dns, dmarc_status),
        "dmarc_current": dmarc_response.get("current", ""),
        "dmarc_expected": dmarc_response.get("entry", ""),
        "dmarc_error": dmarc_response.get("error", ""),
    }


def load_domains_to_delete(path):
    """Read a domain deletion list; ignore blank lines and comments."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            entries = [
                line.strip().lower().rstrip(".")
                for line in handle
                if line.strip() and not line.lstrip().startswith("#")
            ]
    except OSError as exc:
        raise RuntimeError(f"Unable to read domain list {path}: {exc}") from exc

    # Deduplicate while preserving the order in the text file.
    unique = list(dict.fromkeys(entries))
    if not unique:
        raise RuntimeError(f"No domains found in deletion list {path}.")
    return unique


def delete_mailgun_domains(domains_to_delete, mailgun_domains):
    """Preview and explicitly confirm deletion of listed domains that exist in Mailgun."""
    available = {
        str(item.get("name", "")).strip().lower().rstrip("."): item.get("name", "")
        for item in mailgun_domains
        if item.get("name")
    }
    targets = []
    results = []

    for requested in domains_to_delete:
        actual_name = available.get(requested)
        if actual_name:
            targets.append(actual_name)
        else:
            results.append({
                "domain": requested,
                "status": "NOT_FOUND",
                "http_status": "",
                "message": "Domain was not found in the current Mailgun domain list; no delete request sent.",
            })

    print("\nMAILGUN DOMAIN DELETION PREVIEW")
    for domain in targets:
        print(f"  {domain}")
    print(f"Listed: {len(domains_to_delete)} | Found in Mailgun: {len(targets)} | Not found: {len(domains_to_delete) - len(targets)}")

    if not targets:
        write_deletion_report(results)
        return 0

    expected = f"DELETE {len(targets)}"
    print(f"\nThis permanently requests deletion of {len(targets)} Mailgun domain(s).")
    print(f"To confirm, type exactly: {expected}")
    confirmation = input("> ").strip()
    if confirmation != expected:
        print("Confirmation did not match; no domains were deleted.")
        for domain in targets:
            results.append({
                "domain": domain,
                "status": "CANCELLED",
                "http_status": "",
                "message": "User did not provide the required confirmation phrase.",
            })
        write_deletion_report(results)
        return 1

    for domain in targets:
        # Do not automatically retry DELETE requests: if a connection drops after
        # Mailgun processes the request, retrying could obscure the actual outcome.
        url = f"{BASE_URL}/v4/domains/{quote(domain, safe='')}"
        try:
            response = SESSION.delete(url, timeout=30)
            if 200 <= response.status_code < 300:
                status = "DELETED"
                message = "Mailgun accepted the deletion request."
            else:
                status = "FAILED"
                message = response.text.strip()[:1000] or response.reason
            results.append({
                "domain": domain,
                "status": status,
                "http_status": response.status_code,
                "message": message,
            })
            print(f"{domain}: {status} (HTTP {response.status_code})")
        except requests.RequestException as exc:
            results.append({
                "domain": domain,
                "status": "ERROR",
                "http_status": "",
                "message": str(exc),
            })
            print(f"{domain}: ERROR ({exc})", file=sys.stderr)

    write_deletion_report(results)
    return 0 if all(row["status"] in {"DELETED", "NOT_FOUND"} for row in results) else 1


def write_deletion_report(results):
    """Write the outcome of a domain deletion run to CSV."""
    output_path = os.environ.get(
        "MAILGUN_DELETION_CSV", "mailgun_domain_deletion_report.csv"
    )
    fields = ["domain", "status", "http_status", "message"]
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    print(f"Deletion report written to: {output_path}")


def read_version():
    """Read the project version from the VERSION file beside this script."""
    version_file = os.path.join(SCRIPT_DIR, "VERSION")
    try:
        with open(version_file, "r", encoding="utf-8") as handle:
            version = handle.read().strip()
    except OSError as exc:
        raise RuntimeError(f"Unable to read version file {version_file}: {exc}") from exc
    if not version:
        raise RuntimeError(f"Version file {version_file} is empty.")
    return version


def main():
    parser = argparse.ArgumentParser(description="Read-only audit of Mailgun domain DNS authentication.")
    try:
        version = read_version()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
        help="show the script version and exit",
    )
    parser.add_argument(
        "--dns-check",
        action="store_true",
        help="run the Mailgun SPF, DKIM, and DMARC audit",
    )
    parser.add_argument(
        "--runcloud-check",
        action="store_true",
        help="compare Mailgun domains with domains configured in RunCloud (without DNS audit unless --dns-check is also supplied)",
    )
    parser.add_argument(
        "--delete-domains",
        metavar="FILE",
        help="delete only the Mailgun domains listed in FILE, after an explicit confirmation",
    )
    args = parser.parse_args()
    # Preserve the historical default: with no check flags, run the DNS audit.
    # When --runcloud-check is used alone, skip per-domain DNS/DMARC requests.
    run_dns_check = args.dns_check or not args.runcloud_check

    global API_KEY
    API_KEY = load_api_key()
    if API_KEY:
        SESSION.auth = ("api", API_KEY)

    if not API_KEY:
        print(
            "ERROR: add your Mailgun API key to apikey.txt or set MAILGUN_API_KEY.",
            file=sys.stderr,
        )
        return 1

    print(f"Mailgun API base: {BASE_URL}", file=sys.stderr)
    if args.delete_domains:
        if args.dns_check or args.runcloud_check:
            print("ERROR: --delete-domains must be used by itself, not with --dns-check or --runcloud-check.", file=sys.stderr)
            return 2
        try:
            domains_to_delete = load_domains_to_delete(args.delete_domains)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        try:
            domains = get_all_domains()
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            print(f"ERROR retrieving domains: {exc}", file=sys.stderr)
            return 1
        return delete_mailgun_domains(domains_to_delete, domains)

    try:
        domains = get_all_domains()
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"ERROR retrieving domains: {exc}", file=sys.stderr)
        return 1

    results = []
    if run_dns_check:
        for item in domains:
            try:
                results.append(audit_domain(item))
            except Exception as exc:
                name = item.get("name", "UNKNOWN")
                print(f"ERROR checking {name}: {exc}", file=sys.stderr)
                results.append({
                    "domain": name,
                    "mailgun_state": item.get("state", "UNKNOWN"),
                    "spf": "ERROR",
                    "dkim": "ERROR",
                    "tracking": "ERROR",
                    "dmarc": "ERROR",
                    "status": "ERROR",
                    "dmarc_current": "",
                    "dmarc_expected": "",
                    "dmarc_error": str(exc),
                })

    if args.runcloud_check:
        runcloud_token = load_runcloud_api_key()
        if not runcloud_token:
            return 1
        try:
            runcloud_domains = get_runcloud_domains(runcloud_token)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            print(f"ERROR retrieving RunCloud domains: {exc}", file=sys.stderr)
            return 1
        missing = report_mailgun_domains_missing_from_runcloud(domains, runcloud_domains)
        if missing:
            _, _, period_label = current_month_utc_period()
            try:
                accepted_counts, period_label = get_accepted_outgoing_by_domain()
                for row in missing:
                    key = str(row["mailgun_domain"]).strip().lower().rstrip(".")
                    row["accepted_outgoing_count"] = accepted_counts.get(key, 0)
                    row["accepted_metrics_error"] = ""
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                print(
                    f"WARNING: could not retrieve Mailgun accepted outgoing metrics: {exc}",
                    file=sys.stderr,
                )
                for row in missing:
                    row["accepted_outgoing_count"] = "UNAVAILABLE"
                    row["accepted_metrics_error"] = str(exc)
            for row in missing:
                row["accepted_period_utc"] = period_label
        report_path = os.environ.get(
            "RUNCLOUD_MISSING_CSV", "mailgun_domains_missing_in_runcloud.csv"
        )
        write_runcloud_report(missing, report_path)

    if run_dns_check:
        fields = [
            "domain", "mailgun_state", "spf", "dkim", "tracking", "dmarc",
            "status", "dmarc_current", "dmarc_expected", "dmarc_error",
        ]
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)

        print("\nDOMAIN\tSPF\tDKIM\tDMARC\tSTATUS")
        for row in results:
            print(
                f"{row['domain']}\t{row['spf']}\t{row['dkim']}\t"
                f"{row['dmarc']}\t{row['status']}"
            )
        print(f"\nCSV written to: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
