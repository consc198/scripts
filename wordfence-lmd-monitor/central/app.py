import base64
import hashlib
import hmac
import json
import os
import smtplib
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ['DATABASE_URL']
APP_SECRET = os.environ['APP_SECRET'].encode()
DASHBOARD_USER = os.getenv('DASHBOARD_USER', '')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', '')
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
app = FastAPI(title='WordPress Malware Monitor', version='0.2.0')


class Event(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    hostname: str = Field(min_length=1, max_length=255)
    site_url: str | None = None
    scanner: str = 'lmd'
    event_type: str
    severity: str = 'info'
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


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, separators=(',', ':'), sort_keys=True).encode()


def verify(body: BaseModel, signature: str | None):
    if not signature:
        raise HTTPException(401, 'missing signature')
    expected = hmac.new(APP_SECRET, canonical(json.loads(body.model_dump_json())), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, 'invalid signature')


def dashboard_auth(request: Request):
    if not DASHBOARD_USER or not DASHBOARD_PASSWORD:
        raise HTTPException(503, 'dashboard authentication is not configured')
    header = request.headers.get('authorization', '')
    if not header.startswith('Basic '):
        raise HTTPException(401, 'authentication required', headers={'WWW-Authenticate': 'Basic realm="Malware Monitor"'})
    try:
        decoded = base64.b64decode(header[6:]).decode()
        user, password = decoded.split(':', 1)
    except Exception:
        raise HTTPException(401, 'invalid authentication', headers={'WWW-Authenticate': 'Basic realm="Malware Monitor"'})
    if not hmac.compare_digest(user, DASHBOARD_USER) or not hmac.compare_digest(password, DASHBOARD_PASSWORD):
        raise HTTPException(401, 'invalid authentication', headers={'WWW-Authenticate': 'Basic realm="Malware Monitor"'})


def upsert_server(conn, b):
    conn.execute(text('''INSERT INTO servers(agent_id,hostname,site_url,agent_version,lmd_version,last_seen_at)
        VALUES(:a,:h,:u,:av,:lv,UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE hostname=VALUES(hostname),site_url=VALUES(site_url),agent_version=VALUES(agent_version),lmd_version=VALUES(lmd_version),last_seen_at=UTC_TIMESTAMP()'''),
        {'a': b.agent_id, 'h': b.hostname, 'u': b.site_url, 'av': b.agent_version, 'lv': b.lmd_version})
    return conn.execute(text('SELECT id FROM servers WHERE agent_id=:a'), {'a': b.agent_id}).scalar_one()


def notify(site, hostname, incident_id, findings):
    body = f"MALWARE DETECTED\nSite: {site or 'unknown'}\nHost: {hostname}\nIncident: {incident_id}\nFindings: {len(findings)}\n" + '\n'.join(f"- {x.get('path', '')} [{x.get('signature') or 'unknown'}]" for x in findings[:20])
    webhook = os.getenv('SLACK_WEBHOOK_URL')
    if webhook:
        try:
            req = urllib.request.Request(webhook, data=json.dumps({'text': body}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass
    host = os.getenv('SMTP_HOST')
    to = os.getenv('ALERT_EMAIL_TO')
    sender = os.getenv('SMTP_FROM', 'malware-monitor@localhost')
    if host and to:
        try:
            msg = EmailMessage()
            msg['Subject'] = f'Malware detected: {site or hostname}'
            msg['From'] = sender
            msg['To'] = to
            msg.set_content(body)
            with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '25')), timeout=10) as s:
                if os.getenv('SMTP_TLS', '0') == '1':
                    s.starttls()
                if os.getenv('SMTP_USER'):
                    s.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
                s.send_message(msg)
        except Exception:
            pass


@app.get('/healthz')
def healthz():
    with engine.connect() as c:
        c.execute(text('SELECT 1'))
    return {'ok': True}


@app.post('/v1/heartbeat')
def heartbeat(body: Heartbeat, x_signature: str | None = Header(default=None)):
    verify(body, x_signature)
    with engine.begin() as c:
        upsert_server(c, body)
    return {'accepted': True}


