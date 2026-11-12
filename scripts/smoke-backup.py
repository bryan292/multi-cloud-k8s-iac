#!/usr/bin/env python3
"""Back up the storage smoke-test volume, restore a volume, and verify its data."""
import json, os, subprocess, sys, time
from pathlib import Path
import yaml
from config import load_config
from target import cloud_environment
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
namespace, original_volume = sys.argv[1:]
if not namespace.startswith('iac-storage-smoke-'):
    raise SystemExit('Only the isolated storage smoke-test namespace is supported')
region, account = c['aws']['region'], c['aws']['account_id']
cluster = f"{c['global']['environment']}-{c['global']['cluster_name']}-cluster"
restored_volume = recovery_point = job = None
pv = namespace + '-restore'

def aws(*args):
    return json.loads(subprocess.check_output(['aws', *args, '--region', region, '--output', 'json'], text=True) or '{}')

def kube(*args, input=None):
    return subprocess.check_output(['kubectl', *args], input=input, text=True)

try:
    info = aws('ec2','describe-volumes','--volume-ids',original_volume)['Volumes'][0]
    job = aws('backup','start-backup-job','--backup-vault-name',cluster+'-volumes',
        '--resource-arn',f'arn:aws:ec2:{region}:{account}:volume/{original_volume}',
        '--iam-role-arn',f'arn:aws:iam::{account}:role/{cluster}-backup')['BackupJobId']
    deadline=time.monotonic()+900
    while True:
        backup=aws('backup','describe-backup-job','--backup-job-id',job)
        if backup['State']=='COMPLETED':
            recovery_point=backup['RecoveryPointArn']
            break
        if backup['State'] in ['FAILED','ABORTED','EXPIRED'] or time.monotonic()>deadline:
            raise RuntimeError(f"Backup failed or timed out: {backup['State']} {backup.get('StatusMessage','')}")
        print('AWS Backup:',backup['State'],flush=True)
        time.sleep(15)
    print('PASS AWS Backup recovery point completed',flush=True)
    snapshot=recovery_point.rsplit('/',1)[-1]
    restored_volume=aws('ec2','create-volume','--snapshot-id',snapshot,'--availability-zone',info['AvailabilityZone'],'--volume-type','gp3','--encrypted')['VolumeId']
    subprocess.run(['aws','ec2','wait','volume-available','--volume-ids',restored_volume,'--region',region],check=True)
    objects=[
      {'apiVersion':'v1','kind':'PersistentVolume','metadata':{'name':pv},'spec':{
        'capacity':{'storage':str(info['Size'])+'Gi'},'accessModes':['ReadWriteOnce'],'persistentVolumeReclaimPolicy':'Retain','storageClassName':'',
        'csi':{'driver':'ebs.csi.aws.com','volumeHandle':restored_volume,'fsType':'ext4'},
        'nodeAffinity':{'required':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'topology.kubernetes.io/zone','operator':'In','values':[info['AvailabilityZone']]}]}]}}
      }},
      {'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':'restore','namespace':namespace},'spec':{
        'accessModes':['ReadWriteOnce'],'storageClassName':'','volumeName':pv,'resources':{'requests':{'storage':str(info['Size'])+'Gi'}}
      }}
    ]
    source=json.loads(kube('get','pod','smoke','-n',namespace,'-o','json'))
    spec=source['spec'];spec.pop('nodeName',None)
    spec['volumes']=[{'name':'data','persistentVolumeClaim':{'claimName':'restore'}}]
    for container in spec['containers']:
        container['volumeMounts']=[{'name':'data','mountPath':'/data'}]
    objects.append({'apiVersion':'v1','kind':'Pod','metadata':{'name':'restore','namespace':namespace},'spec':spec})
    kube('apply','-f','-',input=yaml.safe_dump_all(objects))
    kube('wait','pod/restore','-n',namespace,'--for=condition=Ready','--timeout=300s')
    assert kube('exec','-n',namespace,'restore','--','cat','/data/proof').strip()=='persistence-ok'
    print('PASS data recovered from AWS Backup snapshot into a new EBS volume',flush=True)
finally:
    kube('delete','pod','restore','-n',namespace,'--ignore-not-found','--wait=true','--timeout=120s')
    kube('delete','pvc','restore','-n',namespace,'--ignore-not-found','--wait=true','--timeout=60s')
    kube('delete','pv',pv,'--ignore-not-found','--wait=true','--timeout=60s')
    if restored_volume:
        subprocess.run(['aws','ec2','wait','volume-available','--volume-ids',restored_volume,'--region',region],check=True)
        aws('ec2','delete-volume','--volume-id',restored_volume)
    if recovery_point:
        aws('backup','delete-recovery-point','--backup-vault-name',cluster+'-volumes','--recovery-point-arn',recovery_point)
    elif job:
        state=aws('backup','describe-backup-job','--backup-job-id',job)['State']
        if state in ['CREATED','PENDING','RUNNING']:
            aws('backup','stop-backup-job','--backup-job-id',job)
