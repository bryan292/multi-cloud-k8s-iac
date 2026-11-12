"""Opt-in WID-005 acceptance; retains namespaces/accounts and never emits credentials."""
import argparse, json, subprocess, sys, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.config import load_config
from scripts.operations import Operations
from scripts.target import cloud_environment
from scripts.workload_identity import export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--identity', default='acceptance-reader')
    args = parser.parse_args()
    config_path = args.config
    c = load_config(config_path)
    provider = c['global']['provider']
    o=Operations(ROOT,config_path);env=cloud_environment(c);env['KUBECONFIG']=str(o.target_dir/'kubeconfig.yaml')
    binding=export(c)[args.identity];sa=binding['service_account'];ns=sa['metadata']['namespace'];account=sa['metadata']['name']
    assert len(ns) <= 56, 'Acceptance namespace must leave room for the negative-test suffix'
    report=[]
    def record(check):
     report.append({'provider':provider,'check':check,'passed':True});print(json.dumps(report[-1]),flush=True)
    def command(args,input=None,env_override=None):
     r=subprocess.run(args,input=input,text=True,capture_output=True,env=env_override or env,timeout=90)
     if r.returncode:raise RuntimeError('Command failed: '+args[0]+' '+args[1])
     return r.stdout
    def apply(item):command(['kubectl','apply','-f','-'],json.dumps(item))
    owner={'app.kubernetes.io/managed-by':'iac-workload-acceptance'}
    for namespace in (ns,ns+'-denied'):
     existing=json.loads(command(['kubectl','get','namespace',namespace,'--ignore-not-found','-o','json']) or '{}')
     if existing and existing.get('metadata',{}).get('labels',{}).get('app.kubernetes.io/managed-by')!=owner['app.kubernetes.io/managed-by']:
      raise RuntimeError('Acceptance namespace already exists with another owner')
     apply({'apiVersion':'v1','kind':'Namespace','metadata':{'name':namespace,'labels':owner}})
    apply(sa)
    for namespace,name in [(ns,account+'-denied'),(ns+'-denied',account)]:
     other=json.loads(json.dumps(sa));other['metadata'].update(namespace=namespace,name=name);apply(other)
    pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':'identity-admission-check','namespace':ns,'labels':binding['pod_labels']},'spec':{'serviceAccountName':account,'restartPolicy':'Never','containers':[{'name':'check','image':'registry.k8s.io/pause:3.10','resources':{'requests':{'cpu':'10m','memory':'16Mi'},'limits':{'cpu':'100m','memory':'32Mi'}}}]}}
    mutated=json.loads(command(['kubectl','create','--dry-run=server','-f','-','-o','json'],json.dumps(pod)))
    variables={v['name']:v.get('value') for v in mutated['spec']['containers'][0].get('env',[])}
    expected_var='AWS_WEB_IDENTITY_TOKEN_FILE' if provider=='aws' else 'AZURE_FEDERATED_TOKEN_FILE'
    assert variables.get(expected_var)
    projections=[source['serviceAccountToken'] for volume in mutated['spec'].get('volumes',[]) for source in volume.get('projected',{}).get('sources',[]) if 'serviceAccountToken' in source]
    assert any(p['audience']==binding['audience'] for p in projections)
    assert not any(volume['name'].startswith('kube-api-access') for volume in mutated['spec'].get('volumes',[]))
    record('webhook_projects_cloud_token_without_default_api_token')
    def token(namespace,name,audience):return command(['kubectl','-n',namespace,'create','token',name,'--audience',audience,'--duration','10m']).strip()
    def exchange(jwt):
     if provider=='aws':
      import boto3
      from botocore import UNSIGNED
      from botocore.config import Config
      from botocore.exceptions import ClientError
      client=boto3.client('sts',region_name=c['aws']['region'],config=Config(signature_version=UNSIGNED))
      try:
       return client.assume_role_with_web_identity(RoleArn=sa['metadata']['annotations']['eks.amazonaws.com/role-arn'],RoleSessionName='workload-acceptance',WebIdentityToken=jwt,DurationSeconds=900)['Credentials']
      except ClientError as error:
       if error.response['Error']['Code'] in ('AccessDenied','InvalidIdentityToken'):return None
       raise RuntimeError('Unexpected AWS token exchange failure') from None
     payload=urllib.parse.urlencode({'client_id':sa['metadata']['annotations']['azure.workload.identity/client-id'],'scope':'https://management.azure.com/.default','grant_type':'client_credentials','client_assertion_type':'urn:ietf:params:oauth:client-assertion-type:jwt-bearer','client_assertion':jwt}).encode()
     request=urllib.request.Request('https://login.microsoftonline.com/'+c['azure']['tenant_id']+'/oauth2/v2.0/token',data=payload)
     try:
      with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)['access_token']
     except urllib.error.HTTPError as error:
      body=json.loads(error.read())
      if error.code in (400,401) and set(body.get('error_codes',[])) & {70021,700212,700213,70025}:return None
      raise RuntimeError('Unexpected Azure token exchange failure') from None
    credentials=None
    for attempt in range(12):
     credentials=exchange(token(ns,account,binding['audience']))
     if credentials:break
     time.sleep(10)
    assert credentials,'Authorized subject did not federate within bounded propagation wait'
    record('authorized_subject_exchanges_token')
    for check,namespace,name,audience in [('other_service_account_denied',ns,account+'-denied',binding['audience']),('other_namespace_denied',ns+'-denied',account,binding['audience']),('other_audience_denied',ns,account,'https://kubernetes.default.svc')]:
     assert exchange(token(namespace,name,audience)) is None,check
     record(check)
    if provider=='aws':
     e={k:v for k,v in env.items() if not k.startswith('AWS_')}
     e.update(AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_EC2_METADATA_DISABLED='true',AWS_REGION=c['aws']['region'],AWS_CONFIG_FILE='/dev/null',AWS_SHARED_CREDENTIALS_FILE='/dev/null')
     bucket=c['aws']['bucket_name']
     command(['aws','s3api','get-bucket-location','--bucket',bucket,'--expected-bucket-owner',c['aws']['account_id']],env_override=e)
     record('scoped_resource_read_allowed')
     r=subprocess.run(['aws','s3api','get-bucket-tagging','--bucket',bucket,'--expected-bucket-owner',c['aws']['account_id']],env=e,capture_output=True,text=True,timeout=60)
     assert r.returncode and 'AccessDenied' in r.stderr
     record('ungranted_operation_denied')
    else:
     def get_group(group):
      url='https://management.azure.com/subscriptions/'+c['azure']['subscription_id']+'/resourcegroups/'+group+'?api-version=2021-04-01'
      request=urllib.request.Request(url,headers={'Authorization':'Bearer '+credentials})
      try:
       with urllib.request.urlopen(request,timeout=60) as response:return response.status,None
      except urllib.error.HTTPError as error:
       body=json.loads(error.read());return error.code,body.get('error',{}).get('code')
     for attempt in range(18):
      status,code=get_group(c['azure']['resource_group_name'])
      if status==200:break
      assert status==403 and code=='AuthorizationFailed'
      time.sleep(10)
     assert status==200,'Role assignment did not propagate within bounded wait'
     record('scoped_resource_read_allowed')
     status,code=get_group(c['azure']['state']['resource_group_name'])
     assert status==403 and code=='AuthorizationFailed'
     record('other_resource_group_denied')
    record('acceptance_resources_retained')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'event': 'acceptance_failed', 'message': 'See the last passed check; raw cloud errors and credentials are intentionally omitted.'}), file=sys.stderr)
        raise SystemExit(1)
