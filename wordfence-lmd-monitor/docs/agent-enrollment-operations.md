# Agent enrollment operations

## Central configuration

Set `ENROLLMENT_BOOTSTRAP_TOKEN` on the central API. Treat it as a short-lived bootstrap secret and store it in the deployment secret manager, not in Git.

Apply `sql/002_agent_enrollment.sql` to the existing MySQL database before starting the wrapped API server.

The central container now starts `server:app`, which wraps the existing API with bearer-token authentication for `/v1/heartbeat` and `/v1/events` and exposes `/v1/enroll`.

## Enrolling a server

The Ansible playbook expects:

- `vault_enrollment_token`: the current bootstrap token
- `security_monitor_url`: the HTTPS collector URL
- `site_url`: site URL per host, if available
- `site_root`: WordPress filesystem root

Run the playbook against a small pilot group first. The enrollment helper stores the returned per-agent token in `/etc/security-monitor/agent.json` with mode `0600`.

The raw token is returned by the API only during enrollment. It is never persisted in the central database; only its SHA-256 hash is stored.

## Revocation

Use the authenticated dashboard credentials to call:

`POST /v1/admin/agents/{agent_id}/revoke`

Revocation immediately causes future heartbeats/events from that agent to return HTTP 401.

## Rotation

Use:

`POST /v1/admin/agents/{agent_id}/rotate`

The response contains the new token exactly once. Update the affected server's protected `agent.json` before the next heartbeat. Rotation does not require changing the server's agent ID.

## Rollout sequence

1. Apply the SQL migration.
2. Deploy the central wrapper.
3. Set the bootstrap token as a secret.
4. Enroll 3 pilot servers.
5. Verify heartbeats and malware events.
6. Disable or rotate the bootstrap token after the fleet rollout.
7. Roll out in batches: 10, 50, 100, then the remaining fleet.
8. Add mTLS after bearer enrollment is proven stable.
