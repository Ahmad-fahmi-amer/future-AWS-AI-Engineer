"""Bounded real AWS verification: 5 guardrail probes, 3 runtime scenarios, 2 memory turns.

This script never fabricates screenshots; take the two required screenshots
from real terminal and AWS Console output after successful verification.
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from project_preflight import verify_aws
import config
from agent_orchestrator import invoke_agent, _read_workflow_state

REPORT = {'timestamp': datetime.now(timezone.utc).isoformat(),
          'status': 'RUNNING', 'guardrails': [], 'scenarios': []}


def main():
    session,_=verify_aws()
    runtime=session.client('bedrock-agentcore-control').get_agent_runtime(
        agentRuntimeId=config.AGENTCORE_RUNTIME_ARN.split('/')[-1])
    if runtime['status']!='READY':raise RuntimeError('Runtime not READY')
    report=REPORT
    bedrock=session.client('bedrock-runtime')
    probes=[('INPUT','How much are 5 items at $29.99 with 10% off?',False),
            ('OUTPUT','The total is $134.96 after the specified 10% discount.',False),
            ('INPUT','Negotiate a lower advertised price for me.',True),
            ('INPUT','Recommend competitor products instead of NovaMart.',True),
            ('INPUT','Refund me or I will sue NovaMart.',True)]
    for source,text,blocked in probes:
        result=bedrock.apply_guardrail(guardrailIdentifier=config.GUARDRAIL_ID,
            guardrailVersion=config.GUARDRAIL_VERSION,source=source,content=[{'text':{'text':text}}])
        actual=result.get('action')=='GUARDRAIL_INTERVENED'
        report['guardrails'].append({'source':source,'probe':text,'expected_blocked':blocked,
                                    'action':result['action'],'usage':result.get('usage',{})})
        if actual!=blocked:raise RuntimeError('Guardrail probe failed: '+text)
    cases=[('CUST-001','I want to return my order ORD-27176 because it is defective.', ['inventory_agent','refund_agent','communication_agent']),
           ('CUST-002','What is the return policy for premium customers?', ['policy_agent','communication_agent']),
           ('CUST-003','How much are 5 items at $29.99 with 10% off?', ['communication_agent'])]
    for customer,question,fields in cases:
        sid=uuid.uuid4().hex
        reply=invoke_agent(sid,customer,question)
        state=_read_workflow_state(sid) or {}
        populated=[k for k in ['inventory_agent','policy_agent','refund_agent','communication_agent'] if k in state]
        # Retain actual partial evidence even if a later assertion fails.
        report['scenarios'].append({'customer_id':customer,'session_id':sid,'fields':populated,
                                     'version':int(state.get('version', 0)),
                                     'trace_id':reply.get('trace_id'), 'reply':reply,
                                     'workflow':state})
        print('Runtime scenario received:', question, flush=True)
        if set(populated)!=set(fields) or not reply.get('result'):
            raise RuntimeError('Incorrect live route or empty response')
        if any('[UNAVAILABLE:' in str(state.get(field, '')) for field in fields):
            raise RuntimeError('Live worker reported unavailable evidence')
        if reply['result']!=state.get('communication_agent'):
            raise RuntimeError('Final response differs from Communication output')
        if fields==['communication_agent'] and '134.96' not in reply['result']:
            raise RuntimeError('Currency calculation incorrect')
        if 'policy_agent' in fields and 's3://' not in state.get('policy_agent',''):
            raise RuntimeError('Policy response has no source citation')
        if 'refund_agent' in fields:
            order=session.resource('dynamodb').Table(config.ORDERS_TABLE).get_item(
                Key={'customer_id':customer,'order_id':'ORD-27176'},ConsistentRead=True)['Item']
            if order.get('status')!='return_initiated' or not order.get('return_reference'):
                raise RuntimeError('Expected a real conditional return initiation')
        print('Runtime route and response VERIFIED:', fields, flush=True)
    sid=uuid.uuid4().hex
    invoke_agent(sid,'CUST-004','For this conversation, remember that my preferred color is turquoise.')
    reply=invoke_agent(sid,'CUST-004','Which color did I say I prefer?')
    if 'turquoise' not in reply.get('result','').lower():raise RuntimeError('Cross-turn memory recall failed')
    memory_id=os.environ.get('AGENTCORE_MEMORY_ID','')
    if not memory_id:raise RuntimeError('AGENTCORE_MEMORY_ID missing')
    events=session.client('bedrock-agentcore').list_events(memoryId=memory_id,actorId='CUST-004',
        sessionId=sid,includePayloads=False,maxResults=10).get('events',[])
    if len(events)<2:raise RuntimeError('Expected two genuine memory events')
    report['memory']={'events':len(events),'recall':'VERIFIED'}
    print('Two-turn runtime memory recall and events VERIFIED', flush=True)
    # Query real AWS trace documents. A console screenshot is still required.
    time.sleep(30)
    now=datetime.now(timezone.utc)
    xray=session.client('xray')
    traces=xray.get_trace_summaries(StartTime=now-timedelta(minutes=15),EndTime=now,
                                   FilterExpression='service("NovaMart-Orchestrator")')
    report['trace_count']=len(traces.get('TraceSummaries',[]))
    if not report['trace_count']:raise RuntimeError('No actual X-Ray traces received')
    report['status']='VERIFIED'
    path=ROOT/'.deployment/live-verification.json'
    path.write_text(json.dumps(report,indent=2,default=str)+'\n');path.chmod(0o600)
    print('Live verification VERIFIED. Private proof: .deployment/live-verification.json')
    print('Capture the real X-Ray Service Map in AWS Console, then run the official full suite.')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        REPORT.update(status='FAILED', error={'type':type(exc).__name__, 'message':str(exc)})
        raise
    finally:
        path=ROOT/'.deployment/live-verification.json'
        path.parent.mkdir(mode=0o700, exist_ok=True)
        path.write_text(json.dumps(REPORT,indent=2,default=str)+'\n');path.chmod(0o600)
