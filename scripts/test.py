#!/usr/bin/env python3
"""Real bounded drills; restore replicas and retain failed reports."""
import base64
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib
import json
import re
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
checks=[]
FORWARDS={}
report={'started_at':datetime.now(timezone.utc).isoformat(),'status':'failed','checks':checks,'findings':[]}

def k(*args):
 return subprocess.check_output(['bash',str(ROOT/'scripts/k.sh'),*args],text=True)

def query(port,expr,tenant=None,grafana_uid=None):
 path=('/api/datasources/proxy/uid/'+grafana_uid if grafana_uid else '/prometheus')+'/api/v1/query'
 if port==8027:path='/api/v1/query'
 headers={}
 if tenant:headers['X-Scope-OrgID']=tenant
 if grafana_uid:headers['Authorization']='Basic '+base64.b64encode(('admin:'+(ROOT/'.local/grafana-password').read_text()).encode()).decode()
 url=f'http://127.0.0.1:{port}{path}?'+urllib.parse.urlencode({'query':expr})
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=6) as response:
  data=json.load(response)
 if data.get('status')!='success':raise RuntimeError('Query failed: '+str(data))
 return data['data']['result']

def wait(label,fn,timeout=150):
 end=time.monotonic()+timeout;last=None
 while time.monotonic()<end:
  try:
   value=fn()
   if value:
    checks.append({'check':label,'status':'passed','evidence':value});return value
   last='Condition not yet true'
  except (OSError,ValueError,RuntimeError) as exc:last=repr(exc)
  time.sleep(3)
 raise AssertionError(label+': '+str(last))

def scale(name,count,namespace='mimir-lab'):
 k('-n',namespace,'scale','deployment/'+name,'--replicas='+str(count))
 # Scaling to zero must wait for termination before interpreting historical queries.
 if count==0:
  end=time.monotonic()+90
  while time.monotonic()<end:
   pods=json.loads(k('-n',namespace,'get','pods','-l','app='+name,'-o','json'))['items']
   if not pods:return
   time.sleep(2)
  raise TimeoutError('Pods did not terminate: '+name)
 else:k('-n',namespace,'rollout','status','deployment/'+name,'--timeout=180s')

def forward(stack,name,port):
 old=FORWARDS.get(name)
 if old is not None and old.poll() is None:old.terminate();old.wait(timeout=10)
 log=(ROOT/'.local'/('forward-'+name+'.log')).open('w');stack.callback(log.close)
 p=subprocess.Popen(['bash',str(ROOT/'scripts/k.sh'),'-n','mimir-lab','port-forward','--address','127.0.0.1','service/'+name,str(port)+':'+str(9009 if name=='mimir' else (3000 if name=='grafana' else 9090))],stdout=log,stderr=log)
 def close():
  if p.poll() is None:p.terminate();p.wait(timeout=10)
 stack.callback(close)
 FORWARDS[name]=p
 return p

