from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from app import app, dashboard_auth, engine


def _remove_existing_dashboard_routes() -> None:
    # app.py already registers the original read-only dashboard. Replace those
    # presentation routes while keeping all ingestion endpoints unchanged.
    paths = {
        "/dashboard",
        "/api/dashboard/summary",
        "/api/dashboard/servers",
        "/api/dashboard/incidents",
    }
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) not in paths]


_remove_existing_dashboard_routes()


def _incident(incident_id: int):
    with engine.connect() as c:
        row = c.execute(text("""SELECT i.id,i.server_id,i.site_url,i.severity,i.status,i.fingerprint,
            i.first_seen_at,i.last_seen_at,s.hostname,s.agent_id,s.agent_version,s.lmd_version,s.last_seen_at AS heartbeat_at
            FROM incidents i JOIN servers s ON s.id=i.server_id WHERE i.id=:id"""), {"id": incident_id}).mappings().first()
        if not row:
            raise HTTPException(404, "incident not found")
        findings = c.execute(text("""SELECT id,path,sha256,signature,detection_type,first_seen_at,last_seen_at
            FROM findings WHERE incident_id=:id ORDER BY first_seen_at ASC,id ASC"""), {"id": incident_id}).mappings().all()
        events = c.execute(text("""SELECT id,scanner,event_type,severity,fingerprint,occurred_at,payload
            FROM events WHERE server_id=:sid AND fingerprint=:fp ORDER BY occurred_at DESC,id DESC LIMIT 100"""),
            {"sid": row["server_id"], "fp": row["fingerprint"]}).mappings().all()
    return dict(row), [dict(x) for x in findings], [dict(x) for x in events]


def _server(server_id: int):
    with engine.connect() as c:
        server = c.execute(text("""SELECT id,agent_id,hostname,site_url,agent_version,lmd_version,last_seen_at
            FROM servers WHERE id=:id"""), {"id": server_id}).mappings().first()
        if not server:
            raise HTTPException(404, "server not found")
        incidents = c.execute(text("""SELECT i.id,i.site_url,i.severity,i.status,i.first_seen_at,i.last_seen_at,
            COUNT(f.id) AS finding_count FROM incidents i LEFT JOIN findings f ON f.incident_id=i.id
            WHERE i.server_id=:id GROUP BY i.id ORDER BY i.last_seen_at DESC LIMIT 100"""), {"id": server_id}).mappings().all()
        scans = c.execute(text("""SELECT id,scanner,scan_type,started_at,completed_at,files_scanned,detections,status
            FROM scans WHERE server_id=:id ORDER BY started_at DESC LIMIT 100"""), {"id": server_id}).mappings().all()
        events = c.execute(text("""SELECT id,scanner,event_type,severity,fingerprint,occurred_at,payload
            FROM events WHERE server_id=:id ORDER BY occurred_at DESC,id DESC LIMIT 100"""), {"id": server_id}).mappings().all()
    return dict(server), [dict(x) for x in incidents], [dict(x) for x in scans], [dict(x) for x in events]


@app.get("/api/dashboard/incidents/{incident_id}")
def incident_detail_api(request: Request, incident_id: int):
    dashboard_auth(request)
    incident, findings, events = _incident(incident_id)
    return {"incident": incident, "findings": findings, "events": events}


@app.get("/api/dashboard/servers/{server_id}")
def server_detail_api(request: Request, server_id: int):
    dashboard_auth(request)
    server, incidents, scans, events = _server(server_id)
    return {"server": server, "incidents": incidents, "scans": scans, "events": events}


@app.get("/dashboard/incidents/{incident_id}", response_class=HTMLResponse)
def incident_detail_page(request: Request, incident_id: int):
    dashboard_auth(request)
    return HTMLResponse(DETAIL_HTML.replace("__KIND__", "incident").replace("__ID__", str(incident_id)))


@app.get("/dashboard/servers/{server_id}", response_class=HTMLResponse)
def server_detail_page(request: Request, server_id: int):
    dashboard_auth(request)
    return HTMLResponse(DETAIL_HTML.replace("__KIND__", "server").replace("__ID__", str(server_id)))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    dashboard_auth(request)
    return HTMLResponse(MAIN_HTML)


