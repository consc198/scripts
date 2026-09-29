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
# Pass one or more domains as arguments:
#
#   ./dns-discovery.sh example.com example.org
#
# Output:
#   <domain>-cloudflare.txt
#
# WHAT IS QUERIED
# ---------------
# The script explicitly checks common web/mail names, including:
#   - apex, www, mail, smtp, imap, pop, mg, mgn, autodiscover, autoconfig
#   - _dmarc
#   - s1._domainkey, s2._domainkey, selector1._domainkey, selector2._domainkey
#   - the corresponding DKIM/DMARC names below mg and mgn
#   - email CNAME records below mg and mgn
#   - common mail SRV records such as _imaps._tcp, _pop3s._tcp,
#     _submission._tcp and _autodiscover._tcp, including mg/mgn variants
#
# Record types queried:
#   A AAAA CNAME MX TXT CAA SRV NS
#
# IMPORTANT LIMITATION
# --------------------
# DNS does not provide a standard, reliable way to enumerate every possible
# subdomain. This script therefore queries a targeted list of known/common
# names. Add additional names to COMMON_NAMES, NESTED_AUTH_NAMES,
# NESTED_MAIL_NAMES or SRV_NAMES below if required.
#
# CLOUDFLARE IMPORT NOTES
# -----------------------
# The generated files use BIND zone-file syntax. Apex NS records are omitted
# because Cloudflare assigns its authoritative nameservers when a zone is
# activated. DNSSEC records are not queried; manage DNSSEC in Cloudflare
# separately after the zone is migrated.
#
# Before importing, review the generated files, especially MX, TXT/SPF, DKIM,
# DMARC, CAA and SRV records.
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

NESTED_AUTH_NAMES=(
  "s1._domainkey.mg" "s1._domainkey.mgn"
  "s2._domainkey.mg" "s2._domainkey.mgn"
  "selector1._domainkey.mg" "selector1._domainkey.mgn"
  "selector2._domainkey.mg" "selector2._domainkey.mgn"
  "_dmarc.mg" "_dmarc.mgn"
)

NESTED_MAIL_NAMES=(
  "email.mg"
  "email.mgn"
)

SRV_NAMES=(
  "_imaps._tcp" "_pop3s._tcp" "_submission._tcp" "_autodiscover._tcp"
  "_imap._tcp" "_pop3._tcp" "_smtps._tcp" "_smtp._tcp"
  "_submission._tcp.mg" "_autodiscover._tcp.mg" "_imaps._tcp.mg" "_pop3s._tcp.mg"
  "_submission._tcp.mgn" "_autodiscover._tcp.mgn" "_imaps._tcp.mgn" "_pop3s._tcp.mgn"
)

TYPES=(A AAAA CNAME MX TXT CAA SRV NS)

query_normal() {
  local fqdn="$1" type="$2"
  dig +noall +answer "$fqdn" "$type" 2>/dev/null || true
}

query_authoritative() {
  local fqdn="$1" type="$2" zone="$3"
  local ns

  for ns in $(dig +short NS "$zone" 2>/dev/null | sed 's/[[:space:]]//g'); do
    [ -z "$ns" ] && continue
    dig +noall +answer +time=3 +tries=1 "@$ns" "$fqdn" "$type" 2>/dev/null || true
  done

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
    echo "; Nested DKIM/DMARC and email CNAME names under mg/mgn are explicitly queried."
    echo "; DNSSEC records are not queried. Apex NS is omitted."
    echo
    printf '%s\n' '$ORIGIN '"${domain}."
    printf '%s\n' '$TTL 3600'
    echo

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

    for name in "${NESTED_AUTH_NAMES[@]}"; do
      fqdn="${name}.${domain}."
      echo "; Explicit authentication check: ${fqdn}"
      for type in TXT CNAME A AAAA; do
        while IFS= read -r line; do [ -z "$line" ] && continue; printf '%s\n' "$line"; done < <(query_normal "$fqdn" "$type")
      done
      case "$name" in
        *.mg) zone="mg.${domain}." ;;
        *.mgn) zone="mgn.${domain}." ;;
        *) zone="${domain}." ;;
      esac
      for type in TXT CNAME A AAAA; do
        while IFS= read -r line; do [ -z "$line" ] && continue; printf '%s\n' "$line"; done < <(query_authoritative "$fqdn" "$type" "$zone")
      done
    done

    for name in "${NESTED_MAIL_NAMES[@]}"; do
      fqdn="${name}.${domain}."
      echo "; Explicit mail CNAME check: ${fqdn}"
      while IFS= read -r line; do [ -z "$line" ] && continue; printf '%s\n' "$line"; done < <(query_normal "$fqdn" CNAME)
      case "$name" in
        *.mg) zone="mg.${domain}." ;;
        *.mgn) zone="mgn.${domain}." ;;
        *) zone="${domain}." ;;
      esac
      while IFS= read -r line; do [ -z "$line" ] && continue; printf '%s\n' "$line"; done < <(query_authoritative "$fqdn" CNAME "$zone")
    done

    for name in "${SRV_NAMES[@]}"; do
      fqdn="${name}.${domain}."
      while IFS= read -r line; do [ -z "$line" ] && continue; printf '%s\n' "$line"; done < <(query_normal "$fqdn" SRV)
    done
  } > "$tmp"

  awk '/^;/ || /^\$ORIGIN/ || /^\$TTL/ { print; next } !seen[$0]++ { print }' "$tmp" > "$outfile"
  rm -f "$tmp"
  echo "Wrote $outfile"
done
