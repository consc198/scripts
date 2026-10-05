import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app import APP_SECRET, engine
from enrollment import hash_token, new_agent_credentials, verify_bootstrap


BOOTSTRAP_TOKEN = os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "")


class EnrollmentRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    site_url: str | None = Field(default=None, max_length=512)
    agent_version: str | None = Field(default=None, max_length=32)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _bearer(request: Request) -> str:
    value = request.headers.get("authorization", "")
    if not value.startswith("Bearer "):
        raise HTTPException(401, "missing agent credentials")
    token = value[7:].strip()
    if not token:
        raise HTTPException(401, "missing agent credentials")
    return token


def authenticate_agent(token: str, agent_id: str) -> None:
    token_hash = hash_token(token)
    with engine.begin() as conn:
        row = conn.execute(text("""SELECT agent_id FROM agent_credentials
            WHERE agent_id=:agent_id AND token_hash=:token_hash AND active=1"""),
            {"agent_id": agent_id, "token_hash": token_hash}).mappings().first()
        if not row:
            raise HTTPException(401, "invalid agent credentials")
        conn.execute(text("UPDATE agent_credentials SET last_used_at=UTC_TIMESTAMP() WHERE agent_id=:agent_id"),
                     {"agent_id": agent_id})


def authenticate_request(request: Request, agent_id: str) -> None:
    token = _bearer(request)
    authenticate_agent(token, agent_id)


def enroll(request: Request, body: EnrollmentRequest):
    if not BOOTSTRAP_TOKEN:
        raise HTTPException(503, "agent enrollment is disabled")
    provided = request.headers.get("authorization", "")
    if not provided.startswith("Bearer ") or not verify_bootstrap(provided[7:].strip(), BOOTSTRAP_TOKEN):
        raise HTTPException(401, "invalid enrollment credential")

    agent_id = "agent-" + secrets.token_hex(16)
    raw_token, token_hash = new_agent_credentials()
    now = utcnow()
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT agent_id FROM servers WHERE hostname=:hostname LIMIT 1"),
                                {"hostname": body.hostname}).scalar()
        if existing:
            raise HTTPException(409, "host is already enrolled")
        conn.execute(text("""INSERT INTO servers(agent_id,hostname,site_url,agent_version,last_seen_at)
            VALUES(:agent_id,:hostname,:site_url,:agent_version,:now)"""),
            {"agent_id": agent_id, "hostname": body.hostname, "site_url": body.site_url,
             "agent_version": body.agent_version, "now": now})
        conn.execute(text("""INSERT INTO agent_credentials(agent_id,token_hash,created_at,last_used_at,active)
            VALUES(:agent_id,:token_hash,:created_at,:last_used_at,1)"""),
            {"agent_id": agent_id, "token_hash": token_hash, "created_at": now, "last_used_at": now})

    return {"agent_id": agent_id, "token": raw_token, "site_url": body.site_url}


def add_agent_auth_middleware(app):
    @app.middleware("http")
    async def agent_auth(request: Request, call_next):
        if request.url.path not in {"/v1/events", "/v1/heartbeat"}:
            return await call_next(request)
        if request.method != "POST":
            return await call_next(request)
        body = await request.body()
        try:
            parsed = json.loads(body)
            agent_id = parsed.get("agent_id")
            if not agent_id:
                raise HTTPException(400, "agent_id is required")
            authenticate_request(request, agent_id)
            signature = hmac.new(APP_SECRET, json.dumps(parsed, separators=(",", ":"), sort_keys=True).encode(), hashlib.sha256).hexdigest()
            headers = list(request.scope["headers"])
            headers = [(k, v) for k, v in headers if k.lower() != b"x-signature"]
            headers.append((b"x-signature", signature.encode()))
            request.scope["headers"] = headers
        except HTTPException as exc:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers or {})
        except Exception:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "invalid request"}, status_code=400)

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request._receive = receive
        return await call_next(request)

    return app
