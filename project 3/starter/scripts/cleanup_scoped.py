"""Cleanup only exact, recorded project stack IDs. Default is dry-run.

Does not alter account-level Transaction Search or delete shared CDKToolkit.
A failed read is an error, never interpreted as an absent resource.
"""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from project_preflight import verify_aws
import config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yes',action='store_true')
    args=parser.parse_args()
    session,_=verify_aws()
    private=ROOT/'.deployment'
    cf=session.client('cloudformation')
    # Exact ARNs/IDs from this run; a matching prefix alone never proves ownership.
    manifest_path=private/'resources.json'
    if not manifest_path.exists():
        raise RuntimeError('No verified deployment inventory; refusing prefix-based cleanup')
    manifest=json.loads(manifest_path.read_text())
    project=config.PROJECT_NAME
    def act(label,operation):
        print(('DELETE ' if args.yes else 'DRY RUN ')+label)
        if args.yes:operation()
    for name in ('runtime','knowledge_bases','foundation'):
        stack_id=manifest.get(name+'_stack_id')
        if not stack_id:continue
        detail=cf.describe_stacks(StackName=stack_id)['Stacks'][0]
        if name!='runtime' and {t['Key']:t['Value'] for t in detail.get('Tags',[])}.get('Project')!=project:
            raise RuntimeError('Stack ownership tags mismatch')
        if detail['StackId']!=stack_id:raise RuntimeError('Stack ID mismatch')
    # Runtime, KBs and their roles are CFN-managed; delete stacks before foundation.
    for name in ('runtime','knowledge_bases'):
        stack_id=manifest.get(name+'_stack_id')
        if stack_id:
            act(name+' stack',lambda sid=stack_id:cf.delete_stack(StackName=sid))
            if args.yes:cf.get_waiter('stack_delete_complete').wait(StackName=stack_id,WaiterConfig={'Delay':10,'MaxAttempts':90})
    memory=manifest.get('memory_id')
    if memory:
        ctl=session.client('bedrock-agentcore-control')
        detail=ctl.get_memory(memoryId=memory)['memory']
        if detail.get('name')!=config.MEMORY_NAME or ctl.list_tags_for_resource(resourceArn=detail['arn']).get('tags',{}).get('Project')!=project:
            raise RuntimeError('Memory ownership mismatch')
        act('recorded memory',lambda:ctl.delete_memory(memoryId=memory))
    guard=manifest.get('guardrail_id')
    if guard:
        client=session.client('bedrock')
        detail=client.get_guardrail(guardrailIdentifier=guard,guardrailVersion='DRAFT')
        tags=client.list_tags_for_resource(resourceARN=detail['guardrailArn'])['tags']
        if detail['name']!=config.GUARDRAIL_NAME or {t['key']:t['value'] for t in tags}.get('Project')!=project:
            raise RuntimeError('Guardrail ownership mismatch')
        act('recorded guardrail and versions',lambda:client.delete_guardrail(guardrailIdentifier=guard))
    foundation=manifest.get('foundation_stack_id')
    if foundation:
        # Resolve the exact bucket from the recorded stack, not an account-wide prefix search.
        resources=cf.list_stack_resources(StackName=foundation)['StackResourceSummaries']
        bucket=next(r['PhysicalResourceId'] for r in resources if r['LogicalResourceId']=='PolicyDocumentsBucket')
        s3=session.client('s3')
        for page in s3.get_paginator('list_object_versions').paginate(Bucket=bucket):
            objects=[{'Key':o['Key'],'VersionId':o['VersionId']} for k in ('Versions','DeleteMarkers') for o in page.get(k,[])]
            for start in range(0,len(objects),1000):
                batch=objects[start:start+1000]
                act(f'{len(batch)} versions from recorded policy bucket',lambda batch=batch:s3.delete_objects(Bucket=bucket,Delete={'Objects':batch,'Quiet':True}))
        act('foundation stack',lambda:cf.delete_stack(StackName=foundation))
        if args.yes:cf.get_waiter('stack_delete_complete').wait(StackName=foundation,WaiterConfig={'Delay':10,'MaxAttempts':90})
    print('Shared CDK bootstrap and account-level observability settings retained.')


if __name__=='__main__':main()
