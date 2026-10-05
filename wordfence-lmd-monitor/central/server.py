from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
import secrets

from app import app, dashboard_auth, engine
from enrollment_api import EnrollmentRequest, add_agent_auth_middleware, enroll
from enrollment import hash_token

add_agent_auth_middleware(app)


@app.post("/v1/enroll")
def enroll_agent(request: Request, body: EnrollmentRequest):
    return enroll(request, body)


@app.get("/v1/enrollment/status")
def enrollment_status():
    import os
    return {"enabled": bool(os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN"))}


@app.post("/v1/admin/agents/{agent_id}/revoke")
def revoke_agent(agent_id: str, request: Request):
    dashboard_auth(request)
    with engine.begin() as conn:
        result = conn.execute(text("""UPDATE agent_credentials
            SET active=0, revoked_at=UTC_TIMESTAMP()
            WHERE agent_id=:agent_id AND active=1"""), {"agent_id": agent_id})
        if result.rowcount == 0:
            return JSONResponse({"revoked": False, "detail": "agent not found or already revoked"}, status_code=404)
    return {"revoked": True, "agent_id": agent_id}


@app.post("/v1/admin/agents/{agent_id}/rotate")
def rotate_agent(agent_id: str, request: Request):
    dashboard_auth(request)
    raw_token = secrets.token_urlsafe(48)
    with engine.begin() as conn:
        row = conn.execute(text("SELECT agent_id FROM agent_credentials WHERE agent_id=:agent_id AND active=1"),
                           {"agent_id": agent_id}).first()
        if not row:
            return JSONResponse({"rotated": False, "detail": "agent not found or inactive"}, status_code=404)
        conn.execute(text("UPDATE agent_credentials SET token_hash=:token_hash,last_used_at=NULL WHERE agent_id=:agent_id"),
                     {"agent_id": agent_id, "token_hash": hash_token(raw_token)})
    return {"rotated": True, "agent_id": agent_id, "token": raw_token}
