#!/usr/bin/env python3
"""Live ALB, ExternalDNS and cert-manager test; cleans up only its unique test resources."""
import json, os, subprocess, time, urllib.request, uuid
from pathlib import Path
import yaml
from config import load_config
from target import cloud_environment
from dns_records import records_for_test
root = Path(__file__).resolve().parents[1]
c = load_config(os.environ.get('IAC_CONFIG', root / 'config.yaml'))
if c['global']['provider'] != 'aws':
    raise SystemExit('This smoke test requires AWS')
_cloud_env = cloud_environment(c)
for _key in list(os.environ):
    if _key not in _cloud_env:
        del os.environ[_key]
os.environ.update(_cloud_env)
os.environ.setdefault('KUBECONFIG', str(root / 'kubeconfig.yaml'))
name = 'iac-smoke-' + uuid.uuid4().hex[:10]
hostname = name + '.' + c['network']['domain']
zone = c['network']['hosted_zone_id']

def aws(*args):
    return json.loads(subprocess.check_output(['aws', *args, '--region', c['aws']['region'], '--output', 'json'], text=True))

def kube(*args, input=None):
    return subprocess.check_output(['kubectl', *args], input=input, text=True)

def records(include_ownership=False):
    return records_for_test(aws, zone, hostname, include_ownership)

def wait_for(fn, description, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = fn()
            if result:
                print('PASS', description, flush=True)
                return result
        except (urllib.error.URLError, subprocess.CalledProcessError, KeyError, IndexError):
            pass
        time.sleep(10)
    raise RuntimeError('Timed out: ' + description)

assert all(c['umbrella'][key] for key in ['aws_load_balancer_controller','external_dns','cert_manager']), 'Enable the three tested controllers'
assert c['eks']['admin_cidrs'], 'The HTTP test needs a trusted public client CIDR'
assert not records(include_ownership=True), 'Refusing to use an existing DNS record'
metadata = {'name':name, 'namespace':name}
objects = [
    {'apiVersion':'v1','kind':'Namespace','metadata':{'name':name}},
    {'apiVersion':'apps/v1','kind':'Deployment','metadata':metadata,'spec':{
        'replicas':1,'selector':{'matchLabels':{'app':name}},'template':{'metadata':{'labels':{'app':name}},'spec':{
            'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'seccompProfile':{'type':'RuntimeDefault'}},
            'containers':[{'name':'echo','image':'hashicorp/http-echo:1.0.0','args':['-listen=:8080','-text=iac-smoke-ok'],
                'ports':[{'containerPort':8080}], 'readinessProbe':{'httpGet':{'path':'/','port':8080}},
                'resources':{'requests':{'cpu':'10m','memory':'16Mi'},'limits':{'cpu':'100m','memory':'32Mi'}},
                'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}}]
        }}
    }},
    {'apiVersion':'v1','kind':'Service','metadata':metadata,'spec':{'selector':{'app':name},'ports':[{'port':80,'targetPort':8080}]}},
    {'apiVersion':'networking.k8s.io/v1','kind':'Ingress','metadata':dict(metadata, annotations={
        'alb.ingress.kubernetes.io/scheme':'internet-facing','alb.ingress.kubernetes.io/target-type':'ip',
        'alb.ingress.kubernetes.io/inbound-cidrs':','.join(c['eks']['admin_cidrs'])
    }), 'spec':{'ingressClassName':'alb','rules':[{'host':hostname,'http':{'paths':[{'path':'/','pathType':'Prefix','backend':{'service':{'name':name,'port':{'number':80}}}}]}}]}},
    {'apiVersion':'cert-manager.io/v1','kind':'Issuer','metadata':metadata,'spec':{'selfSigned':{}}},
    {'apiVersion':'cert-manager.io/v1','kind':'Certificate','metadata':metadata,'spec':{'secretName':name,'dnsNames':[hostname],'issuerRef':{'name':name,'kind':'Issuer'}}}
]
try:
    kube('apply','-f','-',input=yaml.safe_dump_all(objects))
    kube('wait','-n',name,'deployment/'+name,'--for=condition=Available','--timeout=180s')
    kube('wait','-n',name,'certificate/'+name,'--for=condition=Ready','--timeout=180s')
    print('PASS cert-manager certificate issuance (self-signed)', flush=True)
    def ingress_address():
        i=json.loads(kube('get','ingress',name,'-n',name,'-o','json'))
        return i.get('status',{}).get('loadBalancer',{}).get('ingress',[{}])[0].get('hostname')
    address=wait_for(ingress_address,'ALB provisioned')
    wait_for(lambda: any(r['Type']=='A' and r.get('AliasTarget',{}).get('DNSName','').rstrip('.').removeprefix('dualstack.') == address for r in records()),'ExternalDNS Route53 alias')
    def echo():
        req=urllib.request.Request('http://'+address,headers={'Host':hostname})
        with urllib.request.urlopen(req,timeout=10) as response:
            return response.status==200 and response.read().strip()==b'iac-smoke-ok'
    wait_for(echo,'HTTP through ALB to pod')
finally:
    # Deleting the namespace waits for the ALB controller finalizer before DNS cleanup.
    kube('delete','namespace',name,'--ignore-not-found','--wait=true','--timeout=300s')
    owned=records(include_ownership=True)
    if owned:
        aws('route53','change-resource-record-sets','--hosted-zone-id',zone,'--change-batch',json.dumps({'Changes':[{'Action':'DELETE','ResourceRecordSet':r} for r in owned]}))
    print('Cleaned test namespace, ALB and exact test DNS records', flush=True)
