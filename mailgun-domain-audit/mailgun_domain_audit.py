#!/usr/bin/env python3
"""Read-only audit of Mailgun domain DNS authentication.

Requires:
    python -m pip install requests

Configuration:
    apikey.txt        Required by default; contains the Mailgun API key on one line.
    MAILGUN_API_KEY   Optional environment-variable override.
    MAILGUN_API_BASE  Optional API base URL. Defaults to the EU endpoint.

This script reports Mailgun DNS verification and DMARC API results separately.
API responses can vary by Mailgun account/features; UNKNOWN means the script
could not confidently classify a record and should not be treated as a failure.
"""

import csv
import os
import sys
import time
from urllib.parse import quote

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_FILE = os.path.join(SCRIPT_DIR, "apikey.txt")


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


API_KEY = load_api_key()
BASE_URL = os.environ.get(
    "MAILGUN_API_BASE",
    "https://api.eu.mailgun.net",
).rstrip("/")
OUTPUT_FILE = os.environ.get("MAILGUN_AUDIT_CSV", "mailgun_domain_audit.csv")

SESSION = requests.Session()
if API_KEY:
    SESSION.auth = ("api", API_KEY)
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


def record_status(record):
    """Classify a Mailgun DNS record from explicit verification fields."""
    if not isinstance(record, dict):
        return "UNKNOWN"

    for key in ("valid", "verified", "is_valid"):
        if isinstance(record.get(key), bool):
            return "PASS" if record[key] else "FAIL"

    for key in ("status", "state"):
        value = record.get(key)
        if isinstance(value, str):
            value = value.lower()
            if value in {"valid", "verified", "active", "pass", "ok"}:
                return "PASS"
            if value in {"invalid", "unverified", "fail", "failed", "error"}:
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


def main():
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
