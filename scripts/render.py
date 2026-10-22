#!/usr/bin/env python3
"""Build the Kubernetes List from the reviewed image lock."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
images=json.loads((root/'config/images.json').read_text())
items=[dict(apiVersion='v1',kind='Namespace',metadata={'name':'mimir-lab'})]

def workload(name,image,args,port,config=None,data=False,uid=65534,env=None,extra_volumes=None,extra_mounts=None):
 volumes=[];mounts=[]
 if config:
  volumes.append({'name':'config','configMap':{'name':config}});mounts.append({'name':'config','mountPath':'/etc/lab','readOnly':True})
 if data:
  items.append({'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':name+'-data'},'spec':{'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':'2Gi'}}}})
  volumes.append({'name':'data','persistentVolumeClaim':{'claimName':name+'-data'}});mounts.append({'name':'data','mountPath':'/data'})
 volumes.extend(extra_volumes or []);mounts.extend(extra_mounts or [])
 c={'name':name,'image':images[image]['pinned'],'args':args,'ports':[{'containerPort':port}],'volumeMounts':mounts,'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'1Gi' if name=='mimir' else '512Mi'}},'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}}}
 if name=='mimir':c['workingDir']='/data'
 if env:c['env']=env
 path='/ready' if name=='mimir' else ('/-/ready' if name.startswith('prometheus') else ('/api/health' if name=='grafana' else '/'))
 c['readinessProbe']={'httpGet':{'path':path,'port':port},'periodSeconds':3,'failureThreshold':30}
 c['startupProbe']={'httpGet':{'path':path,'port':port},'periodSeconds':3,'failureThreshold':60}
 items.append({'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':name},'spec':{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':name}},'template':{'metadata':{'labels':{'app':name}},'spec':{'automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'runAsGroup':uid,'fsGroup':uid,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[c],'volumes':volumes}}}})
 items.append({'apiVersion':'v1','kind':'Service','metadata':{'name':name},'spec':{'selector':{'app':name},'ports':[{'port':port,'targetPort':port}]}})

workload('mimir','mimir',['-config.file=/etc/lab/mimir.yaml','-activity-tracker.filepath=/data/metrics-activity.log'],9009,'mimir-config',True,10001)
for tenant in ('a','b'):workload('prometheus-'+tenant,'prometheus',['--config.file=/etc/lab/prometheus.yaml','--storage.tsdb.path=/data','--storage.tsdb.retention.time=2h'],9090,'prometheus-'+tenant+'-config',True)
workload('blackbox','blackbox',['--config.file=/etc/lab/blackbox.yaml'],9115,'blackbox-config')
volumes=[{'name':'datasources','configMap':{'name':'grafana-datasources'}},{'name':'providers','configMap':{'name':'grafana-providers'}},{'name':'dashboard','configMap':{'name':'grafana-dashboard'}}]
mounts=[{'name':'datasources','mountPath':'/etc/grafana/provisioning/datasources','readOnly':True},{'name':'providers','mountPath':'/etc/grafana/provisioning/dashboards','readOnly':True},{'name':'dashboard','mountPath':'/var/lib/grafana/dashboards','readOnly':True}]
env=[{'name':'GF_PATHS_DATA','value':'/data'},{'name':'GF_SECURITY_ADMIN_PASSWORD','valueFrom':{'secretKeyRef':{'name':'grafana-admin','key':'password'}}},{'name':'GF_ANALYTICS_REPORTING_ENABLED','value':'false'},{'name':'GF_ANALYTICS_CHECK_FOR_UPDATES','value':'false'}]
workload('grafana','grafana',[],3000,data=True,uid=472,env=env,extra_volumes=volumes,extra_mounts=mounts)
(root/'manifests/stack.json').write_text(json.dumps({'apiVersion':'v1','kind':'List','items':items},indent=2)+'\n')
