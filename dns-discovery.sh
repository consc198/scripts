#!/usr/bin/env bash
# Discover DNS records and write Cloudflare-compatible BIND zone files.
# Usage: ./dns-discovery.sh domain1 domain2 domain3
# Output: <domain>-cloudflare.txt for each domain.
set -euo pipefail

if ! command -v dig >/dev/null 2>&1; then
  echo "Error: dig is required (install dnsutils/bind-utils)." >&2
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 DOMAIN [DOMAIN ...]" >&2
  exit 2
fi

# Targeted names. DNS does not provide a standard way to enumerate arbitrary
# subdomains, so add known names here when migrating a zone.
COMMON_NAMES=(
  "" "www" "mg" "mgn" "mail" "smtp" "imap" "pop"
  "autodiscover" "autoconfig" "ftp" "webmail" "cpanel" "calendar"
  "mta" "mx" "_dmarc" "_domainkey" "selector1._domainkey"
  "selector2._domainkey" "dkim"
)

# Types that can be represented as ordinary Cloudflare DNS records.
TYPES=(A AAAA CNAME MX TXT CAA SRV NS)

# Query one record type and convert the dig answer into a zone-file line.
# The output format from dig is: name ttl class type data...
query_type() {
  local fqdn="$1"
  local type="$2"
  dig +noall +answer +multiline "$fqdn" "$type" 2>/dev/null || true
}

# Escape TXT data for a BIND zone file. dig +short is intentionally avoided
# because it loses TTL/type information and can make multi-string TXT records
# awkward to preserve.
for domain_arg in "$@"; do
  domain="${domain_arg%.}"
  outfile="${domain}-cloudflare.txt"

  {
    echo "; Cloudflare-compatible BIND zone import"
    echo "; Domain: ${domain}"
    echo "; Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo ";"
    echo "; Records are queried explicitly from DNS. DNSSEC DNSKEY/RRSIG/NSEC/NSEC3"
    echo "; records are intentionally excluded; Cloudflare manages DNSSEC separately."
    echo "; The SOA record is also excluded because Cloudflare manages the zone SOA."
    echo "; Nameserver records are excluded by default because Cloudflare assigns its"
    echo "; own authoritative nameservers when the zone is activated."
    echo ";"
    echo "; IMPORTANT: DNS cannot enumerate arbitrary subdomains. This file therefore"
    echo "; contains the apex and the targeted names in COMMON_NAMES above."
    echo
    echo '\$ORIGIN '"${domain}."
    echo '\$TTL 3600'
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

          # dig +multiline may indent continuation lines. Ignore non-record
          # continuation/diagnostic lines; ordinary answers begin with a name.
          case "$line" in
            \;*) continue ;;
          esac

          # Normalize whitespace while preserving quoted TXT contents.
          # Extract the fields with awk; TXT values are reconstructed from field 5+.
          name_out=$(awk '{print $1}' <<< "$line")
          ttl_out=$(awk '{print $2}' <<< "$line")
          class_out=$(awk '{print $3}' <<< "$line")
          type_out=$(awk '{print $4}' <<< "$line")
          [ "$type_out" = "$type" ] || continue

          case "$type_out" in
            A|AAAA)
              data=$(awk '{print $5}' <<< "$line")
              echo "${name_out} ${ttl_out} IN ${type_out} ${data}"
              ;;
            CNAME|NS|PTR)
              data=$(awk '{print $5}' <<< "$line")
              case "$data" in *. ) : ;; *) data="${data}." ;; esac
              echo "${name_out} ${ttl_out} IN ${type_out} ${data}"
              ;;
            MX)
              pref=$(awk '{print $5}' <<< "$line")
              target=$(awk '{print $6}' <<< "$line")
              case "$target" in *. ) : ;; *) target="${target}." ;; esac
              echo "${name_out} ${ttl_out} IN MX ${pref} ${target}"
              ;;
            SRV)
              priority=$(awk '{print $5}' <<< "$line")
              weight=$(awk '{print $6}' <<< "$line")
              port=$(awk '{print $7}' <<< "$line")
              target=$(awk '{print $8}' <<< "$line")
              case "$target" in *. ) : ;; *) target="${target}." ;; esac
              echo "${name_out} ${ttl_out} IN SRV ${priority} ${weight} ${port} ${target}"
              ;;
            CAA)
              flags=$(awk '{print $5}' <<< "$line")
              tag=$(awk '{print $6}' <<< "$line")
              value=$(awk '{print $7}' <<< "$line")
              echo "${name_out} ${ttl_out} IN CAA ${flags} ${tag} ${value}"
              ;;
            TXT)
              # dig +multiline can emit TXT as one or more quoted strings.
              txt=$(sed -E 's/^[^;]*IN TXT[[:space:]]+//' <<< "$line")
              echo "${name_out} ${ttl_out} IN TXT ${txt}"
              ;;
          esac
        done < <(query_type "$fqdn" "$type")
      done
    done

  } | awk 'NF || /^;/ || /^\\$/ ' | awk '!seen[$0]++' > "$outfile"

  echo "Wrote $outfile"
done