@app.post('/v1/events')
def event(body: Event, x_signature: str | None = Header(default=None)):
    verify(body, x_signature)
    incident_id = None
    new = False
    findings = []
    now = body.occurred_at.replace(tzinfo=None)
    with engine.begin() as c:
        sid = upsert_server(c, body)
        c.execute(text('''INSERT INTO events(server_id,scanner,event_type,severity,fingerprint,occurred_at,payload)
            VALUES(:sid,:scanner,:etype,:sev,:fp,:occurred,:payload)'''),
            {'sid': sid, 'scanner': body.scanner, 'etype': body.event_type, 'sev': body.severity,
             'fp': body.fingerprint, 'occurred': now, 'payload': json.dumps(body.payload)})
        if body.event_type == 'malware_detected' and body.fingerprint:
            findings = body.payload.get('findings', [])
            existing = c.execute(text("SELECT id FROM incidents WHERE server_id=:sid AND fingerprint=:fp AND status <> 'resolved' ORDER BY id DESC LIMIT 1"), {'sid': sid, 'fp': body.fingerprint}).scalar()
            if existing:
                incident_id = existing
                c.execute(text('UPDATE incidents SET last_seen_at=:t WHERE id=:id'), {'t': now, 'id': existing})
            else:
                result = c.execute(text('''INSERT INTO incidents(server_id,site_url,severity,fingerprint,first_seen_at,last_seen_at)
                    VALUES(:sid,:url,:sev,:fp,:t,:t)'''),
                    {'sid': sid, 'url': body.site_url, 'sev': body.severity, 'fp': body.fingerprint, 't': now})
                incident_id = result.lastrowid
                new = True
            for f in findings:
                c.execute(text('''INSERT INTO findings(incident_id,path,sha256,signature,detection_type,first_seen_at,last_seen_at)
                    VALUES(:iid,:path,:sha,:sig,:dtype,:t,:t)'''),
                    {'iid': incident_id, 'path': f.get('path', ''), 'sha': f.get('sha256'), 'sig': f.get('signature'), 'dtype': f.get('detection_type'), 't': now})
    if new:
        notify(body.site_url, body.hostname, incident_id, findings)
    return {'accepted': True, 'incident_id': incident_id, 'new_incident': new}


@app.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request):
    dashboard_auth(request)
    return HTMLResponse(DASHBOARD_HTML)


@app.get('/api/dashboard/summary')
def dashboard_summary(request: Request):
    dashboard_auth(request)
    with engine.connect() as c:
        row = c.execute(text('''SELECT
            COUNT(*) AS total_servers,
            SUM(CASE WHEN last_seen_at >= UTC_TIMESTAMP() - INTERVAL 15 MINUTE THEN 1 ELSE 0 END) AS online_servers,
            SUM(CASE WHEN last_seen_at < UTC_TIMESTAMP() - INTERVAL 15 MINUTE OR last_seen_at IS NULL THEN 1 ELSE 0 END) AS stale_servers
            FROM servers''')).mappings().one()
        incidents = c.execute(text("SELECT COUNT(*) AS open_incidents, SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS critical_incidents FROM incidents WHERE status <> 'resolved'" )).mappings().one()
        scans = c.execute(text('''SELECT COUNT(*) AS scans_24h,
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS successful_24h,
            SUM(CASE WHEN status NOT IN ('completed','running') THEN 1 ELSE 0 END) AS failed_24h
            FROM scans WHERE started_at >= UTC_TIMESTAMP() - INTERVAL 24 HOUR''')).mappings().one()
    return {**dict(row), **dict(incidents), **dict(scans)}


@app.get('/api/dashboard/servers')
def dashboard_servers(request: Request, limit: int = 100):
    dashboard_auth(request)
    limit = max(1, min(limit, 5000))
    with engine.connect() as c:
        rows = c.execute(text(f'''SELECT s.id,s.agent_id,s.hostname,s.site_url,s.agent_version,s.lmd_version,s.last_seen_at,
            (SELECT MAX(sc.started_at) FROM scans sc WHERE sc.server_id=s.id) AS last_scan_at,
            (SELECT COUNT(*) FROM incidents i WHERE i.server_id=s.id AND i.status <> 'resolved') AS open_incidents
            FROM servers s ORDER BY (s.last_seen_at IS NULL), s.last_seen_at DESC LIMIT {limit}''')).mappings().all()
    return {'servers': [dict(r) for r in rows]}


@app.get('/api/dashboard/incidents')
def dashboard_incidents(request: Request, status: str = 'open', limit: int = 100):
    dashboard_auth(request)
    limit = max(1, min(limit, 500))
    with engine.connect() as c:
        if status == 'all':
            rows = c.execute(text(f'''SELECT i.id,i.site_url,i.severity,i.status,i.first_seen_at,i.last_seen_at,
                s.hostname,s.agent_id,COUNT(f.id) AS finding_count
                FROM incidents i JOIN servers s ON s.id=i.server_id LEFT JOIN findings f ON f.incident_id=i.id
                GROUP BY i.id ORDER BY i.last_seen_at DESC LIMIT {limit}''')).mappings().all()
        else:
            rows = c.execute(text(f'''SELECT i.id,i.site_url,i.severity,i.status,i.first_seen_at,i.last_seen_at,
                s.hostname,s.agent_id,COUNT(f.id) AS finding_count
                FROM incidents i JOIN servers s ON s.id=i.server_id LEFT JOIN findings f ON f.incident_id=i.id
                WHERE i.status=:status GROUP BY i.id ORDER BY i.last_seen_at DESC LIMIT {limit}'''), {'status': status}).mappings().all()
    return {'incidents': [dict(r) for r in rows]}


