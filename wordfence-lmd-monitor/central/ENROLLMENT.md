# Agent enrollment

The fleet uses one-time bootstrap enrollment. The bootstrap secret is supplied through Ansible Vault and is never stored by the API. Each successful enrollment creates a random per-agent token; only its SHA-256 hash is persisted centrally.

## Flow

1. Operator stores `vault_enrollment_token` in Ansible Vault.
2. Ansible installs the enrollment helper on a server.
3. The helper sends hostname/site metadata over HTTPS to `/v1/enroll`.
4. The API verifies the bootstrap secret, creates an agent identity and generates a unique token.
5. The API returns the token exactly once.
6. The token is stored locally as `/etc/security-monitor/credentials.json` with mode `0600`.
7. All later event/heartbeat requests authenticate using that per-agent credential.

## Security requirements

- Use HTTPS only; do not deploy the collector over plain HTTP.
- Keep the bootstrap secret in Ansible Vault or an equivalent secret manager.
- Never log enrollment requests or responses.
- Never store the raw per-agent token centrally.
- Revoke an individual compromised host by disabling its agent identity.
- Enrollment should be disabled after the initial fleet rollout, or protected by a separate short-lived bootstrap credential.
- Back up the database, but treat the bootstrap secret and local agent credentials as separate secrets.

## Production recommendation

For the 500-server rollout, use a dedicated enrollment credential with a short lifetime and rotate it after the fleet is enrolled. For higher assurance, add mutual TLS after the enrollment workflow is proven.
