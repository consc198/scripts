# WordPress Malware Monitor

Centralized Layer-2 malware monitoring for WordPress fleets using Linux Malware Detect (LMD) on each Ubuntu host and a small HTTPS collector backed by MySQL.

## Architecture

- Host: LMD 2.x + YARA + inotify watches the WordPress document root.
- Agent: reads LMD JSON reports and sends signed events/heartbeats to the central API.
- Central: FastAPI + MySQL. Events are retained; incidents are deduplicated by fingerprint.
- Alerts: central service sends Slack/email only for new incidents.
- Wordfence: remains installed and managed by Wordfence Central; this system is independent of WordPress.

## Layout

```text
wordfence-lmd-monitor/
  central/      FastAPI collector and Docker deployment
  agent/        Host-side reporting agent
  ansible/      Fleet installation/playbook
  systemd/      Agent units
  lmd/          LMD configuration
  sql/          MySQL schema
  docs/         Operations notes
```

## Security

No secrets are committed. Each host receives a unique token or, preferably, an mTLS identity. The API accepts authenticated HTTPS requests. Agents queue unsent events locally so a central outage does not lose detections.

LMD is configured for detection only initially: automatic quarantine/cleanup is disabled.

## LMD strategy

- real-time inotify monitoring
- nightly recent-file scan
- weekly full scan
- YARA enabled where available
- ClamAV optional
- no automatic cleanup

## Central deployment

Copy `central/.env.example` to `central/.env`, set a strong application secret, MySQL credentials and alert configuration, then:

```bash
cd central
docker compose up -d --build
```

Put the API behind an HTTPS reverse proxy.

## Agent deployment

The Ansible playbook installs the agent and LMD on Ubuntu hosts. Test on three representative machines before rolling out to all 500 servers.

```bash
cd ansible
ansible-playbook -i inventory.ini deploy.yml
```

Secrets should be supplied through Ansible Vault or a secret manager, never committed.

## Remediation policy

This project does not automatically delete or modify detected files. Detection creates an incident; remediation is a separate human-approved workflow.
