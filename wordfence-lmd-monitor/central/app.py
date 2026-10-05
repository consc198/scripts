import hashlib, hmac, json, os, smtplib, urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

DATABASE_URL=os.environ['DATABASE_URL']; APP_SECRET=os.environ['APP_SECRET'].encode(); engine=create_engine(DATABASE_URL,pool_pre_ping=True,pool_recycle=1800)
app=FastAPI(title='WordPress Malware Monitor',version='0.1.0')

class Event(BaseModel):
    agent_id:str=Field(min_length=1,max_length=64); hostname:str=Field(min_length=1,max_length=255); site_url:str|None=None
    scanner:str='lmd'; event_type:str; severity:str='info'; fingerprint:str|None=None; occurred_at:datetime
    payload:dict[str,Any]={}; agent_version:str|None=None; lmd_version:str|None=None
class Heartbeat(BaseModel):
    agent_id:str; hostname:str; site_url:str|None=None; agent_version:str|None=None; lmd_version:str|None=None

def verify(raw:bytes, signature:str|None):
    if not signature: raise HTTPException(401,'missing signature')
    expected=hmac.new(APP_SECRET,raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature): raise HTTPException(401,'invalid signature')

def upsert_server(conn,b):
    conn.execute(text('''INSERT INTO servers(agent_id,hostname,site_url,agent_version,lmd_version,last_seen_at) VALUES(:a,:h,:u,:av,:lv,UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE hostname=VALUES(hostname),site_url=VALUES(site_url),agent_version=VALUES(agent_version),lmd_version=VALUES(lmd_version),last_seen_at=UTC_TIMESTAMP()'''),{'a':b.agent_id,'h':b.hostname,'u':b.site_url,'av':b.agent_version,'lv':b.lmd_version})
    return conn.execute(text('SELECT id FROM servers WHERE agent_id=:a'),{'a':b.agent_id}).scalar_one()

def notify(site,hostname,incident_id,findings):
    text_body=f"MALWARE DETECTED\nSite: {site or 'unknown'}\nHost: {hostname}\nIncident: {incident_id}\nFindings: {len(findings)}\n"+'\n'.join(f"- {x.get('path','')} [{x.get('signature') or 'unknown'}]" for x in findings[:20])
    webhook=os.getenv('SLACK_WEBHOOK_URL')
    if webhook:
        try:
            req=urllib.request.Request(webhook,data=json.dumps({'text':text_body}).encode(),headers={'Content-Type':'application/json'},method='POST')
            urllib.request.urlopen(req,timeout=10).read()
        except Exception: pass
    host=os.getenv('SMTP_HOST'); to=os.getenv('ALERT_EMAIL_TO'); sender=os.getenv('SMTP_FROM','malware-monitor@localhost')
    if host and to:
        try:
            msg=EmailMessage(); msg['Subject']=f'🚨 Malware detected: {site or hostname}'; msg['From']=sender; msg['To']=to; msg.set_content(text_body)
            with smtplib.SMTP(host,int(os.getenv('SMTP_PORT','25')),timeout=10) as s:
                if os.getenv('SMTP_TLS','0')=='1': s.starttls()
                if os.getenv('SMTP_USER'): s.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
                s.send_message(msg)
        except Exception: pass

@app.get('/healthz')
def healthz():
    with engine.connect() as c: c.execute(text('SELECT 1'))
    return {'ok':True}

@app.post('/v1/heartbeat')
def heartbeat(body:Heartbeat,x_signature:str|None=Header(default=None)):
    raw=body.model_dump_json().encode(); verify(raw,x_signature)
    with engine.begin() as c: upsert_server(c,body)
    return {'accepted':True}

@app.post('/v1/events')
def event(body:Event,x_signature:str|None=Header(default=None)):
    raw=body.model_dump_json().encode(); verify(raw,x_signature); incident_id=None; new=False; findings=[]
    with engine.begin() as c:
        sid=upsert_server(c,body)
        c.execute(text('''INSERT INTO events(server_id,scanner,event_type,severity,fingerprint,occurred_at,payload) VALUES(:sid,:scanner,:etype,:sev,:fp,:occurred,:payload)'''),{'sid':sid,'scanner':body.scanner,'etype':body.event_type,'sev':body.severity,'fp':body.fingerprint,'occurred':body.occurred_at.replace(tzinfo=None),'payload':json.dumps(body.payload)})
        if body.event_type=='malware_detected' and body.fingerprint:
            findings=body.payload.get('findings',[])
            existing=c.execute(text("SELECT id FROM incidents WHERE server_id=:sid AND fingerprint=:fp AND status <> 'resolved' ORDER BY id DESC LIMIT 1"),{'sid':sid,'fp':body.fingerprint}).scalar()
            if existing:
                incident_id=existing; c.execute(text('UPDATE incidents SET last_seen_at=:t WHERE id=:id'),{'t':body.occurred_at.replace(tzinfo=None),'id':existing})
            else:
                result=c.execute(text('''INSERT INTO incidents(server_id,site_url,severity,fingerprint,first_seen_at,last_seen_at) VALUES(:sid,:url,:sev,:fp,:t,:t)'''),{'sid':sid,'url':body.site_url,'sev':body.severity,'fp':body.fingerprint,'t':body.occurred_at.replace(tzinfo=None)})
                incident_id=result.lastrowid; new=True
            for f in findings:
                c.execute(text('''INSERT INTO findings(incident_id,path,sha256,signature,detection_type,first_seen_at,last_seen_at) VALUES(:iid,:path,:sha,:sig,:dtype,:t,:t)'''),{'iid':incident_id,'path':f.get('path',''),'sha':f.get('sha256'),'sig':f.get('signature'),'dtype':f.get('detection_type'),'t':body.occurred_at.replace(tzinfo=None)})
            if new: c.execute(text('UPDATE incidents SET alert_sent_at=UTC_TIMESTAMP() WHERE id=:id'),{'id':incident_id})
    if new: notify(body.site_url,body.hostname,incident_id,findings)
    return {'accepted':True,'incident_id':incident_id,'new_incident':new}
