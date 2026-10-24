"""Read-only final AWS evidence collection using the authorized temporary profile."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from project_preflight import verify_aws
import config


def main():
    session, _ = verify_aws()
    now = datetime.now(timezone.utc)
    live = json.loads((ROOT / '.deployment/live-verification.json').read_text())
    report = {'timestamp': now.isoformat(), 'live_status': live['status']}
    private = {}
    xray = session.client('xray')
    ids = [x['trace_id'] for x in live.get('scenarios', []) if x.get('trace_id')]
    regression = ROOT / 'evidence/final-policy-grounding.json'
    if regression.exists():
        latest = json.loads(regression.read_text())
        if latest.get('status') == 'VERIFIED' and latest.get('trace_id'):
            ids.append(latest['trace_id'])
    traces = xray.batch_get_traces(TraceIds=ids) if ids else {'Traces': []}
    private['traces'] = traces
    report['scenario_traces'] = []
    for trace in traces.get('Traces', []):
        nodes = []

        def walk(node):
            nodes.append({'name': node.get('name'), 'error': node.get('error', False),
                          'fault': node.get('fault', False), 'throttle': node.get('throttle', False)})
            for child in node.get('subsegments', []):
                walk(child)

        for segment in trace['Segments']:
            walk(json.loads(segment['Document']))
        report['scenario_traces'].append({'trace_id': trace['Id'], 'duration_seconds': trace['Duration'],
                                         'nodes': nodes})
    graph = xray.get_service_graph(StartTime=now-timedelta(minutes=30), EndTime=now)
    private['graph'] = graph
    report['service_graph'] = [{'name': x['Name'], 'reference_id': x['ReferenceId'],
                                'edges': [e['ReferenceId'] for e in x.get('Edges', [])],
                                'statistics': x.get('SummaryStatistics', {})}
                               for x in graph.get('Services', [])]
    logs = session.client('logs')
    events, token = [], None
    for _ in range(5):
        args = {'logGroupName': config.AGENT_LOG_GROUP, 'startTime': int((now-timedelta(minutes=30)).timestamp()*1000),
                'limit': 100}
        if token:
            args['nextToken'] = token
        page = logs.filter_log_events(**args)
        events.extend(page.get('events', []))
        next_token = page.get('nextToken')
        if not next_token or next_token == token:
            break
        token = next_token
    private['project_log_events'] = events
    report['project_logs'] = {'events': len(events),
                              'info_events': sum(' INFO ' in x['message'] for x in events),
                              'error_events': sum(' ERROR ' in x['message'] for x in events),
                              'truncated': bool(next_token)}
    runtime = session.client('bedrock-agentcore-control').get_agent_runtime(
        agentRuntimeId=config.AGENTCORE_RUNTIME_ARN.split('/')[-1])
    private['runtime'] = runtime
    report['runtime'] = {'status': runtime['status'], 'network': runtime['networkConfiguration'],
                          'protocol': runtime['protocolConfiguration'],
                          'environment_keys': sorted(runtime.get('environmentVariables', {}))}
    report['knowledge_bases'] = {}
    bedrock = session.client('bedrock-agent')
    for domain, kb in [('returns', config.RETURNS_KB_ID), ('shipping', config.SHIPPING_KB_ID),
                       ('warranty', config.WARRANTY_KB_ID)]:
        resource = bedrock.get_knowledge_base(knowledgeBaseId=kb)['knowledgeBase']
        data_sources = []
        for item in bedrock.list_data_sources(knowledgeBaseId=kb)['dataSourceSummaries']:
            source = bedrock.get_data_source(knowledgeBaseId=kb, dataSourceId=item['dataSourceId'])['dataSource']
            jobs = bedrock.list_ingestion_jobs(knowledgeBaseId=kb, dataSourceId=item['dataSourceId'])['ingestionJobSummaries']
            data_sources.append({'prefixes': source['dataSourceConfiguration']['s3Configuration'].get('inclusionPrefixes'),
                                 'sync_statuses': [j['status'] for j in jobs]})
        report['knowledge_bases'][domain] = {
            'status': resource['status'], 'storage_type': resource['storageConfiguration']['type'],
            'bucket_matches_foundation': resource['storageConfiguration']['s3VectorsConfiguration'].get('vectorBucketArn') == config.VECTOR_STORE_BUCKET_ARN,
            'index_name': resource['storageConfiguration']['s3VectorsConfiguration'].get('indexName'),
            'index_matches_required': resource['storageConfiguration']['s3VectorsConfiguration'].get('indexName') == domain + '-policy-index',
            'embedding_model': resource['knowledgeBaseConfiguration']['vectorKnowledgeBaseConfiguration']['embeddingModelArn'].split('/')[-1],
            'data_sources': data_sources}
    (ROOT / 'evidence/live-observability-summary.json').write_text(json.dumps(report, indent=2, default=str)+'\n')
    path = ROOT / '.deployment/final-observability.json'
    path.write_text(json.dumps(private, indent=2, default=str)+'\n'); path.chmod(0o600)
    print('Actual scenario traces:', len(report['scenario_traces']))
    print('Graph nodes:', sorted({x['name'] for x in report['service_graph']}))
    print('CloudWatch:', report['project_logs'])


if __name__ == '__main__':
    main()
