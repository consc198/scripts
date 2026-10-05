#!/usr/bin/env python3
import argparse, json, socket, subprocess, sys, time, urllib.request, hashlib
from datetime import datetime, timezone
from pathlib import Path

CONFIG=Path('/etc/security-monitor/agent.json')
QUEUE=Path('/var/lib/wp-malware-monitor/queue')
AGENT_VERSION='0.3'

def load():
    return json.loads(CONFIG.read_text())

def canonical(obj):
    return json.dumps(obj,separators=(',',':'),sort_keys=True).encode()

def post(cfg,path,payload):
    body=canonical(payload)
    req=urllib.request.Request(
        cfg['api_url'].rstrip('/')+path,
        data=body,
        method='POST',
        headers={
            'Content-Type':'application/json',
            'Authorization':'Bearer '+cfg['token'],
            'User-Agent':f'wp-malware-monitor-agent/{AGENT_VERSION}'
        })
    with urllib.request.urlopen(req,timeout=15) as r:
        return r.status

def enqueue(cfg,path,payload):
    QUEUE.mkdir(parents=True,exist_ok=True)
    item={'path':path,'payload':payload}
    name=f"{int(time.time()*1000)}-{hashlib.sha256(canonical(item)).hexdigest()[:16]}.json"
    (QUEUE/name).write_bytes(canonical(item))

def flush(cfg):
    if not QUEUE.exists(): return
    for f in sorted(QUEUE.iterdir())[:100]:
        try:
            item=json.loads(f.read_text())
            post(cfg,item['path'],item['payload'])
            f.unlink()
        except Exception:
            break

def lmd_version():
    try: return subprocess.check_output(['maldet','--version'],text=True,stderr=subprocess.STDOUT,timeout=10).strip()
    except Exception: return None

def heartbeat(cfg):
    p={'agent_id':cfg['agent_id'],'hostname':socket.gethostname(),'site_url':cfg.get('site_url'),'agent_version':AGENT_VERSION,'lmd_version':lmd_version()}
    try: post(cfg,'/v1/heartbeat',p)
    except Exception: enqueue(cfg,'/v1/heartbeat',p)

def emit_findings(cfg,findings,source='scan'):
    normalized=[{'path':h.get('path') or h.get('file') or '','sha256':h.get('sha256'),'signature':h.get('signature') or h.get('sig'),'detection_type':h.get('type') or h.get('engine')} for h in findings]
    if not normalized: return
    fp=hashlib.sha256(canonical({'site':cfg.get('site_url'),'findings':normalized})).hexdigest()
    p={'agent_id':cfg['agent_id'],'hostname':socket.gethostname(),'site_url':cfg.get('site_url'),'scanner':'lmd','event_type':'malware_detected','severity':'critical','fingerprint':fp,'occurred_at':datetime.now(timezone.utc).isoformat(),'payload':{'source':source,'findings':normalized},'agent_version':AGENT_VERSION,'lmd_version':lmd_version()}
    try: post(cfg,'/v1/events',p)
    except Exception: enqueue(cfg,'/v1/events',p)

def scan(cfg):
    try:
        subprocess.check_output(['maldet','-a',cfg['site_root']],text=True,stderr=subprocess.STDOUT,timeout=cfg.get('full_scan_timeout',3600))
        report=json.loads(subprocess.check_output(['maldet','--json-report','newest'],text=True,stderr=subprocess.STDOUT,timeout=60))
        hits=[]
        for r in report.get('reports',[]) if isinstance(report,dict) else []: hits.extend(r.get('hits',[]) if isinstance(r,dict) else [])
        emit_findings(cfg,hits,'scheduled_scan')
    except Exception as exc: send_error(cfg,str(exc))

def hook(cfg):
    try:
        data=json.load(sys.stdin); hits=[]
        for r in data.get('reports',[]) if isinstance(data,dict) else []: hits.extend(r.get('hits',[]) if isinstance(r,dict) else [])
        emit_findings(cfg,hits,'lmd_post_scan_hook')
    except Exception as exc: send_error(cfg,str(exc))

def send_error(cfg,error):
    p={'agent_id':cfg['agent_id'],'hostname':socket.gethostname(),'site_url':cfg.get('site_url'),'scanner':'lmd','event_type':'scan_error','severity':'high','occurred_at':datetime.now(timezone.utc).isoformat(),'payload':{'error':error},'agent_version':AGENT_VERSION,'lmd_version':lmd_version()}
    try: post(cfg,'/v1/events',p)
    except Exception: enqueue(cfg,'/v1/events',p)

def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['heartbeat','scan','hook','run']); args=p.parse_args(); cfg=load(); QUEUE.mkdir(parents=True,exist_ok=True); flush(cfg)
    if args.mode=='heartbeat': heartbeat(cfg)
    elif args.mode=='scan': scan(cfg)
    elif args.mode=='hook': hook(cfg)
    else: heartbeat(cfg); scan(cfg)
    flush(cfg)

if __name__=='__main__': main()
