# Evaluation Rubric — Official Criteria Organized as Checklists

The following are required according to the **user-supplied evaluation rubric**; the checkboxes here are **unverified**, not a record of work completed.

## A. Multi-Agent Graph

### Worker agents: tools/models/configuration

- [ ] `build_inventory_agent()` returns Strands Agent with `check_order_status`, `get_customer_tier`, `list_customer_orders`.
- [ ] `build_refund_agent()` returns Strands Agent with `get_inventory_context`, `initiate_refund`.
- [ ] Refund eligibility windows: **Standard = 30 days**, **Premium = 60 days**.
- [ ] `build_communication_agent()` returns Strands Agent with `get_full_workflow_context`.
- [ ] All worker agents use `config.WORKER_MODEL_ID` (Claude Sonnet 4.5).
- [ ] Inventory, Refund temperature = **0.1**; Communication temperature = **0.3**.
- [ ] Every tool function has clear purpose/parameters/return-value docstring.

### Multi-agent RAG

- [ ] `build_policy_agent()` creates Returns, Shipping, Warranty retriever **sub-agents**.
- [ ] Each retriever has a single tool invoking `retrieve_from_knowledge_base()` with the correct ID from `config`.
- [ ] `search_all_policies`: **`ThreadPoolExecutor(max_workers=3)` and `as_completed()`**.
- [ ] All three retriever results are returned.
- [ ] Retriever temperature **0.0**, Policy coordinator temperature **0.2**.

### Orchestrator/WorkflowState

- [ ] `build_orchestrator_agent()` returns Strands Agent using `config.ORCHESTRATOR_MODEL_ID` (Claude Haiku 4.5), temperature **0.0**.
- [ ] System prompt implements **all 6 routing rules** in `02_ARCHITECTURE_AND_WORKFLOW.md`.
- [ ] `initialize_session` creates WorkflowState at session start.
- [ ] Each routing tool reads WorkflowState before worker invocation, updates afterward using `_update_workflow_state()` with correct `expected_version`.
- [ ] `route_to_communication_agent` is **last tool call** for every request; Orchestrator never composes final response.
- [ ] `python tests/test_agent.py task2` passes.

## B. AgentCore Runtime and Guardrails

### Bedrock Guardrail

- [ ] Content filter strengths: `SEXUAL`, `VIOLENCE`, `HATE` **HIGH**; `INSULTS`, `MISCONDUCT` **MEDIUM**.
- [ ] PII: block credit cards and SSNs; anonymize email addresses and phone numbers.
- [ ] Topic policy denies competitor products, pricing negotiations and legal threats.
- [ ] Managed profanity list enabled.
- [ ] Calls `create_guardrail_version()` after creation and returns `(guardrail_id, guardrail_version)` with a **numbered version** (not DRAFT).
- [ ] Task 3 supplementary instructions specify `topicPolicyConfig.tierConfig STANDARD`, `crossRegionConfig us.guardrail.v1:0`, friendly input/output messages and permitting ordinary discount calculations.

### Deploy Runtime

- [ ] `deploy_to_agentcore_runtime()` uses AgentCore CLI wrapper `agentcore_cli.configure_runtime()`, `agentcore_cli.deploy()`, `agentcore_cli.deployed_runtime_arn()` per supplied rubric.
- [ ] Networking **PUBLIC**, protocol **HTTP**, execution role from foundation CloudFormation stack.
- [ ] Runtime env: `AWS_REGION`, `PROJECT_NAME`, `RETURNS_KB_ID`, `SHIPPING_KB_ID`, `WARRANTY_KB_ID`, `AGENT_LOG_GROUP`, `GUARDRAIL_ID`, numbered `GUARDRAIL_VERSION`.
- [ ] Prewritten `_apply_guardrail()` is said to apply guardrail on each agent model (not found in uploaded starter; see conflicts).
- [ ] `.env` contains valid `AGENTCORE_RUNTIME_ARN`.
- [ ] `python tests/test_agent.py task3` passes after prerequisites.

## C. Memory and Knowledge Bases

### AgentCore Memory

- [ ] `configure_memory()` calls `agentcore_control.create_memory()` with `summaryMemoryStrategy` (SESSION_SUMMARY).
- [ ] `eventExpiryDuration=7` for 7-day event retention.
- [ ] Descriptive name and description.
- [ ] Returns Memory ARN.
- [ ] `python tests/test_agent.py task4` passes.

### KBs and parallel retrieval

- [ ] KBs created in console: Returns, Shipping, Warranty; data-source prefixes respectively `policies/returns/`, `policies/shipping/`, `policies/warranty/`.
- [ ] Each uses **`amazon.titan-embed-text-v2:0`**.
- [ ] Each uses stack-provisioned **S3 Vectors VectorStoreBucket** with respective `returns-policy-index`, `shipping-policy-index`, `warranty-policy-index`.
- [ ] Each data source synced.
- [ ] `.env` contains non-empty, valid `RETURNS_KB_ID`, `SHIPPING_KB_ID`, `WARRANTY_KB_ID`.
- [ ] `search_all_policies()` yields **non-empty results from all 3 KBs**.
- [ ] `python tests/test_agent.py task5` passes, including `test_5_parallel_retrieval` as described in rubric.

## D. Observability

- [ ] `configure_observability()` builds `loggingConfiguration` and passes it to prewritten `apply_observability_config()` **inside try/except** per supplied rubric.
- [ ] CloudWatch: `logGroupName=config.AGENT_LOG_GROUP`, `logLevel='INFO'`, `enabled=True`.
- [ ] X-Ray: `enabled=True`, `samplingRate=1.0`.
- [ ] `python tests/test_agent.py task6` passes.
- [ ] Submitted X-Ray Service Map screenshot shows a **connected** trace from `NovaMart-Orchestrator` to worker nodes **including PolicyAgent and KnowledgeBase agents** after live `test` invocation.

## E. Industry Best Practices

- [ ] Tool docstrings accurately describe purpose, parameters and results.
- [ ] Agent builder functions are self-contained, returning **exactly one Agent** each.
- [ ] Descriptive naming and PEP8-style `snake_case` functions/variables.
- [ ] Orchestrator uses `config.ORCHESTRATOR_MODEL_ID`, workers use `config.WORKER_MODEL_ID`, not hard-coded model strings.

## F. Final proof of work (Final Phase instructions)

- [ ] Full tests: `python tests/test_agent.py all` succeeds.
- [ ] Screenshot shows **all tests passed and score 120**.
- [ ] X-Ray screenshot delivered; completed implementation file and `.env` and KBs documented as instructed.

## Optional enhancements — NOT mandatory project criteria

These appeared under **“Suggestions to Make Your Project Stand Out”** and are not required for pass:

- Adversarial Guardrail validation (prompt injection, competitor mentions, legal threats) with blocked-response screenshots.
- Additional DynamoDB `agent-sessions` table + Strands `DynamoDbSessionStorage` for durable chat session recall beyond AgentCore Memory.
- CloudWatch dashboard for invocations, per-agent latency, Guardrail trigger frequency.
- Cognito authentication + React/HTML/JS frontend calling AgentCore Runtime.

**Do not elevate optional suggestions into mandatory acceptance requirements.**
