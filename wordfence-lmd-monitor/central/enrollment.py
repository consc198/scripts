"""Agent enrollment helpers.

Enrollment uses a one-time bootstrap secret and returns a per-agent token.
The bootstrap secret is never stored in the database.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_bootstrap(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())


def new_agent_credentials() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
