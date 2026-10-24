"""Read-only AWS readiness checks. Store identifiers privately; print summaries only."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from project_preflight import verify_aws
from botocore.config import Config
from botocore.exceptions import ClientError


def main():
    session, _ = verify_aws()
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'checks': {}}
    cfg = Config(connect_timeout=5, read_timeout=15, retries={'max_attempts': 1})

    def check(name, service, operation, **kwargs):
        try:
            value = getattr(session.client(service, config=cfg), operation)(**kwargs)
            value.pop('ResponseMetadata', None)
            report['checks'][name] = {'status': 'VERIFIED', 'result': value}
            print(name + ': VERIFIED')
            return value
        except ClientError as exc:
            err = exc.response['Error']
            if err['Code'] in ('ValidationError', 'NoSuchEntity') and (
                    'does not exist' in err.get('Message', '') or err['Code'] == 'NoSuchEntity'):
                report['checks'][name] = {'status': 'ABSENT', 'error': err}
                print(name + ': ABSENT')
                return
            report['checks'][name] = {'status': 'BLOCKED', 'error': err}
            print(name + ': BLOCKED (' + err['Code'] + ')')
        except Exception as exc:
            report['checks'][name] = {'status': 'BLOCKED', 'error': str(exc)}
            print(name + ': BLOCKED (' + type(exc).__name__ + ')')

    for stack in ('udacity-agentcore', 'udacity-agentcore-knowledge-bases',
                  'AgentCore-udacity-default', 'CDKToolkit'):
        check('stack:' + stack, 'cloudformation', 'describe_stacks', StackName=stack)
    check('foundation-template', 'cloudformation', 'validate_template',
          TemplateBody=(ROOT / 'infrastructure/starter_stack.yaml').read_text())
    check('kb-template', 'cloudformation', 'validate_template',
          TemplateBody=(ROOT / 'infrastructure/knowledge_bases.json').read_text())
    check('knowledge-bases', 'bedrock-agent', 'list_knowledge_bases', maxResults=100)
    check('guardrails', 'bedrock', 'list_guardrails', maxResults=100)
    check('runtimes', 'bedrock-agentcore-control', 'list_agent_runtimes', maxResults=100)
    check('memories', 'bedrock-agentcore-control', 'list_memories', maxResults=100)
    check('vectors', 's3vectors', 'list_vector_buckets', maxResults=100)
    check('tables', 'dynamodb', 'list_tables', Limit=100)
    check('transaction-search', 'xray', 'get_trace_segment_destination')
    check('model-profiles', 'bedrock', 'list_inference_profiles', maxResults=100)
    for model in ('anthropic.claude-haiku-4-5-20251001-v1:0',
                  'anthropic.claude-sonnet-4-5-20250929-v1:0',
                  'amazon.titan-embed-text-v2:0'):
        check('model:' + model, 'bedrock', 'get_foundation_model_availability', modelId=model)
    for service in ('bedrock-agentcore', 'bedrock'):
        check('quotas:' + service, 'service-quotas', 'list_service_quotas',
              ServiceCode=service, MaxResults=100)
    role = check('runtime-role', 'iam', 'get_role',
                 RoleName='udacity-agentcore-agentcore-role')
    if role:
        check('runtime-role-inline', 'iam', 'list_role_policies',
              RoleName=role['Role']['RoleName'])
        check('runtime-role-attached', 'iam', 'list_attached_role_policies',
              RoleName=role['Role']['RoleName'])
    path = ROOT / '.deployment/cloud-preflight.json'
    path.write_text(json.dumps(report, indent=2, default=str) + '\n')
    path.chmod(0o600)
    public = {k: {x: v[x] for x in ('status',) if x in v}
              for k, v in report['checks'].items()}
    (ROOT / 'evidence/cloud-preflight-summary.json').write_text(
        json.dumps({'timestamp': report['timestamp'], 'checks': public}, indent=2) + '\n')


if __name__ == '__main__':
    main()