try:
 with ExitStack() as stack:
  for name,port in [('mimir',8025),('grafana',8026),('prometheus-a',8027)]:forward(stack,name,port)
  def healthy(tenant):
   samples=query(8025,'probe_success{job="notes-http"}','tenant-'+tenant)
   return samples if len(samples)==2 and all(x['metric'].get('tenant_origin')==tenant and float(x['value'][1])==1 for x in samples) else None
  for tenant in ('a','b'):wait('healthy-tenant-'+tenant,lambda tenant=tenant:healthy(tenant))
  with urllib.request.urlopen('http://127.0.0.1:8025/config',timeout=6) as response:runtime_config=response.read().decode()
  retention=re.search(r'compactor_blocks_retention_period:\s+(\S+)',runtime_config)
  assert retention and retention[1] in ('24h','24h0m0s','1d'),retention[1] if retention else 'retention missing'
  checks.append({'check':'retention-configured-not-expiration-tested','status':'passed','configured_value':retention[1]})
  for tenant,other in [('a','b'),('b','a')]:
   data=query(8025,'probe_success{tenant_origin="'+other+'"}','tenant-'+tenant)
   assert data==[],data
   checks.append({'check':'tenant-'+tenant+'-does-not-contain-'+other,'status':'passed','evidence':data})
  try:query(8025,'up')
  except urllib.error.HTTPError as exc:
   assert exc.code==401,exc.code
   checks.append({'check':'tenant-header-required','status':'passed','http_status':exc.code})
  else:raise AssertionError('Missing tenant header was accepted')
  for tenant in ('a','b'):
   wait('grafana-proxy-tenant-'+tenant,lambda tenant=tenant:query(8026,'probe_success{job="notes-http",tenant_origin="'+tenant+'"}',grafana_uid='mimir-'+tenant))
  # Stop A to prevent its WAL replay from masking loss in Mimir's PVC.
  before=query(8025,'timestamp(probe_success{job="notes-http",endpoint="healthz"})','tenant-a')[0]
  timestamp=float(before['value'][1])
  wait('historical-sample-before-restart',lambda:query(8025,f'probe_success{{job="notes-http",endpoint="healthz"}} @ {timestamp}','tenant-a'))
  scale('prometheus-a',0)
  k('-n','mimir-lab','rollout','restart','deployment/mimir');k('-n','mimir-lab','rollout','status','deployment/mimir','--timeout=180s')
  # Port-forward is attached to a Pod; recreate it after replacement.
  forward(stack,'mimir',8025)
  wait('mimir-pvc-history-with-writer-stopped',lambda:query(8025,f'probe_success{{job="notes-http",endpoint="healthz"}} @ {timestamp}','tenant-a'))
  scale('prometheus-a',1);forward(stack,'prometheus-a',8027)
  wait('writer-a-recovered',lambda:query(8027,'up{job="prometheus"}'))
  scale('notes-api',0,'notes-lab')
  wait('api-outage-arrives-in-mimir',lambda:[x for x in query(8025,'probe_success{job="notes-http"}','tenant-a') if float(x['value'][1])==0])
  scale('notes-api',2,'notes-lab')
  wait('api-recovery-arrives-in-mimir',lambda: len([x for x in query(8025,'probe_success{job="notes-http"}','tenant-a') if float(x['value'][1])==1])==2)
  retry_before=query(8027,'sum(prometheus_remote_storage_samples_retried_total)')
  retry_before=float(retry_before[0]['value'][1]) if retry_before else 0
  scale('mimir',0)
  outage_start=time.time();time.sleep(25);outage_end=time.time()
  wait('remote-write-retried-during-outage',lambda:[x for x in query(8027,'sum(prometheus_remote_storage_samples_retried_total)') if float(x['value'][1])>retry_before],timeout=60)
  scale('mimir',1);forward(stack,'mimir',8025)
  # A count_over_time range wholly inside the outage counts raw samples, not lookback repeats.
  end=outage_end-2
  expr=f'count_over_time(probe_success{{job="notes-http",endpoint="healthz"}}[20s] @ {end})'
  wait('remote-write-backfilled-outage-window',lambda:[x for x in query(8025,expr,'tenant-a') if float(x['value'][1])>=3])
  report['remote_write_outage']={'start_epoch':outage_start,'end_epoch':outage_end,'query':expr}
  report['status']='passed'
except Exception as exc:
 report['findings'].append({'error':repr(exc)})
finally:
 cleanup=[]
 for namespace,name,count in [('notes-lab','notes-api',2),('mimir-lab','mimir',1),('mimir-lab','prometheus-a',1)]:
  try:scale(name,count,namespace);cleanup.append({'deployment':name,'restored_replicas':count})
  except Exception as exc:cleanup.append({'deployment':name,'error':repr(exc)});report['status']='failed'
 report['cleanup']=cleanup
 report['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for directory in ('config','scripts','manifests') for p in (ROOT/directory).glob('*') if p.is_file()}
 report['images']=json.loads((ROOT/'config/images.json').read_text())
 report['finished_at']=datetime.now(timezone.utc).isoformat()
 destination=ROOT/'evidence'/('test-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
 destination.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'passed_checks':len(checks),'findings':report['findings'],'report':str(destination)},indent=2))
raise SystemExit(0 if report['status']=='passed' else 1)
