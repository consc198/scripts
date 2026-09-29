#!/usr/bin/env bash
# Query selected DNS names and produce Cloudflare-importable BIND zone files.
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

COMMON_NAMES=(
  "" "www" "mg" "mgn" "mail" "smtp" "imap" "pop"
  "autodiscover" "autoconfig" "ftp" "webmail" "cpanel" "calendar"
  "mta" "mx" "_dmarc" "_domainkey" "selector1._domainkey"
  "selector2._domainkey" "dkim"
)
TYPES=(A AAAA CNAME MX TXT CAA SRV)

for domain_arg in "$@"; do
  domain="${domain_arg%.}"
  outfile="${domain}-cloudflare.txt"

  {
    echo "; Cloudflare BIND zone import for ${domain}"
    echo "; Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo ";"
    echo "; SOA, authoritative NS and DNSSEC records are omitted because Cloudflare"
    echo "; manages those when the zone is activated."
    echo "; This is a targeted discovery list; DNS cannot enumerate arbitrary names."
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
        # Ask the resolver for exactly this name/type. +short gives clean RDATA.
        # A separate +answer query supplies the TTL for each answer.
        while IFS= read -r line; do
          [ -z "$line" ] && continue
          ttl=$(awk '{print $2}' <<< "$line")
          rdata=$(cut -d' ' -f5- <<< "$line")
          case "$type" in
            A|AAAA)
              printf '%s %s IN %s %s\n' "$fqdn" "$ttl" "$type" "$rdata"
              ;;
            CNAME)
              target="$rdata"; [[ "$target" == *. ]] || target="${target}."
              printf '%s %s IN CNAME %s\n' "$fqdn" "$ttl" "$target"
              ;;
            MX)
              pref=$(awk '{print $1}' <<< "$rdata")
              target=$(awk '{print $2}' <<< "$rdata")
              [[ "$target" == *. ]] || target="${target}."
              printf '%s %s IN MX %s %s\n' "$fqdn" "$ttl" "$pref" "$target"
              ;;
            SRV)
              priority=$(awk '{print $1}' <<< "$rdata")
              weight=$(awk '{print $2}' <<< "$rdata")
              port=$(awk '{print $3}' <<< "$rdata")
              target=$(awk '{print $4}' <<< "$rdata")
              [[ "$target" == *. ]] || target="${target}."
              printf '%s %s IN SRV %s %s %s %s\n' "$fqdn" "$ttl" "$priority" "$weight" "$port" "$target"
              ;;
            TXT|CAA)
              # Preserve quoted TXT/CAA RDATA exactly as returned by dig.
              printf '%s %s IN %s %s\n' "$fqdn" "$ttl" "$type" "$rdata"
              ;;
          esac
        done < <(dig +noall +answer "$fqdn" "$type" 2>/dev/null)
      done
    done
  } | awk '!seen[$0]++' > "$outfile"

  echo "Wrote $outfile"
done
