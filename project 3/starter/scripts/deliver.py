"""Bounded project delivery. No mutations unless --apply is explicitly supplied.

A network failure, unowned stack, replacement, failed ingestion or failed test
stops execution. No automatic teardown. Run with the authorized named profile.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from project_preflight import verify_aws
from botocore.exceptions import ClientError
from dotenv import set_key

PROJECT = 'udacity-agentcore'
PRIVATE = ROOT/'.deployment'


def record(name, value):
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    path=PRIVATE/name
    path.write_text(json.dumps(value, default=str, indent=2)+'\n')
    path.chmod(0o600)


def command(*args):
    subprocess.run(list(args), cwd=ROOT, check=True)


def deploy_stack(cf, name, template, parameters=None):
    """Review server-side change set and fail on resource replacement/removal."""
    try:
        existing=cf.describe_stacks(StackName=name)['Stacks'][0]
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'ValidationError' or 'does not exist' not in exc.response['Error']['Message']:
            raise
        existing=None
    if existing:
        tags={t['Key']:t['Value'] for t in existing.get('Tags',[])}
        if tags.get('Project') != PROJECT:
            raise RuntimeError(f'Existing stack {name} has no verified project ownership; review it before adoption')
        if existing['StackStatus'] not in ('CREATE_COMPLETE','UPDATE_COMPLETE','UPDATE_ROLLBACK_COMPLETE'):
            raise RuntimeError(f'Stack {name} is not ready for a safe update')
    change='novamart-'+uuid.uuid4().hex[:12]
    cf.create_change_set(StackName=name,ChangeSetName=change,
        ChangeSetType='UPDATE' if existing else 'CREATE',TemplateBody=template.read_text(),
        Parameters=parameters if parameters is not None else [
            {'ParameterKey':'ProjectName','ParameterValue':PROJECT}],
        Capabilities=['CAPABILITY_NAMED_IAM'],Tags=[{'Key':'Project','Value':PROJECT}])
    deadline=time.monotonic()+300
    while True:
        result=cf.describe_change_set(StackName=name,ChangeSetName=change)
        if result['Status']=='CREATE_COMPLETE':break
        if result['Status']=='FAILED':
            if 'didn\'t contain changes' in result.get('StatusReason','') or 'No updates' in result.get('StatusReason',''):
                cf.delete_change_set(StackName=name,ChangeSetName=change)
                return cf.describe_stacks(StackName=name)['Stacks'][0]
            raise RuntimeError(result.get('StatusReason','Change set failed'))
        if time.monotonic()>deadline:raise TimeoutError('Change set timed out')
        time.sleep(3)
    record(name+'-changes.json',result)
    changes=result.get('Changes',[])
    if result.get('NextToken'):
        raise RuntimeError('Paginated change set requires manual review')
    for item in changes:
        resource=item['ResourceChange']
        if resource.get('Action')=='Remove' or resource.get('Replacement') in ('True','Conditional'):
            raise RuntimeError('Destructive/replacing change requires separate human approval')
    cf.execute_change_set(StackName=name,ChangeSetName=change)
    deadline=time.monotonic()+1200
    while True:
        state=cf.describe_stacks(StackName=name)['Stacks'][0]
        status=state['StackStatus']
        if status in ('CREATE_COMPLETE','UPDATE_COMPLETE'):break
        if 'FAILED' in status or 'ROLLBACK' in status:raise RuntimeError(f'{name} failed: {status}')
        if time.monotonic()>deadline:raise TimeoutError('Stack creation timed out')
        time.sleep(5)
    record(name+'-stack.json',state)
    manifest_path=PRIVATE/'resources.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest[{'udacity-agentcore': 'foundation_stack_id',
              'udacity-agentcore-knowledge-bases': 'knowledge_bases_stack_id',
              'CDKToolkit': 'bootstrap_stack_id'}[name]]=state['StackId']
    record('resources.json',manifest)
    return state


def sync_policies(session, stack):
    agent=session.client('bedrock-agent')
    outputs={o['OutputKey']:o['OutputValue'] for o in stack['Outputs']}
    env_path=ROOT/'.env'
    env_path.touch(mode=0o600,exist_ok=True);env_path.chmod(0o600)
    for domain in ('Returns','Shipping','Warranty'):
        kb=outputs[domain+'KbId'];ds=outputs[domain+'DataSourceId']
        set_key(str(env_path),domain.upper()+'_KB_ID',kb)
        job=agent.start_ingestion_job(knowledgeBaseId=kb,dataSourceId=ds,
            clientToken=str(uuid.uuid4()))['ingestionJob']
        deadline=time.monotonic()+600
        while job['status']!='COMPLETE':
            if job['status'] in ('FAILED','STOPPED') or time.monotonic()>deadline:
                raise RuntimeError(f'{domain} ingestion failed/timed out: {job.get("failureReasons",[])}')
            time.sleep(5)
            job=agent.get_ingestion_job(knowledgeBaseId=kb,dataSourceId=ds,
                                      ingestionJobId=job['ingestionJobId'])['ingestionJob']
        record(domain.lower()+'-sync.json',job)
        if job.get('statistics',{}).get('numberOfDocumentsFailed',0):
            raise RuntimeError(f'{domain} ingestion contains failed documents')
        print(domain+' KB sync VERIFIED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step',choices=['foundation','bootstrap','knowledge-bases','runtime','verify','all'])
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        print('Plan: preflight -> foundation change set -> seed -> KB change set/sync -> CLI runtime/memory/observability -> bounded verification.')
        print('No AWS calls or mutations. Add --apply to execute the selected step after reviewing IAM templates.')
        return
    if sys.version_info[:2] != (3,12):
        raise RuntimeError('Use the reproducible Python 3.12 environment (.venv312) for deployment')
    # Keep CLI packaging caches inside the writable project, including when
    # CDK spawns uv. setup.sh exports do not persist into a later shell.
    os.environ.setdefault('UV_CACHE_DIR', str(ROOT / '.tools/uv-cache'))
    os.environ.setdefault('UV_PYTHON_INSTALL_DIR', str(ROOT / '.tools/python'))
    session,identity=verify_aws()
    cf=session.client('cloudformation')
    if args.step in ('bootstrap','all'):
        deploy_stack(cf,'CDKToolkit',ROOT/'infrastructure/cdk_bootstrap.json', parameters=[
            {'ParameterKey':'FileAssetsBucketKmsKeyId','ParameterValue':'AWS_MANAGED_KEY'}])
    if args.step in ('foundation','all'):
        deploy_stack(cf,PROJECT,ROOT/'infrastructure/starter_stack.yaml')
        command(sys.executable,'infrastructure/seed_data.py')
    if args.step in ('knowledge-bases','all'):
        stack=deploy_stack(cf,PROJECT+'-knowledge-bases',ROOT/'infrastructure/knowledge_bases.json')
        sync_policies(session,stack)
    if args.step in ('runtime','all'):
        target=[{'name':'default','account':identity['account'],'region':identity['region']}]
        path=ROOT/'agentcore/aws-targets.json'
        existing=json.loads(path.read_text())
        if existing and existing != target:raise RuntimeError('CLI deployment targets differ from verified account/region')
        path.write_text(json.dumps(target,indent=2)+'\n')
        command(sys.executable,'src/agent_orchestrator.py','deploy')
        from dotenv import dotenv_values
        env=dotenv_values(ROOT/'.env')
        manifest_path=PRIVATE/'resources.json'
        manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        manifest.update(runtime_stack_id=cf.describe_stacks(StackName='AgentCore-udacity-default')['Stacks'][0]['StackId'],
                        guardrail_id=env['GUARDRAIL_ID'],memory_id=env['AGENTCORE_MEMORY_ID'])
        record('resources.json',manifest)
    if args.step in ('verify','all'):
        command(sys.executable,'scripts/verify_live.py')
        result=subprocess.run([sys.executable,'tests/test_agent.py','all'],cwd=ROOT,
                              capture_output=True,text=True,timeout=900)
        text=result.stdout+result.stderr
        (ROOT/'evidence/official-all.log').write_text(text)
        print(text)
        if result.returncode or 'FAIL' in text or '120/120' not in text:
            raise RuntimeError('Official suite did not verify every requirement; inspect evidence/official-all.log')


if __name__=='__main__':main()
