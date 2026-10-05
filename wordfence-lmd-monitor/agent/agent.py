#!/usr/bin/env python3
import argparse, hashlib, hmac, json, socket, subprocess, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path('/etc/wp-malware-monitor/agent.json')
QUEUE = Path('/var/lib/wp-malware-monitor/queue')

def load(): return json.loads(CONFIG.read_text())
def canonical(obj): return json.dumps(obj, separators=(',', ':'), sort_keys=True).encode()

def post(cfg, path, payload):
    body = canonical(payload)
    sig = hmac.new(cfg['secret'].encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(cfg['api_url'].rstrip('/') + path, data=body, method='POST', headers={'Content-Type':'application/json','X-Signature':sig,'User-Agent':'wp-malware-monitor-agent/0.1'})
    with urllib.request.urlopen(req, timeout=15) as r: return r.status

def enqueue(cfg, path, payload):
    QUEUE.mkdir(parents=True, exist_ok=True)
    item={'path':path,'payload':payload}
    name=f"{int(time.time()*1000)}-{hashlib.sha256(canonical(item)).hexdigest()[:16]}.json"
    (QUEUE/name).write_bytes(canonical(item))

def flush(cfg):
    if not QUEUE.exists(): return
    for f in sorted(QUEUE.iterdir())[:100]:
        try:
            item=json.loads(f.read_text()); post(cfg,item['path'],item['payload']); f.unlink()
        except Exception: break

def lmd_version():
    try: return subprocess.check_output(['maldet','--version'],text=True,stderr=subprocess.STDOUT,timeout=10).strip()
    except Exception: return None

def heartbeat(cfg):
    payload={'agent_id':cfg['agent_id'],'hostname':socket.gethostname(),'site_url':cfg.get('site_url'),'agent_version':'0.1','lmd_version':lmd_version()}
    try: post(cfg,'/v1/heartbeat',payload)
    except Exception: enqueue(cfg,'/v1/heartbeat',payload)

def scan(cfg):
    root=cfg['site_root']
    try:
        subprocess.check_output(['maldet','-a',root],text=True,stderr=subprocess.STDOUT,timeout=cfg.get('full_scan_timeout',3600))
        raw=subprocess.check_output(['maldet','--json-report','newest'],text=True,stderr=subprocess.STDOUT,timeout=60)
        report=json.loads(raw)
        hits=[]
        for r in report.get('reports',[]) if isinstance(report,dict) else []:
            hits.extend(r.get('hits',[]) if isinstance(r,dict) else [])
        if not hits: return
        normalized=[{'path':h.get('path') or h.get('file') or '','sha256':h.get('sha256'),'signature':h.get('signature') or h.get('sig'),'detection_type':h.get('type') or h.get('engine')} for h in hits]
        fp=hashlib.sha256(canonical({'site':cfg.get('site_url'),'findings':normalized})).hexdigest()
        payload={'agent_id':cfg['agent_id'],'hostname':socket.gethostname(),'site_url':cfg.get('site_url'),'scanner':'lmd','event_type':'malware_detected','severity':'critical','fingerprint':fp,'occurred_at':datetime.now(timezone.utc).isoformat(),'payload':{'findings':normalized},'agent_version':'0.1','lmd_version':lmd_version()}
        try: post(cfg,'/v1/events',payload)
        except Exception: enqueue(cfg,'/v1/events',payload)
    except Exception as exc:
        payload={'agent_id':cfg['agent_id'],'hostname':socket.gethostname(),'site_url':cfg.get('site_url'),'scanner':'lmd','event_type':'scan_error','severity':'high','occurred_at':datetime.now(timezone.utc).isoformat(),'payload':{'error':str(exc)},'agent_version':'0.1','lmd_version':lmd_version()}
        try: post(cfg,'/v1/events',payload)
        except Exception: enqueue(cfg,'/v1/events',payload)

def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['heartbeat','scan','run']); args=p.parse_args()
    cfg=load(); QUEUE.mkdir(parents=True,exist_ok=True); flush(cfg)
    if args.mode in ('heartbeat','run'): heartbeat(cfg)
    if args.mode in ('scan','run'): scan(cfg)
    flush(cfg)

if __name__=='__main__': main()
