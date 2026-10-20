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
import os
import sys
import time
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
    data = api_get(f"/v4/domains/{quote(domain, safe='')}")
    return data.get("domain", data)


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
    # Standard Mailgun sending subdomains map to their root domain.
    if domain.startswith("mg."):
        return domain[3:]
    return domain


def normalize_runcloud_domain(domain):
    """Normalize common host prefixes so www.example.com matches example.com."""
    domain = str(domain).strip().lower().rstrip(".")
    if domain.startswith("www."):
        return domain[4:]
    return domain


def runcloud_get(path, token, params=None, retries=3):
    """GET a RunCloud API endpoint with retry handling for transient errors."""
    url = f"{RUNCLOUD_BASE_URL}{path}"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries - 1:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = max(1, int(retry_after)) if retry_after else 2 ** (attempt + 1)
                    except ValueError:
                        delay = 2 ** (attempt + 1)
                    print(
                        f"RunCloud temporary HTTP {response.status_code}; retrying in {delay}s...",
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
    raise RuntimeError(f"RunCloud request failed: {url}")


def runcloud_list_all(path, token):
    """Read all pages from a RunCloud list endpoint."""
    items = []
    page = 1
    while True:
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
    servers = runcloud_list_all("/servers", token)
    print(f"Retrieved {len(servers)} RunCloud server(s).", file=sys.stderr)
    for server in servers:
        server_id = server.get("id")
        if server_id is None:
            continue
        apps = runcloud_list_all(f"/servers/{server_id}/webapps", token)
        for app in apps:
            app_id = app.get("id")
            if app_id is None:
                continue
            path = f"/servers/{server_id}/webapps/{app_id}/domains"
            for item in runcloud_list_all(path, token):
                name = item.get("name")
                if name:
                    found.add(normalize_runcloud_domain(name))
    return found


def report_mailgun_domains_missing_from_runcloud(mailgun_domains, runcloud_domains):
    """Return Mailgun domains whose normalized root domain is absent from RunCloud."""
    missing = []
    for item in mailgun_domains:
        mailgun_domain = item.get("name", "")
        root_domain = normalize_mailgun_domain(mailgun_domain)
        if root_domain and root_domain not in runcloud_domains:
            missing.append({
                "mailgun_domain": mailgun_domain,
                "normalized_domain": root_domain,
                "mailgun_state": item.get("state", "UNKNOWN"),
            })
    return missing


def write_runcloud_report(missing, output_path="mailgun_domains_missing_in_runcloud.csv"):
    fields = ["mailgun_domain", "normalized_domain", "mailgun_state"]
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
        "--runcloud-check",
        action="store_true",
        help="compare Mailgun domains with domains configured in RunCloud",
    )
    args = parser.parse_args()

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
    try:
        domains = get_all_domains()
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"ERROR retrieving domains: {exc}", file=sys.stderr)
        return 1

    results = []
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
        report_path = os.environ.get(
            "RUNCLOUD_MISSING_CSV", "mailgun_domains_missing_in_runcloud.csv"
        )
        write_runcloud_report(missing, report_path)

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