@app.get("/api/dashboard/summary")
def dashboard_summary_api(request: Request):
    dashboard_auth(request)
    with engine.connect() as c:
        row = c.execute(text("""SELECT COUNT(*) AS total_servers,
            SUM(CASE WHEN last_seen_at >= UTC_TIMESTAMP() - INTERVAL 15 MINUTE THEN 1 ELSE 0 END) AS online_servers,
            SUM(CASE WHEN last_seen_at < UTC_TIMESTAMP() - INTERVAL 15 MINUTE OR last_seen_at IS NULL THEN 1 ELSE 0 END) AS stale_servers
            FROM servers""")).mappings().one()
        incidents = c.execute(text("""SELECT COUNT(*) AS open_incidents,
            SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS critical_incidents
            FROM incidents WHERE status <> 'resolved'""")).mappings().one()
        scans = c.execute(text("""SELECT COUNT(*) AS scans_24h,
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS successful_24h,
            SUM(CASE WHEN status NOT IN ('completed','running') THEN 1 ELSE 0 END) AS failed_24h
            FROM scans WHERE started_at >= UTC_TIMESTAMP() - INTERVAL 24 HOUR""")).mappings().one()
    return {**dict(row), **dict(incidents), **dict(scans)}


@app.get("/api/dashboard/servers")
def dashboard_servers_api(request: Request, limit: int = 100):
    dashboard_auth(request)
    limit = max(1, min(limit, 5000))
    with engine.connect() as c:
        rows = c.execute(text(f"""SELECT s.id,s.agent_id,s.hostname,s.site_url,s.agent_version,s.lmd_version,s.last_seen_at,
            (SELECT MAX(sc.started_at) FROM scans sc WHERE sc.server_id=s.id) AS last_scan_at,
            (SELECT COUNT(*) FROM incidents i WHERE i.server_id=s.id AND i.status <> 'resolved') AS open_incidents
            FROM servers s ORDER BY (s.last_seen_at IS NULL), s.last_seen_at DESC LIMIT {limit}""")).mappings().all()
    return {"servers": [dict(r) for r in rows]}


@app.get("/api/dashboard/incidents")
def dashboard_incidents_api(request: Request, status: str = "open", limit: int = 100):
    dashboard_auth(request)
    limit = max(1, min(limit, 500))
    if status not in {"open", "resolved", "all"}:
        raise HTTPException(400, "invalid status")
    with engine.connect() as c:
        where = "" if status == "all" else "WHERE i.status=:status"
        params = {} if status == "all" else {"status": status}
        rows = c.execute(text(f"""SELECT i.id,i.site_url,i.severity,i.status,i.first_seen_at,i.last_seen_at,
            s.id AS server_id,s.hostname,s.agent_id,COUNT(f.id) AS finding_count
            FROM incidents i JOIN servers s ON s.id=i.server_id LEFT JOIN findings f ON f.incident_id=i.id
            {where} GROUP BY i.id ORDER BY i.last_seen_at DESC LIMIT {limit}"""), params).mappings().all()
    return {"incidents": [dict(r) for r in rows]}


BASE_CSS = """
:root{color-scheme:dark;--bg:#0b1020;--panel:#111827;--muted:#94a3b8;--text:#e5e7eb;--line:#263244;--good:#34d399;--bad:#fb7185;--warn:#fbbf24;--accent:#60a5fa}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}header{padding:22px 28px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}main{padding:24px 28px;max-width:1500px;margin:auto}h1{font-size:21px;margin:0 0 4px}.muted{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:14px;margin-bottom:22px}.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px}.card{padding:18px}.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.value{font-size:29px;font-weight:700;margin-top:7px}.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.panel{padding:18px;margin-bottom:18px}.panel h2{font-size:15px;margin:0 0 14px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-top:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-size:12px;font-weight:500}.pill{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:600}.pill.good{background:#063d30}.pill.bad{background:#4a1521}.pill.warn{background:#4a3608}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}.empty{padding:22px;text-align:center;color:var(--muted)}.back{display:inline-block;margin-bottom:16px}@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:16px}header{padding:18px}.panel{overflow:auto}}
"""