DASHBOARD_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WordPress Malware Monitor</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#111827;--muted:#94a3b8;--text:#e5e7eb;--line:#263244;--good:#34d399;--bad:#fb7185;--warn:#fbbf24;--accent:#60a5fa}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{padding:24px 28px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}h1{font-size:21px;margin:0}.muted{color:var(--muted)}main{padding:24px 28px;max-width:1500px;margin:auto}.cards{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:14px;margin-bottom:24px}.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px}.card{padding:18px}.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.value{font-size:30px;font-weight:700;margin-top:8px}.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.panel{padding:18px;margin-bottom:20px}.panel h2{font-size:15px;margin:0 0 14px}.toolbar{display:flex;gap:8px;margin-bottom:12px}button,select{background:#172033;color:var(--text);border:1px solid var(--line);border-radius:6px;padding:7px 10px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-top:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-size:12px;font-weight:500}.pill{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:600}.pill.good{background:#063d30}.pill.bad{background:#4a1521}.pill.warn{background:#4a3608}.empty{padding:22px;text-align:center;color:var(--muted)}@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:16px}header{padding:18px}.panel{overflow:auto}}
</style></head>
<body><header><div><h1>WordPress Malware Monitor</h1><div class="muted">Fleet security overview</div></div><div class="muted" id="updated">Loading…</div></header>
<main><section class="cards"><div class="card"><div class="label">Servers</div><div class="value" id="total">—</div></div><div class="card"><div class="label">Online</div><div class="value good" id="online">—</div></div><div class="card"><div class="label">Open incidents</div><div class="value bad" id="incidents">—</div></div><div class="card"><div class="label">Critical incidents</div><div class="value bad" id="critical">—</div></div></section>
<section class="panel"><h2>Scanner health — last 24 hours</h2><div id="scanHealth" class="muted">Loading…</div></section>
<section class="panel"><h2>Open incidents</h2><div id="incidentTable">Loading…</div></section>
<section class="panel"><h2>Servers</h2><div id="serverTable">Loading…</div></section></main>
<script>
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=v=>v?new Date(v+'Z').toLocaleString(): 'Never';
async function get(url){const r=await fetch(url);if(!r.ok)throw new Error(await r.text());return r.json()}
async function refresh(){try{const [s,i,sv]=await Promise.all([get('/api/dashboard/summary'),get('/api/dashboard/incidents?status=open'),get('/api/dashboard/servers')]);
 document.querySelector('#total').textContent=s.total_servers??0;document.querySelector('#online').textContent=s.online_servers??0;document.querySelector('#incidents').textContent=s.open_incidents??0;document.querySelector('#critical').textContent=s.critical_incidents??0;
 document.querySelector('#scanHealth').innerHTML=`${s.successful_24h??0} successful / ${s.failed_24h??0} failed / ${s.scans_24h??0} total scans`;
 document.querySelector('#updated').textContent='Updated '+new Date().toLocaleTimeString();
 document.querySelector('#incidentTable').innerHTML=i.incidents.length?`<table><thead><tr><th>Site</th><th>Severity</th><th>Findings</th><th>First seen</th><th>Last seen</th><th>Host</th></tr></thead><tbody>${i.incidents.map(x=>`<tr><td>${esc(x.site_url||'unknown')}</td><td><span class="pill bad">${esc(x.severity)}</span></td><td>${x.finding_count}</td><td>${time(x.first_seen_at)}</td><td>${time(x.last_seen_at)}</td><td>${esc(x.hostname)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">No open malware incidents.</div>';
 document.querySelector('#serverTable').innerHTML=sv.servers.length?`<table><thead><tr><th>Site</th><th>Host</th><th>Last heartbeat</th><th>Last scan</th><th>LMD</th><th>Incidents</th></tr></thead><tbody>${sv.servers.map(x=>{const stale=!x.last_seen_at||Date.now()-new Date(x.last_seen_at+'Z').getTime()>15*60*1000;return `<tr><td>${esc(x.site_url||'unknown')}</td><td>${esc(x.hostname)}</td><td><span class="pill ${stale?'warn':'good'}">${stale?'STALE':'ONLINE'}</span><br>${time(x.last_seen_at)}</td><td>${time(x.last_scan_at)}</td><td>${esc(x.lmd_version||'unknown')}</td><td>${x.open_incidents}</td></tr>`}).join('')}</tbody></table>`:'<div class="empty">No servers registered yet.</div>';
 }catch(e){document.querySelector('#updated').textContent='Dashboard error';console.error(e)}}refresh();setInterval(refresh,30000);
</script></body></html>'''
