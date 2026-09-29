#!/usr/bin/env bash
# Discover DNS records for one or more domains.
# Usage: ./dns-discovery.sh domain1 domain2 domain3
# Output: <domain>-discovered.txt for each domain.
set -euo pipefail

if ! command -v dig >/dev/null 2>&1; then
  echo "Error: dig is required (install dnsutils/bind-utils)." >&2
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 DOMAIN [DOMAIN ...]" >&2
  exit 2
fi

# Explicitly query the important subdomains, including mg and mgn.
# DNS does not provide a standard way to enumerate every possible subdomain,
# so this is a targeted discovery pass. Add names to COMMON_NAMES as needed.
COMMON_NAMES=(
  ""
  "www"
  "mg"
  "mgn"
  "mail"
  "smtp"
  "imap"
  "pop"
  "autodiscover"
  "autoconfig"
  "ftp"
  "webmail"
  "cpanel"
  "calendar"
  "mta"
  "mx"
  "_dmarc"
  "_domainkey"
  "selector1._domainkey"
  "selector2._domainkey"
  "dkim"
)

TYPES=(A AAAA CNAME MX TXT CAA SRV NS)

for domain in "$@"; do
  domain="${domain%.}"
  outfile="${domain}-discovered.txt"

  {
    echo "; DNS discovery for ${domain}"
    echo "; Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "; Requires: dig"
    echo ";"
    echo "; This script explicitly queries mg and mgn for every supplied domain."
    echo "; Empty DNS answers are retained as headings so it is clear that the"
    echo "; name was checked. DNS cannot enumerate arbitrary subdomains by itself."
    echo

    for name in "${COMMON_NAMES[@]}"; do
      if [ -n "$name" ]; then
        fqdn="${name}.${domain}"
      else
        fqdn="$domain"
      fi

      echo "===== ${fqdn} ====="
      for type in "${TYPES[@]}"; do
        echo "### ${fqdn} ${type}"
        # Query the name directly. +noall +answer avoids misleading ANY output.
        dig +noall +answer "$fqdn" "$type" || true
        echo
      done
    done
  } > "$outfile"

  echo "Wrote $outfile"
done
