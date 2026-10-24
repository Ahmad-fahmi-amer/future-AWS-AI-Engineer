"""Deterministic tests. AWS/model doubles here are NOT live AWS evidence.

The official tests/test_agent.py is kept byte-identical and run separately.
"""
import sys
import json
import os
import threading
import io
import unittest
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src'), str(Path(__file__).resolve().parents[1])]
import config
import agent_orchestrator as ao
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters


def conflict():
    return ClientError({'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'version mismatch'}}, 'UpdateItem')


def fn(agent, name):
    return agent.tool_registry.registry[name]._tool_func


class LocalTest(unittest.TestCase):
    def setUp(self):
        self.patchers = [patch.dict(os.environ, {'AGENTCORE_MEMORY_ID': ''}), patch.object(config, '_exports_cache', {
            'udacity-agentcore-OrdersTable': 'orders', 'udacity-agentcore-CustomersTable': 'customers',
            'udacity-agentcore-WorkflowStateTable': 'workflows', 'udacity-agentcore-AgentLogGroup': '/test/novamart'}),
            patch.object(config, 'GUARDRAIL_ID', '', create=True),
            patch.object(config, 'GUARDRAIL_VERSION', '', create=True)]
        for key in ('RETURNS_KB_ID','SHIPPING_KB_ID','WARRANTY_KB_ID'):
            self.patchers.append(patch.object(config, key, key[:10], create=True))
        for p in self.patchers: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patchers)])
        self.scope = ao.RequestScope()
        self.scope.active = self.scope.initialized = True
        self.scope.session_id = 'session123'
        self.scope.customer_id = 'CUST-001'
        self.scope.request = 'Please return order ORD-27176'
        self.scope.turn_id = 'turn123'
        self.state = {'session_id': 'session123', 'customer_id': 'CUST-001', 'version': 2,
                      'inventory_agent': 'Delivered order and Premium customer'}

    def order(self, age=12, **updates):
        return {'customer_id': 'CUST-001', 'order_id': 'ORD-27176', 'status': 'delivered',
                'order_date': (date(2026,10,21)-timedelta(days=age)).isoformat(), **updates}

    def test_refund_inclusive_standard_and_premium_boundaries(self):
        for tier, maximum in [('Standard',30),('Premium',60)]:
            for age, allowed in [(0,True),(maximum,True),(maximum+1,False),(-1,False)]:
                with self.subTest(tier=tier,age=age):
                    self.assertEqual(ao.refund_eligibility(self.order(age), {'tier':tier}, date(2026,10,21))['eligible'], allowed)

    def test_refund_rejects_unknown_tier_invalid_date_and_non_delivered(self):
        for order,customer in [(self.order(), {'tier':'Gold'}),
             (self.order(order_date='bad'),{'tier':'Premium'}),
             (self.order(status='shipped'),{'tier':'Premium'}),
             (self.order(final_sale=True),{'tier':'Premium'})]:
            self.assertFalse(ao.refund_eligibility(order,customer,date(2026,10,21))['eligible'])

    def test_actual_delivery_preferred_over_order_date(self):
        result=ao.refund_eligibility(self.order(100, delivered_at='2026-10-20'),{'tier':'Standard'},date(2026,10,21))
        self.assertTrue(result['eligible']); self.assertEqual(result['date_basis'],'delivered_at')

    def test_estimated_delivery_is_not_actual_delivery(self):
        self.assertFalse(ao.refund_eligibility(self.order(80,estimated_delivery='2026-10-20'),{'tier':'Premium'},date(2026,10,21))['eligible'])

    def test_six_route_families(self):
        cases={
          'I want to return order ORD-27176':['inventory_agent','refund_agent'],
          'What is my order status?':['inventory_agent','refund_agent'],
          'What is the return policy for premium customers?':['policy_agent'],
          'What are the shipping rates?':['policy_agent'],
          'What is the shipping policy for orders over $50?':['policy_agent'],
          'What is my account tier?':['inventory_agent'],
          'Am I premium?':['inventory_agent'],
          'How much are 5 items at $29.99 with 10% off?':[]}
        for request,expected in cases.items():self.assertEqual(ao._required_workers(request),expected)

    def test_state_reads_are_strongly_consistent(self):
        with patch.object(ao,'dynamodb') as db:
            ao._read_workflow_state('session123')
            db.Table.return_value.get_item.assert_called_once_with(Key={'session_id':'session123'},ConsistentRead=True)

    def test_state_creation_cannot_overwrite_existing_session(self):
        with patch.object(ao,'dynamodb') as db:
            result=ao._create_workflow_state('session123','CUST-001')
            self.assertEqual(result['version'],0)
            self.assertEqual(db.Table.return_value.put_item.call_args.kwargs['ConditionExpression'], 'attribute_not_exists(session_id)')

    def test_state_conditional_write_and_return_new_attributes(self):
        with patch.object(ao,'dynamodb') as db:
            db.Table.return_value.update_item.return_value={'Attributes':{'version':3}}
            self.assertEqual(ao._update_workflow_state('session123',{'policy_agent':'source'},2),{'version':3})
            args=db.Table.return_value.update_item.call_args.kwargs
            self.assertIn('#v = :old',args['ConditionExpression'])
            self.assertEqual(args['ExpressionAttributeValues'][':new'],3)
            self.assertEqual(args['ReturnValues'],'ALL_NEW')

    def test_conflict_retries_independent_field_with_fresh_version(self):
        with patch.object(ao,'dynamodb') as db, patch.object(ao,'_read_workflow_state',return_value={'version':5,'inventory_agent':'facts'}), patch.object(ao.time,'sleep'):
            db.Table.return_value.update_item.side_effect=[conflict(),{'Attributes':{'version':6}}]
            self.assertEqual(ao._update_workflow_state('session123',{'policy_agent':'source'},2)['version'],6)
            self.assertEqual(db.Table.return_value.update_item.call_args.kwargs['ExpressionAttributeValues'][':old'],5)

    def test_conflict_rejects_stale_same_worker_overwrite(self):
        with patch.object(ao,'dynamodb') as db, patch.object(ao,'_read_workflow_state',return_value={'version':3,'policy_agent':'newer'}):
            db.Table.return_value.update_item.side_effect=conflict()
            with self.assertRaisesRegex(RuntimeError,'stale overwrite'):
                ao._update_workflow_state('session123',{'policy_agent':'stale'},2)
            self.assertEqual(db.Table.return_value.update_item.call_count,1)

    def test_state_metadata_cannot_be_overwritten_by_worker(self):
        for key in ['customer_id','version','ttl','session_id','lease_owner']:
            with self.assertRaises(ValueError):ao._update_workflow_state('session123',{key:'attacker'},2)

    def test_tools_reject_cross_customer_and_session(self):
        agent=ao.build_inventory_agent(self.scope)
        with patch.object(ao,'_read_workflow_state',return_value=self.state), patch.object(ao,'dynamodb') as db:
            with self.assertRaises(PermissionError):fn(agent,'check_order_status')('CUST-002','ORD-27176')
            db.Table.assert_not_called()
        with self.assertRaises(PermissionError):self.scope.validate('another-session','CUST-001')

    def test_tool_rejects_uninitialized_scope(self):
        self.scope.initialized=False
        with self.assertRaises(RuntimeError):fn(ao.build_inventory_agent(self.scope),'get_customer_tier')('CUST-001')

    def test_inventory_uses_composite_key(self):
        with patch.object(ao,'_read_workflow_state',return_value=self.state), patch.object(ao,'dynamodb') as db:
            fn(ao.build_inventory_agent(self.scope),'check_order_status')('CUST-001','ORD-27176')
            self.assertEqual(db.Table.return_value.get_item.call_args.kwargs['Key'],{'customer_id':'CUST-001','order_id':'ORD-27176'})

    def test_customer_profile_minimizes_pii(self):
        with patch.object(ao,'_read_workflow_state',return_value=self.state), patch.object(ao,'dynamodb') as db:
            db.Table.return_value.get_item.return_value={'Item':{'customer_id':'CUST-001','tier':'Premium','email':'private@example.org'}}
            result=fn(ao.build_inventory_agent(self.scope),'get_customer_tier')('CUST-001')
            self.assertNotIn('email',result);self.assertEqual(result['tier'],'Premium')

    def test_orders_paginate(self):
        with patch.object(ao,'_read_workflow_state',return_value=self.state), patch.object(ao,'dynamodb') as db:
            db.Table.return_value.query.side_effect=[{'Items':[{'order_id':'ORD-27176'}],'LastEvaluatedKey':{'customer_id':'CUST-001','order_id':'ORD-27176'}},{'Items':[{'order_id':'ORD-27180'}]}]
            result=fn(ao.build_inventory_agent(self.scope),'list_customer_orders')('CUST-001')
            self.assertEqual(len(result['orders']),2)
            self.assertIn('ExclusiveStartKey',db.Table.return_value.query.call_args.kwargs)

    def test_refund_requires_inventory_read_before_mutation(self):
        with patch.object(ao,'_read_workflow_state',return_value=self.state), patch.object(ao,'dynamodb') as db:
            with self.assertRaises(RuntimeError):fn(ao.build_refund_agent(self.scope),'initiate_refund')('CUST-001','ORD-27176','unwanted')
            db.Table.assert_not_called()

    def test_status_or_policy_questions_cannot_start_return(self):
        self.scope.inventory_read=True
        agent=ao.build_refund_agent(self.scope)
        for request in ['What is my order status ORD-27176?', 'Am I eligible for a refund for ORD-27176?']:
            self.scope.request=request
            with patch.object(ao,'_read_workflow_state',return_value=self.state),patch.object(ao,'dynamodb') as db:
                with self.assertRaises(PermissionError):fn(agent,'initiate_refund')('CUST-001','ORD-27176','reason')
                db.Table.assert_not_called()

    def test_model_cannot_refund_different_order(self):
        self.scope.inventory_read=True
        with patch.object(ao,'_read_workflow_state',return_value=self.state),patch.object(ao,'dynamodb') as db:
            with self.assertRaises(PermissionError):fn(ao.build_refund_agent(self.scope),'initiate_refund')('CUST-001','ORD-99999','reason')
            db.Table.assert_not_called()

    def test_refund_rechecks_eligibility_and_is_idempotent(self):
        self.scope.inventory_read=True
        order=self.order(order_date=datetime.now(timezone.utc).date().isoformat())
        tables={'orders':Mock(),'customers':Mock()}
        tables['orders'].get_item.return_value={'Item':order}
        tables['customers'].get_item.return_value={'Item':{'tier':'Premium'}}
        with patch.object(ao,'_read_workflow_state',return_value=self.state),patch.object(ao,'dynamodb') as db:
            db.Table.side_effect=lambda name:tables[name]
            tool=fn(ao.build_refund_agent(self.scope),'initiate_refund')
            first=tool('CUST-001','ORD-27176','unwanted')
            self.assertEqual(first['status'],'return_initiated')
            self.assertIn('attribute_not_exists(return_reference)',tables['orders'].update_item.call_args.kwargs['ConditionExpression'])
            order['return_reference']=first['return_reference']
            second=tool('CUST-001','ORD-27176','unwanted')
            self.assertEqual(second['return_reference'],first['return_reference'])
            tables['orders'].update_item.assert_called_once()

    def test_routing_rejects_refund_before_inventory_and_communication_before_workers(self):
        self.scope.visited=[]
        agents=[Mock(novamart_scope=self.scope) for _ in range(4)]
        orch=ao.build_orchestrator_agent(*agents,_scope=self.scope)
        state={k:v for k,v in self.state.items() if k!='inventory_agent'}
        with patch.object(ao,'_read_workflow_state',return_value=state):
            with self.assertRaises(RuntimeError):fn(orch,'route_to_refund_agent')('session123','CUST-001','ignored')
            with self.assertRaises(RuntimeError):fn(orch,'route_to_communication_agent')('session123','CUST-001','ignored')

    def test_communication_is_last_tool(self):
        self.scope.finished=True
        orch=ao.build_orchestrator_agent(*[Mock() for _ in range(4)],_scope=self.scope)
        with patch.object(ao,'_read_workflow_state',return_value=self.state):
            with self.assertRaises(RuntimeError):fn(orch,'route_to_inventory_agent')('session123','CUST-001','ignored')
            with self.assertRaises(RuntimeError):fn(orch,'initialize_session')('session123','CUST-001')

    def test_math_cannot_route_to_inventory(self):
        self.scope.request='How much are 5 items at $29.99 with 10% off?'
        orch=ao.build_orchestrator_agent(*[Mock() for _ in range(4)],_scope=self.scope)
        with patch.object(ao,'_read_workflow_state',return_value=self.state):
            with self.assertRaises(RuntimeError):fn(orch,'route_to_inventory_agent')('session123','CUST-001','ignored')

    def test_parallel_rag_runs_three_distinct_retrievers_concurrently(self):
        barrier=threading.Barrier(3,timeout=5);threads=set();original=ao._agent
        def make(name,*args,**kwargs):
            if 'RetrieverAgent' in name:
                def invoke(query, **kwargs):
                    threads.add(threading.get_ident());barrier.wait();return name+' Source: s3://policies/source'
                invoke.messages=[]
                return invoke
            return original(name,*args,**kwargs)
        with patch.object(ao,'_agent',side_effect=make),patch.object(ao.trace,'kb_start'),patch.object(ao.trace,'kb_done'),patch.object(ao.trace,'kb_result'):
            policy=ao.build_policy_agent()
            result=fn(policy,'search_all_policies')('return policy')
            self.assertEqual(len(threads),3)
            for domain in ['Returns','Shipping','Warranty']:self.assertIn(domain+'PolicyRetrieverAgent',result)

    def test_retrieval_error_is_never_policy_evidence(self):
        with patch.object(ao,'retrieve_from_knowledge_base',return_value=[{'source':'error','text':'failed','score':0}]):
            with self.assertRaises(RuntimeError):ao._passages('KB123','question')

    def test_model_configurations_and_guardrail_for_subagents(self):
        with patch.object(config,'GUARDRAIL_ID','guard123'),patch.object(config,'GUARDRAIL_VERSION','1'):
            policy=ao.build_policy_agent()
            for agent in [policy]+policy.novamart_retrievers:
                self.assertEqual(agent.model.config['guardrail_id'],'guard123')
                self.assertEqual(agent.model.config['guardrail_version'],'1')
            self.assertEqual(policy.model.config['temperature'],0.2)
            for agent in policy.novamart_retrievers:self.assertEqual(agent.model.config['temperature'],0.0)

    def test_guardrail_creation_validates_against_real_sdk_schema(self):
        client=ao.boto3.client('bedrock',region_name='us-east-1')
        mock=Mock();mock.get_paginator.return_value.paginate.return_value=[{'guardrails':[]}]
        mock.create_guardrail.return_value={'guardrailId':'guard123'}
        mock.get_guardrail.return_value={'status':'READY'}
        mock.create_guardrail_version.return_value={'version':'1'}
        with patch.object(ao.boto3,'client',return_value=mock):
            self.assertEqual(ao.create_guardrail(),('guard123','1'))
        args=mock.create_guardrail.call_args.kwargs
        validate_parameters(args,client.meta.service_model.operation_model('CreateGuardrail').input_shape)
        self.assertEqual(args['topicPolicyConfig']['tierConfig']['tierName'],'STANDARD')
        self.assertEqual(len(args['contentPolicyConfig']['filtersConfig']),5)

    def test_memory_creation_schema_and_runtime_env(self):
        client=ao.boto3.client('bedrock-agentcore-control',region_name='us-east-1')
        mock=Mock();mock.list_memories.return_value={'memories':[]}
        mock.create_memory.return_value={'memory':{'id':'udacity_agentcore_memory-1234567890','arn':'arn:example', 'status':'ACTIVE', 'eventExpiryDuration':7,'strategies':[{'type':'SUMMARIZATION'}]}}
        with patch.object(ao,'agentcore_control',mock),patch('agentcore_cli.configure_runtime') as configure:
            self.assertEqual(ao.configure_memory('runtime'),'arn:example')
            self.assertIn('AGENTCORE_MEMORY_ID',configure.call_args.kwargs['env_vars'])
        validate_parameters(mock.create_memory.call_args.kwargs,client.meta.service_model.operation_model('CreateMemory').input_shape)

    def test_memory_context_is_actor_and_session_scoped(self):
        mock=Mock();mock.list_events.return_value={'events':[]};mock.retrieve_memory_records.return_value={'memoryRecordSummaries':[]}
        with patch.object(ao,'agentcore_client',mock):ao._memory_context('memory123','CUST-001','session123')
        self.assertEqual(mock.list_events.call_args.kwargs['actorId'],'CUST-001')
        self.assertEqual(mock.list_events.call_args.kwargs['sessionId'],'session123')
        self.assertEqual(mock.retrieve_memory_records.call_args.kwargs['namespace'],'/summaries/CUST-001/session123')

    def test_inference_loop_is_bounded(self):
        limit=ao.InferenceLimit();limit.reset(None)
        for _ in range(8):limit.check(None)
        with self.assertRaises(RuntimeError):limit.check(None)

    def test_process_rejects_malformed_or_cross_customer_envelope(self):
        orch=Mock(novamart_scope=self.scope)
        with self.assertRaises(ValueError):ao.process_request(orch,'short','CUST-001','hello')
        with self.assertRaises(ValueError):ao.process_request(orch,'session123','CUST-001',{'attack':'x'})
        with patch.object(ao,'_read_workflow_state',return_value=self.state):
            with self.assertRaises(PermissionError):ao.process_request(orch,'session123','CUST-002','hello')
        orch.assert_not_called()

    def test_observability_failure_cannot_report_success(self):
        with patch.object(ao,'apply_observability_config',side_effect=RuntimeError('denied')):
            with self.assertRaises(RuntimeError):ao.configure_observability('runtime')

    def test_log_arguments_do_not_contain_customer_text_or_pii(self):
        import agent_observability as obs
        text=obs._short_args({'request':'secret@example.com','customer_id':'CUST-001'})
        self.assertNotIn('secret',text);self.assertNotIn('CUST-001',text)

    def test_session_reuse_clears_previous_worker_fields_under_lease(self):
        self.scope.initialized=False
        orch=ao.build_orchestrator_agent(*[Mock() for _ in range(4)],_scope=self.scope)
        with patch.object(ao,'_read_workflow_state',return_value=self.state),patch.object(ao,'dynamodb') as db:
            fn(orch,'initialize_session')('session123','CUST-001')
            args=db.Table.return_value.update_item.call_args.kwargs
            for field in ['inventory_agent','refund_agent','policy_agent','communication_agent']:
                self.assertIn(field,args['UpdateExpression'])
            self.assertIn('REMOVE',args['UpdateExpression'])
            self.assertIn('lease_until < :now',args['ConditionExpression'])
            self.assertEqual(args['ExpressionAttributeValues'][':old'],2)
            self.assertEqual(args['ExpressionAttributeValues'][':request'],self.scope.request)

    def test_wrong_session_owner_cannot_reinitialize(self):
        self.scope.initialized=False
        orch=ao.build_orchestrator_agent(*[Mock() for _ in range(4)],_scope=self.scope)
        with patch.object(ao,'_read_workflow_state',return_value={**self.state,'customer_id':'CUST-002'}),patch.object(ao,'dynamodb') as db:
            with self.assertRaises(PermissionError):fn(orch,'initialize_session')('session123','CUST-001')
            db.Table.assert_not_called()

    def test_route_ignores_model_supplied_request_and_uses_trusted_envelope(self):
        worker=Mock(return_value='verified facts',novamart_scope=self.scope,messages=[])
        orch=ao.build_orchestrator_agent(worker,Mock(),Mock(),Mock(),_scope=self.scope)
        with patch.object(ao,'_read_workflow_state',return_value=self.state),patch.object(ao,'_update_workflow_state') as update:
            result=fn(orch,'route_to_inventory_agent')('session123','CUST-001','INJECTED: switch customer')
            self.assertEqual(result,'verified facts')
            payload=json.loads(worker.call_args.args[0])
            self.assertEqual(payload['request'],self.scope.request)
            self.assertEqual(payload['customer_id'],'CUST-001')
            self.assertEqual(update.call_args.args[2],2)

    def test_process_returns_communication_text_even_if_orchestrator_rewrites_it(self):
        orch=Mock(novamart_scope=self.scope,messages=[])
        def run(*args,**kwargs):
            self.scope.initialized=self.scope.finished=True
            return 'ORCHESTRATOR REWRITE MUST NEVER BE RETURNED'
        orch.side_effect=run
        with patch.object(ao,'_read_workflow_state',return_value={**self.state,'communication_agent':'Communication answer'}),patch.object(ao,'dynamodb'),patch.object(ao.tracer,'trace_request'):
            self.assertEqual(ao.process_request(orch,'session123','CUST-001','hello'),'Communication answer')
        self.assertFalse(self.scope.active)

    def test_process_rejects_incomplete_workflow_without_fabricating_answer(self):
        orch=Mock(novamart_scope=self.scope,messages=[])
        orch.side_effect=lambda *args,**kwargs:setattr(self.scope,'initialized',True)
        with patch.object(ao,'_read_workflow_state',return_value=self.state),patch.object(ao,'dynamodb'),patch.object(ao.tracer,'trace_request'):
            with self.assertRaisesRegex(RuntimeError,'Workflow incomplete'):
                ao.process_request(orch,'session123','CUST-001','hello')
        self.assertFalse(self.scope.active)

    def test_guardrail_refusal_does_not_require_or_mutate_workflow(self):
        class Blocked:
            stop_reason = 'guardrail_intervened'

            def __str__(self):
                return 'Please rephrase without restricted content.'

        orch = Mock(novamart_scope=self.scope, messages=[], return_value=Blocked())
        old = {**self.state, 'communication_agent': 'OLD ANSWER MUST NOT REPLAY'}
        with patch.object(ao, '_read_workflow_state', return_value=old) as read, \
                patch.object(ao, 'dynamodb') as db, patch.object(ao.tracer, 'trace_request'):
            reply = ao.process_request(orch, 'session123', 'CUST-001', 'restricted input')
            self.assertEqual(reply, 'Please rephrase without restricted content.')
            read.assert_called_once_with('session123')
            db.Table.assert_not_called()
        self.assertFalse(self.scope.active)

    def test_runtime_invocation_does_not_retry_paid_turns_on_timeout(self):
        client = Mock()
        client.invoke_agent_runtime.return_value = {'response': io.BytesIO(b'{"result":"ok"}')}
        with patch.object(config, 'AGENTCORE_RUNTIME_ARN', 'test-runtime', create=True), \
                patch.object(ao.boto3, 'client', return_value=client) as build:
            self.assertEqual(ao.invoke_agent('session123', 'CUST-001', 'hello'), {'result': 'ok'})
            settings = build.call_args.kwargs['config']
            self.assertEqual(settings.read_timeout, 900)
            self.assertEqual(settings.retries['total_max_attempts'], 1)
            self.assertEqual(len(client.invoke_agent_runtime.call_args.kwargs['runtimeSessionId']), 64)

    def test_process_persists_real_turn_payload_in_memory_schema(self):
        orch=Mock(novamart_scope=self.scope,messages=[])
        def run(*args,**kwargs):self.scope.initialized=self.scope.finished=True
        orch.side_effect=run
        mock=Mock()
        with patch.dict(os.environ,{'AGENTCORE_MEMORY_ID':'memory1234567890'}),patch.object(ao,'_memory_context',return_value=[]),patch.object(ao,'agentcore_client',mock),patch.object(ao,'_read_workflow_state',return_value={**self.state,'communication_agent':'Communication answer'}),patch.object(ao,'dynamodb'),patch.object(ao.tracer,'trace_request'):
            ao.process_request(orch,'session123','CUST-001','hello')
        args=mock.create_event.call_args.kwargs
        self.assertEqual(args['actorId'],'CUST-001')
        self.assertEqual(args['sessionId'],'session123')
        self.assertEqual([p['conversational']['role'] for p in args['payload']],['USER','ASSISTANT'])
        client=ao.boto3.client('bedrock-agentcore',region_name='us-east-1')
        validate_parameters(args,client.meta.service_model.operation_model('CreateEvent').input_shape)

    def test_unconfigured_kbs_do_not_invoke_billable_models(self):
        for key in ('RETURNS_KB_ID','SHIPPING_KB_ID','WARRANTY_KB_ID'):setattr(config,key,'')
        with patch.object(ao.trace,'kb_start'),patch.object(ao.trace,'kb_done'),patch.object(ao.trace,'kb_result'):
            policy=ao.build_policy_agent()
            for agent in policy.novamart_retrievers:
                agent.messages.append({'role':'user','content':[{'text':'marker'}]})
            result=fn(policy,'search_all_policies')('question')
            self.assertIn('not configured',result)
            for agent in policy.novamart_retrievers:self.assertEqual(len(agent.messages),1)

    def test_runtime_deploy_keeps_cli_contract(self):
        import agentcore_cli
        with patch.dict(config.__dict__,{'ACCOUNT_ID':'000000000000','AGENTCORE_ROLE_ARN':'arn:example'}),patch.object(agentcore_cli,'stage_runtime_code'),patch.object(agentcore_cli,'deployed_runtime_arn',side_effect=['','arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/test']),patch.object(agentcore_cli,'configure_runtime') as configure,patch.object(agentcore_cli,'deploy') as deploy,patch.object(ao,'wait_for_runtime_ready'):
            result=ao.deploy_to_agentcore_runtime(Mock(),'guard123','1')
            self.assertTrue(result.endswith('/test'))
            self.assertEqual(configure.call_args.kwargs['network_mode'],'PUBLIC')
            self.assertEqual(configure.call_args.kwargs['protocol'],'HTTP')
            self.assertEqual(configure.call_args.kwargs['env_vars']['GUARDRAIL_VERSION'],'1')
            deploy.assert_called_once()


if __name__=='__main__': unittest.main(verbosity=2)
