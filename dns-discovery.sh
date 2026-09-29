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
# Download the latest version from GitHub:
#
#   curl -fsSL https://raw.githubusercontent.com/consc198/scripts/main/dns-discovery.sh -o dns-discovery.sh
#   chmod +x dns-discovery.sh
#
# RUN
# ---
# Pass one or more domains as arguments:
#
#   ./dns-discovery.sh gunterbroodcoorens.com studio4.be ondernemersvlaanderen.be
#
# The script creates one Cloudflare-ready BIND zone file per domain:
#
#   gunterbroodcoorens.com-cloudflare.txt
#   studio4.be-cloudflare.txt
#   ondernemersvlaanderen.be-cloudflare.txt
#
# WHAT IS QUERIED
# ---------------
# The script explicitly checks common web/mail names, including:
#   - apex, www, mail, smtp, imap, pop, mg, mgn, autodiscover, autoconfig
#   - _dmarc
#   - s1._domainkey, s2._domainkey, selector1._domainkey, selector2._domainkey
#   - the corresponding DKIM/DMARC names below mg and mgn
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
# names. Add additional names to COMMON_NAMES or SRV_NAMES below if required.
#
# CLOUDFLARE IMPORT NOTES
# -----------------------
# The generated files use BIND zone-file syntax. Apex NS records are omitted
# because Cloudflare assigns its authoritative nameservers when a zone is
# activated. DNSSEC records are not queried; enable/manage DNSSEC in Cloudflare
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
  "s1._domainkey.mg" "s2._domainkey.mg" "selector1._domainkey.mg" "selector2._domainkey.mg" "_dmarc.mg"
  "s1._domainkey.mgn" "s2._domainkey.mgn" "selector1._domainkey.mgn" "selector2._domainkey.mgn" "_dmarc.mgn"
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
    echo "; DNSSEC records are not queried. Apex NS is omitted for normal Cloudflare"
    echo "; full-zone setup because Cloudflare supplies authoritative nameservers."
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
        done < <(dig +noall +answer "$fqdn" "$type" 2>/dev/null)
      done
    done

    for name in "${SRV_NAMES[@]}"; do
      fqdn="${name}.${domain}."
      while IFS= read -r line; do
        [ -z "$line" ] && continue
        printf '%s\n' "$line"
      done < <(dig +noall +answer "$fqdn" SRV 2>/dev/null)
    done
  } > "$tmp"

  awk '/^;/ || /^\$ORIGIN/ || /^\$TTL/ { print; next } !seen[$0]++ { print }' "$tmp" > "$outfile"
  rm -f "$tmp"
  echo "Wrote $outfile"
done
