#!/usr/bin/env bash
# ==============================================================================
# DNS Discovery -> Cloudflare BIND Zone Import
# ==============================================================================
#
# PURPOSE
# -------
# Query selected DNS names and produce BIND-format zone files suitable for
# Cloudflare's DNS Import feature.
#
# REQUIREMENTS
# ------------
# - Linux/macOS/WSL or another POSIX shell environment
# - The `dig` command
#
# Ubuntu/Debian:
#   sudo apt update && sudo apt install -y dnsutils
#
# RHEL/CentOS/Fedora:
#   sudo dnf install -y bind-utils
#
# INSTALL / DOWNLOAD
# ------------------
#   curl -fsSL https://raw.githubusercontent.com/consc198/scripts/main/dns-discovery.sh -o dns-discovery.sh
#   chmod +x dns-discovery.sh
#
# RUN
# ---
#   ./dns-discovery.sh gunterbroodcoorens.com studio4.be ondernemersvlaanderen.be
#
# Output:
#   <domain>-cloudflare.txt
#
# IMPORTANT
# ---------
# DNS cannot reliably enumerate every possible subdomain. This script uses a
# targeted list of common names. For DKIM/DMARC below mg/mgn, the exact names
# are queried directly from authoritative DNS servers as an extra verification
# step. This avoids missing records because of a local/caching resolver.
#
# ============================================================================

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
  "mta" "mx" "dkim" "_domainkey"
  "s1._domainkey" "s2._domainkey" "selector1._domainkey" "selector2._domainkey"
  "_dmarc"
)

# These are the exact nested names that must be checked. They are deliberately
# separate from COMMON_NAMES so there is no ambiguity about how the labels are
# assembled.
NESTED_AUTH_NAMES=(
  "s1._domainkey.mg"
  "s1._domainkey.mgn"
  "s2._domainkey.mg"
  "s2._domainkey.mgn"
  "selector1._domainkey.mg"
  "selector1._domainkey.mgn"
  "selector2._domainkey.mg"
  "selector2._domainkey.mgn"
  "_dmarc.mg"
  "_dmarc.mgn"
)

SRV_NAMES=(
  "_imaps._tcp"
  "_pop3s._tcp"
  "_submission._tcp"
  "_autodiscover._tcp"
  "_imap._tcp"
  "_pop3._tcp"
  "_smtps._tcp"
  "_smtp._tcp"
  "_submission._tcp.mg"
  "_autodiscover._tcp.mg"
  "_imaps._tcp.mg"
  "_pop3s._tcp.mg"
  "_submission._tcp.mgn"
  "_autodiscover._tcp.mgn"
  "_imaps._tcp.mgn"
  "_pop3s._tcp.mgn"
)

TYPES=(A AAAA CNAME MX TXT CAA SRV NS)

# Query a name using the system resolver.
query_normal() {
  local fqdn="$1" type="$2"
  dig +noall +answer "$fqdn" "$type" 2>/dev/null || true
}

# Query an exact name against the authoritative nameservers for its closest
# available zone. This is particularly important for delegated mg/mgn zones.
query_authoritative() {
  local fqdn="$1" type="$2" zone="$3"
  local ns

  # First try nameservers for the possible delegated zone itself.
  for ns in $(dig +short NS "$zone" 2>/dev/null | sed 's/[[:space:]]//g'); do
    [ -z "$ns" ] && continue
    dig +noall +answer +time=3 +tries=1 "@$ns" "$fqdn" "$type" 2>/dev/null || true
  done

  # Also query the parent domain's authoritative nameservers.
  for ns in $(dig +short NS "$DOMAIN_ROOT" 2>/dev/null | sed 's/[[:space:]]//g'); do
    [ -z "$ns" ] && continue
    dig +noall +answer +time=3 +tries=1 "@$ns" "$fqdn" "$type" 2>/dev/null || true
  done
}

for domain_arg in "$@"; do
  domain="${domain_arg%.}"
  DOMAIN_ROOT="$domain."
  outfile="${domain}-cloudflare.txt"
  tmp="${outfile}.tmp"

  {
    echo "; Cloudflare DNS Import / BIND zone file"
    echo "; Domain: ${domain}"
    echo "; Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo ";"
    echo "; Records are copied directly from dig output."
    echo "; Nested DKIM/DMARC names under mg/mgn are also queried directly against"
    echo "; authoritative DNS servers."
    echo "; DNSSEC records are not queried. Apex NS is omitted."
    echo
    printf '%s\n' '$ORIGIN '"${domain}."
    printf '%s\n' '$TTL 3600'
    echo

    # Standard/common records.
    for name in "${COMMON_NAMES[@]}"; do
      if [ -n "$name" ]; then fqdn="${name}.${domain}."; else fqdn="${domain}."; fi
      for type in "${TYPES[@]}"; do
        while IFS= read -r line; do
          [ -z "$line" ] && continue
          if [ "$fqdn" = "${domain}." ] && [ "$type" = "NS" ]; then continue; fi
          printf '%s\n' "$line"
        done < <(query_normal "$fqdn" "$type")
      done
    done

    # Explicit nested DKIM/DMARC verification. Query TXT first (the expected
    # record type), then CNAME/A/AAAA in case the provider uses indirection.
    for name in "${NESTED_AUTH_NAMES[@]}"; do
      fqdn="${name}.${domain}."
      echo "; Explicit authentication check: ${fqdn}"

      # Normal resolver first.
      for type in TXT CNAME A AAAA; do
        while IFS= read -r line; do
          [ -z "$line" ] && continue
          printf '%s\n' "$line"
        done < <(query_normal "$fqdn" "$type")
      done

      # Then authoritative servers for the delegated mg/mgn zone and root.
      case "$name" in
        *.mg) zone="mg.${domain}." ;;
        *.mgn) zone="mgn.${domain}." ;;
        *) zone="${domain}." ;;
      esac
      for type in TXT CNAME A AAAA; do
        while IFS= read -r line; do
          [ -z "$line" ] && continue
          printf '%s\n' "$line"
        done < <(query_authoritative "$fqdn" "$type" "$zone")
      done
    done

    # Explicit SRV service names.
    for name in "${SRV_NAMES[@]}"; do
      fqdn="${name}.${domain}."
      while IFS= read -r line; do
        [ -z "$line" ] && continue
        printf '%s\n' "$line"
      done < <(query_normal "$fqdn" SRV)
    done
  } > "$tmp"

  awk '/^;/ || /^\$ORIGIN/ || /^\$TTL/ { print; next } !seen[$0]++ { print }' "$tmp" > "$outfile"
  rm -f "$tmp"
  echo "Wrote $outfile"
done
