# NovaMart deployment review — 2026-10-21

User approved the bounded deployment and verification estimate of $3–$8,
with a review stop at an estimated $10 and an overall $25 budget. This is
an operational stop, not an enforced AWS billing cap. No AdministratorAccess
or unrelated IAM expansion is authorized.

## Scope

- Foundation: three on-demand DynamoDB tables, policy-document S3 bucket,
  one S3 Vectors bucket and three indexes, scoped runtime role, 14-day logs.
- Three self-managed Bedrock KBs, one data source each, Titan Text Embeddings v2.
- One HTTP/PUBLIC CodeZip AgentCore runtime, numbered guardrail, seven-day
  summary memory; existing supplied CLI/CDK deployment approach.
- One bounded verification pass: five guardrail probes, three required
  scenarios, two memory turns, official evaluation and telemetry inspection.
- No OpenSearch, provisioned model capacity, optional gateway, or frontend.

## Cost assumptions and limits

Estimate assumes small seeded policy files, a single runtime, roughly
60–120 model calls with short outputs, and a short testing window. Actual
tokens, retry work, memory summarization and log volume remain uncertain.
The model hook limits each agent to 8 calls and each request to 40 calls,
with 1,800 output tokens per call. These limits do not bound aggregate input
tokens or enforce dollars. Review actual usage after each live scenario;
stop to reassess repeated failures rather than rerunning the whole suite.

Reserve approximately $1–$6 for inference, $1–$2 for guardrails, runtime,
embeddings, memory and telemetry, and retain the remaining budget as margin.
Storage persists until separately authorized cleanup; no automatic teardown
before submission evidence. The estimate is not a quote or a worst-case cap.

Pricing reviewed against [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
and [AgentCore pricing](https://aws.amazon.com/bedrock/agentcore/pricing/).
Bedrock content and topic filters each cost $0.15/1,000 text units; PII
filters $0.10/1,000 text units. Runtime v1 lists $0.0895/vCPU-hour and
$0.00945/GB-hour; actual runtime generation must be checked after deployment.
Cost Explorer reported estimated October usage of $0.0004 at preflight,
which can lag and does not establish available Udacity credit.

## Read-only preflight

DNS, HTTPS, local socketpair and STS succeeded inside workspace-write.
Project stacks and expected runtime role were absent; lists for tables,
KBs, guardrails, runtimes, memories and vector buckets were empty.
Both CloudFormation templates validated. IAM simulation allowed core
creation actions; simulation does not prove SCP, PassRole or service-side
constraints. Model region and authorization checks passed; Claude agreement
status was NOT_AVAILABLE, with first-time use-case data already present.
Model access still requires verification before substantial inference.

Evidence: `starter/evidence/current-session-preflight.json`,
`starter/evidence/current-cloud-preflight.log`; identifiers and detailed
responses remain private in `starter/.deployment/`.

## Verified outcome

Runtime version 3 is READY with PUBLIC/HTTP and the scoped foundation execution role. Three original-bucket S3 Vectors KBs are ACTIVE and synced; summary memory is ACTIVE with seven-day retention; guardrail version 1 is READY. Full official evaluation passed 120/120 and 43 local tests passed. Real deployed routing, return initiation, memory recall, safety rejection and idempotency passed.

CDK deployment uses CliCredentialsStackSynthesizer with the already authorized temporary profile; no AdministratorAccess is granted to a bootstrap role. Early CFN execution-role failures and a runtime ApplyGuardrail profile AccessDenied are documented in EXECUTION_LOG.md. The required guardrail profile permission was applied only to the project role.

Remaining submission blockers are two complete, reviewed screenshots. Draft ZIP is integrity-checked; final packaging deliberately refuses those missing images. Current observed-model cost estimate and delayed billing limitations are in EXPENSE_LOG.md.
