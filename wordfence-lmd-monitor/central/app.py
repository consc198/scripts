import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
APP_SECRET = os.environ["APP_SECRET"].encode()
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
app = FastAPI(title="WordPress Malware Monitor", version="0.1.0")

class Event(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    hostname: str = Field(min_length=1, max_length=255)
    site_url: str | None = None
    scanner: str = "lmd"
    event_type: str
    severity: str = "info"
    fingerprint: str | None = None
    occurred_at: datetime
    payload: dict[str, Any] = {}
    agent_version: str | None = None
    lmd_version: str | None = None

class Heartbeat(BaseModel):
    agent_id: str
    hostname: str
    site_url: str | None = None
    agent_version: str | None = None
    lmd_version: str | None = None


def verify_signature(raw: bytes, signature: str | None):
    if not signature:
        raise HTTPException(401, "missing signature")
    expected = hmac.new(APP_SECRET, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "invalid signature")


def upsert_server(conn, agent_id, hostname, site_url, agent_version, lmd_version):
    conn.execute(text("""
      INSERT INTO servers(agent_id,hostname,site_url,agent_version,lmd_version,last_seen_at)
      VALUES(:a,:h,:u,:av,:lv,UTC_TIMESTAMP())
      ON DUPLICATE KEY UPDATE hostname=VALUES(hostname),site_url=VALUES(site_url),
      agent_version=VALUES(agent_version),lmd_version=VALUES(lmd_version),last_seen_at=UTC_TIMESTAMP()
    """), dict(a=agent_id,h=hostname,u=site_url,av=agent_version,lv=lmd_version))
    return conn.execute(text("SELECT id FROM servers WHERE agent_id=:a"), {"a": agent_id}).scalar_one()

@app.get("/healthz")
def healthz():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True}

@app.post("/v1/heartbeat")
def heartbeat(body: Heartbeat, x_signature: str | None = Header(default=None)):
    raw = body.model_dump_json().encode()
    verify_signature(raw, x_signature)
    with engine.begin() as conn:
        upsert_server(conn, body.agent_id, body.hostname, body.site_url, body.agent_version, body.lmd_version)
    return {"accepted": True}

@app.post("/v1/events")
def event(body: Event, x_signature: str | None = Header(default=None)):
    raw = body.model_dump_json().encode()
    verify_signature(raw, x_signature)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as conn:
        server_id = upsert_server(conn, body.agent_id, body.hostname, body.site_url, body.agent_version, body.lmd_version)
        conn.execute(text("""
          INSERT INTO events(server_id,scanner,event_type,severity,fingerprint,occurred_at,payload)
          VALUES(:sid,:scanner,:etype,:sev,:fp,:occurred,:payload)
        """), dict(sid=server_id,scanner=body.scanner,etype=body.event_type,sev=body.severity,
                    fp=body.fingerprint,occurred=body.occurred_at.replace(tzinfo=None),payload=json.dumps(body.payload)))
        if body.event_type == "malware_detected" and body.fingerprint:
            existing = conn.execute(text("""
              SELECT id FROM incidents WHERE server_id=:sid AND fingerprint=:fp AND status <> 'resolved'
              ORDER BY id DESC LIMIT 1
            """), {"sid":server_id,"fp":body.fingerprint}).scalar()
            if existing:
                conn.execute(text("UPDATE incidents SET last_seen_at=:t WHERE id=:id"), {"t":body.occurred_at.replace(tzinfo=None),"id":existing})
                incident_id = existing
                new_incident = False
            else:
                result = conn.execute(text("""
                  INSERT INTO incidents(server_id,site_url,severity,fingerprint,first_seen_at,last_seen_at)
                  VALUES(:sid,:url,:sev,:fp,:t,:t)
                """), {"sid":server_id,"url":body.site_url,"sev":body.severity,"fp":body.fingerprint,"t":body.occurred_at.replace(tzinfo=None)})
                incident_id = result.lastrowid
                new_incident = True
            for finding in body.payload.get("findings", []):
                conn.execute(text("""
                  INSERT INTO findings(incident_id,path,sha256,signature,detection_type,first_seen_at,last_seen_at)
                  VALUES(:iid,:path,:sha,:sig,:dtype,:t,:t)
                """), {"iid":incident_id,"path":finding.get("path",""),"sha":finding.get("sha256"),
                       "sig":finding.get("signature"),"dtype":finding.get("detection_type"),"t":body.occurred_at.replace(tzinfo=None)})
    return {"accepted": True, "incident_id": incident_id if body.event_type == "malware_detected" else None,
            "new_incident": new_incident if body.event_type == "malware_detected" else False}
