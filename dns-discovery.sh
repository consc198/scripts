#!/usr/bin/env bash
# Query selected DNS names and produce BIND zone files suitable for
# Cloudflare's DNS Import feature.
# Usage: ./dns-discovery.sh domain1 domain2 domain3
# Output: <domain>-cloudflare.txt
set -euo pipefail

if ! command -v dig >/dev/null 2>&1; then
  echo "Error: dig is required (install dnsutils/bind-utils)." >&2
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 DOMAIN [DOMAIN ...]" >&2
  exit 2
fi

# Query exact/common names plus the authentication names below mg/mgn.
COMMON_NAMES=(
  "" "www" "mg" "mgn" "mail" "smtp" "imap" "pop"
  "autodiscover" "autoconfig" "ftp" "webmail" "cpanel" "calendar"
  "mta" "mx" "dkim" "_domainkey"
  "s1._domainkey" "s2._domainkey" "selector1._domainkey" "selector2._domainkey"
  "_dmarc"
  "s1._domainkey.mg" "s2._domainkey.mg" "selector1._domainkey.mg" "selector2._domainkey.mg" "_dmarc.mg"
  "s1._domainkey.mgn" "s2._domainkey.mgn" "selector1._domainkey.mgn" "selector2._domainkey.mgn" "_dmarc.mgn"
)

TYPES=(A AAAA CNAME MX TXT CAA SRV NS)

for domain_arg in "$@"; do
  domain="${domain_arg%.}"
  outfile="${domain}-cloudflare.txt"
  tmp="${outfile}.tmp"

  {
    echo "; Cloudflare DNS Import / BIND zone file"
    echo "; Domain: ${domain}"
    echo "; Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo ";"
    echo "; Records are copied directly from dig output."
    echo "; Explicitly checks s1._domainkey and _dmarc at the apex, plus variants"
    echo "; below mg and mgn."
    echo "; DNSSEC records are not queried. Apex NS is omitted for normal Cloudflare"
    echo "; full-zone setup because Cloudflare supplies authoritative nameservers."
    echo
    printf '%s\n' '$ORIGIN '"${domain}."
    printf '%s\n' '$TTL 3600'
    echo

    for name in "${COMMON_NAMES[@]}"; do
      if [ -n "$name" ]; then
        fqdn="${name}.${domain}."
      else
        fqdn="${domain}."
      fi

      for type in "${TYPES[@]}"; do
        while IFS= read -r line; do
          [ -z "$line" ] && continue
          if [ "$fqdn" = "${domain}." ] && [ "$type" = "NS" ]; then
            continue
          fi
          printf '%s\n' "$line"
        done < <(dig +noall +answer "$fqdn" "$type" 2>/dev/null)
      done
    done
  } > "$tmp"

  awk '
    /^;/ || /^\$ORIGIN/ || /^\$TTL/ { print; next }
    !seen[$0]++ { print }
  ' "$tmp" > "$outfile"
  rm -f "$tmp"

  echo "Wrote $outfile"
done