MAIN_HTML = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WordPress Malware Monitor</title><style>{BASE_CSS}</style></head><body>
<header><div><h1>WordPress Malware Monitor</h1><div class="muted">Fleet security overview</div></div><div class="muted" id="updated">Loading…</div></header><main>
<section class="cards"><div class="card"><div class="label">Servers</div><div class="value" id="total">—</div></div><div class="card"><div class="label">Online</div><div class="value good" id="online">—</div></div><div class="card"><div class="label">Open incidents</div><div class="value bad" id="incidents">—</div></div><div class="card"><div class="label">Critical incidents</div><div class="value bad" id="critical">—</div></div></section>
<section class="panel"><h2>Scanner health — last 24 hours</h2><div id="health" class="muted">Loading…</div></section>
<section class="panel"><h2>Open incidents</h2><div id="incidentsTable">Loading…</div></section>
<section class="panel"><h2>Servers</h2><div id="serversTable">Loading…</div></section></main>
<script>const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const t=v=>v?new Date(v+'Z').toLocaleString():'Never';async function get(u){{const r=await fetch(u);if(!r.ok)throw Error(await r.text());return r.json()}}async function refresh(){{try{{const[s,i,sv]=await Promise.all([get('/api/dashboard/summary'),get('/api/dashboard/incidents?status=open'),get('/api/dashboard/servers')]);document.querySelector('#total').textContent=s.total_servers??0;document.querySelector('#online').textContent=s.online_servers??0;document.querySelector('#incidents').textContent=s.open_incidents??0;document.querySelector('#critical').textContent=s.critical_incidents??0;document.querySelector('#health').textContent=`${{s.successful_24h??0}} successful / ${{s.failed_24h??0}} failed / ${{s.scans_24h??0}} total scans`;document.querySelector('#updated').textContent='Updated '+new Date().toLocaleTimeString();document.querySelector('#incidentsTable').innerHTML=i.incidents.length?`<table><thead><tr><th>Site</th><th>Severity</th><th>Findings</th><th>Last seen</th><th>Server</th></tr></thead><tbody>${{i.incidents.map(x=>`<tr><td><a href="/dashboard/incidents/${{x.id}}">${{esc(x.site_url||'unknown')}}</a></td><td><span class="pill bad">${{esc(x.severity)}}</span></td><td>${{x.finding_count}}</td><td>${{t(x.last_seen_at)}}</td><td><a href="/dashboard/servers/${{x.server_id}}">${{esc(x.hostname)}}</a></td></tr>`).join('')}}</tbody></table>`:'<div class="empty">No open malware incidents.</div>';document.querySelector('#serversTable').innerHTML=sv.servers.length?`<table><thead><tr><th>Site</th><th>Host</th><th>Heartbeat</th><th>Last scan</th><th>LMD</th><th>Incidents</th></tr></thead><tbody>${{sv.servers.map(x=>{{const stale=!x.last_seen_at||Date.now()-new Date(x.last_seen_at+'Z').getTime()>900000;return `<tr><td><a href="/dashboard/servers/${{x.id}}">${{esc(x.site_url||'unknown')}}</a></td><td>${{esc(x.hostname)}}</td><td><span class="pill ${{stale?'warn':'good'}}">${{stale?'STALE':'ONLINE'}}</span><br>${{t(x.last_seen_at)}}</td><td>${{t(x.last_scan_at)}}</td><td>${{esc(x.lmd_version||'unknown')}}</td><td>${{x.open_incidents}}</td></tr>`}}).join('')}}</tbody></table>`:'<div class="empty">No servers registered yet.</div>'}}catch(e){{document.querySelector('#updated').textContent='Dashboard error';console.error(e)}}}}refresh();setInterval(refresh,30000);</script></body></html>'''

DETAIL_HTML = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WordPress Malware Monitor</title><style>{BASE_CSS}.code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all;font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><header><div><h1 id="title">Loading…</h1><div class="muted" id="subtitle"></div></div><div><a href="/dashboard">← Dashboard</a></div></header><main><div id="content">Loading…</div></main>
<script>const kind='__KIND__',id='__ID__';const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const t=v=>v?new Date(v+'Z').toLocaleString():'Never';async function get(u){{const r=await fetch(u);if(!r.ok)throw Error(await r.text());return r.json()}}function pill(s){{const cls=s==='critical'||s==='high'?'bad':s==='resolved'||s==='completed'?'good':'warn';return `<span class="pill ${{cls}}">${{esc(s)}}</span>`}}async function load(){{const d=await get(`/api/dashboard/${{kind}}s/${{id}}`);if(kind==='incident'){{const x=d.incident;document.title=`Incident #${{x.id}}`;document.querySelector('#title').textContent=`Incident #${{x.id}} — ${{x.site_url||'unknown'}}`;document.querySelector('#subtitle').textContent=`${{x.hostname}} · ${{x.agent_id}}`;document.querySelector('#content').innerHTML=`<section class="cards"><div class="card"><div class="label">Severity</div><div class="value">${{pill(x.severity)}}</div></div><div class="card"><div class="label">Status</div><div class="value">${{pill(x.status)}}</div></div><div class="card"><div class="label">Findings</div><div class="value">${{d.findings.length}}</div></div><div class="card"><div class="label">First seen</div><div class="value" style="font-size:16px">${{t(x.first_seen_at)}}</div></div></section><section class="panel"><h2>Incident details</h2><div class="grid"><div><b>Last seen</b><br>${{t(x.last_seen_at)}}</div><div><b>Fingerprint</b><br><span class="code">${{esc(x.fingerprint)}}</span></div><div><b>Host heartbeat</b><br>${{t(x.heartbeat_at)}}</div></div></section><section class="panel"><h2>Detected files</h2>${{d.findings.length?`<table><thead><tr><th>Path</th><th>Signature</th><th>Type</th><th>SHA-256</th><th>First seen</th></tr></thead><tbody>${{d.findings.map(f=>`<tr><td class="code">${{esc(f.path)}}</td><td>${{esc(f.signature||'')}}</td><td>${{esc(f.detection_type||'')}}</td><td class="code">${{esc(f.sha256||'')}}</td><td>${{t(f.first_seen_at)}}</td></tr>`).join('')}}</tbody></table>`:'<div class="empty">No file findings recorded.</div>'}}</section><section class="panel"><h2>Detection events</h2>${{d.events.length?`<table><thead><tr><th>Time</th><th>Scanner</th><th>Event</th><th>Severity</th><th>Fingerprint</th></tr></thead><tbody>${{d.events.map(e=>`<tr><td>${{t(e.occurred_at)}}</td><td>${{esc(e.scanner)}}</td><td>${{esc(e.event_type)}}</td><td>${{pill(e.severity)}}</td><td class="code">${{esc(e.fingerprint||'')}}</td></tr>`).join('')}}</tbody></table>`:'<div class="empty">No events.</div>'}}</section>`}}else{{const x=d.server;document.title=x.site_url||x.hostname;document.querySelector('#title').textContent=x.site_url||x.hostname;document.querySelector('#subtitle').textContent=x.hostname+' · '+x.agent_id;document.querySelector('#content').innerHTML=`<section class="cards"><div class="card"><div class="label">Heartbeat</div><div class="value">${{pill(!x.last_seen_at||Date.now()-new Date(x.last_seen_at+'Z').getTime()>900000?'stale':'online')}}</div></div><div class="card"><div class="label">LMD</div><div class="value" style="font-size:18px">${{esc(x.lmd_version||'unknown')}}</div></div><div class="card"><div class="label">Agent</div><div class="value" style="font-size:18px">${{esc(x.agent_version||'unknown')}}</div></div><div class="card"><div class="label">Last heartbeat</div><div class="value" style="font-size:16px">${{t(x.last_seen_at)}}</div></div></section><section class="panel"><h2>Incidents</h2>${{d.incidents.length?`<table><thead><tr><th>Site</th><th>Severity</th><th>Status</th><th>Findings</th><th>Last seen</th></tr></thead><tbody>${{d.incidents.map(i=>`<tr><td><a href="/dashboard/incidents/${{i.id}}">${{esc(i.site_url||'unknown')}}</a></td><td>${{pill(i.severity)}}</td><td>${{pill(i.status)}}</td><td>${{i.finding_count}}</td><td>${{t(i.last_seen_at)}}</td></tr>`).join('')}}</tbody></table>`:'<div class="empty">No incidents.</div>'}}</section><section class="panel"><h2>Scan history</h2>${{d.scans.length?`<table><thead><tr><th>Started</th><th>Scanner</th><th>Type</th><th>Status</th><th>Files</th><th>Detections</th></tr></thead><tbody>${{d.scans.map(s=>`<tr><td>${{t(s.started_at)}}</td><td>${{esc(s.scanner)}}</td><td>${{esc(s.scan_type)}}</td><td>${{pill(s.status)}}</td><td>${{s.files_scanned??0}}</td><td>${{s.detections??0}}</td></tr>`).join('')}}</tbody></table>`:'<div class="empty">No scan records.</div>'}}</section><section class="panel"><h2>Recent events</h2>${{d.events.length?`<table><thead><tr><th>Time</th><th>Scanner</th><th>Event</th><th>Severity</th></tr></thead><tbody>${{d.events.map(e=>`<tr><td>${{t(e.occurred_at)}}</td><td>${{esc(e.scanner)}}</td><td>${{esc(e.event_type)}}</td><td>${{pill(e.severity)}}</td></tr>`).join('')}}</tbody></table>`:'<div class="empty">No events.</div>'}}</section>`}}}}load().catch(e=>document.querySelector('#content').innerHTML=`<div class="panel">Unable to load details: ${{esc(e.message)}}</div>`);</script></body></html>'''
