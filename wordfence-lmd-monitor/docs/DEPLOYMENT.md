# Deployment plan

## Phase 0: central

1. Provision a small Ubuntu VM with Docker and a private MySQL volume.
2. Clone this repository and enter `wordfence-lmd-monitor/central`.
3. Copy `.env.example` to `.env` and replace every `CHANGE_ME` value.
4. Put the API behind TLS at a stable hostname such as `security.example.com`.
5. Start with `docker compose up -d --build`.
6. Verify `/healthz` through the reverse proxy.

## Phase 1: three-server pilot

Use one low-traffic site, one high-traffic site and one large WordPress installation. Deploy LMD and the agent with Ansible. Keep quarantine and cleanup disabled. Measure CPU, IO, scan time and false positives for at least several days.

## Phase 2: staged fleet rollout

Roll out 10 -> 50 -> 100 -> 500 hosts. After each stage check heartbeats, scan completion, API error rates and incident deduplication.

## Current alert path

LMD monitor mode -> LMD post-scan hook -> local agent -> HTTPS -> FastAPI -> MySQL -> Slack/email.

Scheduled daily scan -> same hook/agent path. Agent also sends a heartbeat every 10 minutes.

## Production hardening before fleet rollout

- Put the API behind TLS; do not expose plain port 8080 to the Internet.
- Replace the prototype shared `APP_SECRET` authentication with per-host credentials or mTLS.
- Store Ansible secrets in Vault or another secret manager.
- Restrict MySQL to the API network only.
- Add backups and point-in-time recovery for MySQL.
- Add rate limiting at the reverse proxy.
- Add a dead-agent alert when heartbeat age exceeds the chosen threshold.
- Add dashboard/authentication before exposing operational UI.
- Test LMD false positives before enabling any quarantine/remediation policy.
- Test with EICAR and synthetic PHP/YARA fixtures on pilot servers.

## Incident policy

The first release only detects and alerts. It never automatically deletes or quarantines production files. Human remediation should use the incident details and Wordfence results as corroborating evidence.
