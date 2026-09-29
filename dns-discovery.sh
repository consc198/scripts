#!/usr/bin/env bash
# Discover commonly used DNS records for one or more domains.
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

# Common hostnames and mail-authentication names. DNS cannot enumerate every
# possible subdomain, so this is a targeted discovery pass plus an apex ANY query.
COMMON_NAMES=(
  ""
  "www"
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
  "_dmarc"
  "_domainkey"
  "selector1._domainkey"
  "selector2._domainkey"
  "dkim"
  "mta"
  "mx"
)

TYPES=(A AAAA CNAME MX TXT CAA SRV NS)

for domain in "$@"; do
  # Strip a trailing dot so generated filenames remain sensible.
  domain="${domain%.}"
  outfile="${domain}-discovered.txt"

  {
    echo "; DNS discovery for ${domain}"
    echo "; Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "; Requires: dig"
    echo ";"
    echo "; NOTE: DNS has no general-purpose subdomain enumeration mechanism."
    echo "; This script queries the apex with ANY and a set of common website,"
    echo "; mail, and authentication names. Empty answers are omitted."
    echo

    echo "===== ${domain} ANY ====="
    dig +noall +answer "$domain" ANY || true
    echo

    for name in "${COMMON_NAMES[@]}"; do
      if [ -n "$name" ]; then
        fqdn="${name}.${domain}"
      else
        fqdn="$domain"
      fi

      for type in "${TYPES[@]}"; do
        echo "### ${fqdn} ${type}"
        dig +noall +answer "$fqdn" "$type" || true
        echo
      done
    done
  } > "$outfile"

  echo "Wrote $outfile"
done
